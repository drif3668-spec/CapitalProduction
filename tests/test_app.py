from io import BytesIO
import sqlite3

import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "DATABASE": str(tmp_path / "test.db"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "PROFILE_UPLOAD_FOLDER": str(tmp_path / "static_uploads" / "profile"),
            "TRADING_ANALYSIS_UPLOAD_FOLDER": str(tmp_path / "static_uploads" / "trading_analysis"),
            "AGENT_UPLOAD_FOLDER": str(tmp_path / "static_uploads" / "agents"),
            "MARKETING_UPLOAD_FOLDER": str(tmp_path / "static_uploads" / "marketing"),
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def register_and_login(client):
    client.post(
        "/register",
        data={
            "full_name": "عميل تجريبي",
            "email": "client@example.com",
            "password": "StrongPass123",
            "confirm_password": "StrongPass123",
        },
    )
    return client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
        follow_redirects=True,
    )


def read_test_db(app):
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


def test_register_starts_trial_and_dashboard(client):
    response = register_and_login(client)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "الرئيسية" in html
    assert "يوم" in html


def test_quick_link_flow_creates_pending_request(client):
    register_and_login(client)
    response = client.post(
        "/subscriptions/adopt",
        data={"card_type": "Pro"},
        follow_redirects=True,
    )
    assert "تم اعتماد البطاقة" in response.get_data(as_text=True)
    response = client.post(
        "/quick-link/start",
        data={
            "subscription_card_id": "1",
            "broker": "Exness",
            "account_type": "MT5",
            "leverage": "1:500",
            "balance": "1000",
        },
    )
    assert response.status_code == 200
    assert "جاري تجهيز نظام الربط" in response.get_data(as_text=True)
    response = client.post(
        "/quick-link/new",
        data={
            "subscription_card_id": "1",
            "card_code": "12345678",
            "broker": "Exness",
            "platform": "MT5",
            "account_type": "Real",
            "leverage": "1:500",
            "balance": "1000",
            "account_number": "123456",
            "investor_password": "invest-pass",
            "email": "client@example.com",
            "extra_info": "demo",
        },
        follow_redirects=True,
    )
    assert "قيد المعالجة" in response.get_data(as_text=True)
    assert "قيد المراجعة" in response.get_data(as_text=True)


def test_admin_can_login_and_view_panel(client):
    response = client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "لوحة الأدمن" in response.get_data(as_text=True)


