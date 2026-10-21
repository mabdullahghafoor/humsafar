# Running the Humsafar backend (for Talha)

Goal: run the API on your PC and call it from the Flutter app.
Short version: **start Postgres, run 5 commands, open the Postman check, point the app at the right address.**

## 1. One-time setup (PowerShell)

You need Python 3.11+ and PostgreSQL (already installed if you followed the Getting Started guide).

```powershell
cd D:\FYP\humsafar\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `backend\.env` and change two lines:
- `DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/humsafar_dev` (your own postgres password)
- `JWT_SECRET_KEY=` any long random text. To make one: `python -c "import secrets; print(secrets.token_hex(32))"`

Create the empty database once (any one of these):
- pgAdmin: right-click Databases, Create, name `humsafar_dev`, or
- `psql -U postgres -c "CREATE DATABASE humsafar_dev;"`

Build the tables:

```powershell
alembic upgrade head
```

## 2. Every time you work

```powershell
cd D:\FYP\humsafar\backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`--host 0.0.0.0` is what lets the emulator or a real phone reach the API. Leave this window open.

Check it works: open http://localhost:8000/health in a browser. It should answer `ok`.
All endpoints with a "try it" page: http://localhost:8000/docs

> After you pull new code from `dev`, run `alembic upgrade head` again. New tasks can add columns.

## 3. Which address does the app use?

| App runs on | Base URL |
|---|---|
| Android **emulator** | `http://10.0.2.2:8000` |
| Real Android phone on the same Wi-Fi as your PC | `http://<your PC's IP>:8000` (find it with `ipconfig`, the "IPv4 Address") |
| Real phone by USB | run `adb reverse tcp:8000 tcp:8000`, then use `http://localhost:8000` |
| Flutter web / Windows desktop | `http://localhost:8000` |

Keep the base URL in **one place** in your code so you change it once.

Real phone on Wi-Fi: Windows Firewall may block port 8000. If the phone cannot connect, allow Python through the firewall for private networks.

Android also blocks plain `http` by default. For development, in `android/app/src/main/AndroidManifest.xml` add this to the `<application ...>` tag:
`android:usesCleartextTraffic="true"`
(Remove it when we use https for real.)

## 4. Test accounts and fake codes (no real SMS or KYC yet)

- Phone OTP is always `123456`. The request call also returns it as `dev_otp`.
- Dependent KYC (`kyc-verify`): a CNIC ending in `0` fails, ending in `9` is pending the first time and verified the second time, anything else is verified. A `liveness_image` starting with `FAIL` fails.
- Register needs: `email`, `phone` (03001234567 style), `password` (8+), `full_name` (2+ letters), `role`.

## 5. Typical order for a full flow

1. Guardian: register, login, verify phone (OTP `123456`).
2. Dependent: register, `kyc-verify` (says "waiting for guardian").
3. Guardian: link to the Dependent (needs the Dependent's `user_id`).
4. Dependent can now log in.

The exact bodies and errors are in `docs/api/` (start with `README.md`). Every error looks like `{ "error": { "code", "message", "details" } }`. Branch on `code`, not `message`.

## 6. Quick Postman check

Import both files from `backend\postman` (Replace), choose environment **Humsafar - Local**, run the collection. All green means your backend is healthy.

## 7. If something goes wrong

| Problem | Fix |
|---|---|
| `connection refused` from the app | uvicorn not running, or you used `localhost` on the emulator (use `10.0.2.2`) |
| Works in browser, not on phone | firewall, or not on the same Wi-Fi, or missing `--host 0.0.0.0` |
| `password authentication failed` | wrong password in `.env` `DATABASE_URL` |
| `relation "users" does not exist` | run `alembic upgrade head` |
| `column ... full_name does not exist` | run `alembic upgrade head` (you pulled new code) |
| Cleartext / `Cleartext HTTP traffic not permitted` | add `usesCleartextTraffic` (section 3) |

## 8. Going live (Task 6.5)
With `ENVIRONMENT=production` the server refuses to start unless these are set in `.env`: `JWT_SECRET_KEY` (32+ random characters), `RECORDS_ENCRYPTION_KEY` (32+ random characters, never change it later), `DEBUG=false`, `ENFORCE_HTTPS=true`, `RATE_LIMIT_ENABLED=true`, and a remote database URL ending in `?sslmode=require`. Behind Render or another proxy also set `TRUST_PROXY_HEADERS=true`. Check any environment with `python -m app.scripts.security_audit` (prints PASS / WARN / FAIL and what is protected how). Details: `docs/backend/security_encryption.md`.

