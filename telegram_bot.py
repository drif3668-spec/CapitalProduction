"""
TrBridgo Telegram Bot
=====================
Production-ready bot using python-telegram-bot v22+ library for local polling,
and direct synchronous httpx calls to the Bot API in production (Flask webhook).

Routes always mounted:
    POST /telegram/webhook   — receives Telegram updates
    GET  /telegram/health    — JSON status

Account linking flow:
    1. User sends /start — if not linked, shows WebApp button → WEBAPP_URL/telegram/connect
    2. User opens the page (logged in on website), copies their one-time code
    3. User sends /link CODE to the bot
    4. Bot validates token, writes telegram_user_id to users table
    5. All data commands now work for that user

Commands:
    /start          — main menu (or link prompt if not linked)
    /link <CODE>    — link website account to Telegram

Callbacks (inline button presses):
    menu            — redisplay main menu
    balance         — live wallet balance from DB
    referrals       — live referral stats from DB
    mt_accounts     — live MT4/MT5 account list from DB
"""

import json
import logging
import os

import httpx
from dotenv import load_dotenv
from flask import Blueprint, jsonify, request

import bot_services

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN:      str = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL:     str = os.getenv("WEBAPP_URL", "").rstrip("/")
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
    logger.warning("TELEGRAM_BOT_TOKEN not set — bot inactive")
else:
    logger.info("Telegram bot loaded | webhook: %s", _WEBHOOK_URL)


# ── Telegram Bot API (synchronous) ────────────────────────────────────────────

_TG_API = "https://api.telegram.org/bot"


def _call_api(method: str, payload: dict) -> dict:
    """Synchronous POST to Telegram Bot API. Logs full response body."""
    url = f"{_TG_API}{BOT_TOKEN}/{method}"
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, json=payload)
    data = resp.json()
    logger.info("TG API ← %s | response: %s", method, json.dumps(data))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data.get("result", {})


def _send(chat_id: int, text: str, keyboard: dict | None = None) -> dict:
    """sendMessage helper."""
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = keyboard
    return _call_api("sendMessage", payload)


def _edit(chat_id: int, message_id: int, text: str, keyboard: dict | None = None) -> None:
    """editMessageText helper — ignores 'not modified' errors."""
    payload: dict = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       text,
        "parse_mode": "Markdown",
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        _call_api("editMessageText", payload)
    except RuntimeError as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _answer_callback(callback_query_id: str) -> None:
    """Dismiss the loading spinner on an inline button press."""
    _call_api("answerCallbackQuery", {"callback_query_id": callback_query_id})


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_keyboard() -> dict:
    """Full main menu — data buttons use callbacks, UI buttons use URLs/WebApp."""
    return {
        "inline_keyboard": [
            # Row 1 — WebApp launcher
            [{"text": "🚀 Open TrBridgo Platform", "web_app": {"url": WEBAPP_URL}}],
            # Row 2 — Dashboard (URL) | Wallet Balance (callback)
            [
                {"text": "📊 Dashboard",      "url":           f"{WEBAPP_URL}/dashboard"},
                {"text": "💰 Wallet Balance",  "callback_data": "balance"},
            ],
            # Row 3 — Referral Stats (callback) | MT Accounts (callback)
            [
                {"text": "👥 Referral Stats",      "callback_data": "referrals"},
                {"text": "🔗 Connected MT Accounts","callback_data": "mt_accounts"},
            ],
            # Row 4 — Deposit (URL) | Withdraw (URL)
            [
                {"text": "💳 Deposit",  "url": f"{WEBAPP_URL}/deposit"},
                {"text": "💸 Withdraw", "url": f"{WEBAPP_URL}/withdraw"},
            ],
            # Row 5 — Support (URL) | AI Assistant (URL)
            [
                {"text": "🆘 Support",      "url": f"{WEBAPP_URL}/support"},
                {"text": "🤖 AI Assistant", "url": f"{WEBAPP_URL}/ai"},
            ],
        ]
    }


def _back_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "⬅️ Main Menu", "callback_data": "menu"}]]}


def _link_keyboard() -> dict:
    """Keyboard for unlinked users — opens the website linking page."""
    return {
        "inline_keyboard": [
            [{"text": "🔗 Link My Account", "web_app": {"url": f"{WEBAPP_URL}/telegram/connect"}}]
        ]
    }


# ── Message Formatters ────────────────────────────────────────────────────────

