"""
TrBridgo Telegram Bot
=====================
Production-ready bot built with python-telegram-bot v20+.

Architecture
------------
- Webhook mode (no polling) for deployment on any WSGI host (Render, Railway, etc.)
- Exposes a Flask Blueprint that mounts a single POST /webhook/telegram endpoint
- Each incoming update is processed inside an isolated asyncio.run() call —
  safe with gunicorn's prefork workers (no shared event-loop state between workers)

Local development (polling)
---------------------------
    python telegram_bot.py

Register webhook after first Render deploy
------------------------------------------
    python -c "
    import asyncio
    from telegram_bot import set_webhook
    asyncio.run(set_webhook('https://capitalproduction.onrender.com'))
    "

Delete webhook (to switch back to polling)
------------------------------------------
    python -c "
    import asyncio
    from telegram_bot import delete_webhook
    asyncio.run(delete_webhook())
    "
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from flask import Blueprint, abort, request
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Environment ───────────────────────────────────────────────────────────────
# load_dotenv() is a no-op if app.py already called it; safe to call again.
load_dotenv()

BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
WEBAPP_URL: str = os.environ.get("WEBAPP_URL", "").rstrip("/")

# Optional: set TELEGRAM_WEBHOOK_SECRET in .env to enable request validation.
# When set, every Telegram update must carry this value in the
# X-Telegram-Bot-Api-Secret-Token header; otherwise the request is rejected.
WEBHOOK_SECRET: str = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Keyboard Builder ──────────────────────────────────────────────────────────

def build_main_keyboard() -> InlineKeyboardMarkup:
    """Return the main-menu inline keyboard with all platform entry points."""
    return InlineKeyboardMarkup(
        [
            # Row 1 — Telegram WebApp full-screen launcher
            [
                InlineKeyboardButton(
                    "🚀 Open TrBridgo Platform",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
            # Row 2 — Dashboard | Deposit
            [
                InlineKeyboardButton("📊 Dashboard", url=f"{WEBAPP_URL}/dashboard"),
                InlineKeyboardButton("💳 Deposit",   url=f"{WEBAPP_URL}/deposit"),
            ],
            # Row 3 — Withdraw | Referral Program
            [
                InlineKeyboardButton("💰 Withdraw",          url=f"{WEBAPP_URL}/withdraw"),
                InlineKeyboardButton("👥 Referral Program",  url=f"{WEBAPP_URL}/referral-program"),
            ],
            # Row 4 — Support | AI Assistant
            [
                InlineKeyboardButton("💬 Support",      url=f"{WEBAPP_URL}/support"),
                InlineKeyboardButton("🤖 AI Assistant", url=f"{WEBAPP_URL}/ai"),
            ],
        ]
    )


# ── Command Handlers ──────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — send branded welcome message with the main keyboard."""
    if update.message is None:
        return

    user = update.effective_user
    name = user.first_name if user else "Trader"

    welcome = (
        f"👋 Welcome, *{name}*!\n\n"
        "🏆 *TrBridgo* — Your Professional Trading Platform\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📈  Real-time trading dashboard\n"
        "💳  Seamless deposits & withdrawals\n"
        "👥  Earn through referral commissions\n"
        "🤖  AI-powered market insights\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tap a button below to get started:"
    )

    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(),
    )

    logger.info(
        "/start — user_id=%s username=%s",
        getattr(user, "id", "?"),
        getattr(user, "username", name),
    )


# ── Application Factory ───────────────────────────────────────────────────────

def _build_webhook_application() -> Application:
    """
    Build a minimal Application for webhook mode.

    - updater=None   → disables the built-in polling loop
    - job_queue=None → no periodic/scheduled tasks (keeps initialize() lightweight)

    Handlers are registered once here; the Application object is module-level
    and shared across requests (read-only after construction — thread-safe).
    """
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .updater(None)
        .job_queue(None)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    logger.info("Telegram Application built (webhook mode, handlers registered)")
    return app


# Module-level Application instance.
# `async with _application` in each request calls initialize() / shutdown()
# which creates / closes the underlying aiohttp session for that single update.
_application: Application = _build_webhook_application()


