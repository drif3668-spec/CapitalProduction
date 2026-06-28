"""
TrBridgo Telegram Bot
=====================
Production-ready bot using python-telegram-bot v22+.

Routes registered (always, even if token is not yet configured):
    POST /telegram/webhook  — receives Telegram updates
    GET  /telegram/health   — returns JSON status (use this to verify deployment)

Design rules
------------
* This module NEVER raises at import time — os.getenv() with defaults throughout.
  A missing TELEGRAM_BOT_TOKEN is logged as a warning; routes still mount.
* Webhook is auto-registered with Telegram on the first HTTP request (idempotent).
* asyncio.run() is used per-request so there is no shared event-loop state
  between gunicorn prefork workers.
* Polling is only used when running this file directly (local dev).

Local development
-----------------
    python telegram_bot.py          # polling mode

Register webhook manually (after deploy or URL change)
------------------------------------------------------
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

# ── Environment ───────────────────────────────────────────────────────────────
# No-op when app.py already called load_dotenv(); safe to call again.
load_dotenv()

# Use getenv() with defaults — this module must NEVER raise KeyError at import.
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "").rstrip("/")
WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.warning(
        "TELEGRAM_BOT_TOKEN is not set — bot routes will mount but updates "
        "cannot be processed until the variable is added to the environment."
    )

# Printed in Render log on every startup so you can confirm the URL at a glance.
_WEBHOOK_URL = f"{WEBAPP_URL}/telegram/webhook" if WEBAPP_URL else "(WEBAPP_URL not set)"
logger.info("Telegram webhook URL: %s", _WEBHOOK_URL)


# ── Lazy imports (only load telegram library when token is present) ────────────

def _get_telegram_classes():
    """
    Import python-telegram-bot types on demand.
    Raises ImportError with a clear message if the package is missing.
    """
    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
        from telegram.ext import Application, CommandHandler, ContextTypes
        return Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo, Application, CommandHandler, ContextTypes
    except ImportError as exc:
        raise ImportError(
            "python-telegram-bot is not installed. "
            "Add 'python-telegram-bot>=20.0' to requirements.txt and redeploy."
        ) from exc


# ── Keyboard Builder ──────────────────────────────────────────────────────────

def build_main_keyboard():
    """Return the main-menu InlineKeyboardMarkup."""
    _, InlineKeyboardButton, InlineKeyboardMarkup, _, WebAppInfo, _, _, _ = _get_telegram_classes()

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

async def start_command(update, context) -> None:
    """Handle /start — branded welcome message with main keyboard."""
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

def _build_webhook_application():
    """
    Build a minimal Application for webhook mode.
      updater=None   → no built-in polling
      job_queue=None → no scheduled tasks; keeps initialize() lightweight
    Returns None (with a warning) if BOT_TOKEN is not set.
    """
    if not BOT_TOKEN:
        logger.warning("Skipping Application build — TELEGRAM_BOT_TOKEN is empty")
        return None

    _, _, _, _, _, Application, CommandHandler, _ = _get_telegram_classes()

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


_application = _build_webhook_application()


# ── Update Dispatcher ─────────────────────────────────────────────────────────

async def _dispatch_update(payload: dict) -> None:
    """
    Process one Telegram update.
    `async with _application` calls initialize() on enter (opens aiohttp session)
    and shutdown() on exit — one clean HTTP session per update.
    """
    async with _application:
        _, _, _, Update, _, _, _, _ = _get_telegram_classes()
        update = Update.de_json(payload, _application.bot)
        await _application.process_update(update)


# ── Webhook Registration ──────────────────────────────────────────────────────

async def set_webhook(base_url: str, secret: str | None = None) -> bool:
    """
    Register the bot webhook with Telegram (idempotent — safe every startup).

    Args:
        base_url: Deployed root URL e.g. "https://capitalproduction.onrender.com"
        secret:   Overrides TELEGRAM_WEBHOOK_SECRET env var if provided.
    """
    if not BOT_TOKEN:
        logger.error("set_webhook: TELEGRAM_BOT_TOKEN is not set")
        return False

    Bot, _, _, _, _, _, _, _ = _get_telegram_classes()

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
    """Return current webhook registration info from Telegram."""
    if not BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN is not set"}

    Bot, _, _, _, _, _, _, _ = _get_telegram_classes()

    async with Bot(token=BOT_TOKEN) as bot:
        info = await bot.get_webhook_info()

    return {
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_message": getattr(info, "last_error_message", None),
        "last_error_date": str(getattr(info, "last_error_date", None)),
    }


async def delete_webhook() -> bool:
    """Remove the registered webhook (use when switching back to polling)."""
    if not BOT_TOKEN:
        return False
    Bot, _, _, _, _, _, _, _ = _get_telegram_classes()
    async with Bot(token=BOT_TOKEN) as bot:
        result = await bot.delete_webhook(drop_pending_updates=True)
    logger.info("delete_webhook → %s", "OK" if result else "FAILED")
    return bool(result)


# ── Auto-webhook setup (fires once per worker on first HTTP request) ───────────
_webhook_initialized: bool = False


def _auto_setup_webhook() -> None:
    """
    Attempt to register the webhook on the first request received by this worker.
    Safe to fail — errors are logged; the Flask app keeps running.
    """
    global _webhook_initialized
    if _webhook_initialized or not WEBAPP_URL or not BOT_TOKEN:
        return
    _webhook_initialized = True  # set first to prevent re-entry

    try:
        result = asyncio.run(set_webhook(WEBAPP_URL))
        if result:
            logger.info("Auto-webhook configured: %s/telegram/webhook", WEBAPP_URL)
        else:
            logger.warning("Auto-webhook returned False — verify BOT_TOKEN and WEBAPP_URL in Render")
    except Exception:
        logger.exception("Auto-webhook setup failed — register manually with set_webhook()")


# ── Flask Blueprint ───────────────────────────────────────────────────────────

telegram_blueprint = Blueprint("telegram_bot", __name__)

# Fire auto-setup once on the first request to this worker.
telegram_blueprint.before_app_request(_auto_setup_webhook)


@telegram_blueprint.route("/telegram/webhook", methods=["POST"])
def telegram_webhook() -> tuple:
    """
    POST /telegram/webhook
    Telegram calls this endpoint for every update (message, callback, etc.).
    Always returns HTTP 200 to prevent Telegram from retrying on handler errors.
    """
    if not BOT_TOKEN or _application is None:
        logger.error("Webhook hit but TELEGRAM_BOT_TOKEN is not configured")
        return jsonify({"error": "bot not configured"}), 503

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
        # Return 200 anyway — error is logged; Telegram won't retry

    return "OK", 200


@telegram_blueprint.route("/telegram/health", methods=["GET"])
def telegram_health() -> tuple:
    """
    GET /telegram/health
    Returns JSON confirming the bot module is active and shows webhook status.
    Open this URL in a browser right after deploying to verify the setup.
    """
    configured = bool(BOT_TOKEN) and _application is not None

    base = {
        "status": "active" if configured else "not_configured",
        "bot_token_set": bool(BOT_TOKEN),
        "webapp_url": WEBAPP_URL or None,
        "webhook_url": _WEBHOOK_URL,
        "routes": {
            "webhook": "/telegram/webhook  [POST]",
            "health":  "/telegram/health   [GET]",
        },
    }

    if not configured:
        base["hint"] = (
            "Add TELEGRAM_BOT_TOKEN and WEBAPP_URL to Render's "
            "Environment Variables, then redeploy."
        )
        return jsonify(base), 200  # 200 so the route itself is confirmed working

    try:
        webhook_info = asyncio.run(get_webhook_info())
        base["telegram_webhook_info"] = webhook_info
        return jsonify(base), 200
    except Exception as exc:
        logger.exception("Health: could not fetch webhook info")
        base["telegram_webhook_info"] = {"error": str(exc)}
        return jsonify(base), 200


# ── Local Development: Polling Mode ──────────────────────────────────────────

def main() -> None:
    """
    Entry point for local development — runs polling mode.
    Do NOT use this on Render (webhook mode is always used in production).

        python telegram_bot.py
    """
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")

    async def _run_polling() -> None:
        _, _, _, _, _, Application, CommandHandler, _ = _get_telegram_classes()
        poll_app = Application.builder().token(BOT_TOKEN).build()
        poll_app.add_handler(CommandHandler("start", start_command))
        logger.info("Starting bot in POLLING mode (local development only)")
        await poll_app.run_polling(drop_pending_updates=True)

    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
