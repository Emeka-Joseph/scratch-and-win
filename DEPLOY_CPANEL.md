# Deploying to cPanel

The app runs under cPanel's **Setup Python App** (Phusion Passenger) with a cPanel **MySQL** database.
You need a cPanel plan that shows "Setup Python App" under *Software* (CloudLinux hosting), with Python **3.9 or newer**.

## 1 · Build the upload package (on your PC)

```bash
python deploy/package.py
```
This creates `dist/razzmattazz_promo_<date>.zip`. It excludes `.env`, the local database, uploaded logos and tests.

## 2 · Create the MySQL database

cPanel → **MySQL® Databases**:
1. Create a database, e.g. `promo` (cPanel names it `cpuser_promo`).
2. Create a user with a strong password (e.g. `cpuser_promouser`).
3. **Add user to database** → tick **ALL PRIVILEGES**.

To set the character set, open phpMyAdmin → database → *Operations* → Collation `utf8mb4_unicode_ci`. Arabic names need this.

## 3 · Domain and SSL

- Use a subdomain such as `promo.yourdomain.com`. cPanel → **Domains** → create it.
- cPanel → **SSL/TLS Status** → run **AutoSSL** so the domain has a certificate. HTTPS is required: the staff camera scanner and the secure login cookies don't work without it.

## 4 · Create the Python app

cPanel → **Setup Python App** → **Create Application**:

| Field | Value |
|---|---|
| Python version | 3.11 (or the newest offered, minimum 3.9) |
| Application root | `razzmattazz_promo` (a folder in your home directory, **not** inside `public_html`) |
| Application URL | `promo.yourdomain.com` (leave the path empty) |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

Click **Create**, then **Stop App** while you upload the files.

At the top of the page, cPanel shows a command like
`source /home/cpuser/virtualenv/razzmattazz_promo/3.11/bin/activate && cd /home/cpuser/razzmattazz_promo`.
Copy it; you need it for SSH.

## 5 · Upload the code

cPanel → **File Manager** → open `razzmattazz_promo` → **Upload** the zip → right-click → **Extract**. Then delete the zip.
`passenger_wsgi.py` must sit directly in `razzmattazz_promo/`, next to the `app/` folder.

## 6 · Configure `.env`

In File Manager, copy `.env.production.example` to `.env` in the same folder and edit it:

- `SECRET_KEY`: a long random value. Generate one locally with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `PUBLIC_BASE_URL=https://promo.yourdomain.com`: scheme and domain only, with no trailing slash and no path.
- `DATABASE_URL=mysql+pymysql://cpuser_promouser:PASSWORD@localhost:3306/cpuser_promo?charset=utf8mb4`.
  URL-encode special characters in the password: `@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`.
- `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`: the first group login.
- `MAIL_*`: a cPanel mailbox, e.g. `mail.yourdomain.com`, port `465`, `MAIL_USE_SSL=1`, `MAIL_USE_TLS=0`, or the Gmail app password.

`.env` stays private in the application root. Passenger only serves the app, never files from this folder.

## 7 · Install packages and create the tables

Back in **Setup Python App** → edit the app:
1. In *Configuration files*, add `requirements.txt` → **Run Pip Install**.
2. In *Execute python script*, enter `deploy/bootstrap.py` → **Run Script**.
   It checks the database connection, creates the tables and the superadmin, and confirms the uploads folder is writable.

**Or over SSH / cPanel Terminal:**
```bash
source /home/cpuser/virtualenv/razzmattazz_promo/3.11/bin/activate && cd /home/cpuser/razzmattazz_promo
pip install -r requirements.txt
python deploy/bootstrap.py
```

## 8 · Start and secure

1. **Start App** (or **Restart**).
2. Open `public_html/promo.yourdomain.com/.htaccess` in File Manager (the subdomain's document root). Paste the lines from `deploy/htaccess-https.txt` at the top and keep the Passenger lines cPanel added.
3. Go to `https://promo.yourdomain.com/login`, sign in as the superadmin and **change the password**.
4. Superadmin → **Settings** → send a **test email**.
5. Create the sub-brands, then print the QR posters. Posters use `PUBLIC_BASE_URL`, so print them only after the live domain is set.

## Updating the live site

1. `python deploy/package.py` on your PC.
2. **Stop App** → upload and extract over the existing folder. `.env` and `app/static/uploads/` are not in the zip, so they are kept.
3. If `requirements.txt` changed, **Run Pip Install**.
4. Run `deploy/bootstrap.py`. It only creates missing tables and never deletes data.
5. **Start App**. You can also restart by touching `tmp/restart.txt` in the application root.

> `bootstrap.py` creates new tables but does not alter columns on tables that already exist. If a later version changes an existing table, it will come with an SQL upgrade script.

## Backups

- cPanel → **Backup** → download a *MySQL database* backup regularly, at least before each update.
- Back up `app/static/uploads/` (brand logos) with File Manager → *Compress*.
- The superadmin's CSV/Excel exports give you an audit copy of every participant and redemption.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "We're sorry, but something went wrong" / 500 on every page | Open the Passenger log: Setup Python App → app → *Passenger log file*, or `stderr.log` in the app root. A `Production configuration error` means `.env` is missing a value; the message says which one. |
| `Access denied for user` | Use the full prefixed names (`cpuser_...`), check the user has ALL PRIVILEGES and URL-encode the password. |
| `ModuleNotFoundError` | Run Pip Install again for the same Python version the app uses. |
| Emails not arriving | Settings → test email. Many hosts block outbound port 587/465 to external SMTP servers like Gmail; use the cPanel mailbox's own server. Add SPF/DKIM in cPanel → **Email Deliverability** so mail isn't marked as spam. |
| Logos don't save | `app/static/uploads` must be writable (permissions 755, owned by your cPanel user). |
| Login loops back to the sign-in page | The site is being opened over `http://`. Add the HTTPS redirect (step 8), or set `TRUST_PROXY=1` if Cloudflare is in front. |
| Code changes don't show | Restart the app. Passenger caches the running code. |
