# TriBridge.io / Capital

منصة Flask محلية لإدارة العملاء والربط السريع لحسابات MT4/MT5، مع فترة تجريبية 14 يومًا، محفظة، إيداع وسحب، بطاقات اشتراك، مركز تسويق ذكي، دعم فني غني، تذاكر ذكية، ولوحة أدمن.

## هيكل المشروع

```text
capital/
├── app.py
├── run.py
├── requirements.txt
├── README.md
├── instance/
│   └── capital.db
├── static/
│   ├── css/
│   ├── img/
│   ├── js/
│   └── uploads/
├── templates/
└── tests/
```

## التشغيل على Windows

افتح PowerShell داخل مجلد المشروع ثم نفّذ:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m flask --app app:app run --host=127.0.0.1 --port=5000
```

الرابط المحلي:

```text
http://127.0.0.1:5000
```

يمكن أيضًا التشغيل عبر:

```powershell
python run.py
```

إذا منع PowerShell تفعيل البيئة:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## حساب الأدمن التجريبي

```text
admin@tribridge.io
Admin12345
```

## الاختبارات

```powershell
py -m pytest -q
```

الاختبارات الحالية تغطي التسجيل، الربط السريع، الإيداع، تفعيل البطاقات، تذاكر التداول، الإحالات، السحب المحلي، تحويل المحفظة إلى محفظة التسويق، ورسائل الدعم.

## تجهيز الإنتاج

- اضبط متغير البيئة `SECRET_KEY` بقيمة قوية قبل النشر.
- لا تستخدم قاعدة بيانات التطوير `instance/capital.db` كقاعدة إنتاج حقيقية.
- احتفظ بنسخ احتياطية من مجلدات الرفع داخل `uploads/` و`static/uploads/`.
- شغّل الاختبارات قبل كل نشر:

```powershell
py -m pytest -q
```

## ملاحظات مهمة

- قاعدة البيانات المحلية تُنشأ تلقائيًا في `instance/capital.db`.
- ملفات إثبات الدفع تحفظ محليًا في `uploads/`.
- يمكن للأدمن فتح صور وصول الدفع من لوحة الأدمن عبر مسار محمي `/uploads/<filename>`.
- تم ربط طلبات الربط ببطاقات الاشتراك عبر العمود `subscription_card_id` داخل جدول `link_requests`، ويضاف تلقائيًا عند تشغيل المشروع إذا كانت قاعدة البيانات قديمة.
- صفحات لوحة العميل مفصولة الآن إلى: الرئيسية، البطاقات، الاشتراكات، الربط السريع، المحفظة، الإيداع، السحب، التذاكر، الإعدادات.
- تمت إضافة جدول `trading_tickets` لتذاكر حالة حساب التداول، ويربط `user_id` و`card_id` ببيانات الحساب والصفقة الحالية.
- تذاكر التداول لا تُنشأ إلا لبطاقات اشتراك نشطة ومربوطة بحساب تداول.
- يتم حساب `risk_percentage` تلقائيًا عند إنشاء أو تعديل تذكرة التداول اعتمادًا على الرصيد، الرافعة المالية، وحجم اللوت.
- تمت إضافة نظام الإحالة عبر الجداول: `referrals`, `referral_commissions`, `referral_levels`, `referral_wallet`.
- تم إضافة العمود `referral_enabled` إلى جدول `users` لتعطيل أو تفعيل نظام الإحالة لكل مستخدم.
- تم إضافة العمود `manual_level` إلى `referral_levels` حتى يحتفظ النظام بالمستوى الذي يحدده الأدمن يدويًا.
- عمولات الإحالة لا تُضاف إلا عند تفعيل اشتراك المستخدم المدعو من لوحة الأدمن.
- صورة MT4/MT5 المستخدمة في الربط السريع موجودة في `static/img/mt4_mt5_float.png`.
- صور الحساب الشخصي تحفظ داخل `static/uploads/profile/`، وتعرض صورة افتراضية من `static/img/default_avatar.svg` عند عدم وجود صورة.
- تمت إضافة العمودين `profile_image` و`local_withdraw_method` إلى جدول `users`.
- تمت إضافة جدول `local_withdrawals` لحفظ طلبات السحب المحلي وحالة كل طلب.
- تمت إضافة جدول `payment_requests` لحفظ طلبات الدفع الآمنة برقم مرجع ورمز تأكيد دون حفظ بيانات البطاقة البنكية أو CVV.
- الحد الأدنى للسحب العادي والمحلي هو `10$`، ويتم منع إنشاء الطلب إذا كان رصيد المحفظة أقل من ذلك.
- تمت إضافة العمود `analysis_image` إلى جدول `trading_tickets` لحفظ صورة تحليل الصفقة.
- صور تحليل الصفقات تحفظ داخل `static/uploads/trading_analysis/` وتظهر مباشرة في تذكرة العميل.
- تمت إضافة جداول دعم فني غنية: `support_messages`, `support_replies`, `support_agents`.
- قسم `الدعم الفني` في لوحة العميل مرتبط بنفس رسائل الدعم في لوحة الأدمن.
- تمت إضافة جداول التسويق: `marketing_wallets`, `marketing_campaigns`, `marketing_recharges`, `marketing_tickets`.
- يمكن تحويل الرصيد من المحفظة الرئيسية إلى محفظة التسويق، ويسجل التحويل بنوع `wallet_to_marketing_transfer`.
- صفحة Smart Marketing Center تقرأ رصيد `marketing_wallets` الحقيقي.
- كلمات المرور مشفرة باستخدام Werkzeug.
- هذه نسخة تطوير محلية، ويجب تغيير `SECRET_KEY` عند النشر.

## جدول trading_tickets

الأعمدة:

```text
id
user_id
card_id
mt_account_number
broker_name
leverage
balance
trading_pair
trade_type
lot_size
risk_percentage
analysis_note
analysis_image
status
created_at
```

## جداول الإحالة

`referrals`

```text
id
referrer_id
referred_user_id
referral_code
created_at
```

`referral_commissions`

```text
id
user_id
referred_user_id
subscription_type
amount
status
created_at
```

`referral_levels`

```text
user_id
current_level
manual_level
total_referrals
active_referrals
total_earnings
updated_at
```

## جدول local_withdrawals

```text
id
user_id
method
amount
ticket_code
status
created_at
```

## جدول payment_requests

```text
id
user_id
full_name
payment_method
amount
currency
reference_number
notes
confirmation_code
status
admin_note
created_at
updated_at
```

`referral_wallet`

```text
user_id
balance
total_earned
total_withdrawn
updated_at
```

## جداول الدعم الفني

`support_messages`

```text
id
user_id
guest_name
guest_email
message
status
assigned_agent_id
created_at
```

`support_replies`

```text
id
message_id
agent_id
reply_text
created_at
```

`support_agents`

```text
id
name
image_path
is_active
created_at
```

## جداول Smart Marketing Center

`marketing_wallets`

```text
user_id
balance
total_recharged
total_spent
updated_at
```

`marketing_campaigns`

```text
id
user_id
campaign_name
countries
budget
duration_days
estimated_reach
expected_leads
estimated_clicks
estimated_conversion_rate
status
progress
agent_notes
created_at
updated_at
```

`marketing_recharges`

```text
id
user_id
amount
payment_method
transaction_number
proof_filename
status
created_at
```

`marketing_tickets`

```text
id
user_id
campaign_id
title
message
status
created_at
```