def test_deposit_request_is_visible(client):
    register_and_login(client)
    response = client.post(
        "/deposit",
        data={
            "method": "USDT (TRC20)",
            "amount": "250",
            "details": "tx",
            "proof": (BytesIO(b"fake-image"), "receipt.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "قيد المراجعة" in response.get_data(as_text=True) or "تم إرسال الطلب" in response.get_data(as_text=True)
    client.post("/logout")
    response = client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "وصل الدفع" in html
    assert "receipt.png" in html or "فتح الوصل" in html


def test_duplicate_card_code_is_rejected(client):
    register_and_login(client)
    client.post("/subscriptions/adopt", data={"card_type": "Basic"})
    client.post("/subscriptions/adopt", data={"card_type": "Ultra"})
    client.post(
        "/quick-link/new",
        data={
            "subscription_card_id": "1",
            "card_code": "87654321",
            "broker": "Broker A",
            "platform": "MT5",
            "account_type": "Demo",
            "leverage": "1:100",
            "balance": "500",
            "account_number": "5551",
            "investor_password": "pass",
            "email": "client@example.com",
        },
    )
    response = client.post(
        "/quick-link/new",
        data={
            "subscription_card_id": "2",
            "card_code": "87654321",
            "broker": "Broker B",
            "platform": "MT4",
            "account_type": "Demo",
            "leverage": "1:100",
            "balance": "600",
            "account_number": "5552",
            "investor_password": "pass",
            "email": "client@example.com",
        },
        follow_redirects=True,
    )
    assert "رمز البطاقة مستخدم بالفعل" in response.get_data(as_text=True)


def test_admin_can_activate_subscription_card(client):
    register_and_login(client)
    client.post("/subscriptions/adopt", data={"card_type": "Ultra"})
    client.post(
        "/quick-link/new",
        data={
            "subscription_card_id": "1",
            "card_code": "11223344",
            "broker": "IC Markets",
            "platform": "MT5",
            "account_type": "Real",
            "leverage": "1:500",
            "balance": "34000",
            "account_number": "999888",
            "investor_password": "pass",
            "email": "client@example.com",
        },
    )
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
    )
    response = client.post(
        "/admin/link/1/status",
        data={"status": "تم الربط بنجاح"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "34000" in html or "34,000" in html
    assert "نشطة" in html
    client.post("/logout")
    response = client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
        follow_redirects=True,
    )
    assert "نشطة" in response.get_data(as_text=True)


def test_admin_can_create_trading_ticket_for_active_card(client):
    register_and_login(client)
    client.post("/subscriptions/adopt", data={"card_type": "Basic"})
    client.post(
        "/quick-link/new",
        data={
            "subscription_card_id": "1",
            "card_code": "24681357",
            "broker": "Exness",
            "platform": "MT5",
            "account_type": "Real",
            "leverage": "1:2000",
            "balance": "100",
            "account_number": "777333",
            "investor_password": "pass",
            "email": "client@example.com",
        },
    )
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
    )
    client.post("/admin/link/1/status", data={"status": "تم الربط بنجاح"})
    response = client.post(
        "/admin/trading-ticket",
        data={
            "card_id": "1",
            "trading_pair": "EURUSD",
            "trade_type": "شراء",
            "lot_size": "0.01",
            "risk_percentage": "30",
            "status": "Live",
            "analysis_note": "الحالة مستقرة.",
            "analysis_image": (BytesIO(b"fake-analysis"), "analysis.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "إدارة تذاكر التداول" in html
    assert "30.00%" in html
    client.post("/logout")
    response = client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
        follow_redirects=True,
    )
    response = client.get("/tickets")
    html = response.get_data(as_text=True)
    assert "حالة حساب التداول" in html
    assert "EURUSD" in html
    assert "Live" in html
    assert "30.00%" in html
    assert "analysis.png" in html or "صورة تحليل الصفقة" in html


def test_referral_signup_and_commission_after_admin_activation(client):
    register_and_login(client)
    response = client.get("/referrals")
    html = response.get_data(as_text=True)
    assert "دعوة الأصدقاء" in html
    assert "CLIENT" in html
    client.post("/logout")
    client.post(
        "/register?ref=CLIENT",
        data={
            "full_name": "صديق مدعو",
            "email": "friend@example.com",
            "referral_code": "CLIENT",
            "password": "StrongPass123",
            "confirm_password": "StrongPass123",
        },
    )
    client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
    )
    response = client.post(
        "/admin/user/3/plan",
        data={"plan": "basic", "subscription_active": "1", "account_status": "نشط"},
        follow_redirects=True,
    )
    assert "إدارة الإحالات" in response.get_data(as_text=True)
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
    )
    response = client.get("/referrals")
    html = response.get_data(as_text=True)
    assert "$2.00" in html
    assert "صديق مدعو" in html


def test_profile_image_and_local_withdrawal_flow(client):
    register_and_login(client)
    response = client.post(
        "/settings/profile",
        data={"profile_image": (BytesIO(b"fake-profile"), "avatar.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "تم تحديث صورة الحساب" in response.get_data(as_text=True)
    response = client.post(
        "/settings/local-withdraw-method",
        data={"local_withdraw_method": "بريدي موب"},
        follow_redirects=True,
    )
    assert "بريدي موب" in response.get_data(as_text=True)
    response = client.get("/withdraw")
    assert "بريدي موب - سحب محلي مباشر" in response.get_data(as_text=True)
    response = client.post(
        "/local-withdraw",
        data={"amount": "75", "ticket_code": "LW-TEST-001"},
        follow_redirects=True,
    )
    assert "الحد الأدنى للسحب هو 10$" in response.get_data(as_text=True)
    client.post(
        "/deposit",
        data={"method": "USDT (TRC20)", "amount": "100", "details": "fund"},
        follow_redirects=True,
    )
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
    )
    client.post("/admin/transaction/1/status", data={"status": "مقبول"})
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
    )
    response = client.post(
        "/local-withdraw",
        data={"amount": "75", "ticket_code": "LW-TEST-001"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "LW-TEST-001" in html
    assert "WhatsApp" in html
    client.post("/logout")
    response = client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "طلبات السحب المحلي" in html
    assert "LW-TEST-001" in html


def test_wallet_transfer_to_marketing_wallet(client, app):
    register_and_login(client)
    client.post(
        "/deposit",
        data={"method": "USDT (TRC20)", "amount": "100", "details": "fund"},
        follow_redirects=True,
    )
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "admin@tribridge.io", "password": "Admin12345"},
    )
    client.post("/admin/transaction/1/status", data={"status": "مقبول"})
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "client@example.com", "password": "StrongPass123"},
    )
    response = client.post(
        "/wallet/transfer-to-marketing",
        data={"amount": "40"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "تم تحويل المبلغ إلى محفظة التسويق بنجاح" in html
    assert "تحويل لمحفظة التسويق" in html
    with read_test_db(app) as db:
        wallet = db.execute("SELECT * FROM marketing_wallets WHERE user_id = 2").fetchone()
        transfer = db.execute(
            "SELECT * FROM wallet_transactions WHERE user_id = 2 AND kind = 'wallet_to_marketing_transfer'"
        ).fetchone()
        assert wallet["balance"] == 40
        assert transfer["amount"] == 40
        assert transfer["status"] == "مقبول"


def test_support_center_uses_rich_support_tables(client, app):
    register_and_login(client)
    response = client.get("/support-center")
    assert response.status_code == 200
    assert "الدعم الفني" in response.get_data(as_text=True)
    response = client.post(
        "/support/messages",
        json={"message": "أحتاج مساعدة في ربط الحساب"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with read_test_db(app) as db:
        message = db.execute("SELECT * FROM support_messages WHERE user_id = 2").fetchone()
        assert message["message"] == "أحتاج مساعدة في ربط الحساب"
        assert message["status"] == "جديدة"
