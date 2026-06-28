"""
TrBridgo Telegram Bot
=====================
python-telegram-bot v22+ is kept for local polling (python telegram_bot.py).

In production (Render / gunicorn) all updates are handled through the Flask
webhook route using direct, synchronous httpx calls to the Telegram Bot API.
This avoids every asyncio / event-loop incompatibility with WSGI workers.

Routes always mounted (even if token is absent — returns 503 JSON):
    POST /telegram/webhook   — receives Telegram updates from the Bot API
    GET  /telegram/health    — JSON status; open in browser to verify deploy

Environment variables (set in Render → Environment):
    TELEGRAM_BOT_TOKEN        required
    WEBAPP_URL                required  (e.g. https://capitalproduction.onrender.com)
    TELEGRAM_WEBHOOK_SECRET   optional  (extra header-validation security)

Local development (polling, do NOT use on Render):
    python telegram_bot.py
"""

import json
import logging
import os

import httpx
from dotenv import load_dotenv
from flask import Blueprint, jsonify, request

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv()  # no-op when app.py already called it

BOT_TOKEN: str     = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL: str    = os.getenv("WEBAPP_URL", "").rstrip("/")
WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_WEBHOOK_URL = f"{WEBAPP_URL}/telegram/webhook" if WEBAPP_URL else "(WEBAPP_URL not set)"

if not BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN is not set — bot is inactive until configured")
else:
    logger.info("Telegram bot module loaded | webhook URL: %s", _WEBHOOK_URL)


# ── Telegram Bot API (synchronous via httpx) ──────────────────────────────────

_TG_API = "https://api.telegram.org/bot"


def _call_api(method: str, payload: dict) -> dict:
    """
    Make a synchronous POST request to the Telegram Bot API.
    Raises RuntimeError on HTTP error or when Telegram returns ok=false.
    """
    url = f"{_TG_API}{BOT_TOKEN}/{method}"
    logger.debug("TG API → %s  payload=%s", method, json.dumps(payload))

    with httpx.Client(timeout=15) as client:
        resp = client.post(url, json=payload)

    data = resp.json()
    logger.debug("TG API ← %s  response=%s", method, json.dumps(data))

    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")

    return data.get("result", {})


# ── Keyboard Builder ──────────────────────────────────────────────────────────

def _build_keyboard() -> dict:
    """
    Return a Telegram InlineKeyboardMarkup dict.
    Row 1  — WebApp launcher (opens the platform inside Telegram).
    Rows 2-4 — deep-link buttons for key platform sections.
    """
    return {
        "inline_keyboard": [
            # Row 1 — full-screen WebApp
            [{"text": "🚀 Open TrBridgo Platform", "web_app": {"url": WEBAPP_URL}}],
            # Row 2
            [
                {"text": "📊 Dashboard", "url": f"{WEBAPP_URL}/dashboard"},
                {"text": "💳 Deposit",   "url": f"{WEBAPP_URL}/deposit"},
            ],
            # Row 3
            [
                {"text": "💰 Withdraw",         "url": f"{WEBAPP_URL}/withdraw"},
                {"text": "👥 Referral Program", "url": f"{WEBAPP_URL}/referral-program"},
            ],
            # Row 4
            [
                {"text": "💬 Support",      "url": f"{WEBAPP_URL}/support"},
                {"text": "🤖 AI Assistant", "url": f"{WEBAPP_URL}/ai"},
            ],
        ]
    }


# ── Command Handlers ──────────────────────────────────────────────────────────

def handle_start(chat_id: int, first_name: str) -> None:
    """
    Send the /start welcome message with the InlineKeyboard to chat_id.
    Uses a direct sendMessage API call — no async, no event loop.
    """
    text = (
        f"👋 Welcome, *{first_name}*!\n\n"
        "🏆 *TrBridgo* — Your Professional Trading Platform\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📈  Real-time trading dashboard\n"
        "💳  Seamless deposits & withdrawals\n"
        "👥  Earn through referral commissions\n"
        "🤖  AI-powered market insights\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tap a button below to get started:"
    )

    _call_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": _build_keyboard(),
    })
    logger.info("START message sent → chat_id=%s name=%s", chat_id, first_name)


# ── Update Router ─────────────────────────────────────────────────────────────

def _route_update(payload: dict) -> None:
    """
    Inspect the update payload and dispatch to the correct handler.
    All command routing lives here so it is easy to extend.
    """
    update_id = payload.get("update_id", "?")
    logger.info("[update_id=%s] routing update", update_id)

    message = payload.get("message")
    if not message:
        logger.info("[update_id=%s] no 'message' key — ignored (type: %s)",
                    update_id, list(payload.keys()))
        return

    chat_id    = message.get("chat", {}).get("id")
    text       = (message.get("text") or "").strip()
    user       = message.get("from") or {}
    first_name = user.get("first_name") or "Trader"
    username   = user.get("username") or first_name

    logger.info("[update_id=%s] message | chat_id=%s | user=%s | text=%r",
                update_id, chat_id, username, text)

    if not chat_id:
        logger.warning("[update_id=%s] missing chat_id — cannot reply", update_id)
        return

    # ── command dispatch ──────────────────────────────────────────────────────
    if text.startswith("/start"):
        logger.info("[update_id=%s] dispatching /start handler", update_id)
        handle_start(chat_id, first_name)

    else:
        logger.info("[update_id=%s] no handler for text=%r", update_id, text)


# ── Webhook Registration (synchronous) ────────────────────────────────────────

