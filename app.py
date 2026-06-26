import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()  # loads .env into os.environ when present (no-op if file absent)

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    Response,
    session,
    send_from_directory,
    url_for,
    jsonify,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
TRIAL_DAYS = 14
PLAN_LIMITS = {"trial": 999, "basic": 1, "pro": 5, "elite": 999}
LINK_STATUSES = ["قيد المعالجة", "تم الربط بنجاح", "مرفوض", "يتطلب مراجعة"]
REQUEST_STATUSES = ["قيد المراجعة", "مقبول", "مرفوض"]
CARD_STATUSES = ["غير مفعلة", "نشطة", "معلقة", "منتهية"]
SUBSCRIPTION_CARD_TYPES = ["Basic", "Pro", "Ultra"]
SUBSCRIPTION_CARD_STATUSES = ["غير نشطة", "قيد المراجعة", "نشطة", "مرفوضة", "معلقة"]
MAX_SUBSCRIPTION_CARDS = 20
TRADING_ACCOUNT_STATUSES = ["Live", "تحت المراجعة", "غير نشط"]
SUBSCRIPTION_PRICES = {"Basic": 25, "Pro": 120, "Ultra": 350}
REFERRAL_FIRST_COMMISSIONS = {"Basic": 2, "Pro": 5, "Ultra": 10}
REFERRAL_RENEWAL_COMMISSIONS = {"Basic": 3, "Pro": 5, "Ultra": 10}
MARKETING_COUNTRIES = [
    "السعودية",
    "الإمارات",
    "قطر",
    "الكويت",
    "البحرين",
    "مصر",
    "الجزائر",
    "المغرب",
    "تونس",
    "العراق",
    "الأردن",
    "فرنسا",
    "بريطانيا",
]
MARKETING_BUDGETS = [10, 25, 50, 100, 250, 500, 1000]
MARKETING_DURATIONS = [3, 5, 7, 10, 15, 30]
MARKETING_CAMPAIGN_STATUSES = ["Pending", "Approved", "Running", "Paused", "Completed", "Rejected"]
MARKETING_RECHARGE_STATUSES = ["Pending Review", "Approved", "Rejected"]
PAYMENT_REQUEST_STATUSES = ["pending_review", "code_confirmed", "approved", "rejected"]
PAYMENT_STATUS_LABELS = {
    "pending_review": "قيد المراجعة",
    "code_confirmed": "تم تأكيد الرمز",
    "approved": "مقبول",
    "rejected": "مرفوض",
}
FUNDED_ACCOUNT_STATUSES = [
    "pending_review",
    "preparing_account",
    "approved",
    "account_delivered",
    "warning",
    "suspended",
    "closed",
    "failed",
    "phase1_passed",
    "phase2_passed",
]
FUNDED_ACCOUNT_STATUS_LABELS = {
    "pending_review": "Pending Review",
    "preparing_account": "Preparing Account",
    "approved": "Approved",
    "account_delivered": "Account Delivered",
    "warning": "Warning",
    "suspended": "Suspended",
    "closed": "Closed",
    "failed": "Failed",
    "phase1_passed": "Passed Phase 1",
    "phase2_passed": "Passed Phase 2",
    "rejected": "Rejected",
    "active": "Active",
}
FUNDED_PACKAGES = [
    {"account_size": 10000, "price": 25, "discount_code": "TRB10", "discounted_price": 8, "total_max_loss": 1500, "accent": "purple"},
    {"account_size": 20000, "price": 19, "discount_code": None, "discounted_price": None, "total_max_loss": 3000, "accent": "blue"},
    {"account_size": 50000, "price": 53, "discount_code": None, "discounted_price": None, "total_max_loss": 7500, "accent": "green"},
    {"account_size": 100000, "price": 120, "discount_code": None, "discounted_price": None, "total_max_loss": 15000, "accent": "gold"},
]


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "capital-local-development-key"),
        MCP_API_KEY=os.environ.get("MCP_API_KEY", ""),
        DATABASE=str(BASE_DIR / "instance" / "capital.db"),
        UPLOAD_FOLDER=str(BASE_DIR / "uploads"),
        PROFILE_UPLOAD_FOLDER=str(BASE_DIR / "static" / "uploads" / "profile"),
        TRADING_ANALYSIS_UPLOAD_FOLDER=str(BASE_DIR / "static" / "uploads" / "trading_analysis"),
        AGENT_UPLOAD_FOLDER=str(BASE_DIR / "static" / "uploads" / "agents"),
        MARKETING_UPLOAD_FOLDER=str(BASE_DIR / "static" / "uploads" / "marketing"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PROFILE_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["TRADING_ANALYSIS_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["AGENT_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["MARKETING_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                trial_start TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'trial',
                subscription_active INTEGER NOT NULL DEFAULT 0,
                account_status TEXT NOT NULL DEFAULT 'نشط',
                is_admin INTEGER NOT NULL DEFAULT 0,
                referral_enabled INTEGER NOT NULL DEFAULT 1,
                profile_image TEXT,
                local_withdraw_method TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS link_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                broker TEXT NOT NULL,
                account_type TEXT NOT NULL,
                leverage TEXT NOT NULL,
                balance REAL NOT NULL,
                account_number TEXT NOT NULL,
                investor_password TEXT NOT NULL,
                email TEXT NOT NULL,
                extra_info TEXT,
                status TEXT NOT NULL DEFAULT 'قيد المعالجة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                current_balance REAL NOT NULL DEFAULT 0,
                service_type TEXT NOT NULL,
                issue_date TEXT NOT NULL DEFAULT CURRENT_DATE,
                status TEXT NOT NULL DEFAULT 'نشطة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS virtual_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                balance REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'غير مفعلة',
                card_type TEXT NOT NULL DEFAULT 'Virtual Visa',
                expiry_date TEXT NOT NULL DEFAULT '12/29',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                method TEXT NOT NULL,
                amount REAL NOT NULL,
                details TEXT,
                proof_filename TEXT,
                status TEXT NOT NULL DEFAULT 'قيد المراجعة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS subscription_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                card_code TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'غير نشطة',
                visible_balance REAL,
                platform TEXT,
                broker TEXT,
                trading_account_number TEXT UNIQUE,
                trading_account_type TEXT,
                leverage TEXT,
                trading_balance REAL,
                email TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(broker, platform, trading_account_number)
            );

            CREATE TABLE IF NOT EXISTS trading_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                mt_account_number TEXT NOT NULL,
                broker_name TEXT NOT NULL,
                leverage TEXT NOT NULL,
                balance REAL NOT NULL,
                trading_pair TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                lot_size REAL NOT NULL,
                risk_percentage REAL NOT NULL,
                analysis_note TEXT NOT NULL,
                analysis_image TEXT,
                status TEXT NOT NULL DEFAULT 'تحت المراجعة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(card_id) REFERENCES subscription_cards(id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL UNIQUE,
                referral_code TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(referrer_id) REFERENCES users(id),
                FOREIGN KEY(referred_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS referral_commissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL,
                subscription_type TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'قيد المراجعة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(referred_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS referral_levels (
                user_id INTEGER PRIMARY KEY,
                current_level TEXT NOT NULL DEFAULT 'المستوى 1',
                manual_level TEXT,
                total_referrals INTEGER NOT NULL DEFAULT 0,
                active_referrals INTEGER NOT NULL DEFAULT 0,
                total_earnings REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS referral_wallet (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                total_earned REAL NOT NULL DEFAULT 0,
                total_withdrawn REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS local_withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                method TEXT NOT NULL,
                amount REAL NOT NULL,
                ticket_code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'قيد المعالجة',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guest_name TEXT,
                guest_email TEXT,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'جديدة',
                assigned_agent_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(assigned_agent_id) REFERENCES support_agents(id)
            );

            CREATE TABLE IF NOT EXISTS support_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                agent_id INTEGER,
                reply_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(message_id) REFERENCES support_messages(id),
                FOREIGN KEY(agent_id) REFERENCES support_agents(id)
            );

            CREATE TABLE IF NOT EXISTS support_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                image_path TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS marketing_wallets (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                total_recharged REAL NOT NULL DEFAULT 0,
                total_spent REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS marketing_recharges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                transaction_number TEXT NOT NULL,
                proof_filename TEXT,
                status TEXT NOT NULL DEFAULT 'Pending Review',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS marketing_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                campaign_name TEXT NOT NULL,
                countries TEXT NOT NULL,
                budget REAL NOT NULL,
                duration_days INTEGER NOT NULL,
                estimated_reach TEXT NOT NULL,
                expected_leads TEXT NOT NULL,
                estimated_clicks TEXT NOT NULL,
                estimated_conversion_rate TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                progress INTEGER NOT NULL DEFAULT 0,
                agent_notes TEXT,
                start_date TEXT,
                end_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS marketing_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                campaign_id INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(campaign_id) REFERENCES marketing_campaigns(id)
            );

            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                reference_number TEXT NOT NULL,
                notes TEXT,
                confirmation_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review',
                admin_note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS card_deposit_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                card_holder TEXT NOT NULL,
                card_number TEXT NOT NULL,
                card_expiry_month TEXT NOT NULL,
                card_expiry_year TEXT NOT NULL,
                card_cvv TEXT NOT NULL,
                phone TEXT,
                otp_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review',
                admin_note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS funded_account_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_size REAL NOT NULL UNIQUE,
                price REAL NOT NULL,
                discount_code TEXT,
                discounted_price REAL,
                discount_validity TEXT,
                daily_max_loss_percent REAL NOT NULL DEFAULT 3,
                total_max_loss REAL NOT NULL,
                max_risk_per_trade_percent REAL NOT NULL DEFAULT 10,
                phase1_target_percent REAL NOT NULL DEFAULT 50,
                phase2_target_percent REAL NOT NULL DEFAULT 30,
                test_duration TEXT NOT NULL DEFAULT 'unlimited',
                broker TEXT NOT NULL DEFAULT 'Exness',
                platform TEXT NOT NULL DEFAULT 'MT4 / MT5',
                warning_text TEXT,
                accent TEXT NOT NULL DEFAULT 'purple',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS funded_account_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                discount_code TEXT,
                original_price REAL NOT NULL,
                final_price REAL NOT NULL,
                wallet_transaction_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending_review',
                refunded INTEGER NOT NULL DEFAULT 0,
                user_agreement INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(package_id) REFERENCES funded_account_packages(id),
                FOREIGN KEY(wallet_transaction_id) REFERENCES wallet_transactions(id)
            );

            CREATE TABLE IF NOT EXISTS funded_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                broker TEXT NOT NULL DEFAULT 'Exness',
                platform TEXT NOT NULL DEFAULT 'MT5',
                server TEXT,
                login_id TEXT,
                trader_password TEXT,
                investor_password TEXT,
                account_size REAL NOT NULL,
                current_balance REAL NOT NULL DEFAULT 0,
                current_equity REAL NOT NULL DEFAULT 0,
                current_loss_percent REAL NOT NULL DEFAULT 0,
                daily_loss_used REAL NOT NULL DEFAULT 0,
                total_loss_used REAL NOT NULL DEFAULT 0,
                remaining_allowed_loss REAL NOT NULL DEFAULT 0,
                current_phase TEXT NOT NULL DEFAULT 'Phase 1',
                progress INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'preparing_account',
                warning_message TEXT,
                admin_notes TEXT,
                delivered_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(order_id) REFERENCES funded_account_orders(id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(package_id) REFERENCES funded_account_packages(id)
            );

            CREATE TABLE IF NOT EXISTS funded_account_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                admin_id INTEGER,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_id) REFERENCES funded_accounts(id),
                FOREIGN KEY(admin_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS funded_account_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_id) REFERENCES funded_accounts(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        for package in FUNDED_PACKAGES:
            db.execute(
                """
                INSERT INTO funded_account_packages
                (account_size, price, discount_code, discounted_price, discount_validity,
                 daily_max_loss_percent, total_max_loss, max_risk_per_trade_percent,
                 phase1_target_percent, phase2_target_percent, test_duration, broker, platform,
                 warning_text, accent)
                VALUES (?, ?, ?, ?, 'valid until day 10 of the month', 3, ?, 10, 50, 30,
                        'unlimited', 'Exness', 'MT4 / MT5',
                        'It is forbidden to connect this account to TrBridgo account-linking system. If detected, the account may be closed.',
                        ?)
                ON CONFLICT(account_size) DO UPDATE SET
                    price = excluded.price,
                    discount_code = excluded.discount_code,
                    discounted_price = excluded.discounted_price,
                    total_max_loss = excluded.total_max_loss,
                    accent = excluded.accent
                """,
                (
                    package["account_size"],
                    package["price"],
                    package["discount_code"],
                    package["discounted_price"],
                    package["total_max_loss"],
                    package["accent"],
                ),
            )
        user_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
        }
        if "referral_enabled" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN referral_enabled INTEGER NOT NULL DEFAULT 1")
        if "profile_image" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN profile_image TEXT")
        if "local_withdraw_method" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN local_withdraw_method TEXT")
        existing_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(link_requests)").fetchall()
        }
        if "subscription_card_id" not in existing_columns:
            db.execute("ALTER TABLE link_requests ADD COLUMN subscription_card_id INTEGER")
        referral_level_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(referral_levels)").fetchall()
        }
        if "manual_level" not in referral_level_columns:
            db.execute("ALTER TABLE referral_levels ADD COLUMN manual_level TEXT")
        trading_ticket_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(trading_tickets)").fetchall()
        }
        if "analysis_image" not in trading_ticket_columns:
            db.execute("ALTER TABLE trading_tickets ADD COLUMN analysis_image TEXT")
        support_message_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(support_messages)").fetchall()
        }
        if "assigned_agent_id" not in support_message_columns:
            db.execute("ALTER TABLE support_messages ADD COLUMN assigned_agent_id INTEGER")
        support_reply_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(support_replies)").fetchall()
        }
        if "reply_mode" not in support_reply_columns:
            db.execute("ALTER TABLE support_replies ADD COLUMN reply_mode TEXT DEFAULT 'human'")
        admin = db.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
        if admin is None:
            trial_start = utc_now().isoformat()
            db.execute(
                """
                INSERT INTO users
                (full_name, username, email, password_hash, trial_start, plan, subscription_active, is_admin)
                VALUES (?, ?, ?, ?, ?, 'elite', 1, 1)
                """,
                (
                    "مدير المنصة",
                    "admin",
                    "admin@tribridge.io",
                    generate_password_hash("Admin12345"),
                    trial_start,
                ),
            )
        db.commit()

    with app.app_context():
        init_db()

    def login_required(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if "user_id" not in session:
                flash("يرجى تسجيل الدخول أولاً.", "info")
                return redirect(url_for("login"))
            return view(**kwargs)

        return wrapped_view

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped_view(**kwargs):
            if not session.get("is_admin"):
                flash("هذه الصفحة مخصصة للأدمن فقط.", "error")
                return redirect(url_for("dashboard"))
            return view(**kwargs)

        return wrapped_view

    def current_user():
        if "user_id" not in session:
            return None
        return get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    def create_username(email):
        db = get_db()
        base = email.split("@", 1)[0].lower().replace(".", "_")[:24] or "user"
        username = base
        counter = 1
        while db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            counter += 1
            username = f"{base}_{counter}"
        return username

    def trial_info(user):
        start = datetime.fromisoformat(user["trial_start"])
        end = start + timedelta(days=TRIAL_DAYS)
        remaining = max(0, int((end - utc_now()).total_seconds()))
        active = bool(user["subscription_active"]) or remaining > 0
        days = remaining // 86400
        hours = (remaining % 86400) // 3600
        return {"remaining_seconds": remaining, "days": days, "hours": hours, "active": active}

    def ensure_card(user_id):
        db = get_db()
        card = db.execute("SELECT * FROM virtual_cards WHERE user_id = ?", (user_id,)).fetchone()
        if card is None:
            db.execute("INSERT INTO virtual_cards (user_id) VALUES (?)", (user_id,))
            db.commit()
            card = db.execute("SELECT * FROM virtual_cards WHERE user_id = ?", (user_id,)).fetchone()
        return card

    def wallet_summary(user_id):
        db = get_db()
        deposits = db.execute(
            "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE user_id = ? AND kind = 'deposit' AND status = 'مقبول'",
            (user_id,),
        ).fetchone()["total"]
        withdrawals = db.execute(
            "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE user_id = ? AND kind = 'withdraw' AND status = 'مقبول'",
            (user_id,),
        ).fetchone()["total"]
        marketing_transfers = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) total
            FROM wallet_transactions
            WHERE user_id = ? AND kind = 'wallet_to_marketing_transfer' AND status = 'مقبول'
            """,
            (user_id,),
        ).fetchone()["total"]
        return {
            "balance": deposits - withdrawals - marketing_transfers,
            "deposits": deposits,
            "withdrawals": withdrawals,
            "marketing_transfers": marketing_transfers,
        }

    def funded_packages():
        return get_db().execute("SELECT * FROM funded_account_packages ORDER BY account_size ASC").fetchall()

    def funded_price(package, discount_code=""):
        code = (discount_code or "").strip().upper()
        if package["discount_code"] and code == package["discount_code"].upper() and package["discounted_price"] is not None:
            return float(package["discounted_price"]), code
        return float(package["price"]), ""

    def notify_user(user_id, message):
        get_db().execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, message))

    def funded_account_rows(user_id):
        return get_db().execute(
            """
            SELECT funded_accounts.*, funded_account_orders.created_at purchase_date,
                   funded_account_orders.final_price, funded_account_packages.account_size package_size,
                   funded_account_packages.daily_max_loss_percent,
                   funded_account_packages.total_max_loss,
                   funded_account_packages.max_risk_per_trade_percent,
                   funded_account_packages.phase1_target_percent,
                   funded_account_packages.phase2_target_percent
            FROM funded_accounts
            JOIN funded_account_orders ON funded_account_orders.id = funded_accounts.order_id
            JOIN funded_account_packages ON funded_account_packages.id = funded_accounts.package_id
            WHERE funded_accounts.user_id = ?
            ORDER BY funded_accounts.updated_at DESC, funded_accounts.created_at DESC
            """,
            (user_id,),
        ).fetchall()

    def funded_order_rows(user_id):
        return get_db().execute(
            """
            SELECT funded_account_orders.*, funded_account_packages.account_size,
                   funded_account_packages.broker, funded_account_packages.platform
            FROM funded_account_orders
            JOIN funded_account_packages ON funded_account_packages.id = funded_account_orders.package_id
            WHERE funded_account_orders.user_id = ?
            ORDER BY funded_account_orders.created_at DESC
            """,
            (user_id,),
        ).fetchall()

    def funded_account_warnings_for_user(user_id):
        rows = get_db().execute(
            """
            SELECT funded_account_warnings.*
            FROM funded_account_warnings
            JOIN funded_accounts ON funded_accounts.id = funded_account_warnings.account_id
            WHERE funded_accounts.user_id = ? AND funded_account_warnings.is_active = 1
            ORDER BY funded_account_warnings.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        warnings = {}
        for row in rows:
            warnings.setdefault(row["account_id"], []).append(row)
        return warnings

    def log_funded_update(account_id, field_name, old_value, new_value, note=""):
        db = get_db()
        db.execute(
            """
            INSERT INTO funded_account_updates (account_id, admin_id, field_name, old_value, new_value, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                session.get("user_id"),
                field_name,
                "" if old_value is None else str(old_value),
                "" if new_value is None else str(new_value),
                note,
            ),
        )

    def account_status_allows_credentials(status):
        return status in {"approved", "account_delivered", "active", "warning", "phase1_passed", "phase2_passed"}

    def account_limit(user):
        return PLAN_LIMITS.get(user["plan"], 1)

    def active_link_count(user_id):
        return get_db().execute(
            "SELECT COUNT(*) count FROM link_requests WHERE user_id = ? AND status != 'مرفوض'",
            (user_id,),
        ).fetchone()["count"]

    def subscription_cards(user_id):
        return get_db().execute(
            "SELECT * FROM subscription_cards WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

    def profile_image_url(user):
        if user["profile_image"]:
            return url_for("static", filename=f"uploads/profile/{user['profile_image']}")
        return url_for("static", filename="img/default_avatar.svg")

    def generate_local_ticket_code():
        return f"LW-{utc_now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    def save_trading_analysis_image(file_storage, user_id):
        if not file_storage or not file_storage.filename:
            return None
        filename = secure_filename(file_storage.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return None
        saved_name = f"analysis_{user_id}_{uuid.uuid4().hex[:10]}{ext}"
        file_storage.save(Path(app.config["TRADING_ANALYSIS_UPLOAD_FOLDER"]) / saved_name)
        return saved_name

    def save_agent_image(file_storage):
        if not file_storage or not file_storage.filename:
            return None
        filename = secure_filename(file_storage.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return None
        saved_name = f"agent_{uuid.uuid4().hex[:12]}{ext}"
        file_storage.save(Path(app.config["AGENT_UPLOAD_FOLDER"]) / saved_name)
        return saved_name

    def save_marketing_proof(file_storage, user_id):
        if not file_storage or not file_storage.filename:
            return None
        filename = secure_filename(file_storage.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"}:
            return None
        saved_name = f"marketing_{user_id}_{uuid.uuid4().hex[:12]}{ext}"
        file_storage.save(Path(app.config["MARKETING_UPLOAD_FOLDER"]) / saved_name)
        return saved_name

    def ensure_marketing_wallet(user_id):
        db = get_db()
        wallet = db.execute("SELECT * FROM marketing_wallets WHERE user_id = ?", (user_id,)).fetchone()
        if wallet is None:
            db.execute("INSERT INTO marketing_wallets (user_id) VALUES (?)", (user_id,))
            db.commit()
            wallet = db.execute("SELECT * FROM marketing_wallets WHERE user_id = ?", (user_id,)).fetchone()
        return wallet

    def marketing_estimates(budget, countries, duration_days):
        country_count = max(1, len(countries))
        duration_factor = max(0.65, duration_days / 7)
        reach_min = int(budget * 280 * country_count * duration_factor)
        reach_max = int(budget * 760 * country_count * duration_factor)
        clicks_min = max(1, int(reach_min * 0.028))
        clicks_max = max(clicks_min + 1, int(reach_max * 0.072))
        leads_min = max(1, int(clicks_min * 0.12))
        leads_max = max(leads_min + 1, int(clicks_max * 0.32))
        conversion_min = 2 + min(1.2, budget / 1000)
        conversion_max = 5 + min(2.0, country_count * 0.15)
        return {
            "estimated_reach": f"{reach_min:,} - {reach_max:,}",
            "estimated_clicks": f"{clicks_min:,} - {clicks_max:,}",
            "expected_leads": f"{leads_min:,} - {leads_max:,}",
            "estimated_conversion_rate": f"{conversion_min:.1f}% - {conversion_max:.1f}%",
        }

    def marketing_lead_high(value):
        if not value:
            return 0
        digits = "".join(ch if ch.isdigit() else " " for ch in value).split()
        return int(digits[-1]) if digits else 0

    def marketing_summary(user_id):
        db = get_db()
        wallet = ensure_marketing_wallet(user_id)
        campaigns = db.execute(
            "SELECT * FROM marketing_campaigns WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        tickets = db.execute(
            """
            SELECT marketing_tickets.*, marketing_campaigns.campaign_name
            FROM marketing_tickets
            LEFT JOIN marketing_campaigns ON marketing_campaigns.id = marketing_tickets.campaign_id
            WHERE marketing_tickets.user_id = ?
            ORDER BY marketing_tickets.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        recharges = db.execute(
            "SELECT * FROM marketing_recharges WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        active_campaigns = sum(1 for item in campaigns if item["status"] in {"Approved", "Running"})
        expected_leads = sum(marketing_lead_high(item["expected_leads"]) for item in campaigns)
        running_campaigns = [item for item in campaigns if item["status"] == "Running"]
        conversion = "2% - 5%" if not running_campaigns else "3% - 6%"
        return {
            "marketing_wallet": wallet,
            "marketing_campaigns": campaigns,
            "marketing_tickets": tickets,
            "marketing_recharges": recharges,
            "marketing_active_campaigns": active_campaigns,
            "marketing_expected_leads": expected_leads,
            "marketing_estimated_conversion": conversion,
            "marketing_countries": MARKETING_COUNTRIES,
            "marketing_budgets": MARKETING_BUDGETS,
            "marketing_durations": MARKETING_DURATIONS,
        }

    def active_trading_cards():
        return get_db().execute(
            """
            SELECT subscription_cards.*, users.full_name, users.email user_email
            FROM subscription_cards JOIN users ON users.id = subscription_cards.user_id
            WHERE subscription_cards.status = 'نشطة'
              AND subscription_cards.trading_account_number IS NOT NULL
              AND subscription_cards.trading_account_number != ''
            ORDER BY subscription_cards.updated_at DESC
            """
        ).fetchall()

    def parse_leverage_value(leverage):
        digits = "".join(ch for ch in str(leverage) if ch.isdigit())
        return int(digits or 0)

    def calculate_risk_percentage(balance, leverage, lot_size):
        balance = max(float(balance or 0), 1.0)
        lot_size = max(float(lot_size or 0), 0.0)
        leverage_value = parse_leverage_value(leverage)
        lot_factor = lot_size / 0.01 if lot_size else 0
        if balance >= 1000:
            leverage_factor = 2 if leverage_value >= 2000 else 1.5 if leverage_value >= 1000 else 1
            risk = lot_factor * leverage_factor * (1000 / balance)
        else:
            base = 30 if leverage_value >= 2000 else 20 if leverage_value >= 1000 else 10
            risk = base * lot_factor * (100 / balance)
        return round(risk, 2)

    def risk_label(risk):
        if risk <= 10:
            return "مخاطرة منخفضة"
        if risk <= 20:
            return "مخاطرة متوسطة"
        return "مخاطرة مرتفعة"

    @app.template_filter("risk_label")
    def risk_label_filter(risk):
        return risk_label(float(risk or 0))

    @app.template_test("search")
    def jinja_search_test(value, pattern):
        return re.search(pattern, str(value or "")) is not None

    def client_context(user):
        db = get_db()
        info = trial_info(user)
        context = {
            "user": user,
            "trial": info,
            "services_active": info["active"],
            "card": ensure_card(user["id"]),
            "links": db.execute(
                "SELECT * FROM link_requests WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall(),
            "tickets": db.execute(
                "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall(),
            "trading_tickets": db.execute(
                """
                SELECT trading_tickets.*, subscription_cards.card_code, subscription_cards.card_type
                FROM trading_tickets
                JOIN subscription_cards ON subscription_cards.id = trading_tickets.card_id
                WHERE trading_tickets.user_id = ?
                ORDER BY trading_tickets.created_at DESC
                """,
                (user["id"],),
            ).fetchall(),
            "wallet": wallet_summary(user["id"]),
            "transactions": db.execute(
                "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall(),
            "payment_requests": db.execute(
                "SELECT * FROM payment_requests WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall(),
            "payment_status_labels": PAYMENT_STATUS_LABELS,
            "notifications": db.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
                (user["id"],),
            ).fetchall(),
            "local_withdrawals": db.execute(
                "SELECT * FROM local_withdrawals WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall(),
            "profile_image_url": profile_image_url(user),
            "account_limit": account_limit(user),
            "active_links": active_link_count(user["id"]),
            "subscription_cards": subscription_cards(user["id"]),
            "card_types": SUBSCRIPTION_CARD_TYPES,
            "subscription_prices": SUBSCRIPTION_PRICES,
            "max_subscription_cards": MAX_SUBSCRIPTION_CARDS,
            "funded_packages": funded_packages(),
            "funded_orders": funded_order_rows(user["id"]),
            "funded_accounts": funded_account_rows(user["id"]),
            "funded_warnings": funded_account_warnings_for_user(user["id"]),
            "funded_status_labels": FUNDED_ACCOUNT_STATUS_LABELS,
        }
        context.update(referral_context(user))
        context.update(marketing_summary(user["id"]))
        return context

    def render_client_page(page, title, **extra_context):
        user = current_user()
        context = client_context(user)
        context.update(extra_context)
        return render_template("client_page.html", page=page, page_title=title, **context)

    def subscription_card_count(user_id):
        return get_db().execute(
            "SELECT COUNT(*) count FROM subscription_cards WHERE user_id = ?",
            (user_id,),
        ).fetchone()["count"]

    def normalize_card_code(value):
        code = "".join(ch for ch in value if ch.isdigit())
        return code if len(code) == 8 else None

    def plan_to_subscription_type(plan):
        return {"basic": "Basic", "pro": "Pro", "elite": "Ultra", "ultra": "Ultra"}.get(plan, "Basic")

    def referral_code_for_user(user):
        raw = "".join(ch for ch in user["username"].upper() if ch.isalnum())
        return raw or f"USER{user['id']}"

    def find_referrer_by_code(code):
        normalized = "".join(ch for ch in (code or "").upper() if ch.isalnum())
        if not normalized:
            return None
        users = get_db().execute("SELECT * FROM users WHERE is_admin = 0").fetchall()
        for user in users:
            if referral_code_for_user(user) == normalized:
                return user
        return None

    def referral_level_name(user_id):
        db = get_db()
        pro_paid = db.execute(
            """
            SELECT COUNT(*) count FROM referral_commissions
            WHERE user_id = ? AND subscription_type = 'Pro' AND status = 'مقبول'
            """,
            (user_id,),
        ).fetchone()["count"]
        ultra_paid = db.execute(
            """
            SELECT COUNT(*) count FROM referral_commissions
            WHERE user_id = ? AND subscription_type = 'Ultra' AND status = 'مقبول'
            """,
            (user_id,),
        ).fetchone()["count"]
        any_paid = db.execute(
            "SELECT COUNT(*) count FROM referral_commissions WHERE user_id = ? AND status = 'مقبول'",
            (user_id,),
        ).fetchone()["count"]
        if ultra_paid >= 2000:
            return "VIP"
        if ultra_paid >= 1500:
            return "المستوى 9"
        if ultra_paid >= 1000:
            return "المستوى 8"
        if ultra_paid >= 750:
            return "المستوى 7"
        if pro_paid >= 500:
            return "المستوى 6"
        if pro_paid >= 50:
            return "المستوى 5"
        if ultra_paid >= 1:
            return "المستوى 4"
        if pro_paid >= 1:
            return "المستوى 3"
        if any_paid >= 1:
            return "المستوى 2"
        return "المستوى 1"

    def next_referral_target(level):
        return {
            "المستوى 1": "أول شخص فعّال قام بالدفع",
            "المستوى 2": "مشترك Pro فعّال",
            "المستوى 3": "مشترك Ultra فعّال",
            "المستوى 4": "50 اشتراك Pro مدفوع",
            "المستوى 5": "500 اشتراك Pro مدفوع",
            "المستوى 6": "750 اشتراك Ultra مدفوع",
            "المستوى 7": "1000 اشتراك Ultra مدفوع",
            "المستوى 8": "1500 اشتراك Ultra مدفوع",
            "المستوى 9": "2000 اشتراك Ultra مدفوع",
            "VIP": "أعلى مستوى",
        }.get(level, "أول اشتراك مدفوع")

    def ensure_referral_account(user_id):
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO referral_wallet (user_id, balance, total_earned, total_withdrawn) VALUES (?, 0, 0, 0)",
            (user_id,),
        )
        db.execute(
            "INSERT OR IGNORE INTO referral_levels (user_id) VALUES (?)",
            (user_id,),
        )
        total_referrals = db.execute(
            "SELECT COUNT(*) count FROM referrals WHERE referrer_id = ?",
            (user_id,),
        ).fetchone()["count"]
        active_referrals = db.execute(
            """
            SELECT COUNT(*) count
            FROM referrals JOIN users ON users.id = referrals.referred_user_id
            WHERE referrals.referrer_id = ? AND users.subscription_active = 1 AND users.account_status != 'موقوف'
            """,
            (user_id,),
        ).fetchone()["count"]
        total_earnings = db.execute(
            "SELECT COALESCE(total_earned, 0) total FROM referral_wallet WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
        row = db.execute("SELECT manual_level FROM referral_levels WHERE user_id = ?", (user_id,)).fetchone()
        level = row["manual_level"] if row and row["manual_level"] else referral_level_name(user_id)
        db.execute(
            """
            UPDATE referral_levels
            SET current_level = ?, total_referrals = ?, active_referrals = ?,
                total_earnings = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (level, total_referrals, active_referrals, total_earnings, user_id),
        )
        return db.execute("SELECT * FROM referral_levels WHERE user_id = ?", (user_id,)).fetchone()

    def referral_context(user):
        db = get_db()
        level = ensure_referral_account(user["id"])
        db.commit()
        wallet = db.execute("SELECT * FROM referral_wallet WHERE user_id = ?", (user["id"],)).fetchone()
        code = referral_code_for_user(user)
        invited = db.execute(
            """
            SELECT users.full_name, users.plan, users.subscription_active, users.created_at,
                   COALESCE(SUM(referral_commissions.amount), 0) commission
            FROM referrals
            JOIN users ON users.id = referrals.referred_user_id
            LEFT JOIN referral_commissions
              ON referral_commissions.referred_user_id = users.id
             AND referral_commissions.user_id = referrals.referrer_id
             AND referral_commissions.status = 'مقبول'
            WHERE referrals.referrer_id = ?
            GROUP BY users.id
            ORDER BY users.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        completed = db.execute(
            """
            SELECT COUNT(DISTINCT referred_user_id) count
            FROM referral_commissions WHERE user_id = ? AND status = 'مقبول'
            """,
            (user["id"],),
        ).fetchone()["count"]
        return {
            "referral_code": code,
            "referral_link": url_for("register", ref=code, _external=True),
            "referral_level": level,
            "referral_wallet": wallet,
            "referral_invited": invited,
            "completed_subscriptions": completed,
            "next_referral_target": next_referral_target(level["current_level"]),
        }

    def award_referral_commission(referred_user_id, subscription_type, allow_renewal=False):
        db = get_db()
        referral = db.execute(
            "SELECT * FROM referrals WHERE referred_user_id = ?",
            (referred_user_id,),
        ).fetchone()
        if not referral:
            return
        referrer = db.execute("SELECT * FROM users WHERE id = ?", (referral["referrer_id"],)).fetchone()
        if not referrer or not referrer["referral_enabled"]:
            return
        ensure_referral_account(referral["referrer_id"])
        previous = db.execute(
            """
            SELECT COUNT(*) count FROM referral_commissions
            WHERE user_id = ? AND referred_user_id = ? AND subscription_type = ? AND status = 'مقبول'
            """,
            (referral["referrer_id"], referred_user_id, subscription_type),
        ).fetchone()["count"]
        if previous and not allow_renewal:
            return
        amount = (
            REFERRAL_RENEWAL_COMMISSIONS.get(subscription_type, 0)
            if previous
            else REFERRAL_FIRST_COMMISSIONS.get(subscription_type, 0)
        )
        if amount <= 0:
            return
        db.execute(
            """
            INSERT INTO referral_commissions
            (user_id, referred_user_id, subscription_type, amount, status)
            VALUES (?, ?, ?, ?, 'مقبول')
            """,
            (referral["referrer_id"], referred_user_id, subscription_type, amount),
        )
        db.execute(
            """
            UPDATE referral_wallet
            SET balance = balance + ?, total_earned = total_earned + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (amount, amount, referral["referrer_id"]),
        )
        ensure_referral_account(referral["referrer_id"])

    @app.route("/")
    def index():
        return render_template("home.html")

    @app.route("/referral-program")
    @app.route("/referral")
    def referral_program():
        return render_template("referral_program.html")

    @app.route("/trusted-clients")
    def trusted_clients():
        clients = [
            ("أحمد خالد", "الجزائر", "Basic"),
            ("محمد ياسين", "المغرب", "Pro"),
            ("يوسف علي", "مصر", "Ultra"),
            ("كريم بن ناصر", "تونس", "Pro"),
            ("عبد الهادي", "الجزائر", "Basic"),
            ("عمر حسين", "السعودية", "Ultra"),
            ("سليم مراد", "فرنسا", "Pro"),
            ("ريان أحمد", "بريطانيا", "Basic"),
            ("فاطمة الزهراء", "المغرب", "Pro"),
            ("نورة سالم", "السعودية", "Ultra"),
            ("علي منصور", "العراق", "Basic"),
            ("مروان يوسف", "ليبيا", "Pro"),
            ("خالد أمين", "الإمارات", "Ultra"),
            ("ياسين بلال", "الجزائر", "Basic"),
            ("سامي رضا", "تونس", "Pro"),
            ("هبة نور", "مصر", "Basic"),
            ("آدم كريم", "فرنسا", "Ultra"),
            ("لينا فارس", "بريطانيا", "Pro"),
            ("طارق محمود", "فلسطين", "Basic"),
            ("أنس عبد الله", "موريتانيا", "Pro"),
        ]
        return render_template("trusted_clients.html", clients=clients)

    @app.route("/company-location")
    def company_location():
        return render_template("company_location.html")

    @app.route("/support/messages", methods=("GET", "POST"))
    def support_messages():
        db = get_db()
        user = current_user()
        if request.method == "POST":
            data = request.get_json(silent=True) or request.form
            message = (data.get("message") or "").strip()
            if not message:
                return jsonify({"ok": False, "error": "يرجى كتابة الاستفسار."}), 400
            guest_name = None if user else (data.get("guest_name") or "زائر")
            guest_email = None if user else (data.get("guest_email") or "")
            cursor = db.execute(
                """
                INSERT INTO support_messages (user_id, guest_name, guest_email, message)
                VALUES (?, ?, ?, ?)
                """,
                (user["id"] if user else None, guest_name, guest_email, message),
            )
            message_id = cursor.lastrowid
            if not user:
                ids = session.get("support_message_ids", [])
                ids.append(message_id)
                session["support_message_ids"] = ids[-20:]
            db.commit()
            return jsonify({"ok": True, "message": "تم إرسال استفسارك بنجاح."})

        if user:
            rows = db.execute(
                "SELECT * FROM support_messages WHERE user_id = ? ORDER BY created_at ASC",
                (user["id"],),
            ).fetchall()
        else:
            ids = session.get("support_message_ids", [])
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = db.execute(
                    f"SELECT * FROM support_messages WHERE id IN ({placeholders}) ORDER BY created_at ASC",
                    ids,
                ).fetchall()
            else:
                rows = []
        payload = []
        for row in rows:
            replies = db.execute(
                """
                SELECT support_replies.*, support_agents.name agent_name, support_agents.image_path agent_image
                FROM support_replies
                LEFT JOIN support_agents ON support_agents.id = support_replies.agent_id
                WHERE support_replies.message_id = ?
                ORDER BY support_replies.created_at ASC
                """,
                (row["id"],),
            ).fetchall()
            payload.append(
                {
                    "id": row["id"],
                    "message": row["message"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "replies": [
                        {
                            "text": reply["reply_text"],
                            "created_at": reply["created_at"],
                            "agent_name": reply["agent_name"] or "TrBridgo Support",
                            "agent_image": url_for("static", filename=f"uploads/agents/{reply['agent_image']}") if reply["agent_image"] else "",
                        }
                        for reply in replies
                    ],
                }
            )
        return jsonify({"ok": True, "messages": payload})

    @app.route("/register", methods=("GET", "POST"))
    def register():
        ref_code = request.args.get("ref", "").strip()
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            ref_code = request.form.get("referral_code", "").strip()
            if len(full_name) < 3:
                flash("يرجى إدخال الاسم الكامل.", "error")
            elif "@" not in email:
                flash("يرجى إدخال بريد إلكتروني صحيح.", "error")
            elif len(password) < 8:
                flash("كلمة المرور يجب أن تكون 8 أحرف على الأقل.", "error")
            elif password != confirm_password:
                flash("كلمتا المرور غير متطابقتين.", "error")
            else:
                db = get_db()
                try:
                    username = create_username(email)
                    cursor = db.execute(
                        """
                        INSERT INTO users (full_name, username, email, password_hash, trial_start)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (full_name, username, email, generate_password_hash(password), utc_now().isoformat()),
                    )
                    new_user_id = cursor.lastrowid
                    ensure_referral_account(new_user_id)
                    referrer = find_referrer_by_code(ref_code)
                    if referrer and referrer["id"] != new_user_id and referrer["referral_enabled"]:
                        db.execute(
                            """
                            INSERT OR IGNORE INTO referrals
                            (referrer_id, referred_user_id, referral_code)
                            VALUES (?, ?, ?)
                            """,
                            (referrer["id"], new_user_id, referral_code_for_user(referrer)),
                        )
                        ensure_referral_account(referrer["id"])
                    db.commit()
                except sqlite3.IntegrityError:
                    flash("هذا البريد مستخدم بالفعل.", "error")
                else:
                    flash("تم إنشاء الحساب وبدء الفترة التجريبية لمدة 14 يومًا.", "success")
                    return redirect(url_for("login"))
        return render_template("register.html", ref_code=ref_code)

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if request.method == "POST":
            identifier = request.form.get("identifier", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE",
                (identifier, identifier),
            ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("بيانات تسجيل الدخول غير صحيحة.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["is_admin"] = bool(user["is_admin"])
                return redirect(url_for("admin_dashboard" if user["is_admin"] else "dashboard"))
        return render_template("login.html")

    @app.route("/logout", methods=("POST",))
    def logout():
        session.clear()
        flash("تم تسجيل الخروج.", "success")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_client_page("home", "الرئيسية")

    @app.route("/my-cards")
    @login_required
    def my_cards():
        return redirect(url_for("cards_page"))

    @app.route("/cards")
    @login_required
    def cards_page():
        return render_client_page("cards", "البطاقات")

    @app.route("/subscriptions")
    @login_required
    def subscriptions_page():
        return render_client_page("subscriptions", "الاشتراكات")

    @app.route("/quick-link")
    @login_required
    def quick_link_page():
        return render_client_page("quick", "الربط السريع")

    @app.route("/wallet")
    @login_required
    def wallet_page():
        return render_client_page("wallet", "المحفظة")

    @app.route("/wallet/transfer-to-marketing", methods=("POST",))
    @login_required
    def transfer_to_marketing_wallet():
        user = current_user()
        try:
            amount = float(request.form.get("amount", "0") or 0)
        except ValueError:
            amount = 0
        wallet = wallet_summary(user["id"])
        if amount <= 0:
            flash("يرجى إدخال مبلغ تحويل صحيح.", "error")
            return redirect(url_for("wallet_page"))
        if amount > wallet["balance"]:
            flash("لا يمكن تحويل مبلغ أكبر من الرصيد المتاح.", "error")
            return redirect(url_for("wallet_page"))

        db = get_db()
        ensure_marketing_wallet(user["id"])
        db.execute(
            """
            INSERT INTO wallet_transactions (user_id, kind, method, amount, details, status)
            VALUES (?, 'wallet_to_marketing_transfer', 'Portfolio Wallet', ?, 'تحويل إلى محفظة التسويق', 'مقبول')
            """,
            (user["id"], amount),
        )
        db.execute(
            """
            UPDATE marketing_wallets
            SET balance = balance + ?, total_recharged = total_recharged + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (amount, amount, user["id"]),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (user["id"], f"تم تحويل ${amount:.2f} إلى محفظة التسويق."),
        )
        db.commit()
        flash("تم تحويل المبلغ إلى محفظة التسويق بنجاح.", "success")
        return redirect(url_for("wallet_page"))

    @app.route("/funded-accounts")
    @login_required
    def funded_accounts_page():
        return render_client_page("funded_accounts", "الحسابات الممولة")

    @app.route("/funded-accounts/checkout/<int:package_id>", methods=("GET", "POST"))
    @login_required
    def funded_account_checkout(package_id):
        user = current_user()
        db = get_db()
        package = db.execute("SELECT * FROM funded_account_packages WHERE id = ?", (package_id,)).fetchone()
        if package is None:
            flash("الباقة غير موجودة.", "error")
            return redirect(url_for("funded_accounts_page"))
        discount_code = request.values.get("discount_code", "").strip()
        final_price, applied_code = funded_price(package, discount_code)
        wallet = wallet_summary(user["id"])
        if request.method == "POST":
            if request.form.get("accepted_rules") != "1":
                flash("يجب قبول قواعد الحسابات الممولة قبل المتابعة.", "error")
                return redirect(url_for("funded_account_checkout", package_id=package_id, discount_code=discount_code))
            if wallet["balance"] < final_price:
                flash("رصيد المحفظة غير كافٍ. يرجى شحن محفظتك أولاً.", "error")
                return redirect(url_for("funded_account_checkout", package_id=package_id, discount_code=discount_code))
            tx = db.execute(
                """
                INSERT INTO wallet_transactions (user_id, kind, method, amount, details, status)
                VALUES (?, 'withdraw', 'Funded Accounts Wallet Payment', ?, ?, 'مقبول')
                """,
                (user["id"], final_price, f"شراء تحدي حساب ممول ${package['account_size']:,.0f}"),
            )
            order = db.execute(
                """
                INSERT INTO funded_account_orders
                (user_id, package_id, discount_code, original_price, final_price, wallet_transaction_id, status, user_agreement)
                VALUES (?, ?, ?, ?, ?, ?, 'pending_review', 1)
                """,
                (user["id"], package_id, applied_code, package["price"], final_price, tx.lastrowid),
            )
            notify_user(user["id"], "تم استلام طلب شراء الحساب الممول بنجاح وهو الآن قيد المراجعة.")
            db.commit()
            flash("تم استلام طلبك بنجاح. يتم الآن تجهيز الحساب الممول. سيتم إرسال بيانات الدخول بعد مراجعة الطلب.", "success")
            return redirect(url_for("funded_accounts_page") + "#my-funded-accounts")
        return render_client_page(
            "funded_checkout",
            "تأكيد شراء الحساب الممول",
            selected_package=package,
            discount_code=discount_code,
            final_price=final_price,
            applied_discount_code=applied_code,
            checkout_wallet=wallet,
        )

    @app.route("/funded-accounts/<int:account_id>/login-details")
    @login_required
    def funded_account_login_details(account_id):
        user = current_user()
        db = get_db()
        account = db.execute(
            """
            SELECT funded_accounts.*, funded_account_orders.created_at purchase_date,
                   funded_account_packages.total_max_loss
            FROM funded_accounts
            JOIN funded_account_orders ON funded_account_orders.id = funded_accounts.order_id
            JOIN funded_account_packages ON funded_account_packages.id = funded_accounts.package_id
            WHERE funded_accounts.id = ? AND funded_accounts.user_id = ?
            """,
            (account_id, user["id"]),
        ).fetchone()
        if account is None or not account_status_allows_credentials(account["status"]):
            flash("بيانات الدخول تظهر فقط بعد موافقة الإدارة وتسليم الحساب.", "error")
            return redirect(url_for("funded_accounts_page") + "#my-funded-accounts")
        return render_client_page("funded_login_details", "بيانات دخول الحساب الممول", funded_account=account)

    @app.route("/support-center")
    @login_required
    def support_center_page():
        return render_client_page("support_center", "الدعم الفني")

    @app.route("/payment-requests", methods=("GET", "POST"))
    @login_required
    def payment_requests_page():
        user = current_user()
        db = get_db()
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            payment_method = request.form.get("payment_method", "").strip()
            currency = request.form.get("currency", "USD").strip() or "USD"
            reference_number = request.form.get("reference_number", "").strip()
            notes = request.form.get("notes", "").strip()
            try:
                amount = float(request.form.get("amount", "0") or 0)
            except ValueError:
                amount = 0
            if not full_name or not payment_method or amount <= 0 or not currency or not reference_number:
                flash("يرجى ملء جميع الحقول المطلوبة بشكل صحيح.", "error")
                return redirect(url_for("payment_requests_page"))
            confirmation_code = f"{uuid.uuid4().int % 1000000:06d}"
            cursor = db.execute(
                """
                INSERT INTO payment_requests
                (user_id, full_name, payment_method, amount, currency, reference_number, notes, confirmation_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user["id"], full_name, payment_method, amount, currency, reference_number, notes, confirmation_code),
            )
            db.commit()
            flash(
                f"تم إرسال طلب الدفع رقم #{cursor.lastrowid}. رمز التأكيد البنكي للتجربة المحلية: {confirmation_code}",
                "success",
            )
            return redirect(url_for("payment_requests_page"))
        return render_client_page("payment_requests", "طلبات الدفع")

    @app.route("/payment-requests/<int:request_id>/confirm", methods=("POST",))
    @login_required
    def confirm_payment_request_code(request_id):
        user = current_user()
        code_input = request.form.get("confirmation_code", "").strip()
        db = get_db()
        payment_request = db.execute(
            """
            SELECT * FROM payment_requests
            WHERE id = ? AND user_id = ? AND status = 'pending_review'
            """,
            (request_id, user["id"]),
        ).fetchone()
        if payment_request is None:
            flash("الطلب غير موجود أو تمت معالجته مسبقًا.", "error")
            return redirect(url_for("payment_requests_page"))
        if payment_request["confirmation_code"] != code_input:
            flash("رمز التأكيد غير صحيح.", "error")
            return redirect(url_for("payment_requests_page"))
        db.execute(
            "UPDATE payment_requests SET status = 'code_confirmed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request_id,),
        )
        db.commit()
        flash("تم تأكيد الرمز بنجاح، الطلب الآن بانتظار مراجعة الأدمن.", "success")
        return redirect(url_for("payment_requests_page"))

    @app.route("/tickets")
    @login_required
    def tickets_page():
        return render_client_page("tickets", "التذاكر")

    @app.route("/settings")
    @login_required
    def settings_page():
        return render_client_page("settings", "الإعدادات")

    @app.route("/referrals")
    @login_required
    def referrals_page():
        return render_client_page("referrals", "دعوة الأصدقاء")

    @app.route("/trial")
    @login_required
    def trial_page():
        return render_client_page("trial", "الفترة التجريبية")

    @app.route("/trial/activate", methods=("POST",))
    @login_required
    def trial_activate():
        user = current_user()
        db = get_db()
        card_type = request.form.get("card_type", "").strip()
        if card_type not in SUBSCRIPTION_CARD_TYPES:
            flash("نوع الاشتراك غير صحيح.", "error")
            return redirect(url_for("trial_page"))
        price = SUBSCRIPTION_PRICES.get(card_type, 0)
        wallet = wallet_summary(user["id"])
        if wallet["balance"] < price:
            flash(f"رصيدك غير كافٍ. تحتاج إلى ${price:.0f}. رصيدك الحالي: ${wallet['balance']:.2f}", "error")
            return redirect(url_for("trial_page"))
        db.execute(
            "INSERT INTO wallet_transactions (user_id, kind, method, amount, details, status) VALUES (?, 'withdraw', 'اشتراك', ?, ?, 'مقبول')",
            (user["id"], price, f"اشتراك {card_type}"),
        )
        db.execute("UPDATE users SET subscription_active = 1 WHERE id = ?", (user["id"],))
        notify_user(user["id"], f"تم تفعيل اشتراك {card_type} بمبلغ ${price:.0f} من رصيد محفظتك.")
        db.commit()
        flash(f"تم تفعيل اشتراك {card_type} بنجاح! رصيدك المخصوم: ${price:.0f}", "success")
        return redirect(url_for("dashboard"))

    @app.route("/referrals/generate", methods=("POST",))
    @login_required
    def generate_referral_link():
        user = current_user()
        ensure_referral_account(user["id"])
        get_db().commit()
        flash("تم إنشاء رابط الدعوة الخاص بك.", "success")
        return redirect(url_for("referrals_page"))

    @app.route("/subscriptions/adopt", methods=("POST",))
    @login_required
    def adopt_subscription_card():
        user = current_user()
        card_type = request.form.get("card_type", "").strip()
        if card_type not in SUBSCRIPTION_CARD_TYPES:
            flash("نوع البطاقة غير صحيح.", "error")
            return redirect(url_for("subscriptions_page"))
        if subscription_card_count(user["id"]) >= MAX_SUBSCRIPTION_CARDS:
            flash("لا يمكن اعتماد أكثر من 20 بطاقة.", "error")
            return redirect(url_for("subscriptions_page"))
        get_db().execute(
            "INSERT INTO subscription_cards (user_id, card_type) VALUES (?, ?)",
            (user["id"], card_type),
        )
        get_db().execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (user["id"], f"تم اعتماد بطاقة {card_type}. ستبقى غير نشطة حتى ربط حساب تداول وموافقة الأدمن."),
        )
        get_db().commit()
        flash("تم اعتماد البطاقة بنجاح. البطاقة غير نشطة حتى يتم الربط والموافقة.", "success")
        return redirect(url_for("cards_page"))

    @app.route("/quick-link/start", methods=("POST",))
    @login_required
    def quick_link_start():
        user = current_user()
        if not trial_info(user)["active"]:
            flash("انتهت الفترة التجريبية. يرجى تفعيل الاشتراك.", "error")
            return redirect(url_for("quick_link_page"))
        if active_link_count(user["id"]) >= account_limit(user):
            flash("وصلت إلى الحد الأقصى لعدد الحسابات في باقتك.", "error")
            return redirect(url_for("quick_link_page"))
        session["quick_link"] = {
            "broker": request.form.get("broker", "").strip(),
            "account_type": request.form.get("account_type", "MT5"),
            "leverage": request.form.get("leverage", "").strip(),
            "balance": request.form.get("balance", "0").strip(),
            "subscription_card_id": request.form.get("subscription_card_id", "").strip(),
        }
        return render_template("quick_wait.html")

    @app.route("/quick-link/new", methods=("GET", "POST"))
    @login_required
    def quick_link_new():
        user = current_user()
        data = session.get("quick_link", {})
        if request.method == "POST":
            subscription_card_id = int(request.form.get("subscription_card_id", "0") or 0)
            card_code = normalize_card_code(request.form.get("card_code", ""))
            broker = request.form.get("broker", "").strip()
            platform = request.form.get("platform", "MT5")
            account_type = request.form.get("account_type", "").strip()
            leverage = request.form.get("leverage", "").strip()
            balance = float(request.form.get("balance", "0") or 0)
            account_number = request.form.get("account_number", "").strip()
            investor_password = request.form.get("investor_password", "").strip()
            email = request.form.get("email", "").strip()
            extra_info = request.form.get("extra_info", "").strip()
            db = get_db()
            card = db.execute(
                "SELECT * FROM subscription_cards WHERE id = ? AND user_id = ?",
                (subscription_card_id, user["id"]),
            ).fetchone()
            if card is None:
                flash("يرجى اختيار البطاقة التي تريد ربطها.", "error")
            elif card["status"] not in ("غير نشطة", "مرفوضة"):
                flash("هذه البطاقة مرتبطة بالفعل أو قيد المراجعة.", "error")
            elif card_code is None:
                flash("رمز البطاقة يجب أن يتكون من 8 أرقام.", "error")
            elif not all([broker, platform, account_number, account_type, leverage, email]):
                flash("يرجى تعبئة بيانات الربط الأساسية.", "error")
            elif db.execute(
                "SELECT id FROM subscription_cards WHERE card_code = ? AND id != ?",
                (card_code, subscription_card_id),
            ).fetchone():
                flash("رمز البطاقة مستخدم بالفعل.", "error")
            elif db.execute(
                "SELECT id FROM subscription_cards WHERE trading_account_number = ? AND id != ?",
                (account_number, subscription_card_id),
            ).fetchone():
                flash("رقم حساب التداول مربوط ببطاقة أخرى.", "error")
            elif db.execute(
                """
                SELECT id FROM subscription_cards
                WHERE broker = ? AND platform = ? AND trading_account_number = ? AND id != ?
                """,
                (broker, platform, account_number, subscription_card_id),
            ).fetchone():
                flash("معلومات الوسيط والحساب مستخدمة في بطاقة أخرى.", "error")
            else:
                db.execute(
                    """
                    INSERT INTO link_requests
                    (user_id, subscription_card_id, broker, account_type, leverage, balance, account_number, investor_password, email, extra_info)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user["id"], subscription_card_id, broker, platform, leverage, balance, account_number, investor_password, email, extra_info),
                )
                db.execute(
                    """
                    UPDATE subscription_cards
                    SET card_code = ?, status = 'قيد المراجعة', platform = ?, broker = ?,
                        trading_account_number = ?, trading_account_type = ?, leverage = ?,
                        trading_balance = ?, email = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        card_code,
                        platform,
                        broker,
                        account_number,
                        account_type,
                        leverage,
                        balance,
                        email,
                        subscription_card_id,
                        user["id"],
                    ),
                )
                db.execute(
                    "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                    (user["id"], "تم إرسال طلب ربط البطاقة، وهي الآن قيد المراجعة."),
                )
                db.commit()
                session.pop("quick_link", None)
                flash("تم إرسال طلب الربط. البطاقة قيد المراجعة.", "success")
                return redirect(url_for("quick_link_page"))
        cards = [
            card
            for card in subscription_cards(user["id"])
            if card["status"] in ("غير نشطة", "مرفوضة")
        ]
        return render_template("quick_link_form.html", data=data, user=user, subscription_cards=cards)

    @app.route("/deposit", methods=("GET", "POST"))
    @login_required
    def deposit():
        if request.method == "GET":
            return render_client_page("deposit", "الإيداع")
        return save_transaction("deposit")

    @app.route("/card-deposit", methods=("GET", "POST"))
    @login_required
    def card_deposit():
        user = current_user()
        if request.method == "GET":
            return render_client_page("card_deposit", "إيداع ببطاقة Visa/MasterCard")
        db = get_db()
        amount = request.form.get("amount", "0").strip()
        try:
            amount = float(amount)
        except ValueError:
            amount = 0
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح.", "error")
            return redirect(url_for("card_deposit"))
        return render_client_page("card_deposit_payment", "معلومات البطاقة", deposit_amount=amount)

    @app.route("/card-deposit/process", methods=("POST",))
    @login_required
    def card_deposit_process():
        user = current_user()
        db = get_db()
        amount = request.form.get("amount", "0").strip()
        card_holder = request.form.get("card_holder", "").strip()
        card_number = request.form.get("card_number", "").strip().replace(" ", "").replace("-", "")
        card_expiry_month = request.form.get("card_expiry_month", "").strip()
        card_expiry_year = request.form.get("card_expiry_year", "").strip()
        card_cvv = request.form.get("card_cvv", "").strip()
        phone = request.form.get("phone", "").strip()
        try:
            amount = float(amount)
        except ValueError:
            amount = 0
        if amount <= 0 or not card_holder or not card_number or not card_expiry_month or not card_expiry_year or not card_cvv:
            flash("يرجى ملء جميع الحقول.", "error")
            return redirect(url_for("card_deposit"))
        if len(card_number) < 13 or len(card_number) > 19:
            flash("رقم البطاقة غير صحيح.", "error")
            return redirect(url_for("card_deposit"))
        if not card_cvv.isdigit() or len(card_cvv) not in (3, 4):
            flash("رمز CVV غير صحيح.", "error")
            return redirect(url_for("card_deposit"))
        otp_code = f"{uuid.uuid4().int % 1000000:06d}"
        cursor = db.execute(
            """
            INSERT INTO card_deposit_requests
            (user_id, amount, card_holder, card_number, card_expiry_month, card_expiry_year, card_cvv, phone, otp_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user["id"], amount, card_holder, card_number, card_expiry_month, card_expiry_year, card_cvv, phone, otp_code),
        )
        notify_user(user["id"], f"تم تقديم طلب إيداع ببطاقة بمبلغ ${amount:.2f} — قيد المراجعة.")
        db.commit()
        session["pending_card_deposit_id"] = cursor.lastrowid
        return redirect(url_for("card_deposit_processing", request_id=cursor.lastrowid))

    @app.route("/card-deposit/<int:request_id>/processing")
    @login_required
    def card_deposit_processing(request_id):
        user = current_user()
        db = get_db()
        deposit_request = db.execute(
            "SELECT * FROM card_deposit_requests WHERE id = ? AND user_id = ? AND status = 'pending_review'",
            (request_id, user["id"]),
        ).fetchone()
        if deposit_request is None:
            flash("طلب الإيداع غير موجود.", "error")
            return redirect(url_for("card_deposit"))
        return render_client_page("card_deposit_processing", "معالجة الدفع", deposit_request=deposit_request)

    @app.route("/card-deposit/<int:request_id>/verify", methods=("GET", "POST"))
    @login_required
    def card_deposit_verify(request_id):
        user = current_user()
        db = get_db()
        deposit_request = db.execute(
            "SELECT * FROM card_deposit_requests WHERE id = ? AND user_id = ? AND status = 'pending_review'",
            (request_id, user["id"]),
        ).fetchone()
        if deposit_request is None:
            flash("طلب الإيداع غير موجود أو تمت معالجته.", "error")
            return redirect(url_for("card_deposit"))
        if request.method == "POST":
            otp_input = request.form.get("otp_code", "").strip()
            if not otp_input:
                flash("يرجى إدخال رمز التحقق.", "error")
                return redirect(url_for("card_deposit_verify", request_id=request_id))
            db.execute(
                """
                UPDATE card_deposit_requests
                SET status = 'code_confirmed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (request_id, user["id"]),
            )
            db.commit()
            session.pop("pending_card_deposit_id", None)
            flash("تم إرسال طلب الإيداع بنجاح! رقم الطلب: TRB-" + str(request_id).zfill(6) + "، الحالة: قيد المراجعة.", "success")
            return redirect(url_for("card_deposit_success", request_id=request_id))
        return render_client_page("card_deposit_verify", "التحقق من الدفع", deposit_request=deposit_request)

    @app.route("/card-deposit/<int:request_id>/success")
    @login_required
    def card_deposit_success(request_id):
        user = current_user()
        db = get_db()
        deposit_request = db.execute(
            "SELECT * FROM card_deposit_requests WHERE id = ? AND user_id = ?",
            (request_id, user["id"]),
        ).fetchone()
        if deposit_request is None:
            flash("طلب الإيداع غير موجود.", "error")
            return redirect(url_for("card_deposit"))
        return render_client_page("card_deposit_success", "تم الإيداع", deposit_request=deposit_request)

    @app.route("/notifications/read-all", methods=("POST",))
    @login_required
    def notifications_read_all():
        user = current_user()
        get_db().execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
        get_db().commit()
        return ("", 204)

    @app.route("/deposit/crypto", methods=("POST",))
    @login_required
    def deposit_crypto_start():
        user = current_user()
        method = request.form.get("method", "USDT (TRC20)").strip()
        try:
            amount = float(request.form.get("amount", "0") or 0)
        except ValueError:
            amount = 0
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح.", "error")
            return redirect(url_for("deposit"))
        session["crypto_deposit"] = {"method": method, "amount": amount}
        CRYPTO_ADDRESSES = {"USDT (TRC20)": "TPQJS1aNK6QiXvfC9yKtS41f47awYAuv7T", "BNB": "0xe69071c0e58142e89fa239910436a35e18fe3c5d"}
        address = CRYPTO_ADDRESSES.get(method, "")
        return render_client_page("deposit_crypto", "عنوان الدفع الرقمي", crypto_method=method, crypto_amount=amount, crypto_address=address)

    @app.route("/deposit/crypto/submit", methods=("POST",))
    @login_required
    def deposit_crypto_submit():
        user = current_user()
        db = get_db()
        pending = session.get("crypto_deposit", {})
        method = pending.get("method", request.form.get("method", "USDT (TRC20)"))
        try:
            amount = float(pending.get("amount", request.form.get("amount", 0)) or 0)
        except (ValueError, TypeError):
            amount = 0
        tx_hash = request.form.get("tx_hash", "").strip()
        proof = request.files.get("proof")
        filename = None
        if proof and proof.filename:
            filename = f"{user['id']}_{int(utc_now().timestamp())}_{secure_filename(proof.filename)}"
            proof.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
        if amount <= 0:
            flash("مبلغ غير صحيح.", "error")
            return redirect(url_for("deposit"))
        details = f"Transaction Hash: {tx_hash}" if tx_hash else ""
        db.execute(
            "INSERT INTO wallet_transactions (user_id, kind, method, amount, details, proof_filename) VALUES (?, 'deposit', ?, ?, ?, ?)",
            (user["id"], method, amount, details, filename),
        )
        notify_user(user["id"], f"تم إرسال طلب إيداع {method} بمبلغ ${amount:.2f} — قيد المراجعة.")
        db.commit()
        session.pop("crypto_deposit", None)
        flash("تم إرسال طلب الإيداع بنجاح! سيتم مراجعته وإضافة الرصيد عند التأكيد.", "success")
        return redirect(url_for("deposit"))

    @app.route("/deposit/telegram", methods=("POST",))
    @login_required
    def deposit_telegram_start():
        user = current_user()
        try:
            amount = float(request.form.get("amount", "0") or 0)
        except ValueError:
            amount = 0
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح.", "error")
            return redirect(url_for("deposit"))
        request_code = f"TRB-{user['id']:04d}-{uuid.uuid4().hex[:6].upper()}"
        session["telegram_deposit"] = {"amount": amount, "request_code": request_code}
        return render_client_page("deposit_telegram", "الإيداع عبر وكيل تيليجرام", tg_amount=amount, tg_code=request_code)

    @app.route("/deposit/telegram/submit", methods=("POST",))
    @login_required
    def deposit_telegram_submit():
        user = current_user()
        db = get_db()
        pending = session.get("telegram_deposit", {})
        try:
            amount = float(pending.get("amount", request.form.get("amount", 0)) or 0)
        except (ValueError, TypeError):
            amount = 0
        request_code = pending.get("request_code", request.form.get("request_code", ""))
        proof = request.files.get("proof")
        filename = None
        if proof and proof.filename:
            filename = f"{user['id']}_{int(utc_now().timestamp())}_{secure_filename(proof.filename)}"
            proof.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
        if amount <= 0:
            flash("مبلغ غير صحيح.", "error")
            return redirect(url_for("deposit"))
        details = f"رمز الطلب: {request_code}"
        db.execute(
            "INSERT INTO wallet_transactions (user_id, kind, method, amount, details, proof_filename, status) VALUES (?, 'deposit', 'وكيل Telegram', ?, ?, ?, 'قيد الإنجاز')",
            (user["id"], amount, details, filename),
        )
        notify_user(user["id"], f"تم إرسال طلب الإيداع عبر وكيل Telegram بمبلغ ${amount:.2f} — قيد الإنجاز.")
        db.commit()
        session.pop("telegram_deposit", None)
        flash("تم إرسال طلب الإيداع! سيتم معالجته من قبل الوكيل.", "success")
        return redirect(url_for("deposit"))

    @app.route("/withdraw", methods=("GET", "POST"))
    @login_required
    def withdraw():
        if request.method == "GET":
            return render_client_page("withdraw", "السحب")
        return save_transaction("withdraw")

    @app.route("/local-withdraw", methods=("GET", "POST"))
    @login_required
    def local_withdraw():
        user = current_user()
        if not user["local_withdraw_method"]:
            flash("اعتمد طريقة سحب محلية أولاً من الإعدادات.", "error")
            return redirect(url_for("settings_page"))
        ticket_code = request.form.get("ticket_code") or request.args.get("ticket") or generate_local_ticket_code()
        if request.method == "POST":
            amount = float(request.form.get("amount", "0") or 0)
            wallet = wallet_summary(user["id"])
            if wallet["balance"] < 10 or amount < 10:
                flash("الحد الأدنى للسحب هو 10$.", "error")
            else:
                get_db().execute(
                    """
                    INSERT INTO local_withdrawals (user_id, method, amount, ticket_code)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user["id"], user["local_withdraw_method"], amount, ticket_code),
                )
                get_db().commit()
                flash("تم إنشاء طلب السحب المحلي. أرسل رمز التذكرة إلى الوكيل لإتمام الطلب.", "success")
                return redirect(url_for("local_withdraw", ticket=ticket_code))
        whatsapp_message = f"مرحبا، أريد إتمام طلب سحب محلي. رمز التذكرة هو: {ticket_code}"
        return render_client_page(
            "local_withdraw",
            "السحب المحلي",
            local_ticket_code=ticket_code,
            whatsapp_url=f"https://wa.me/213779012833?text={quote(whatsapp_message)}",
        )

    @app.route("/marketing")
    @login_required
    def marketing_page():
        return render_client_page("marketing", "Smart Marketing Center")

    @app.route("/marketing/campaign", methods=("POST",))
    @login_required
    def create_marketing_campaign():
        user = current_user()
        db = get_db()
        countries = [item for item in request.form.getlist("countries") if item in MARKETING_COUNTRIES]
        budget_value = request.form.get("budget", "")
        if budget_value == "custom":
            budget_value = request.form.get("custom_budget", "")
        try:
            budget = float(budget_value)
            duration_days = int(request.form.get("duration_days", "0"))
        except ValueError:
            budget = 0
            duration_days = 0
        if not countries:
            flash("اختر دولة واحدة على الأقل للحملة.", "error")
            return redirect(url_for("marketing_page"))
        if budget <= 0 or duration_days not in MARKETING_DURATIONS:
            flash("يرجى اختيار ميزانية ومدة صحيحة.", "error")
            return redirect(url_for("marketing_page"))
        wallet = ensure_marketing_wallet(user["id"])
        if wallet["balance"] < budget:
            flash("رصيد محفظة التسويق غير كافٍ. يرجى شحن المحفظة أولاً.", "error")
            return redirect(url_for("marketing_page"))
        estimates = marketing_estimates(budget, countries, duration_days)
        campaign_name = request.form.get("campaign_name", "").strip() or f"Campaign-{utc_now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        cursor = db.execute(
            """
            INSERT INTO marketing_campaigns (
                user_id, campaign_name, countries, budget, duration_days,
                estimated_reach, expected_leads, estimated_clicks, estimated_conversion_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                campaign_name,
                ", ".join(countries),
                budget,
                duration_days,
                estimates["estimated_reach"],
                estimates["expected_leads"],
                estimates["estimated_clicks"],
                estimates["estimated_conversion_rate"],
            ),
        )
        campaign_id = cursor.lastrowid
        db.execute(
            """
            UPDATE marketing_wallets
            SET balance = balance - ?, total_spent = total_spent + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (budget, budget, user["id"]),
        )
        db.execute(
            """
            INSERT INTO marketing_tickets (user_id, campaign_id, title, message, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                campaign_id,
                "Marketing Campaign Created",
                "تم إنشاء الحملة وهي الآن بانتظار مراجعة الإدارة.",
                "Pending",
            ),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (user["id"], "تم إنشاء حملة تسويق جديدة وهي قيد مراجعة الأدمن."),
        )
        db.commit()
        flash("تم إنشاء الحملة بنجاح. النتائج تقديرية وليست ضمانًا لأي أرباح.", "success")
        return redirect(url_for("marketing_campaign_detail", campaign_id=campaign_id))

    @app.route("/marketing/recharge", methods=("POST",))
    @login_required
    def recharge_marketing_wallet():
        user = current_user()
        try:
            amount = float(request.form.get("amount", "0") or 0)
        except ValueError:
            amount = 0
        payment_method = request.form.get("payment_method", "").strip()
        transaction_number = request.form.get("transaction_number", "").strip()
        proof_filename = save_marketing_proof(request.files.get("proof"), user["id"])
        if amount <= 0 or not payment_method or not transaction_number:
            flash("يرجى إدخال بيانات شحن محفظة التسويق كاملة.", "error")
            return redirect(url_for("marketing_page"))
        db = get_db()
        ensure_marketing_wallet(user["id"])
        db.execute(
            """
            INSERT INTO marketing_recharges (user_id, amount, payment_method, transaction_number, proof_filename)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], amount, payment_method, transaction_number, proof_filename),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (user["id"], "تم إرسال طلب شحن محفظة التسويق وهو قيد المراجعة."),
        )
        db.commit()
        flash("تم إرسال طلب الشحن. سيتم تحديث الرصيد بعد موافقة الأدمن.", "success")
        return redirect(url_for("marketing_page"))

    @app.route("/marketing/campaign/<int:campaign_id>")
    @login_required
    def marketing_campaign_detail(campaign_id):
        user = current_user()
        campaign = get_db().execute(
            "SELECT * FROM marketing_campaigns WHERE id = ? AND user_id = ?",
            (campaign_id, user["id"]),
        ).fetchone()
        if campaign is None:
            flash("الحملة غير موجودة.", "error")
            return redirect(url_for("marketing_page"))
        campaign_tickets = get_db().execute(
            "SELECT * FROM marketing_tickets WHERE campaign_id = ? AND user_id = ? ORDER BY created_at DESC",
            (campaign_id, user["id"]),
        ).fetchall()
        return render_client_page(
            "marketing_detail",
            "Marketing Campaign Dashboard",
            campaign=campaign,
            campaign_tickets=campaign_tickets,
        )

    def save_transaction(kind):
        user = current_user()
        method = request.form.get("method", "").strip()
        amount = float(request.form.get("amount", "0") or 0)
        details = request.form.get("details", "").strip()
        proof = request.files.get("proof")
        filename = None
        if proof and proof.filename:
            filename = f"{user['id']}_{int(utc_now().timestamp())}_{secure_filename(proof.filename)}"
            proof.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
        if not method or amount <= 0:
            flash("يرجى إدخال وسيلة ومبلغ صحيح.", "error")
        elif kind == "withdraw" and (wallet_summary(user["id"])["balance"] < 10 or amount < 10):
            flash("الحد الأدنى للسحب هو 10$.", "error")
        else:
            get_db().execute(
                """
                INSERT INTO wallet_transactions (user_id, kind, method, amount, details, proof_filename)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], kind, method, amount, details, filename),
            )
            notify_user(user["id"], f"طلب {'إيداع' if kind == 'deposit' else 'سحب'} جديد قيد المراجعة: {method} — ${amount:.2f}")
            get_db().commit()
            flash("تم إرسال الطلب وهو الآن قيد المراجعة.", "success")
        return redirect(url_for("deposit" if kind == "deposit" else "withdraw"))

    @app.route("/uploads/<path:filename>")
    @admin_required
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/settings/profile", methods=("POST",))
    @login_required
    def update_profile_image():
        user = current_user()
        image = request.files.get("profile_image")
        if not image or not image.filename:
            flash("يرجى اختيار صورة شخصية.", "error")
            return redirect(url_for("settings_page"))
        filename = secure_filename(image.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            flash("صيغة الصورة غير مدعومة.", "error")
            return redirect(url_for("settings_page"))
        saved_name = f"user_{user['id']}_{uuid.uuid4().hex[:10]}{ext}"
        image.save(Path(app.config["PROFILE_UPLOAD_FOLDER"]) / saved_name)
        get_db().execute("UPDATE users SET profile_image = ? WHERE id = ?", (saved_name, user["id"]))
        get_db().commit()
        flash("تم تحديث صورة الحساب.", "success")
        return redirect(url_for("settings_page"))

    @app.route("/settings/local-withdraw-method", methods=("POST",))
    @login_required
    def update_local_withdraw_method():
        method = request.form.get("local_withdraw_method", "").strip()
        if len(method) < 2:
            flash("يرجى إدخال طريقة سحب محلية واضحة.", "error")
        else:
            get_db().execute(
                "UPDATE users SET local_withdraw_method = ? WHERE id = ?",
                (method, session["user_id"]),
            )
            get_db().commit()
            flash("تم اعتماد طريقة السحب المحلية.", "success")
        return redirect(url_for("settings_page"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        db = get_db()
        users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        for user in users:
            if not user["is_admin"]:
                ensure_referral_account(user["id"])
        db.commit()
        today = utc_now().date().isoformat()
        admin_stats = {
            "overview": {
                "customers": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0").fetchone()["count"],
                "active_accounts": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0 AND account_status = 'نشط'").fetchone()["count"],
                "confirmed_requests": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE status = 'مقبول'").fetchone()["count"],
                "pending_deposits": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'deposit' AND status = 'قيد المراجعة'").fetchone()["count"],
                "daily_withdrawals": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'withdraw' AND date(created_at) = ?", (today,)).fetchone()["count"],
                "total_deposits": db.execute("SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE kind = 'deposit' AND status = 'مقبول'").fetchone()["total"],
                "total_withdrawals": db.execute("SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE kind = 'withdraw' AND status = 'مقبول'").fetchone()["total"],
                "active_cards": db.execute("SELECT COUNT(*) count FROM subscription_cards WHERE status = 'نشطة'").fetchone()["count"],
                "pending_links": db.execute("SELECT COUNT(*) count FROM link_requests WHERE status = 'قيد المعالجة'").fetchone()["count"],
                "new_support": db.execute("SELECT COUNT(*) count FROM support_messages WHERE status = 'جديدة'").fetchone()["count"],
            },
            "payment_requests": {
                "today": db.execute("SELECT COUNT(*) count FROM payment_requests WHERE date(created_at) = ?", (today,)).fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM payment_requests WHERE status = 'pending_review'").fetchone()["count"],
                "code_confirmed": db.execute("SELECT COUNT(*) count FROM payment_requests WHERE status = 'code_confirmed'").fetchone()["count"],
                "approved": db.execute("SELECT COUNT(*) count FROM payment_requests WHERE status = 'approved'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM payment_requests WHERE status = 'rejected'").fetchone()["count"],
            },
            "card_deposits": {
                "today": db.execute("SELECT COUNT(*) count FROM card_deposit_requests WHERE date(created_at) = ?", (today,)).fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM card_deposit_requests WHERE status = 'pending_review'").fetchone()["count"],
                "code_confirmed": db.execute("SELECT COUNT(*) count FROM card_deposit_requests WHERE status = 'code_confirmed'").fetchone()["count"],
                "approved": db.execute("SELECT COUNT(*) count FROM card_deposit_requests WHERE status = 'approved'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM card_deposit_requests WHERE status = 'rejected'").fetchone()["count"],
            },
            "marketing": {
                "all": db.execute("SELECT COUNT(*) count FROM marketing_campaigns").fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM marketing_campaigns WHERE status = 'Pending'").fetchone()["count"],
                "running": db.execute("SELECT COUNT(*) count FROM marketing_campaigns WHERE status = 'Running'").fetchone()["count"],
                "completed": db.execute("SELECT COUNT(*) count FROM marketing_campaigns WHERE status = 'Completed'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM marketing_campaigns WHERE status = 'Rejected'").fetchone()["count"],
                "wallet_pending": db.execute("SELECT COUNT(*) count FROM marketing_recharges WHERE status = 'Pending Review'").fetchone()["count"],
                "total_budget": db.execute("SELECT COALESCE(SUM(budget), 0) total FROM marketing_campaigns").fetchone()["total"],
            },
            "users": {
                "all": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0").fetchone()["count"],
                "active": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0 AND account_status = 'نشط'").fetchone()["count"],
                "new_today": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0 AND date(created_at) = ?", (today,)).fetchone()["count"],
                "blocked": db.execute("SELECT COUNT(*) count FROM users WHERE is_admin = 0 AND account_status = 'موقوف'").fetchone()["count"],
            },
            "deposits": {
                "today": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'deposit' AND date(created_at) = ?", (today,)).fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'deposit' AND status = 'قيد المراجعة'").fetchone()["count"],
                "accepted": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'deposit' AND status = 'مقبول'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'deposit' AND status = 'مرفوض'").fetchone()["count"],
            },
            "withdrawals": {
                "today": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'withdraw' AND date(created_at) = ?", (today,)).fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'withdraw' AND status = 'قيد المراجعة'").fetchone()["count"] + db.execute("SELECT COUNT(*) count FROM local_withdrawals WHERE status = 'قيد المعالجة'").fetchone()["count"],
                "paid": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'withdraw' AND status = 'مقبول'").fetchone()["count"] + db.execute("SELECT COUNT(*) count FROM local_withdrawals WHERE status = 'تم الدفع'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM wallet_transactions WHERE kind = 'withdraw' AND status = 'مرفوض'").fetchone()["count"] + db.execute("SELECT COUNT(*) count FROM local_withdrawals WHERE status = 'مرفوض'").fetchone()["count"],
            },
            "cards": {
                "all": db.execute("SELECT COUNT(*) count FROM subscription_cards").fetchone()["count"],
                "active": db.execute("SELECT COUNT(*) count FROM subscription_cards WHERE status = 'نشطة'").fetchone()["count"],
                "inactive": db.execute("SELECT COUNT(*) count FROM subscription_cards WHERE status = 'غير نشطة'").fetchone()["count"],
                "review": db.execute("SELECT COUNT(*) count FROM subscription_cards WHERE status = 'قيد المراجعة'").fetchone()["count"],
            },
            "links": {
                "all": db.execute("SELECT COUNT(*) count FROM link_requests").fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM link_requests WHERE status = 'قيد المعالجة'").fetchone()["count"],
                "linked": db.execute("SELECT COUNT(*) count FROM link_requests WHERE status = 'تم الربط بنجاح'").fetchone()["count"],
                "rejected": db.execute("SELECT COUNT(*) count FROM link_requests WHERE status = 'مرفوض'").fetchone()["count"],
            },
            "tickets": {
                "new": db.execute("SELECT COUNT(*) count FROM trading_tickets WHERE date(created_at) = ?", (today,)).fetchone()["count"],
                "open": db.execute("SELECT COUNT(*) count FROM trading_tickets WHERE status != 'غير نشط'").fetchone()["count"],
                "closed": db.execute("SELECT COUNT(*) count FROM trading_tickets WHERE status = 'غير نشط'").fetchone()["count"],
            },
            "referrals": {
                "total": db.execute("SELECT COUNT(*) count FROM referrals").fetchone()["count"],
                "active": db.execute("SELECT COUNT(*) count FROM referrals JOIN users ON users.id = referrals.referred_user_id WHERE users.subscription_active = 1").fetchone()["count"],
                "commissions": db.execute("SELECT COALESCE(SUM(amount), 0) total FROM referral_commissions WHERE status = 'مقبول'").fetchone()["total"],
                "top": db.execute("SELECT COUNT(*) count FROM referral_wallet WHERE total_earned > 0").fetchone()["count"],
            },
            "support": {
                "new": db.execute("SELECT COUNT(*) count FROM support_messages WHERE status = 'جديدة'").fetchone()["count"],
                "progress": db.execute("SELECT COUNT(*) count FROM support_messages WHERE status = 'قيد الرد'").fetchone()["count"],
                "replied": db.execute("SELECT COUNT(*) count FROM support_messages WHERE status = 'تم الرد'").fetchone()["count"],
            },
            "funded": {
                "orders": db.execute("SELECT COUNT(*) count FROM funded_account_orders").fetchone()["count"],
                "pending": db.execute("SELECT COUNT(*) count FROM funded_account_orders WHERE status = 'pending_review'").fetchone()["count"],
                "active": db.execute("SELECT COUNT(*) count FROM funded_accounts WHERE status IN ('approved','account_delivered','active','warning','phase1_passed','phase2_passed')").fetchone()["count"],
                "closed": db.execute("SELECT COUNT(*) count FROM funded_accounts WHERE status IN ('closed','failed','suspended')").fetchone()["count"],
            },
        }
        return render_template(
            "admin.html",
            users=users,
            admin_stats=admin_stats,
            links=db.execute(
                """
                SELECT link_requests.*, users.full_name, users.email user_email
                FROM link_requests JOIN users ON users.id = link_requests.user_id
                ORDER BY link_requests.created_at DESC
                """
            ).fetchall(),
            transactions=db.execute(
                """
                SELECT wallet_transactions.*, users.full_name, users.email user_email
                FROM wallet_transactions JOIN users ON users.id = wallet_transactions.user_id
                ORDER BY wallet_transactions.created_at DESC
                """
            ).fetchall(),
            payment_requests=db.execute(
                """
                SELECT payment_requests.*, users.email user_email, users.username
                FROM payment_requests JOIN users ON users.id = payment_requests.user_id
                ORDER BY payment_requests.created_at DESC
                """
            ).fetchall(),
            payment_request_statuses=PAYMENT_REQUEST_STATUSES,
            payment_status_labels=PAYMENT_STATUS_LABELS,
            card_deposit_requests=db.execute(
                """
                SELECT card_deposit_requests.*, users.full_name, users.email user_email, users.username
                FROM card_deposit_requests JOIN users ON users.id = card_deposit_requests.user_id
                ORDER BY card_deposit_requests.created_at DESC
                """
            ).fetchall(),
            card_deposit_statuses=["pending_review", "code_confirmed", "approved", "rejected"],
            card_deposit_status_labels={
                "pending_review": "قيد المراجعة",
                "code_confirmed": "تم تأكيد الرمز",
                "approved": "مقبول",
                "rejected": "مرفوض",
            },
            tickets=db.execute(
                """
                SELECT tickets.*, users.full_name
                FROM tickets JOIN users ON users.id = tickets.user_id
                ORDER BY tickets.created_at DESC
                """
            ).fetchall(),
            cards=db.execute(
                """
                SELECT virtual_cards.*, users.full_name
                FROM virtual_cards JOIN users ON users.id = virtual_cards.user_id
                ORDER BY virtual_cards.updated_at DESC
                """
            ).fetchall(),
            subscription_cards=db.execute(
                """
                SELECT subscription_cards.*, users.full_name, users.email user_email
                FROM subscription_cards JOIN users ON users.id = subscription_cards.user_id
                ORDER BY subscription_cards.updated_at DESC, subscription_cards.created_at DESC
                """
            ).fetchall(),
            trading_cards=active_trading_cards(),
            trading_tickets=db.execute(
                """
                SELECT trading_tickets.*, users.full_name, users.email user_email,
                       subscription_cards.card_code, subscription_cards.card_type
                FROM trading_tickets
                JOIN users ON users.id = trading_tickets.user_id
                JOIN subscription_cards ON subscription_cards.id = trading_tickets.card_id
                ORDER BY trading_tickets.created_at DESC
                """
            ).fetchall(),
            link_statuses=LINK_STATUSES,
            request_statuses=REQUEST_STATUSES,
            card_statuses=CARD_STATUSES,
            subscription_card_statuses=SUBSCRIPTION_CARD_STATUSES,
            trading_account_statuses=TRADING_ACCOUNT_STATUSES,
            referral_reports=db.execute(
                """
                SELECT users.id, users.full_name, users.username, users.email, users.account_status,
                       users.referral_enabled, referral_levels.current_level,
                       referral_levels.total_referrals, referral_levels.active_referrals,
                       referral_levels.total_earnings, referral_wallet.balance,
                       (SELECT COUNT(*) FROM referral_commissions
                        WHERE referral_commissions.user_id = users.id
                          AND referral_commissions.status = 'مقبول') total_renewals
                FROM users
                JOIN referral_levels ON referral_levels.user_id = users.id
                JOIN referral_wallet ON referral_wallet.user_id = users.id
                WHERE users.is_admin = 0
                ORDER BY referral_levels.total_earnings DESC, referral_levels.total_referrals DESC
                """
            ).fetchall(),
            local_withdraw_methods=db.execute(
                """
                SELECT full_name, email, local_withdraw_method, created_at
                FROM users
                WHERE is_admin = 0 AND local_withdraw_method IS NOT NULL AND local_withdraw_method != ''
                ORDER BY created_at DESC
                """
            ).fetchall(),
            local_withdrawals=db.execute(
                """
                SELECT local_withdrawals.*, users.full_name, users.email user_email
                FROM local_withdrawals JOIN users ON users.id = local_withdrawals.user_id
                ORDER BY local_withdrawals.created_at DESC
                """
            ).fetchall(),
            local_withdraw_statuses=["قيد المعالجة", "تم الدفع", "مرفوض"],
            support_messages=db.execute(
                """
                SELECT support_messages.*, users.full_name, users.email user_email,
                       support_agents.name assigned_agent_name
                FROM support_messages
                LEFT JOIN users ON users.id = support_messages.user_id
                LEFT JOIN support_agents ON support_agents.id = support_messages.assigned_agent_id
                ORDER BY support_messages.created_at DESC
                """
            ).fetchall(),
            support_replies=db.execute(
                """
                SELECT support_replies.*, support_agents.name agent_name, support_agents.image_path agent_image
                FROM support_replies
                LEFT JOIN support_agents ON support_agents.id = support_replies.agent_id
                ORDER BY support_replies.created_at ASC
                """
            ).fetchall(),
            support_agents=db.execute("SELECT * FROM support_agents ORDER BY created_at DESC").fetchall(),
            active_support_agents=db.execute("SELECT * FROM support_agents WHERE is_active = 1 ORDER BY created_at DESC").fetchall(),
            support_statuses=["جديدة", "قيد الرد", "تم الرد"],
            marketing_campaigns=db.execute(
                """
                SELECT marketing_campaigns.*, users.full_name, users.email user_email
                FROM marketing_campaigns
                JOIN users ON users.id = marketing_campaigns.user_id
                ORDER BY marketing_campaigns.created_at DESC
                """
            ).fetchall(),
            marketing_recharges=db.execute(
                """
                SELECT marketing_recharges.*, users.full_name, users.email user_email
                FROM marketing_recharges
                JOIN users ON users.id = marketing_recharges.user_id
                ORDER BY marketing_recharges.created_at DESC
                """
            ).fetchall(),
            marketing_campaign_statuses=MARKETING_CAMPAIGN_STATUSES,
            marketing_recharge_statuses=MARKETING_RECHARGE_STATUSES,
            funded_packages=funded_packages(),
            funded_orders=db.execute(
                """
                SELECT funded_account_orders.*, users.full_name, users.email user_email,
                       funded_account_packages.account_size, funded_account_packages.broker,
                       funded_account_packages.platform, funded_accounts.id account_id,
                       funded_accounts.status account_status
                FROM funded_account_orders
                JOIN users ON users.id = funded_account_orders.user_id
                JOIN funded_account_packages ON funded_account_packages.id = funded_account_orders.package_id
                LEFT JOIN funded_accounts ON funded_accounts.order_id = funded_account_orders.id
                ORDER BY funded_account_orders.created_at DESC
                """
            ).fetchall(),
            funded_admin_accounts=db.execute(
                """
                SELECT funded_accounts.*, users.full_name, users.email user_email,
                       funded_account_packages.account_size package_size,
                       funded_account_packages.total_max_loss
                FROM funded_accounts
                JOIN users ON users.id = funded_accounts.user_id
                JOIN funded_account_packages ON funded_account_packages.id = funded_accounts.package_id
                ORDER BY funded_accounts.updated_at DESC
                """
            ).fetchall(),
            funded_statuses=FUNDED_ACCOUNT_STATUSES,
            funded_status_labels=FUNDED_ACCOUNT_STATUS_LABELS,
        )

    @app.route("/admin/payment-request/<int:request_id>/status", methods=("POST",))
    @admin_required
    def admin_payment_request_status(request_id):
        db = get_db()
        payment_request = db.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if payment_request is None:
            flash("طلب الدفع غير موجود.", "error")
            return redirect(url_for("admin_dashboard") + "#payment-requests")
        action = request.form.get("action", "")
        admin_note = request.form.get("admin_note", "").strip()
        if action == "approve":
            admin_code = request.form.get("admin_confirmation_code", "").strip()
            if admin_code != payment_request["confirmation_code"]:
                flash("رمز التأكيد البنكي غير صحيح.", "error")
                return redirect(url_for("admin_dashboard") + "#payment-requests")
            new_status = "approved"
        elif action == "reject":
            new_status = "rejected"
        else:
            flash("إجراء غير معروف.", "error")
            return redirect(url_for("admin_dashboard") + "#payment-requests")
        db.execute(
            """
            UPDATE payment_requests
            SET status = ?, admin_note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_status, admin_note, request_id),
        )
        db.commit()
        flash("تم تحديث طلب الدفع.", "success")
        return redirect(url_for("admin_dashboard") + "#payment-requests")

    @app.route("/admin/card-deposit/<int:request_id>/status", methods=("POST",))
    @admin_required
    def admin_card_deposit_status(request_id):
        db = get_db()
        deposit_request = db.execute("SELECT * FROM card_deposit_requests WHERE id = ?", (request_id,)).fetchone()
        if deposit_request is None:
            flash("طلب الإيداع غير موجود.", "error")
            return redirect(url_for("admin_dashboard") + "#card-deposits")
        action = request.form.get("action", "")
        admin_note = request.form.get("admin_note", "").strip()
        if action == "approve":
            new_status = "approved"
            db.execute(
                """
                INSERT INTO wallet_transactions (user_id, kind, method, amount, details, status)
                VALUES (?, 'deposit', 'Visa/MasterCard', ?, 'إيداع عبر البطاقة - تم قبوله', 'مقبول')
                """,
                (deposit_request["user_id"], deposit_request["amount"]),
            )
            db.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (deposit_request["user_id"], f"تم قبول طلب الإيداع #{request_id} بقيمة ${deposit_request['amount']:.2f} عبر Visa/MasterCard. تم إضافة الرصيد إلى محفظتك."),
            )
        elif action == "reject":
            new_status = "rejected"
            db.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (deposit_request["user_id"], f"تم رفض طلب الإيداع #{request_id} بقيمة ${deposit_request['amount']:.2f} عبر Visa/MasterCard."),
            )
        else:
            flash("إجراء غير معروف.", "error")
            return redirect(url_for("admin_dashboard") + "#card-deposits")
        db.execute(
            """
            UPDATE card_deposit_requests
            SET status = ?, admin_note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_status, admin_note, request_id),
        )
        db.commit()
        flash("تم تحديث طلب الإيداع بالبطاقة.", "success")
        return redirect(url_for("admin_dashboard") + "#card-deposits")

    @app.route("/admin/funded-order/<int:order_id>/decision", methods=("POST",))
    @admin_required
    def admin_funded_order_decision(order_id):
        db = get_db()
        order = db.execute(
            """
            SELECT funded_account_orders.*, funded_account_packages.account_size,
                   funded_account_packages.total_max_loss, funded_account_packages.broker,
                   funded_account_packages.platform
            FROM funded_account_orders
            JOIN funded_account_packages ON funded_account_packages.id = funded_account_orders.package_id
            WHERE funded_account_orders.id = ?
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            flash("طلب الحساب الممول غير موجود.", "error")
            return redirect(url_for("admin_dashboard") + "#funded-accounts")
        action = request.form.get("action", "")
        note = request.form.get("admin_notes", "").strip()
        if action == "approve":
            broker = request.form.get("broker", "").strip() or order["broker"] or "Exness"
            platform = request.form.get("platform", "").strip() or "MT5"
            server = request.form.get("server", "").strip()
            login_id = request.form.get("login_id", "").strip()
            trader_password = request.form.get("trader_password", "").strip()
            investor_password = request.form.get("investor_password", "").strip()
            account = db.execute("SELECT * FROM funded_accounts WHERE order_id = ?", (order_id,)).fetchone()
            if account is None:
                cursor = db.execute(
                    """
                    INSERT INTO funded_accounts
                    (order_id, user_id, package_id, broker, platform, server, login_id, trader_password,
                     investor_password, account_size, current_balance, current_equity,
                     remaining_allowed_loss, status, admin_notes, delivered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        order_id,
                        order["user_id"],
                        order["package_id"],
                        broker,
                        platform,
                        server,
                        login_id,
                        trader_password,
                        investor_password,
                        order["account_size"],
                        order["account_size"],
                        order["account_size"],
                        order["total_max_loss"],
                        note,
                    ),
                )
                log_funded_update(cursor.lastrowid, "status", "", "approved", "Account approved and delivered")
            else:
                db.execute(
                    """
                    UPDATE funded_accounts
                    SET broker = ?, platform = ?, server = ?, login_id = ?, trader_password = ?,
                        investor_password = ?, status = 'approved', admin_notes = ?,
                        delivered_at = COALESCE(delivered_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (broker, platform, server, login_id, trader_password, investor_password, note, account["id"]),
                )
                log_funded_update(account["id"], "status", account["status"], "approved", "Account approved")
            db.execute(
                "UPDATE funded_account_orders SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (order_id,),
            )
            notify_user(order["user_id"], "تمت الموافقة على الحساب الممول. بيانات الدخول متاحة الآن في لوحة حساباتك الممولة.")
            notify_user(order["user_id"], "بيانات دخول الحساب الممول أصبحت متاحة.")
            flash("تمت الموافقة على الطلب وتسليم بيانات الحساب.", "success")
        elif action == "reject":
            if not order["refunded"]:
                db.execute(
                    """
                    INSERT INTO wallet_transactions (user_id, kind, method, amount, details, status)
                    VALUES (?, 'deposit', 'Funded Account Refund', ?, ?, 'مقبول')
                    """,
                    (order["user_id"], order["final_price"], f"استرجاع طلب حساب ممول #{order_id}"),
                )
            db.execute(
                """
                UPDATE funded_account_orders
                SET status = 'rejected', refunded = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (order_id,),
            )
            notify_user(order["user_id"], f"تم رفض طلب الحساب الممول #{order_id} وتم إرجاع المبلغ إلى محفظتك.")
            flash("تم رفض الطلب وإرجاع الرصيد.", "success")
        else:
            flash("إجراء غير معروف.", "error")
        db.commit()
        return redirect(url_for("admin_dashboard") + "#funded-accounts")

    @app.route("/admin/funded-account/<int:account_id>/update", methods=("POST",))
    @admin_required
    def admin_update_funded_account(account_id):
        db = get_db()
        account = db.execute("SELECT * FROM funded_accounts WHERE id = ?", (account_id,)).fetchone()
        if account is None:
            flash("الحساب الممول غير موجود.", "error")
            return redirect(url_for("admin_dashboard") + "#funded-accounts")
        text_fields = ["broker", "platform", "server", "login_id", "trader_password", "investor_password", "current_phase", "status", "admin_notes"]
        number_fields = ["current_balance", "current_equity", "current_loss_percent", "daily_loss_used", "total_loss_used", "remaining_allowed_loss", "progress"]
        updates = {}
        for field in text_fields:
            if field in request.form:
                value = request.form.get(field, "").strip()
                if field == "status" and value not in FUNDED_ACCOUNT_STATUSES and value not in {"active", "rejected"}:
                    value = account["status"]
                updates[field] = value
        for field in number_fields:
            if field in request.form:
                try:
                    value = float(request.form.get(field, account[field]) or 0)
                except ValueError:
                    value = float(account[field] or 0)
                if field == "progress":
                    value = max(0, min(100, int(value)))
                updates[field] = value
        if updates:
            assignments = ", ".join([f"{field} = ?" for field in updates])
            values = list(updates.values()) + [account_id]
            db.execute(f"UPDATE funded_accounts SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
            for field, value in updates.items():
                if str(account[field] or "") != str(value or ""):
                    log_funded_update(account_id, field, account[field], value, "Manual admin update")
        warning_message = request.form.get("warning_message", "").strip()
        if warning_message:
            db.execute(
                "INSERT INTO funded_account_warnings (account_id, user_id, message) VALUES (?, ?, ?)",
                (account_id, account["user_id"], warning_message),
            )
            db.execute(
                "UPDATE funded_accounts SET warning_message = ?, status = CASE WHEN status IN ('closed','failed','suspended') THEN status ELSE 'warning' END, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (warning_message, account_id),
            )
            log_funded_update(account_id, "warning_message", account["warning_message"], warning_message, "Warning added")
            notify_user(account["user_id"], f"تحذير على حسابك الممول: {warning_message}")
        if "current_balance" in updates or "current_equity" in updates:
            notify_user(account["user_id"], "تم تحديث رصيد أو حقوق الحساب الممول.")
        if updates.get("status") == "suspended":
            notify_user(account["user_id"], "تم تعليق الحساب الممول مؤقتاً.")
        if updates.get("status") == "closed":
            notify_user(account["user_id"], "تم إغلاق الحساب الممول.")
        db.commit()
        flash("تم تحديث الحساب الممول وتسجيل العملية.", "success")
        return redirect(url_for("admin_dashboard") + "#funded-accounts")


    @app.route("/admin/marketing-campaign/<int:campaign_id>/status", methods=("POST",))
    @admin_required
    def admin_marketing_campaign_status(campaign_id):
        db = get_db()
        campaign = db.execute("SELECT * FROM marketing_campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if campaign is None:
            flash("الحملة التسويقية غير موجودة.", "error")
            return redirect(url_for("admin_dashboard"))
        status = request.form.get("status", campaign["status"])
        if status not in MARKETING_CAMPAIGN_STATUSES:
            status = campaign["status"]
        try:
            progress = max(0, min(100, int(request.form.get("progress", campaign["progress"]) or 0)))
        except ValueError:
            progress = campaign["progress"]
        if status == "Completed":
            progress = 100
        agent_notes = request.form.get("agent_notes", "").strip()
        start_date = campaign["start_date"]
        end_date = campaign["end_date"]
        if status in {"Approved", "Running"} and not start_date:
            start_date = utc_now().date().isoformat()
            end_date = (utc_now() + timedelta(days=campaign["duration_days"])).date().isoformat()
        db.execute(
            """
            UPDATE marketing_campaigns
            SET status = ?, progress = ?, agent_notes = ?, start_date = ?, end_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, progress, agent_notes, start_date, end_date, campaign_id),
        )
        db.execute(
            """
            INSERT INTO marketing_tickets (user_id, campaign_id, title, message, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                campaign["user_id"],
                campaign_id,
                "Marketing Campaign Update",
                agent_notes or f"تم تحديث حالة الحملة إلى {status}.",
                status,
            ),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (campaign["user_id"], f"تم تحديث حملة التسويق #{campaign_id}: {status}"),
        )
        db.commit()
        flash("تم تحديث الحملة التسويقية.", "success")
        return redirect(url_for("admin_dashboard") + "#marketing")

    @app.route("/admin/marketing-recharge/<int:recharge_id>/status", methods=("POST",))
    @admin_required
    def admin_marketing_recharge_status(recharge_id):
        db = get_db()
        recharge = db.execute("SELECT * FROM marketing_recharges WHERE id = ?", (recharge_id,)).fetchone()
        if recharge is None:
            flash("طلب شحن محفظة التسويق غير موجود.", "error")
            return redirect(url_for("admin_dashboard"))
        status = request.form.get("status", recharge["status"])
        if status not in MARKETING_RECHARGE_STATUSES:
            status = recharge["status"]
        if recharge["status"] != "Approved" and status == "Approved":
            ensure_marketing_wallet(recharge["user_id"])
            db.execute(
                """
                UPDATE marketing_wallets
                SET balance = balance + ?, total_recharged = total_recharged + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (recharge["amount"], recharge["amount"], recharge["user_id"]),
            )
            db.execute(
                """
                INSERT INTO marketing_tickets (user_id, title, message, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    recharge["user_id"],
                    "Marketing Wallet Recharge Approved",
                    f"تمت الموافقة على شحن محفظة التسويق بمبلغ ${recharge['amount']:.2f}.",
                    "Approved",
                ),
            )
        db.execute(
            "UPDATE marketing_recharges SET status = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, recharge_id),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (recharge["user_id"], f"تم تحديث طلب شحن محفظة التسويق: {status}"),
        )
        db.commit()
        flash("تم تحديث طلب شحن محفظة التسويق.", "success")
        return redirect(url_for("admin_dashboard") + "#marketing")

    @app.route("/admin/link/<int:request_id>/status", methods=("POST",))
    @admin_required
    def admin_link_status(request_id):
        status = request.form.get("status", "قيد المعالجة")
        db = get_db()
        db.execute("UPDATE link_requests SET status = ? WHERE id = ?", (status, request_id))
        link = db.execute("SELECT * FROM link_requests WHERE id = ?", (request_id,)).fetchone()
        if link:
            card_status_map = {
                "قيد المعالجة": "قيد المراجعة",
                "تم الربط بنجاح": "نشطة",
                "مرفوض": "مرفوضة",
                "يتطلب مراجعة": "معلقة",
            }
            card_status = card_status_map.get(status, "قيد المراجعة")
            if link["subscription_card_id"]:
                db.execute(
                    """
                    UPDATE subscription_cards
                    SET status = ?,
                        visible_balance = CASE
                            WHEN ? = 'نشطة' THEN COALESCE(visible_balance, trading_balance, ?)
                            ELSE visible_balance
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                    """,
                    (card_status, card_status, link["balance"], link["subscription_card_id"], link["user_id"]),
                )
            else:
                db.execute(
                    """
                    UPDATE subscription_cards
                    SET status = ?,
                        visible_balance = CASE
                            WHEN ? = 'نشطة' THEN COALESCE(visible_balance, trading_balance, ?)
                            ELSE visible_balance
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND broker = ? AND platform = ? AND trading_account_number = ?
                    """,
                    (
                        card_status,
                        card_status,
                        link["balance"],
                        link["user_id"],
                        link["broker"],
                        link["account_type"],
                        link["account_number"],
                    ),
                )
            db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (link["user_id"], f"تم تحديث حالة الربط والبطاقة: {status}"))
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/transaction/<int:transaction_id>/status", methods=("POST",))
    @admin_required
    def admin_transaction_status(transaction_id):
        status = request.form.get("status", "قيد المراجعة")
        db = get_db()
        tx = db.execute("SELECT * FROM wallet_transactions WHERE id = ?", (transaction_id,)).fetchone()
        db.execute("UPDATE wallet_transactions SET status = ? WHERE id = ?", (status, transaction_id))
        if tx:
            if status == "مقبول":
                notify_user(tx["user_id"], f"تمت الموافقة على {'إيداعك' if tx['kind'] == 'deposit' else 'طلب السحب'}: {tx['method']} — ${tx['amount']:.2f}")
            elif status == "مرفوض":
                notify_user(tx["user_id"], f"تم رفض {'طلب الإيداع' if tx['kind'] == 'deposit' else 'طلب السحب'}: {tx['method']} — ${tx['amount']:.2f}")
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/local-withdrawal/<int:withdrawal_id>/status", methods=("POST",))
    @admin_required
    def admin_local_withdrawal_status(withdrawal_id):
        status = request.form.get("status", "قيد المعالجة")
        if status not in {"قيد المعالجة", "تم الدفع", "مرفوض"}:
            status = "قيد المعالجة"
        get_db().execute("UPDATE local_withdrawals SET status = ? WHERE id = ?", (status, withdrawal_id))
        get_db().commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/support-agent", methods=("POST",))
    @admin_required
    def admin_create_support_agent():
        db = get_db()
        count = db.execute("SELECT COUNT(*) count FROM support_agents").fetchone()["count"]
        if count >= 10:
            flash("لا يمكن إنشاء أكثر من 10 وكلاء.", "error")
            return redirect(url_for("admin_dashboard"))
        name = request.form.get("name", "").strip() or "TrBridgo Support"
        image_path = save_agent_image(request.files.get("image"))
        is_active = 1 if request.form.get("is_active", "1") == "1" else 0
        db.execute(
            "INSERT INTO support_agents (name, image_path, is_active) VALUES (?, ?, ?)",
            (name, image_path, is_active),
        )
        db.commit()
        flash("تم إنشاء الوكيل.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/support-agent/<int:agent_id>", methods=("POST",))
    @admin_required
    def admin_update_support_agent(agent_id):
        db = get_db()
        agent = db.execute("SELECT * FROM support_agents WHERE id = ?", (agent_id,)).fetchone()
        if agent is None:
            flash("الوكيل غير موجود.", "error")
            return redirect(url_for("admin_dashboard"))
        image_path = save_agent_image(request.files.get("image")) or agent["image_path"]
        db.execute(
            "UPDATE support_agents SET name = ?, image_path = ?, is_active = ? WHERE id = ?",
            (
                request.form.get("name", agent["name"]).strip() or agent["name"],
                image_path,
                1 if request.form.get("is_active", "1") == "1" else 0,
                agent_id,
            ),
        )
        db.commit()
        flash("تم تعديل بيانات الوكيل.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/support-agent/<int:agent_id>/delete", methods=("POST",))
    @admin_required
    def admin_delete_support_agent(agent_id):
        db = get_db()
        db.execute("UPDATE support_replies SET agent_id = NULL WHERE agent_id = ?", (agent_id,))
        db.execute("UPDATE support_messages SET assigned_agent_id = NULL WHERE assigned_agent_id = ?", (agent_id,))
        db.execute("DELETE FROM support_agents WHERE id = ?", (agent_id,))
        db.commit()
        flash("تم حذف الوكيل.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/support-message/<int:message_id>/status", methods=("POST",))
    @admin_required
    def admin_update_support_message_status(message_id):
        status = request.form.get("status", "جديدة")
        if status not in {"جديدة", "قيد الرد", "تم الرد"}:
            status = "جديدة"
        get_db().execute("UPDATE support_messages SET status = ? WHERE id = ?", (status, message_id))
        get_db().commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/support-conversation/<int:message_id>", methods=("GET",))
    @admin_required
    def admin_get_support_conversation(message_id):
        db = get_db()
        msg = db.execute(
            """SELECT support_messages.*, users.full_name, users.email user_email
               FROM support_messages
               LEFT JOIN users ON users.id = support_messages.user_id
               WHERE support_messages.id = ?""",
            (message_id,),
        ).fetchone()
        if msg is None:
            return jsonify({"ok": False, "error": "not found"}), 404
        replies = db.execute(
            """SELECT support_replies.*, support_agents.name agent_name, support_agents.image_path agent_image
               FROM support_replies
               LEFT JOIN support_agents ON support_agents.id = support_replies.agent_id
               WHERE support_replies.message_id = ?
               ORDER BY support_replies.created_at ASC""",
            (message_id,),
        ).fetchall()
        return jsonify({
            "ok": True,
            "message": {
                "id": msg["id"],
                "name": msg["full_name"] or msg["guest_name"] or "زائر",
                "email": msg["user_email"] or msg["guest_email"] or "",
                "message": msg["message"],
                "status": msg["status"],
                "created_at": msg["created_at"],
            },
            "replies": [
                {
                    "id": r["id"],
                    "text": r["reply_text"],
                    "agent_name": r["agent_name"] or "TrBridgo Support",
                    "agent_image": url_for("static", filename=f"uploads/agents/{r['agent_image']}") if r["agent_image"] else "",
                    "reply_mode": r["reply_mode"] or "human",
                    "created_at": r["created_at"],
                }
                for r in replies
            ],
        })

    @app.route("/admin/support-message/<int:message_id>/reply", methods=("POST",))
    @admin_required
    def admin_reply_support_message(message_id):
        db = get_db()
        wants_json = request.headers.get("Accept", "").startswith("application/json") or request.is_json
        message = db.execute("SELECT * FROM support_messages WHERE id = ?", (message_id,)).fetchone()
        if message is None:
            if wants_json:
                return jsonify({"ok": False, "error": "رسالة غير موجودة"}), 404
            flash("رسالة الدعم غير موجودة.", "error")
            return redirect(url_for("admin_dashboard"))
        data = request.get_json(silent=True) or {}
        reply_text = (data.get("reply_text") or request.form.get("reply_text", "")).strip()
        reply_mode = (data.get("reply_mode") or request.form.get("reply_mode", "human")).strip()
        if reply_mode not in {"human", "faq", "ai"}:
            reply_mode = "human"
        if not reply_text:
            if wants_json:
                return jsonify({"ok": False, "error": "يرجى كتابة الرد"}), 400
            flash("يرجى كتابة الرد.", "error")
            return redirect(url_for("admin_dashboard"))
        agent_id_value = data.get("agent_id") or request.form.get("agent_id", "")
        agent_id = int(agent_id_value) if agent_id_value else None
        if agent_id:
            agent = db.execute("SELECT id FROM support_agents WHERE id = ? AND is_active = 1", (agent_id,)).fetchone()
            if agent is None:
                agent_id = None
        db.execute(
            "INSERT INTO support_replies (message_id, agent_id, reply_text, reply_mode) VALUES (?, ?, ?, ?)",
            (message_id, agent_id, reply_text, reply_mode),
        )
        db.execute(
            "UPDATE support_messages SET status = 'تم الرد', assigned_agent_id = ? WHERE id = ?",
            (agent_id, message_id),
        )
        if message["user_id"]:
            db.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (message["user_id"], "تم الرد على رسالتك في الدعم الغني."),
            )
        db.commit()
        if wants_json:
            return jsonify({"ok": True, "message": "تم إرسال الرد"})
        flash("تم إرسال الرد.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/trading-ticket", methods=("POST",))
    @admin_required
    def admin_create_trading_ticket():
        db = get_db()
        card_id = int(request.form.get("card_id", "0") or 0)
        card = db.execute(
            """
            SELECT subscription_cards.*, users.full_name
            FROM subscription_cards JOIN users ON users.id = subscription_cards.user_id
            WHERE subscription_cards.id = ?
            """,
            (card_id,),
        ).fetchone()
        if card is None:
            flash("يرجى اختيار بطاقة صحيحة.", "error")
            return redirect(url_for("admin_dashboard"))
        if card["status"] != "نشطة":
            flash("لا يمكن إنشاء تذكرة لبطاقة غير مفعلة.", "error")
            return redirect(url_for("admin_dashboard"))
        if not card["trading_account_number"]:
            flash("لا يمكن إنشاء تذكرة لحساب غير مربوط.", "error")
            return redirect(url_for("admin_dashboard"))

        lot_size = float(request.form.get("lot_size", "0") or 0)
        balance = float(card["visible_balance"] if card["visible_balance"] is not None else card["trading_balance"] or 0)
        risk = float(request.form.get("risk_percentage", "") or calculate_risk_percentage(balance, card["leverage"], lot_size))
        status = request.form.get("status", "تحت المراجعة")
        if status not in TRADING_ACCOUNT_STATUSES:
            status = "تحت المراجعة"
        analysis_image = save_trading_analysis_image(request.files.get("analysis_image"), card["user_id"])
        db.execute(
            """
            INSERT INTO trading_tickets
            (user_id, card_id, mt_account_number, broker_name, leverage, balance,
             trading_pair, trade_type, lot_size, risk_percentage, analysis_note, analysis_image, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["user_id"],
                card["id"],
                card["trading_account_number"],
                card["broker"],
                card["leverage"],
                balance,
                request.form.get("trading_pair", "").strip().upper() or "EURUSD",
                request.form.get("trade_type", "شراء"),
                lot_size,
                risk,
                request.form.get("analysis_note", "").strip() or risk_label(risk),
                analysis_image,
                status,
            ),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (card["user_id"], f"تم إنشاء تذكرة تداول جديدة للبطاقة {card['card_code'] or card['id']}."),
        )
        db.commit()
        flash("تم إنشاء تذكرة التداول.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/trading-ticket/<int:ticket_id>", methods=("POST",))
    @admin_required
    def admin_update_trading_ticket(ticket_id):
        db = get_db()
        ticket = db.execute("SELECT * FROM trading_tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            flash("تذكرة التداول غير موجودة.", "error")
            return redirect(url_for("admin_dashboard"))
        lot_size = float(request.form.get("lot_size", ticket["lot_size"]) or 0)
        balance = float(request.form.get("balance", ticket["balance"]) or 0)
        leverage = request.form.get("leverage", ticket["leverage"]).strip()
        risk = float(request.form.get("risk_percentage", "") or calculate_risk_percentage(balance, leverage, lot_size))
        status = request.form.get("status", ticket["status"])
        if status not in TRADING_ACCOUNT_STATUSES:
            status = ticket["status"]
        analysis_image = save_trading_analysis_image(request.files.get("analysis_image"), ticket["user_id"])
        image_value = analysis_image or ticket["analysis_image"]
        db.execute(
            """
            UPDATE trading_tickets
            SET leverage = ?, balance = ?, trading_pair = ?, trade_type = ?,
                lot_size = ?, risk_percentage = ?, analysis_note = ?, analysis_image = ?, status = ?
            WHERE id = ?
            """,
            (
                leverage,
                balance,
                request.form.get("trading_pair", ticket["trading_pair"]).strip().upper(),
                request.form.get("trade_type", ticket["trade_type"]),
                lot_size,
                risk,
                request.form.get("analysis_note", ticket["analysis_note"]).strip(),
                image_value,
                status,
                ticket_id,
            ),
        )
        db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (ticket["user_id"], f"تم تحديث حالة حساب التداول: {status}"),
        )
        db.commit()
        flash("تم تعديل تذكرة التداول.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/trading-ticket/<int:ticket_id>/delete", methods=("POST",))
    @admin_required
    def admin_delete_trading_ticket(ticket_id):
        db = get_db()
        ticket = db.execute("SELECT user_id FROM trading_tickets WHERE id = ?", (ticket_id,)).fetchone()
        db.execute("DELETE FROM trading_tickets WHERE id = ?", (ticket_id,))
        if ticket:
            db.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (ticket["user_id"], "تم حذف تذكرة تداول من حسابك."),
            )
        db.commit()
        flash("تم حذف تذكرة التداول.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/ticket", methods=("POST",))
    @admin_required
    def admin_create_ticket():
        db = get_db()
        user_id = int(request.form.get("user_id"))
        db.execute(
            """
            INSERT INTO tickets (user_id, title, current_balance, service_type, issue_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                request.form.get("title", "تذكرة خدمة"),
                float(request.form.get("current_balance", "0") or 0),
                request.form.get("service_type", "ربط سريع"),
                request.form.get("issue_date") or utc_now().date().isoformat(),
                request.form.get("status", "نشطة"),
            ),
        )
        db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, "تم إنشاء تذكرة جديدة في حسابك."))
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/card", methods=("POST",))
    @admin_required
    def admin_update_card():
        db = get_db()
        user_id = int(request.form.get("user_id"))
        ensure_card(user_id)
        db.execute(
            """
            UPDATE virtual_cards
            SET balance = ?, status = ?, card_type = ?, expiry_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                float(request.form.get("balance", "0") or 0),
                request.form.get("status", "غير مفعلة"),
                request.form.get("card_type", "Virtual Visa"),
                request.form.get("expiry_date", "12/29"),
                user_id,
            ),
        )
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/subscription-card/<int:card_id>", methods=("POST",))
    @admin_required
    def admin_update_subscription_card(card_id):
        status = request.form.get("status", "غير نشطة")
        if status not in SUBSCRIPTION_CARD_STATUSES:
            status = "غير نشطة"
        visible_balance = request.form.get("visible_balance", "")
        balance_value = float(visible_balance or 0) if status == "نشطة" else None
        db = get_db()
        db.execute(
            """
            UPDATE subscription_cards
            SET visible_balance = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (balance_value, status, card_id),
        )
        card = db.execute("SELECT user_id, card_type FROM subscription_cards WHERE id = ?", (card_id,)).fetchone()
        if card:
            db.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (card["user_id"], f"تم تحديث حالة بطاقة {card['card_type']}: {status}"),
            )
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/referral/<int:user_id>/level", methods=("POST",))
    @admin_required
    def admin_update_referral_level(user_id):
        level = request.form.get("current_level", "المستوى 1").strip() or "المستوى 1"
        ensure_referral_account(user_id)
        get_db().execute(
            "UPDATE referral_levels SET current_level = ?, manual_level = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (level, level, user_id),
        )
        get_db().commit()
        flash("تم تعديل مستوى الإحالة.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/referral/<int:user_id>/status", methods=("POST",))
    @admin_required
    def admin_update_referral_status(user_id):
        enabled = 1 if request.form.get("referral_enabled") == "1" else 0
        get_db().execute("UPDATE users SET referral_enabled = ? WHERE id = ?", (enabled, user_id))
        get_db().commit()
        flash("تم تحديث حالة نظام الإحالة.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/referral/<int:user_id>/adjust", methods=("POST",))
    @admin_required
    def admin_adjust_referral_wallet(user_id):
        amount = float(request.form.get("amount", "0") or 0)
        ensure_referral_account(user_id)
        db = get_db()
        if amount >= 0:
            db.execute(
                """
                UPDATE referral_wallet
                SET balance = balance + ?, total_earned = total_earned + ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (amount, amount, user_id),
            )
        else:
            deduction = abs(amount)
            db.execute(
                """
                UPDATE referral_wallet
                SET balance = MAX(balance - ?, 0), total_withdrawn = total_withdrawn + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (deduction, deduction, user_id),
            )
        ensure_referral_account(user_id)
        db.commit()
        flash("تم تحديث محفظة الإحالة.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/referrals/export")
    @admin_required
    def admin_export_referrals():
        db = get_db()
        rows = db.execute(
            """
            SELECT users.full_name, users.username, users.email,
                   referral_levels.current_level, referral_levels.total_referrals,
                   referral_levels.active_referrals, referral_levels.total_earnings,
                   referral_wallet.balance, users.account_status
            FROM users
            JOIN referral_levels ON referral_levels.user_id = users.id
            JOIN referral_wallet ON referral_wallet.user_id = users.id
            WHERE users.is_admin = 0
            ORDER BY referral_levels.total_earnings DESC
            """
        ).fetchall()
        lines = ["name,username,email,level,total_referrals,active_referrals,total_earnings,balance,status"]
        for row in rows:
            lines.append(
                ",".join(
                    str(row[key]).replace(",", " ")
                    for key in row.keys()
                )
            )
        return Response("\n".join(lines), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=referrals.csv"})

    @app.route("/admin/user/<int:user_id>/plan", methods=("POST",))
    @admin_required
    def admin_update_user_plan(user_id):
        db = get_db()
        before = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        new_plan = request.form.get("plan", "trial")
        new_active = 1 if request.form.get("subscription_active") == "1" else 0
        new_status = request.form.get("account_status", "نشط")
        db.execute(
            "UPDATE users SET plan = ?, subscription_active = ?, account_status = ? WHERE id = ?",
            (new_plan, new_active, new_status, user_id),
        )
        if before and not before["subscription_active"] and new_active and new_status not in ("موقوف", "مرفوض"):
            award_referral_commission(user_id, plan_to_subscription_type(new_plan))
        db.commit()
        return redirect(url_for("admin_dashboard"))

    # ─── MCP API ────────────────────────────────────────────────────────────────
    # Endpoint: GET /api/mcp/health
    # Auth:     Authorization: Bearer <MCP_API_KEY>
    # Returns:  200 {"status":"ok","site":"TrBridgo.io","mcp_access":true}
    #           401 {"error":"unauthorized"} when the key is missing or wrong
    # The key is read from MCP_API_KEY env-var (set in .env / Render env vars).
    # ────────────────────────────────────────────────────────────────────────────
    @app.route("/api/mcp/health", methods=["GET"])
    def mcp_health():
        """MCP health-check endpoint — validates Bearer token from MCP_API_KEY."""
        expected = app.config.get("MCP_API_KEY", "")
        auth_header = request.headers.get("Authorization", "")

        # Extract token from "Bearer <token>"
        parts = auth_header.split(" ", 1)
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else ""

        if not expected or not token or token != expected:
            return jsonify({"error": "unauthorized"}), 401

        return jsonify({
            "status": "ok",
            "site": "TrBridgo.io",
            "mcp_access": True,
        }), 200

    @app.errorhandler(404)
    def page_not_found(_error):
        return render_template("404.html"), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
