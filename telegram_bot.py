"""
TrBridgo Telegram Bot
=====================
Production-ready bot built with python-telegram-bot v22+.

Webhook URL: <WEBAPP_URL>/telegram/webhook
Health URL:  <WEBAPP_URL>/telegram/health

Architecture
------------
- Webhook mode only (no polling) — safe for Render / gunicorn prefork workers
- Flask Blueprint mounts two routes:
    POST /telegram/webhook  — receives Telegram updates
    GET  /telegram/health   — confirms bot module is active
- Webhook is auto-registered with Telegram on the first HTTP request to the server
  (idempotent — safe to call every startup)
- Each update is processed in an isolated asyncio.run() call, no shared event-loop
  state between gunicorn workers

Local development (polling — do NOT use on Render)
--------------------------------------------------
    python telegram_bot.py

Register webhook manually (one-off or after URL change)
-------------------------------------------------------
    python -c "
    import asyncio; from telegram_bot import set_webhook
    asyncio.run(set_webhook('https://capitalproduction.onrender.com'))
    "
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from flask import Blueprint, abort, jsonify, request
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Environment ───────────────────────────────────────────────────────────────
# No-op if app.py already called load_dotenv(); safe to call again.
load_dotenv()

BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
WEBAPP_URL: str = os.environ.get("WEBAPP_URL", "").rstrip("/")

# Optional secret that Telegram must include in every webhook request header:
#   X-Telegram-Bot-Api-Secret-Token: <TELEGRAM_WEBHOOK_SECRET>
# Set it in Render's environment variables for extra request validation.
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
                InlineKeyboardButton("💰 Withdraw",         url=f"{WEBAPP_URL}/withdraw"),
                InlineKeyboardButton("👥 Referral Program", url=f"{WEBAPP_URL}/referral-program"),
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
      updater=None   → no built-in polling loop
      job_queue=None → no scheduled tasks; keeps initialize() lightweight
    """
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .updater(None)
        .job_queue(None)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    logger.info("Telegram Application built — webhook mode, handlers registered")
    return app


_application: Application = _build_webhook_application()

# Startup log — always visible in Render's log dashboard
_WEBHOOK_URL = f"{WEBAPP_URL}/telegram/webhook" if WEBAPP_URL else "(WEBAPP_URL not set)"
logger.info("Telegram webhook URL: %s", _WEBHOOK_URL)


# ── Update Dispatcher ─────────────────────────────────────────────────────────

async def _dispatch_update(payload: dict) -> None:
    """
    Process one Telegram update inside a managed async context.
    `async with _application` calls initialize() on enter (opens aiohttp session)
    and shutdown() on exit (closes it) — one clean session per update.
    """
    async with _application:
        update = Update.de_json(payload, _application.bot)
        await _application.process_update(update)


# ── Webhook Registration ──────────────────────────────────────────────────────

async def set_webhook(base_url: str, secret: str | None = None) -> bool:
    """
    Register the bot webhook with Telegram (idempotent — safe to call every startup).

    Args:
        base_url: Deployed root URL, e.g. "https://capitalproduction.onrender.com"
        secret:   Overrides TELEGRAM_WEBHOOK_SECRET env var if provided.

    Returns:
        True if registration succeeded.
    """
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    token = secret if secret is not None else (WEBHOOK_SECRET or None)

    async with Bot(token=BOT_TOKEN) as bot:
        kwargs: dict = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
        }
        if token:
            kwargs["secret_token"] = token

        result = await bot.set_webhook(**kwargs)

    logger.info("set_webhook(%s) → %s", webhook_url, "OK" if result else "FAILED")
    return bool(result)


async def get_webhook_info() -> dict:
    """Return the current webhook info from Telegram."""
    async with Bot(token=BOT_TOKEN) as bot:
        info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_message": getattr(info, "last_error_message", None),
        "last_error_date": str(getattr(info, "last_error_date", None)),
    }


async def delete_webhook() -> bool:
    """Remove the registered webhook (use when switching to polling)."""
    async with Bot(token=BOT_TOKEN) as bot:
        result = await bot.delete_webhook(drop_pending_updates=True)
    logger.info("delete_webhook → %s", "OK" if result else "FAILED")
    return bool(result)


# ── Auto-webhook setup (fires once on first HTTP request) ─────────────────────
_webhook_initialized: bool = False


def _auto_setup_webhook() -> None:
    """
    Attempt to register the webhook with Telegram on the first server request.
    Called from before_app_request — runs exactly once per worker process.
    Safe to fail: errors are logged but do not break the Flask app.
    """
    global _webhook_initialized
    if _webhook_initialized or not WEBAPP_URL:
        return
    _webhook_initialized = True  # set before calling to prevent re-entry

    try:
        result = asyncio.run(set_webhook(WEBAPP_URL))
        if result:
            logger.info("Auto-webhook configured: %s/telegram/webhook", WEBAPP_URL)
        else:
            logger.warning("Auto-webhook call returned False — check BOT_TOKEN and WEBAPP_URL")
    except Exception:
        logger.exception("Auto-webhook setup failed — register manually with set_webhook()")


# ── Flask Blueprint ───────────────────────────────────────────────────────────

telegram_blueprint = Blueprint("telegram_bot", __name__)
telegram_blueprint.before_app_request(_auto_setup_webhook)


@telegram_blueprint.route("/telegram/webhook", methods=["POST"])
def telegram_webhook() -> tuple:
    """
    POST /telegram/webhook

    Telegram calls this URL for every update.
    Always returns HTTP 200 so Telegram does not retry on handler errors.
    """
    # Optional secret-token validation
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != WEBHOOK_SECRET:
            logger.warning("Webhook: invalid secret token from %s", request.remote_addr)
            abort(403)

    payload = request.get_json(force=True, silent=True)
    if not payload:
        logger.warning("Webhook: empty or non-JSON body from %s", request.remote_addr)
        abort(400)

    try:
        asyncio.run(_dispatch_update(payload))
    except TimeoutError:
        logger.error("Webhook: timeout on update_id=%s", payload.get("update_id"))
    except Exception:
        logger.exception("Webhook: error on update_id=%s", payload.get("update_id"))

    return "OK", 200


@telegram_blueprint.route("/telegram/health", methods=["GET"])
def telegram_health() -> tuple:
    """
    GET /telegram/health

    Confirms the Telegram bot module is active and returns current webhook info.
    Use this to verify the bot is correctly configured after deployment.
    """
    try:
        webhook_info = asyncio.run(get_webhook_info())
        return jsonify({
            "status": "active",
            "bot_token_set": bool(BOT_TOKEN),
            "webapp_url": WEBAPP_URL or None,
            "webhook_url": _WEBHOOK_URL,
            "telegram_webhook_info": webhook_info,
        }), 200
    except Exception as exc:
        logger.exception("Health check failed")
        return jsonify({
            "status": "error",
            "error": str(exc),
            "bot_token_set": bool(BOT_TOKEN),
            "webapp_url": WEBAPP_URL or None,
        }), 500


# ── Local Development: Polling Mode ──────────────────────────────────────────

def main() -> None:
    """
    Entry point for local development only — runs polling mode.
    NOT used on Render (webhook mode is used there).

        python telegram_bot.py
    """
    async def _run_polling() -> None:
        poll_app = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )
        poll_app.add_handler(CommandHandler("start", start_command))
        logger.info("Starting bot in POLLING mode (local development only)")
        await poll_app.run_polling(drop_pending_updates=True)

    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