# ── Update Dispatcher ─────────────────────────────────────────────────────────

async def _dispatch_update(payload: dict) -> None:
    """
    Process one Telegram update inside a fresh async context.

    `async with _application` lifecycle per call:
      __aenter__ → initialize() → opens aiohttp session, verifies bot token
      process_update() → dispatches through registered handlers
      __aexit__  → shutdown() → closes aiohttp session cleanly
    """
    async with _application:
        update = Update.de_json(payload, _application.bot)
        await _application.process_update(update)


# ── Flask Blueprint (Webhook Endpoint) ───────────────────────────────────────

telegram_blueprint = Blueprint("telegram_bot", __name__)


@telegram_blueprint.route("/webhook/telegram", methods=["POST"])
def telegram_webhook() -> tuple:
    """
    POST /webhook/telegram

    Telegram calls this URL for every update (message, callback_query, etc.).
    The handler is intentionally sync so it works with Flask's default WSGI mode
    and gunicorn's prefork workers without any shared event-loop state.
    """
    # ── Optional secret-token validation ──────────────────────────────────────
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != WEBHOOK_SECRET:
            logger.warning(
                "Webhook: rejected — invalid secret token from %s",
                request.remote_addr,
            )
            abort(403)

    # ── Parse request body ────────────────────────────────────────────────────
    payload = request.get_json(force=True, silent=True)
    if not payload:
        logger.warning("Webhook: empty or non-JSON body from %s", request.remote_addr)
        abort(400)

    # ── Dispatch update ───────────────────────────────────────────────────────
    try:
        asyncio.run(_dispatch_update(payload))
    except TimeoutError:
        logger.error(
            "Webhook: timeout processing update_id=%s", payload.get("update_id")
        )
    except Exception:
        logger.exception(
            "Webhook: unhandled error for update_id=%s", payload.get("update_id")
        )
        # Return 200 even on error — prevents Telegram from retrying indefinitely.
        # All errors are captured in logs / Render's log dashboard.

    return "OK", 200


# ── Webhook Registration Utility ──────────────────────────────────────────────

async def set_webhook(base_url: str, secret: str | None = None) -> bool:
    """
    Register the bot's webhook URL with Telegram.

    Call this once after deploying to Render (or whenever the URL changes).
    Telegram will then POST every update to  <base_url>/webhook/telegram.

    Args:
        base_url: Deployed app root URL, e.g. "https://capitalproduction.onrender.com"
        secret:   Overrides TELEGRAM_WEBHOOK_SECRET env var if provided.

    Returns:
        True if registration succeeded.

    Example:
        python -c "
        import asyncio
        from telegram_bot import set_webhook
        asyncio.run(set_webhook('https://capitalproduction.onrender.com'))
        "
    """
    webhook_url = f"{base_url.rstrip('/')}/webhook/telegram"
    token = secret if secret is not None else (WEBHOOK_SECRET or None)

    async with Bot(token=BOT_TOKEN) as bot:
        kwargs: dict = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
        }
        if token:
            kwargs["secret_token"] = token

        result = await bot.set_webhook(**kwargs)

    status = "OK" if result else "FAILED"
    logger.info("set_webhook(%s) → %s", webhook_url, status)
    return bool(result)


async def delete_webhook() -> bool:
    """
    Remove the registered webhook from Telegram.

    Use this when switching back to polling mode (local dev) or resetting.
    """
    async with Bot(token=BOT_TOKEN) as bot:
        result = await bot.delete_webhook(drop_pending_updates=True)
    logger.info("delete_webhook → %s", "OK" if result else "FAILED")
    return bool(result)


# ── Local Development: Polling Mode ──────────────────────────────────────────

def main() -> None:
    """
    Entry point for local development — runs the bot in polling mode.
    This is NOT used in production (webhook mode is used there instead).

        python telegram_bot.py
    """
    async def _run_polling() -> None:
        poll_app = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()  # includes Updater + JobQueue for polling
        )
        poll_app.add_handler(CommandHandler("start", start_command))
        logger.info("Starting bot in POLLING mode (local development)")
        await poll_app.run_polling(drop_pending_updates=True)

    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
