# Razzmattazz Hospitality Group — Scratch & Win Promo Platform

Flask + MySQL platform with three connected modules:

| Route | Who | What |
|---|---|---|
| `/admin` | Group **superadmin** (black & red) | Create sub-brands (name EN/AR, logo, colours, goods & prizes, campaign rules, admin login), monitor every brand live, audit log, CSV / Excel exports, uniqueness settings |
| `/brand` (sign in at `/b/<brand>/login`) | **Brand admin** and **branch staff** (themed in the brand's colours) | Campaign rules (minimum bill, fallback voucher %), prize stock & odds, branches, team, printable QR posters, scan & redeem, participants, exports |
| `/p/<brand>/<branch>` | **Customers** (mobile, Arabic / English) | Language choice → register (name, mobile, email, T&C) → 7-character email code → scratch card → prize, QR and 8-character claim code |

## Customer journey

1. Staff check the bill meets the brand's **minimum spend**, then present the branch's printed QR poster.
2. The guest scans it, picks **English or العربية** (the whole UI, emails included, follows that choice; Arabic is right-to-left), and registers.
3. A **7-character code** (letters + numbers) is emailed. Wrong attempts, expiry and resend cool-downs are enforced.
4. On verification the server draws the prize at random. Every remaining unit of stock goes into one shuffled pool, so each unit has the same chance and a prize's odds equal its share of what's left. Stock is taken atomically, and the brand's **X% voucher** is given once the pool is empty. The 7-character verify code, 8-character claim code and QR token come from a cryptographic random generator.
5. The guest scratches the coating to reveal the prize name, a **QR code** and an **8-character claim code**, and receives a confirmation email.
6. Staff scan the QR (in-app camera scanner, or the phone camera opens the link) or type the code, then tap **Won & delivered**. A receipt reference (e.g. `R261027-7KQ4M2`) is generated automatically and appears on the screen, in the participant record and in exports. Redemption is atomic, so a second scan shows "already redeemed". It appears instantly on the brand and group dashboards.

**One customer, one gift:** the email and mobile (normalised, so `+966…` and `00966…` match) are unique identifiers. The superadmin chooses the scope in Settings: per campaign (default), per sub-brand, or group-wide.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit (see below)
set FLASK_APP=run.py          # PowerShell: $env:FLASK_APP="run.py"
flask init-db                 # create tables
flask create-superadmin       # uses SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD from .env
flask seed-demo               # optional: demo brand "Oak Grill"
python run.py                 # http://127.0.0.1:9800
```

### MySQL
```
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/razzmattazz_promo?charset=utf8mb4
```
Create the database with `CREATE DATABASE razzmattazz_promo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;` then run `flask init-db`. If `DATABASE_URL` is empty, the app uses `instance/dev.db` (SQLite) for local development.

### Important settings
- `PUBLIC_BASE_URL`: the address baked into QR codes and emails. For phone testing on the same Wi-Fi, use your LAN IP (e.g. `http://192.168.1.20:9800`). In production, use your HTTPS domain. **Reprint posters if it changes.**
- `APP_TIMEZONE`: drives "today" totals and the dates shown (default `Asia/Riyadh`).
- `MAIL_*`: SMTP settings. `MAIL_SUPPRESS_SEND=1` prints emails to the console instead of sending them.
- The in-browser camera scanner needs **HTTPS** (or localhost). Staff can always use the phone camera, which opens the redeem link directly.

## Production
- **cPanel:** follow [DEPLOY_CPANEL.md](DEPLOY_CPANEL.md). It covers `passenger_wsgi.py`, `deploy/bootstrap.py` and `deploy/package.py`.
- Other servers: `gunicorn -w 4 wsgi:app` (Linux) or `waitress-serve --port=8000 wsgi:app` (Windows), behind HTTPS.
- With `FLASK_ENV=production` the app uses secure cookies. It refuses to start if `SECRET_KEY` is weak, the database is SQLite or `PUBLIC_BASE_URL` isn't https. Template: `.env.production.example`.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```
These cover the full flow (brand creation → registration → email code → scratch → staff redemption → exports), stock exhaustion and fallback, sold out, group-wide uniqueness, brand isolation and form validation.

## Structure
```
app/
  __init__.py        app factory, filters, error pages
  models.py          User, Brand, Branch, Campaign, Prize, Participant, Award, AuditLog, Setting
  services.py        uniqueness, random stock draw, atomic stock & redemption
  reports.py         KPIs, trends, breakdowns, export rows
  forms.py           shared form validation
  i18n.py            English / Arabic strings
  cli.py             init-db, create-superadmin, seed-demo
  blueprints/        auth · superadmin · brand · customer
  utils/             mailer, qr, exports (csv/xlsx), audit, theming, codes, time
  templates/         layouts, superadmin, brand, customer, emails
  static/            css, js, uploads (logos)
deploy/              bootstrap.py (tables + superadmin), package.py (upload zip), htaccess-https.txt
passenger_wsgi.py    cPanel / Passenger entry point
wsgi.py              gunicorn / waitress entry point
```