def _fmt_currency(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_date(s: str | None) -> str:
    if not s:
        return "—"
    return s[:16].replace("T", " ")


def _build_wallet_text(user_id: int) -> str:
    d = bot_services.get_user_wallet_summary(user_id)
    return (
        "💰 *Wallet Balance*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Available Balance:    *{_fmt_currency(d['balance'])}*\n"
        f"Pending Deposits:     {_fmt_currency(d['pending_deposits'])}\n"
        f"Pending Withdrawals:  {_fmt_currency(d['pending_withdrawals'])}\n"
        f"Total Deposited:      {_fmt_currency(d['total_deposits'])}\n"
        f"Total Withdrawn:      {_fmt_currency(d['total_withdrawals'])}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Last activity: {_fmt_date(d['last_updated'])}"
    )


def _build_referral_text(user_id: int, username: str) -> str:
    d = bot_services.get_user_referral_summary(user_id, username)
    return (
        "👥 *Referral Stats*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Referral Code:     `{d['referral_code']}`\n"
        f"Level:             {d['current_level']}\n"
        f"Total Invited:     {d['total_invited']}\n"
        f"Active Referrals:  {d['active_referrals']}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Referral Balance:  *{_fmt_currency(d['wallet_balance'])}*\n"
        f"Total Earned:      {_fmt_currency(d['total_earned'])}\n"
        f"Paid Rewards:      {_fmt_currency(d['paid_rewards'])}\n"
        f"Pending Rewards:   {_fmt_currency(d['pending_rewards'])}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Referral Link:\n{d['referral_link']}"
    )


def _build_mt_text(user_id: int) -> str:
    accounts = bot_services.get_user_mt_accounts(user_id)
    if not accounts:
        return (
            "🔗 *Connected MT Accounts*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "No accounts found yet.\n\n"
            "Use the platform to link your MT4/MT5 account."
        )

    lines = ["🔗 *Connected MT Accounts*", "━━━━━━━━━━━━━━━━━━━━"]
    nums  = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    for i, acc in enumerate(accounts):
        n   = nums[i] if i < len(nums) else f"{i+1}."
        num = acc.get("trading_account_number") or "—"
        bal = _fmt_currency(acc["trading_balance"]) if acc.get("trading_balance") is not None else "—"

        lines.append(
            f"\n{n} *Account #{num}*\n"
            f"   Platform: {acc.get('platform') or '—'}\n"
            f"   Broker:   {acc.get('broker') or '—'}\n"
            f"   Type:     {acc.get('card_type') or '—'}\n"
            f"   Leverage: {acc.get('leverage') or '—'}\n"
            f"   Balance:  {bal}\n"
            f"   Status:   {acc['status_display']}\n"
            f"   Updated:  {_fmt_date(acc.get('updated_at'))}"
        )
    return "\n".join(lines)


# ── Command Handlers ──────────────────────────────────────────────────────────

def _handle_start(chat_id: int, tg_user: dict) -> None:
    tg_id     = str(tg_user.get("id", ""))
    tg_name   = tg_user.get("first_name") or "Trader"
    user = bot_services.get_user_by_telegram_id(tg_id)

    if not user:
        _send(
            chat_id,
            (
                f"👋 Hello, *{tg_name}*!\n\n"
                "To use the TrBridgo bot you need to link your website account.\n\n"
                "*Steps:*\n"
                "1. Open the platform and log in\n"
                "2. Tap *Link My Account* below\n"
                "3. Copy the 6-character code\n"
                f"4. Send `/link YOUR_CODE` here\n\n"
                "_Code expires in 10 minutes._"
            ),
            _link_keyboard(),
        )
        logger.info("/start | chat_id=%s | not linked", chat_id)
        return

    logger.info("/start | chat_id=%s | user_id=%s (%s)", chat_id, user["id"], user["username"])
    _send(
        chat_id,
        (
            f"👋 Welcome back, *{user['full_name']}*!\n\n"
            "🏆 *TrBridgo* — Your Trading Dashboard\n\n"
            "Choose an option:"
        ),
        _main_keyboard(),
    )


def _handle_link(chat_id: int, tg_user: dict, raw_token: str) -> None:
    tg_id   = str(tg_user.get("id", ""))
    tg_name = tg_user.get("first_name") or "Trader"
    tg_uname = tg_user.get("username") or ""

    # Already linked?
    existing = bot_services.get_user_by_telegram_id(tg_id)
    if existing:
        _send(
            chat_id,
            f"✅ Your account is already linked to *{existing['full_name']}*.\n\nSend /start to open the menu.",
        )
        return

    if not raw_token:
        _send(
            chat_id,
            "Usage: `/link YOUR_CODE`\n\nGet your code from the platform:",
            _link_keyboard(),
        )
        return

    user_id = bot_services.consume_link_token(raw_token)
    if not user_id:
        _send(
            chat_id,
            "❌ *Invalid or expired code.*\n\nCodes are valid for 10 minutes. Generate a new one:",
            _link_keyboard(),
        )
        logger.warning("/link | chat_id=%s | invalid token: %s", chat_id, raw_token)
        return

    bot_services.link_telegram_to_user(user_id, tg_id, tg_uname, tg_name)
    user = bot_services.get_user_by_id(user_id)
    name = user["full_name"] if user else "User"

    _send(
        chat_id,
        (
            f"✅ *Account linked successfully!*\n\n"
            f"Welcome, *{name}*!\n\n"
            "Your Telegram is now connected to your TrBridgo account.\n"
            "Send /start to open the menu."
        ),
    )
    logger.info("/link | chat_id=%s | linked to user_id=%s (%s)", chat_id, user_id, name)


# ── Callback Handlers ─────────────────────────────────────────────────────────

def _handle_callback(chat_id: int, message_id: int, tg_user: dict, data: str) -> None:
    tg_id = str(tg_user.get("id", ""))
    user  = bot_services.get_user_by_telegram_id(tg_id)

    if not user:
        _edit(
            chat_id, message_id,
            "🔒 Your account is not linked yet.\n\nSend /start to begin.",
            _link_keyboard(),
        )
        return

    logger.info("CALLBACK | data=%s | user_id=%s", data, user["id"])

    if data == "menu":
        _edit(
            chat_id, message_id,
            (
                f"👋 Welcome back, *{user['full_name']}*!\n\n"
                "🏆 *TrBridgo* — Your Trading Dashboard\n\n"
                "Choose an option:"
            ),
            _main_keyboard(),
        )

    elif data == "balance":
        try:
            text = _build_wallet_text(user["id"])
        except Exception:
            logger.exception("balance callback failed for user_id=%s", user["id"])
            text = "⚠️ Could not load wallet data. Please try again."
        _edit(chat_id, message_id, text, _back_keyboard())

    elif data == "referrals":
        try:
            text = _build_referral_text(user["id"], user["username"])
        except Exception:
            logger.exception("referrals callback failed for user_id=%s", user["id"])
            text = "⚠️ Could not load referral data. Please try again."
        _edit(chat_id, message_id, text, _back_keyboard())

    elif data == "mt_accounts":
        try:
            text = _build_mt_text(user["id"])
        except Exception:
            logger.exception("mt_accounts callback failed for user_id=%s", user["id"])
            text = "⚠️ Could not load account data. Please try again."
        _edit(chat_id, message_id, text, _back_keyboard())

    else:
        logger.warning("CALLBACK | unknown data=%s", data)


# ── Update Router ─────────────────────────────────────────────────────────────

def _route_update(payload: dict) -> None:
    update_id = payload.get("update_id", "?")
    logger.info("[%s] routing update | keys=%s", update_id, list(payload.keys()))

    # ── Regular message ───────────────────────────────────────────────────────
    if "message" in payload:
        msg     = payload["message"]
        chat_id = msg.get("chat", {}).get("id")
        text    = (msg.get("text") or "").strip()
        tg_user = msg.get("from") or {}

        logger.info("[%s] message | chat_id=%s | text=%r", update_id, chat_id, text)

        if not chat_id:
            return

        if text.startswith("/start"):
            _handle_start(chat_id, tg_user)

        elif text.startswith("/link"):
            parts = text.split(maxsplit=1)
            token = parts[1].strip() if len(parts) > 1 else ""
            _handle_link(chat_id, tg_user, token)

        else:
            logger.info("[%s] no handler for text=%r", update_id, text)

    # ── Callback query (inline button press) ──────────────────────────────────
    elif "callback_query" in payload:
        cq         = payload["callback_query"]
        cq_id      = cq["id"]
        chat_id    = cq.get("message", {}).get("chat", {}).get("id")
        message_id = cq.get("message", {}).get("message_id")
        tg_user    = cq.get("from") or {}
        data       = cq.get("data", "")

        logger.info("[%s] callback | data=%s | chat_id=%s", update_id, data, chat_id)

        _answer_callback(cq_id)  # dismiss loading spinner immediately

        if chat_id and message_id:
            _handle_callback(chat_id, message_id, tg_user, data)

    else:
        logger.info("[%s] unsupported update type — skipped", update_id)


# ── Webhook Registration ──────────────────────────────────────────────────────

def set_webhook(base_url: str) -> bool:
    """Register webhook with Telegram. Idempotent — safe to call every startup."""
    if not BOT_TOKEN:
        logger.error("set_webhook: TELEGRAM_BOT_TOKEN not set")
        return False
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    payload: dict = {
        "url":             webhook_url,
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
    if not BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not set"}
    try:
        info = _call_api("getWebhookInfo", {})
        return {
            "url":                  info.get("url", ""),
            "pending_update_count": info.get("pending_update_count", 0),
            "last_error_message":   info.get("last_error_message"),
            "last_error_date":      info.get("last_error_date"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def delete_webhook() -> bool:
    if not BOT_TOKEN:
        return False
    try:
        _call_api("deleteWebhook", {"drop_pending_updates": True})
        return True
    except Exception:
        logger.exception("deleteWebhook FAILED")
        return False


# ── Auto-webhook (once per worker, on first HTTP request) ─────────────────────
_webhook_initialized: bool = False


def _auto_setup_webhook() -> None:
    global _webhook_initialized
    if _webhook_initialized or not WEBAPP_URL or not BOT_TOKEN:
        return
    _webhook_initialized = True
    if set_webhook(WEBAPP_URL):
        logger.info("Auto-webhook configured: %s/telegram/webhook", WEBAPP_URL)
    else:
        logger.warning("Auto-webhook FAILED — check BOT_TOKEN and WEBAPP_URL in Render")


# ── Flask Blueprint ───────────────────────────────────────────────────────────

telegram_blueprint = Blueprint("telegram_bot", __name__)
telegram_blueprint.before_app_request(_auto_setup_webhook)


@telegram_blueprint.route("/telegram/webhook", methods=["POST"])
def telegram_webhook() -> tuple:
    """POST /telegram/webhook — receives all Telegram updates."""
    raw_body = request.get_data(as_text=True)
    logger.info(
        "WEBHOOK HIT | ip=%s | content_type=%s | body_len=%d",
        request.remote_addr, request.content_type, len(raw_body),
    )
    logger.info("RAW UPDATE: %s", raw_body)

    if not BOT_TOKEN:
        logger.error("WEBHOOK: BOT_TOKEN not configured")
        return jsonify({"error": "bot not configured"}), 503

    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != WEBHOOK_SECRET:
            logger.warning("WEBHOOK: invalid secret from %s", request.remote_addr)
            return "Forbidden", 403

    try:
        payload = json.loads(raw_body) if raw_body else None
    except json.JSONDecodeError:
        logger.error("WEBHOOK: invalid JSON body")
        return "OK", 200

    if not payload:
        return "OK", 200

    try:
        _route_update(payload)
    except Exception:
        logger.exception("WEBHOOK: error on update_id=%s", payload.get("update_id"))

    return "OK", 200


@telegram_blueprint.route("/telegram/health", methods=["GET"])
def telegram_health() -> tuple:
    """GET /telegram/health — verify bot is active after deploy."""
    configured = bool(BOT_TOKEN) and bool(WEBAPP_URL)
    body = {
        "status":        "active" if configured else "not_configured",
        "bot_token_set": bool(BOT_TOKEN),
        "webapp_url":    WEBAPP_URL or None,
        "webhook_url":   _WEBHOOK_URL,
        "routes": {
            "webhook": "POST /telegram/webhook",
            "health":  "GET  /telegram/health",
            "connect": "GET  /telegram/connect  (login required)",
        },
    }
    if not configured:
        body["hint"] = "Set TELEGRAM_BOT_TOKEN and WEBAPP_URL in Render → Environment, then redeploy."
        return jsonify(body), 200
    body["telegram_webhook_info"] = get_webhook_info()
    return jsonify(body), 200


# ── Local Development: Polling ────────────────────────────────────────────────

def main() -> None:
    """
    Local polling mode — do NOT use on Render.
        python telegram_bot.py
    """
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")

    import asyncio
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler  # type: ignore

    async def _start(update, ctx):
        tg_user = update.effective_user
        _handle_start(
            update.effective_chat.id,
            {"id": tg_user.id, "first_name": tg_user.first_name, "username": tg_user.username},
        )

    async def _link(update, ctx):
        args = ctx.args or []
        token = args[0] if args else ""
        tg_user = update.effective_user
        _handle_link(
            update.effective_chat.id,
            {"id": tg_user.id, "first_name": tg_user.first_name, "username": tg_user.username},
            token,
        )

    async def _callback(update, ctx):
        cq = update.callback_query
        await cq.answer()
        tg_user = cq.from_user
        _handle_callback(
            cq.message.chat_id,
            cq.message.message_id,
            {"id": tg_user.id, "first_name": tg_user.first_name, "username": tg_user.username},
            cq.data,
        )

    async def _run():
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", _start))
        app.add_handler(CommandHandler("link",  _link))
        app.add_handler(CallbackQueryHandler(_callback))
        logger.info("Polling mode started (local dev only)")
        await app.run_polling(drop_pending_updates=True)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
