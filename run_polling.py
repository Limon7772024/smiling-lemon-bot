"""
Миттєвий запуск бота Smiling-lemon (@ShporaNMT_bot) у режимі Long Polling (БЕЗ домену, SSL та вебхуків).
Також підтримує одночасний запуск кількох ваших ботів на одній базі даних через EXTRA_BOT_TOKENS!

Запуск:
  1) Пропишіть у файлі .env лише BOT_TOKEN, LLM_API_KEY та ADMIN_IDS
  2) Виконайте: python run_polling.py
"""
import asyncio
import logging
import secrets
import sys
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select, func

from app.config import settings
from app.core.db.models import Base, BotInstance, RequiredChannel
from app.core.db.session import engine, async_session_maker, ensure_schema_upgrades
from app.core.services.memory_kv import InMemoryKV
from app.core.services.sub_checker import SubscriptionService
from app.bot.dispatcher import create_dispatcher
from app.worker.tasks import ensure_renderer_started, renderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("smiling_lemon")

REGION_DEFAULTS = {
    "UA": {"lang": "uk", "currency": "UAH", "price": 419, "tz": "Europe/Kyiv"},
    "BY": {"lang": "be", "currency": "BYN", "price": 33, "tz": "Europe/Minsk"},
    "RU": {"lang": "ru", "currency": "RUB", "price": 990, "tz": "Europe/Moscow"},
}


async def register_or_sync_bot(token: str, region: str) -> Bot:
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    uname = me.username or "ShporaNMT_bot"
    reg = REGION_DEFAULTS.get(region.upper(), REGION_DEFAULTS["UA"])

    async with async_session_maker() as session:
        # ВАЖЛИВО: шукаємо бота за номером BOT_ID (а не за токеном!).
        # Інакше при зміні токена на тому ж сервері створюється дублікат бота №2 з тим самим юзернеймом,
        # і користувачі пишуть уже в іншу (порожню) базу — ліміти й статистика «зникають».
        existing = await session.scalar(select(BotInstance).where(BotInstance.id == settings.BOT_ID))
        if not existing:
            # Сумісність зі старою базою: якщо запис із таким токеном уже є під іншим номером — перевикористовуємо його,
            # щоб не впасти на унікальності токена і не втратити користувачів.
            legacy = await session.scalar(select(BotInstance).where(BotInstance.token == token))
            if legacy:
                logger.warning(
                    "У базі вже є цей токен під номером #%s (а в .env BOT_ID=%s). Використовую наявний запис.",
                    legacy.id, settings.BOT_ID,
                )
                legacy.username = uname
                legacy.is_active = True
                await session.commit()
                await bot.delete_webhook(drop_pending_updates=False)
                return bot
        if not existing:
            existing = BotInstance(
                id=settings.BOT_ID,
                token=token,
                webhook_secret=secrets.token_urlsafe(24),
                username=uname,
                region=region.upper(),
                language=reg["lang"],
                currency=reg["currency"],
                pro_price_usd=10.00,
                pro_price_local=reg["price"],
                timezone=reg["tz"],
                pro_enabled=False,
                is_active=True,
            )
            session.add(existing)
        else:
            existing.token = token
            existing.webhook_secret = existing.webhook_secret or secrets.token_urlsafe(24)
            existing.username = uname
            existing.region = region.upper()
            existing.language = reg["lang"]
            existing.currency = reg["currency"]
            existing.timezone = reg["tz"]
            existing.is_active = True
        await session.commit()

    await bot.delete_webhook(drop_pending_updates=False)

    # Автоматично прив'язуємо основний канал (наприклад, @smiling_lemon_school) на чистому хмарному сервері,
    # якщо таблиця каналів ще порожня, щоб воронка 3 -> 20 працювала з першої секунди!
    if settings.DEFAULT_CHANNEL_USERNAME:
        try:
            async with async_session_maker() as session:
                ch_count = (
                    await session.scalar(
                        select(func.count(RequiredChannel.id)).where(
                            RequiredChannel.bot_id == settings.BOT_ID
                        )
                    )
                    or 0
                )
                if ch_count == 0:
                    ch_handle = settings.DEFAULT_CHANNEL_USERNAME.strip()
                    if not ch_handle.startswith("@"):
                        ch_handle = f"@{ch_handle}"
                    chat_info = await bot.get_chat(ch_handle)
                    clean_uname = ch_handle.lstrip("@")
                    session.add(
                        RequiredChannel(
                            bot_id=settings.BOT_ID,
                            chat_id=chat_info.id,
                            invite_url=f"https://t.me/{clean_uname}",
                            title=chat_info.title or "Smiling-lemon 🍋 Шкільний помічник",
                            tier=1,
                            is_active=True,
                        )
                    )
                    await session.commit()
                    logger.info("Автоматично прив'язано канал %s (%s) для апгрейду 3 -> 20!", ch_handle, chat_info.id)
        except Exception as exc:
            logger.warning("Не вдалося автоматично перевірити канал %s: %s", settings.DEFAULT_CHANNEL_USERNAME, exc)

    logger.info("Бот #%s @%s готовий до прийому повідомлень (регіон: %s)", settings.BOT_ID, uname, region.upper())
    return bot


async def main() -> None:
    tokens = [t.strip() for t in ([settings.BOT_TOKEN] + list(settings.EXTRA_BOT_TOKENS)) if t and t.strip()]
    if not tokens:
        logger.error("Помилка: не вказано BOT_TOKEN у файлі .env!")
        sys.exit(1)
    if not settings.LLM_API_KEY:
        logger.warning("Увага: LLM_API_KEY порожній у .env — розпізнавання фото не працюватиме до додавання ключа.")

    # 1. Автоматичне створення всіх таблиць БД + безпечне оновлення колонок (SQLite або PostgreSQL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema_upgrades()
    logger.info("База даних ініціалізована (%s)", settings.DATABASE_URL)

    # 2. Запуск headless-браузера Playwright для миттєвого рендеру PNG-карток
    await ensure_renderer_started()
    logger.info("Рендерер зошитових PNG-карток Smiling-lemon запущено")

    # 3. Підготовка ботів та сервісів
    kv = InMemoryKV()
    sub_service = SubscriptionService(redis=kv)
    dp = create_dispatcher(redis=kv)

    bots: list[Bot] = []
    try:
        for tok in tokens:
            bots.append(await register_or_sync_bot(tok, settings.BOT_REGION))

        logger.info("Запущено ботів: %d. Натисніть Ctrl+C для зупинки.", len(bots))
        await dp.start_polling(
            *bots,
            sub_service=sub_service,
            redis=kv,
        )
    finally:
        await renderer.stop()
        for b in bots:
            await b.session.close()
        await engine.dispose()


def _disable_windows_quickedit_freeze() -> None:
    """Вимкнення зависання чорного вікна Windows при випадковому кліку мишкою (QuickEdit Mode)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # Скидаємо ENABLE_QUICK_EDIT_MODE (0x0040), ставимо ENABLE_EXTENDED_FLAGS (0x0080)
            new_mode = (mode.value & ~0x0040) | 0x0080
            kernel32.SetConsoleMode(handle, new_mode)
        kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass


if __name__ == "__main__":
    _disable_windows_quickedit_freeze()
    asyncio.run(main())
