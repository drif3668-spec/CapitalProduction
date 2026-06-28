"""
bot_services.py — Shared Data Service Layer
============================================
Used by BOTH the Flask dashboard routes and the Telegram bot.
Direct SQLite connections only — never uses Flask's request context (g),
so it works safely outside HTTP request scope (e.g. from telegram_bot.py).

Rule: this module NEVER returns passwords, OTPs, CVVs, or full card numbers.
Sensitive columns are explicitly excluded from every SELECT statement.
"""

import os
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Database path — same file used by app.py
BASE_DIR = Path(__file__).resolve().parent
DATABASE = str(BASE_DIR / "instance" / "capital.db")

# Webapp URL (used to build referral links)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")

# One-time link tokens: 6 uppercase alphanumeric chars, valid 10 minutes
_TOKEN_CHARS = string.ascii_uppercase + string.digits
_TOKEN_LEN = 6
_TOKEN_TTL_MINUTES = 10


# ── DB connection ─────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    """Open a fresh, short-lived SQLite connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ── User lookup ───────────────────────────────────────────────────────────────

def get_user_by_telegram_id(telegram_user_id: str) -> dict | None:
    """Return the website user linked to this Telegram ID, or None."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, full_name, username, email, plan, subscription_active, "
            "account_status, telegram_username, telegram_first_name, telegram_linked_at "
            "FROM users WHERE telegram_user_id = ?",
            (str(telegram_user_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Return basic user info by primary key."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, full_name, username, email, plan, subscription_active, "
            "account_status, telegram_user_id "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def link_telegram_to_user(
    user_id: int,
    telegram_user_id: str,
    telegram_username: str,
    telegram_first_name: str,
) -> None:
    """Store Telegram identity against the website user account."""
    conn = _db()
    try:
        conn.execute(
            """
            UPDATE users
            SET telegram_user_id    = ?,
                telegram_username   = ?,
                telegram_first_name = ?,
                telegram_linked_at  = ?
            WHERE id = ?
            """,
            (
                str(telegram_user_id),
                telegram_username or "",
                telegram_first_name or "",
                datetime.now(timezone.utc).isoformat(),
                user_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def unlink_telegram(user_id: int) -> None:
    """Remove Telegram linkage from a user account."""
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET telegram_user_id = NULL, telegram_username = NULL, "
            "telegram_first_name = NULL, telegram_linked_at = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ── One-time link tokens ──────────────────────────────────────────────────────

def create_link_token(user_id: int) -> str:
    """
    Generate a one-time linking token valid for 10 minutes.
    Any previous unused token for this user is invalidated first.
    """
    token = "".join(secrets.choice(_TOKEN_CHARS) for _ in range(_TOKEN_LEN))
    expires = (
        datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)
    ).isoformat()
    conn = _db()
    try:
        # Invalidate existing unused tokens for this user
        conn.execute(
            "UPDATE telegram_link_tokens SET used = 1 WHERE user_id = ? AND used = 0",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO telegram_link_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def consume_link_token(raw_token: str) -> int | None:
    """
    Validate and consume a one-time token.
    Returns the linked user_id on success, None if invalid/expired.
    """
    token = raw_token.strip().upper()
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    try:
        row = conn.execute(
            "SELECT user_id FROM telegram_link_tokens "
            "WHERE token = ? AND used = 0 AND expires_at > ?",
            (token, now),
        ).fetchone()
        if not row:
            return None
        user_id = row["user_id"]
        conn.execute(
            "UPDATE telegram_link_tokens SET used = 1 WHERE token = ?", (token,)
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


# ── Wallet summary ────────────────────────────────────────────────────────────

def get_user_wallet_summary(user_id: int) -> dict:
    """
    Mirror of wallet_summary() in app.py — live data from wallet_transactions.
    Returns the same fields used by the Flask dashboard.
    """
    conn = _db()
    try:
        def _sum(kind: str, status: str) -> float:
            return conn.execute(
                "SELECT COALESCE(SUM(amount), 0) v FROM wallet_transactions "
                "WHERE user_id = ? AND kind = ? AND status = ?",
                (user_id, kind, status),
            ).fetchone()["v"]

        deposits            = _sum("deposit",  "مقبول")
        withdrawals         = _sum("withdraw", "مقبول")
        mktg_transfers      = _sum("wallet_to_marketing_transfer", "مقبول")
        pending_deposits    = _sum("deposit",  "قيد المراجعة")
        pending_withdrawals = _sum("withdraw", "قيد المراجعة")

        last_tx = conn.execute(
            "SELECT created_at FROM wallet_transactions "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        return {
            "balance":             deposits - withdrawals - mktg_transfers,
            "total_deposits":      deposits,
            "total_withdrawals":   withdrawals,
            "pending_deposits":    pending_deposits,
            "pending_withdrawals": pending_withdrawals,
            "last_updated":        last_tx["created_at"] if last_tx else None,
        }
    finally:
        conn.close()


# ── Referral summary ──────────────────────────────────────────────────────────

def _referral_code(username: str, user_id: int) -> str:
    """Same algorithm used by app.py's referral_code_for_user()."""
    raw = "".join(ch for ch in username.upper() if ch.isalnum())
    return raw or f"USER{user_id}"