def set_webhook(base_url: str) -> bool:
    """
    Register the bot webhook with Telegram.
    Idempotent — safe to call on every startup.

    Args:
        base_url: e.g. "https://capitalproduction.onrender.com"
    Returns:
        True if Telegram confirmed ok.
    """
    if not BOT_TOKEN:
        logger.error("set_webhook: TELEGRAM_BOT_TOKEN is not set")
        return False

    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    payload: dict = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
    }
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET

    try:
        _call_api("setWebhook", payload)
        logger.info("setWebhook OK → %s", webhook_url)
        return True
    except Exception:
        logger.exception("setWebhook FAILED for %s", webhook_url)
        return False


def get_webhook_info() -> dict:
    """Return current webhook registration from Telegram."""
    if not BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not set"}
    try:
        info = _call_api("getWebhookInfo", {})
        return {
            "url":                   info.get("url", ""),
            "pending_update_count":  info.get("pending_update_count", 0),
            "last_error_message":    info.get("last_error_message"),
            "last_error_date":       info.get("last_error_date"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def delete_webhook() -> bool:
    """Remove the registered webhook (use when switching to polling)."""
    if not BOT_TOKEN:
        return False
    try:
        _call_api("deleteWebhook", {"drop_pending_updates": True})
        logger.info("deleteWebhook OK")
        return True
    except Exception:
        logger.exception("deleteWebhook FAILED")
        return False


# ── Auto-webhook setup (once per worker, on first HTTP request) ───────────────
_webhook_initialized: bool = False


def _auto_setup_webhook() -> None:
    """
    Register webhook with Telegram on the first request received by this worker.
    Runs at most once per worker process. Errors are logged, not raised.
    """
    global _webhook_initialized
    if _webhook_initialized or not WEBAPP_URL or not BOT_TOKEN:
        return
    _webhook_initialized = True  # guard before I/O to prevent re-entry

    result = set_webhook(WEBAPP_URL)
    if result:
        logger.info("Auto-webhook OK: %s/telegram/webhook", WEBAPP_URL)
    else:
        logger.warning("Auto-webhook FAILED — check BOT_TOKEN and WEBAPP_URL")


# ── Flask Blueprint ───────────────────────────────────────────────────────────

telegram_blueprint = Blueprint("telegram_bot", __name__)
telegram_blueprint.before_app_request(_auto_setup_webhook)


@telegram_blueprint.route("/telegram/webhook", methods=["POST"])
def telegram_webhook() -> tuple:
    """
    POST /telegram/webhook

    1. Log the raw incoming body.
    2. Validate optional secret-token header.
    3. Parse JSON.
    4. Route the update.
    5. Always return 200 OK so Telegram does not retry.
    """
    # ── 1. Raw body log ───────────────────────────────────────────────────────
    raw_body = request.get_data(as_text=True)
    logger.info("WEBHOOK HIT | ip=%s | content_type=%s | body_len=%d",
                request.remote_addr, request.content_type, len(raw_body))
    logger.info("RAW UPDATE BODY: %s", raw_body)

    # ── 2. Bot not configured guard ───────────────────────────────────────────
    if not BOT_TOKEN:
        logger.error("WEBHOOK: BOT_TOKEN not set — cannot process update")
        return jsonify({"error": "bot not configured"}), 503

    # ── 3. Secret-token validation (optional) ─────────────────────────────────
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != WEBHOOK_SECRET:
            logger.warning("WEBHOOK: invalid secret token from %s", request.remote_addr)
            return "Forbidden", 403

    # ── 4. Parse JSON ─────────────────────────────────────────────────────────
    try:
        payload = json.loads(raw_body) if raw_body else None
    except json.JSONDecodeError:
        logger.error("WEBHOOK: invalid JSON — body=%s", raw_body[:200])
        return "OK", 200  # return 200 so Telegram doesn't retry a malformed body

    if not payload:
        logger.warning("WEBHOOK: empty payload")
        return "OK", 200

    # ── 5. Route the update ───────────────────────────────────────────────────
    try:
        _route_update(payload)
    except Exception:
        logger.exception("WEBHOOK: unhandled error for update_id=%s",
                         payload.get("update_id"))
        # Return 200 — error is in logs; Telegram won't retry

    return "OK", 200


@telegram_blueprint.route("/telegram/health", methods=["GET"])
def telegram_health() -> tuple:
    """
    GET /telegram/health
    Open in browser after deploying to confirm the bot is wired up correctly.
    """
    configured = bool(BOT_TOKEN) and bool(WEBAPP_URL)

    payload = {
        "status":         "active" if configured else "not_configured",
        "bot_token_set":  bool(BOT_TOKEN),
        "webapp_url":     WEBAPP_URL or None,
        "webhook_url":    _WEBHOOK_URL,
        "routes": {
            "webhook": "POST /telegram/webhook",
            "health":  "GET  /telegram/health",
        },
    }

    if not configured:
        payload["hint"] = (
            "Set TELEGRAM_BOT_TOKEN and WEBAPP_URL in Render → Environment, "
            "then redeploy."
        )
        return jsonify(payload), 200

    payload["telegram_webhook_info"] = get_webhook_info()
    return jsonify(payload), 200


# ── Local Development: Polling Mode ──────────────────────────────────────────

def main() -> None:
    """
    Local development entry point — polling mode only.
    Do NOT use on Render (webhook mode is used in production).

        python telegram_bot.py
    """
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")

    import asyncio
    from telegram.ext import Application, CommandHandler  # type: ignore[import]

    async def start_handler(update, context):
        user = update.effective_user
        name = user.first_name if user else "Trader"
        handle_start(update.effective_chat.id, name)

    async def _poll() -> None:
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_handler))
        logger.info("Polling mode started (local dev only)")
        await app.run_polling(drop_pending_updates=True)

    asyncio.run(_poll())


if __name__ == "__main__":
    main()
