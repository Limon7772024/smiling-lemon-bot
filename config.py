import os
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    # Якщо підключено постійний том /data (наприклад, Volume на Railway / Docker), зберігаємо БД там
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "sqlite+aiosqlite:////data/shpora.db"
    return "sqlite+aiosqlite:///./shpora.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # === ХТО Я (важливо, коли на одному сервері працює кілька наших ботів) ===
    # Номер бота мережі: 1 = флагман @ShporaNMT_bot, 2 = другий бот, 3 = третій.
    # УВАЖНО: у КОЖНОГО бота свій BOT_ID, інакше вони переплутають базу й ліміти.
    BOT_ID: int = 1

    # === МОВНИЙ РЕЖИМ ===
    # True  = лише українська (рекомендовано для старту на ринку UA!):
    #         бот завжди відповідає українською, навіть якщо людина написала російською,
    #         і не витрачає час на визначення мови.
    # False = мультиязычный режим (uk / ru / be / en) — увімкнемо пізніше для інших країн.
    LANG_UKRAINIAN_ONLY: bool = True

    # === ШВИДКІСТЬ ВІДПОВІДІ ===
    # Скільки «внутрішніх роздумів» дозволено моделі. Чим менше — тим швидша відповідь.
    # 128 — швидкий режим для шкільних задач (рекомендовано). 0 — максимально швидко,
    # але на складних задачах можливі помилки. 512 — повільно, залишати лише за потреби.
    LLM_REASONING_EFFORT: str = "128"

    # === ШВИДКИЙ СТАРТ ОДНОГО АБО КІЛЬКОХ БОТІВ (POLLING БЕЗ ДОМЕНУ) ===
    BOT_TOKEN: str = ""
    EXTRA_BOT_TOKENS: list[str] = []  # Додаткові токени наших інших ботів на тій самій БД
    BOT_REGION: str = "UA"            # 'UA' | 'BY' | 'RU'

    # === АДМІНІСТРАТОРИ (числові Telegram ID) ===
    ADMIN_IDS: list[int] = [123456789]

    # === ШІ МОДЕЛІ (OpenAI або сумісний API) ===
    LLM_API_KEY: str = ""
    # ДОДАТКОВІ безкоштовні ключі Gemini (головний прискорювач):
    # коли основний ключ упирається в ліміт — бот миттєво бере наступний.
    # Формат у .env:  LLM_API_KEYS=["AIza...key2", "AIza...key3"]
    LLM_API_KEYS: list[str] = []
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_FREE_MODEL: str = "gpt-4o-mini"
    LLM_PRO_MODEL: str = "gpt-4o"

    # === БАЗА ДАНИХ (за замовчуванням локальний SQLite або /data/shpora.db у хмарі, для кластера — PostgreSQL) ===
    DATABASE_URL: str = _default_database_url()

    # === КАНАЛ ЗА ЗАМОВЧУВАННЯМ ДЛЯ АПГРЕЙДУ 3 → 20 ЗАПИТІВ/ДЕНЬ ===
    DEFAULT_CHANNEL_USERNAME: str = "@smiling_lemon_school"

    # === МАСШТАБУВАННЯ ЧЕРЕЗ REDIS / TASKIQ / МУЛЬТИ-ВЕБХУК ===
    USE_TASKIQ_QUEUE: bool = False
    REDIS_URL: str = "redis://redis:6379/0"
    WEBHOOK_BASE_URL: str = "https://api.yourdomain.com"

    # === ПЛАТІЖНІ ШЛЮЗИ (зарезервовано під майбутнє /toggle_pro) ===
    STARS_PRICE_PRO: int = 500
    MONO_MERCHANT_TOKEN: str = ""
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    BEPAID_SHOP_ID: str = ""
    BEPAID_SECRET_KEY: str = ""


settings = Settings()