def get_user_referral_summary(user_id: int, username: str) -> dict:
    """Live referral data from the same tables used by the Flask dashboard."""
    code = _referral_code(username, user_id)
    conn = _db()
    try:
        total_invited = conn.execute(
            "SELECT COUNT(*) c FROM referrals WHERE referrer_id = ?", (user_id,)
        ).fetchone()["c"]

        active_referrals = conn.execute(
            """
            SELECT COUNT(*) c
            FROM referrals
            JOIN users ON users.id = referrals.referred_user_id
            WHERE referrals.referrer_id = ?
              AND users.subscription_active = 1
              AND users.account_status != 'موقوف'
            """,
            (user_id,),
        ).fetchone()["c"]

        pending_rewards = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) v FROM referral_commissions "
            "WHERE user_id = ? AND status = 'قيد المراجعة'",
            (user_id,),
        ).fetchone()["v"]

        paid_rewards = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) v FROM referral_commissions "
            "WHERE user_id = ? AND status = 'مقبول'",
            (user_id,),
        ).fetchone()["v"]

        wallet = conn.execute(
            "SELECT balance, total_earned, total_withdrawn FROM referral_wallet "
            "WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        level_row = conn.execute(
            "SELECT current_level FROM referral_levels WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        return {
            "referral_code":    code,
            "referral_link":    f"{WEBAPP_URL}/register?ref={code}",
            "total_invited":    total_invited,
            "active_referrals": active_referrals,
            "pending_rewards":  pending_rewards,
            "paid_rewards":     paid_rewards,
            "wallet_balance":   wallet["balance"]       if wallet else 0.0,
            "total_earned":     wallet["total_earned"]  if wallet else 0.0,
            "current_level":    level_row["current_level"] if level_row else "المستوى 1",
        }
    finally:
        conn.close()


# ── MT / Subscription-card accounts ──────────────────────────────────────────

# Status map: Arabic DB value → English display
_MT_STATUS = {
    "نشطة":          "✅ Active",
    "غير نشطة":      "⚪ Inactive",
    "قيد المراجعة":  "🔄 Under Review",
    "معلقة":         "⏸ Suspended",
    "منتهية":        "❌ Expired",
    "مرفوضة":        "🚫 Rejected",
}


def get_user_mt_accounts(user_id: int) -> list[dict]:
    """
    Return subscription cards (MT4/MT5 accounts) for the user.
    Explicitly selects only safe columns — no passwords ever returned.
    """
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, card_type, status, platform, broker,
                   trading_account_number, trading_account_type,
                   leverage, trading_balance, visible_balance,
                   created_at, updated_at
            FROM subscription_cards
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["status_display"] = _MT_STATUS.get(d.get("status", ""), d.get("status", ""))
            result.append(d)
        return result
    finally:
        conn.close()


# ── Recent transactions ───────────────────────────────────────────────────────

_TX_KIND_LABEL = {
    "deposit":                      "💳 Deposit",
    "withdraw":                     "💸 Withdrawal",
    "wallet_to_marketing_transfer": "📢 Marketing Transfer",
    "referral_withdrawal":          "👥 Referral Payout",
}

_TX_STATUS_LABEL = {
    "مقبول":        "✅ Approved",
    "قيد المراجعة": "🔄 Pending",
    "مرفوض":        "❌ Rejected",
    "قيد الإنجاز":  "⏳ Processing",
}


def get_user_recent_transactions(user_id: int, limit: int = 5) -> list[dict]:
    """Return the most recent wallet transactions — no sensitive details."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT kind, method, amount, status, created_at "
            "FROM wallet_transactions "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["kind_label"]   = _TX_KIND_LABEL.get(d["kind"], d["kind"])
            d["status_label"] = _TX_STATUS_LABEL.get(d["status"], d["status"])
            result.append(d)
        return result
    finally:
        conn.close()
