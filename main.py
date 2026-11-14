from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Depends, Request, Query
from fastapi.responses import RedirectResponse
from aiogram.types import Update
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.bot_manager import MultiBotManager
from app.core.db.session import get_session, ensure_schema_upgrades
from app.core.db.models import RequiredBot
from app.core.services.sub_checker import SubscriptionService
from app.core.services.payments import activate_pro_subscription
from app.bot.dispatcher import create_dispatcher
from app.worker.tasks import broker

redis_client = Redis.from_url(settings.REDIS_URL)
sub_service = SubscriptionService(redis=redis_client)
bot_manager = MultiBotManager(webhook_base_url=settings.WEBHOOK_BASE_URL)
dp = create_dispatcher(redis=redis_client)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_schema_upgrades()
    if not broker.is_worker_process:
        await broker.startup()
    yield
    if not broker.is_worker_process:
        await broker.shutdown()
    await bot_manager.close_all()
    await redis_client.aclose()


app = FastAPI(title="Smiling-lemon Multi-Bot Network API", lifespan=lifespan)


@app.get("/health")
async def healthcheck():
    return {"status": "ok"}


@app.get("/go/bot/{req_bot_id}")
async def redirect_to_partner_bot(
    req_bot_id: int,
    u: int = Query(..., description="Telegram user ID"),
    src: str = Query("main", description="Source bot username"),
    session: AsyncSession = Depends(get_session),
):
    """
    Перенаправляє юзера в наш другий/третій бот сітки з deep-link міткою `?start=from_{src}`.
    Якщо другий бот у нашій БД — верифікація йде за реальним натисканням /start у `bot_users`;
    якщо ще зовнішній — фіксується перехід у Redis.
    """
    rb = await session.get(RequiredBot, req_bot_id)
    if not rb or not rb.is_active:
        raise HTTPException(status_code=404, detail="Partner bot not found")

    await sub_service.mark_external_bot_click(req_bot_id=rb.id, user_id=u)
    return RedirectResponse(url=f"https://t.me/{rb.target_username}?start=from_{src}")


@app.post("/webhook/{bot_id}")
async def telegram_webhook(
    bot_id: int,
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    pair = await bot_manager.get_bot_and_config(bot_id, session)
    if not pair:
        raise HTTPException(status_code=404, detail="Bot not found")

    bot, bot_config = pair
    if x_telegram_bot_api_secret_token != bot_config.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    tg_update = Update.model_validate(update, context={"bot": bot})
    await dp.feed_update(
        bot=bot,
        update=tg_update,
        bot_config=bot_config,
        db_session=session,
        sub_service=sub_service,
        redis=redis_client,
    )
    return {"ok": True}


@app.post("/payments/webhook/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    body = await request.json()
    order_id: str | None = None

    if provider == "monobank" and body.get("status") == "success":
        order_id = body.get("reference")
    elif provider == "yookassa" and body.get("event") == "payment.succeeded":
        order_id = body.get("object", {}).get("metadata", {}).get("order_id")
    elif provider == "bepaid" and body.get("transaction", {}).get("status") == "successful":
        order_id = body.get("transaction", {}).get("tracking_id")

    if order_id:
        user, bot_id = await activate_pro_subscription(session, order_id)
        if user and bot_id and user.pro_until:
            pair = await bot_manager.get_bot_and_config(bot_id, session)
            if pair:
                bot, _ = pair
                await bot.send_message(
                    user.telegram_id,
                    f"💎 <b>PRO успішно активовано до {user.pro_until.strftime('%d.%m.%Y')}!</b>",
                )
    return {"received": True}
