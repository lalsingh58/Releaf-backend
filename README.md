# ReLeaf: Backend API

Django REST Framework backend for **ReLeaf**, a mobile app that shows live air quality,
nudges users to take a green action (plant a tree / water a plant) when the air is bad, verifies photo
proof, and rewards users with points, streaks and levels.

**Stack:** Django 5.2 · DRF · SimpleJWT · Pillow · django-cors-headers · Open-Meteo · SQLite (dev) / PostgreSQL (prod)

---

## Table of contents
1. [Project structure](#project-structure)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [API reference](#api-reference)
5. [Business rules](#business-rules)
6. [Plugging in AI proof verification](#plugging-in-ai-proof-verification)
7. [Django admin](#django-admin)
8. [Tests](#tests)
9. [PostgreSQL & production notes](#postgresql--production-notes)

---

## Project structure

```
releaf/
├── manage.py
├── requirements.txt
├── .env.example                 # copy to .env
├── config/                      # project package
│   ├── settings.py              # env-driven settings (CORS, JWT, media, DRF, ...)
│   ├── urls.py                  # project-level URLs
│   ├── wsgi.py / asgi.py
└── apps/
    ├── core/                    # shared building blocks
    │   ├── aqi.py               # Open-Meteo client + caching + challenge logic
    │   ├── exceptions.py        # uniform JSON error envelope
    │   ├── validators.py        # image validation (type, size, real content, dimensions)
    │   ├── utils.py             # level calculation, hashing
    │   ├── views.py / urls.py   # /api/aqi/, /api/impact/, /api/health/
    │   └── testing.py           # shared test helpers
    ├── users/                   # accounts & profiles
    │   ├── models.py            # User (email login), Profile, UserStats
    │   ├── signals.py           # auto-create Profile + UserStats for new users
    │   ├── serializers.py / views.py
    │   ├── auth_urls.py         # /api/auth/...
    │   ├── urls.py              # /api/profile/...
    │   └── admin.py
    └── actions/                 # green actions
        ├── models.py            # Action, Proof
        ├── services.py          # points, streaks, levels, approve/reject (business logic)
        ├── verification.py      # PLACEHOLDER for AI verification
        ├── serializers.py / views.py / urls.py
        └── admin.py             # proof moderation (approve/reject actions)
```

---

## Quick start

Requires **Python 3.10+**.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env                 # Windows: copy .env.example .env
#    Edit .env and set DJANGO_SECRET_KEY. Generate one with:
#    python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

# 4. Create the database tables
python manage.py migrate

# 5. Create an admin user (log in with email + password)
python manage.py createsuperuser

# 6. Run the server
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/` and the admin at `http://127.0.0.1:8000/admin/`.

> **Android emulator:** the host machine is `10.0.2.2`, which is already in `DJANGO_ALLOWED_HOSTS` in `.env.example`.
> Run `python manage.py runserver 0.0.0.0:8000` to reach it from a physical phone on the same network.

### Try it with curl

```bash
# Register (returns user + access + refresh tokens)
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Asha Verma","email":"asha@example.com","password":"Gr33n-Action!42"}'

# Login
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"asha@example.com","password":"Gr33n-Action!42"}'

export TOKEN="<paste access token>"

# Live AQI (public)
curl "http://127.0.0.1:8000/api/aqi/?latitude=27.60&longitude=78.05"

# Submit a green action with photo proof
curl -X POST http://127.0.0.1:8000/api/actions/submit/ \
  -H "Authorization: Bearer $TOKEN" \
  -F action_type=plant -F latitude=27.60 -F longitude=78.05 \
  -F description="Planted a neem sapling" -F aqi=165 \
  -F image=@/path/to/photo.jpg

# My stats / profile / leaderboard
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/stats/me/
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/profile/me/
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/leaderboard/

# Update profile (multipart, to include a picture)
curl -X PUT http://127.0.0.1:8000/api/profile/me/ \
  -H "Authorization: Bearer $TOKEN" \
  -F full_name="Asha V." -F bio="Greening Hathras" -F city="Hathras" \
  -F profile_picture=@/path/to/me.jpg
```

---

## Configuration

All settings come from environment variables (or `.env`). See `.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | none (**required** unless `DJANGO_DEBUG=True`) | Django/JWT signing key |
| `DJANGO_DEBUG` | `False` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated hosts |
| `DJANGO_TIME_ZONE` | `Asia/Kolkata` | Streaks are counted per calendar day in this zone |
| `DATABASE_URL` | SQLite `db.sqlite3` | e.g. `postgres://user:pass@host:5432/db` |
| `CORS_ALLOWED_ORIGINS` | empty | Origins for web clients (mobile apps don't need CORS) |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | `60` / `30` | Token lifetimes |
| `AQI_CHALLENGE_THRESHOLD` | `100` | US AQI at/above which the app should trigger a challenge |
| `AQI_CACHE_SECONDS` | `600` | How long AQI per ~1 km cell is cached |
| `PROOF_MAX_SIZE_MB` / `PROOF_MIN_DIMENSION` | `5` / `200` | Proof image limits |
| `PROOF_AUTO_APPROVE` | `True` | `False` = proofs wait for manual approval in the admin |
| `MAX_ACTIONS_PER_DAY` | `5` | Anti-abuse daily cap per user |
| `THROTTLE_ANON` / `THROTTLE_USER` / `THROTTLE_AUTH` / `THROTTLE_SUBMIT` | `60/min` / `300/min` / `10/min` / `30/hour` | DRF rate limits |
| `REDIS_URL` | unset | Shared cache (recommended with multiple workers) |

---

## API reference

All endpoints are under `/api/`. Authenticated endpoints need `Authorization: Bearer <access_token>`.
Lists are paginated (`?page=1&page_size=20`, max 100).

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register/` | public | `{full_name, email, password}` → `{user, access, refresh}` |
| POST | `/api/auth/login/` | public | `{email, password}` → `{access, refresh, user}` |
| POST | `/api/auth/token/refresh/` | public | `{refresh}` → new `access` (+ rotated `refresh`) |
| POST | `/api/auth/logout/` | yes | `{refresh}` → blacklists the refresh token |
| GET  | `/api/auth/me/` | yes | Current user with stats |

### Profile
| Method | Path | Description |
|---|---|---|
| GET | `/api/profile/me/` | My profile: picture, bio, city, stats, rank, recent actions |
| PUT / PATCH | `/api/profile/me/` | Update `full_name`, `bio`, `city`, `profile_picture` (multipart for the picture); `remove_profile_picture=true` deletes it |
| GET | `/api/profile/<user_id>/` | Public profile (no email; only approved actions shown) |
| GET | `/api/profile/me/actions/` | My actions (same as `/api/actions/my/`) |

### Core features
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/aqi/?latitude=..&longitude=..` | public | Live AQI from Open-Meteo + whether to trigger a challenge |
| POST | `/api/actions/submit/` | yes | Multipart: `action_type` (`plant`/`water`), `latitude`, `longitude`, `image`, optional `description`, `aqi` |
| GET | `/api/actions/my/` | yes | My actions. Filters: `?status=pending\|approved\|rejected`, `?action_type=plant\|water` |
| GET | `/api/leaderboard/` | yes | Ranked users + `me` (your own entry) |
| GET | `/api/stats/me/` | yes | Points, level, streaks, total actions, rank |
| GET | `/api/impact/` | public | Community totals (trees planted, plants watered, estimated CO₂) |
| GET | `/api/health/` | public | Liveness probe |

### Example: `GET /api/aqi/`
```json
{
  "location": {"latitude": 27.6, "longitude": 78.05},
  "measured_at": "2026-10-10T12:00",
  "us_aqi": 162,
  "european_aqi": 120,
  "category": "Unhealthy",
  "category_level": 3,
  "pollutants": {"pm2_5": {"value": 71.2, "unit": "μg/m³"}, "pm10": {"value": 110.5, "unit": "μg/m³"}},
  "source": "Open-Meteo",
  "challenge": {
    "triggered": true,
    "threshold": 100,
    "message": "Air quality is poor (AQI 162). Plant a tree or water a plant to take green action!",
    "suggested_actions": [{"type": "plant", "base_points": 50}, {"type": "water", "base_points": 20}]
  }
}
```

### Example: `POST /api/actions/submit/` → `201`
```json
{
  "message": "Great work! You earned 65 points.",
  "points_awarded": 65,
  "leveled_up": false,
  "action": {"id": 1, "action_type": "plant", "points": 65, "points_awarded": true,
             "proof": {"status": "approved", "image": "http://.../media/proofs/1/2026/10/....jpg"}},
  "stats": {"points": 65, "level": 1, "current_streak": 1, "longest_streak": 1, "total_actions": 1, "rank": 1}
}
```

### Error format
Every error uses the same envelope, so the mobile client needs a single parser:
```json
{"error": {"status_code": 400, "code": "validation_error", "message": "Invalid input.",
           "details": {"image": ["Image is too small (40x40px). The shortest side must be at least 200px."]}}}
```
Common codes: `validation_error` (400), `not_authenticated` (401), `daily_limit_reached` (429),
`throttled` (429), `aqi_not_available` (404), `upstream_error` (502).

---

## Business rules

All of this lives in `apps/actions/services.py`.

**Points.** Plant = **50**, water = **20**. If the client sends the `aqi` it displayed, a bonus applies:
AQI ≥ 100 → +10, ≥ 150 → +15, ≥ 200 → +20, ≥ 300 → +30. Tweak `POINTS_PER_ACTION` / `AQI_BONUS_POINTS` in `settings.py`.

**Levels.** Level *n* starts at `100 × (n−1)²` points (L2 = 100, L3 = 400, L4 = 900 ...), with titles from
*Seedling* to *Earth Hero*. Responses include `points_to_next_level` and `level_progress_percent`.

**Streaks.** Counted per calendar day in `DJANGO_TIME_ZONE`:
first action → 1 · same day → unchanged · next day → +1 · a missed day → resets to 1. `longest_streak` is the all-time best.

**Proof validation** (before anything is saved): extension (jpg/jpeg/png/webp), max size, real image content
verified with Pillow (renamed non-images are rejected), allowed format, minimum dimensions.

**Anti-abuse.** The same photo cannot be submitted twice (SHA-256 check) · max `MAX_ACTIONS_PER_DAY` per user ·
rate limits on register/login/submit.

**Approval flow.** Points, total actions and streak are credited only when the proof is **approved**, exactly once.
Rejecting an already-approved proof takes the points back (streaks are left untouched).
With `PROOF_AUTO_APPROVE=True` (default) valid photos are approved instantly; set it to `False` to review them in the admin.

---

## Plugging in AI proof verification

`apps/actions/verification.py` contains `verify_proof_image(proof)`, a **placeholder** that currently approves
(or leaves pending) based on `PROOF_AUTO_APPROVE`. The file includes a commented-out Google Cloud Vision sketch.

To switch to a real verifier:
1. Write a function `verify_proof_image(proof) -> VerificationResult` in a new module, e.g. `apps/actions/cloud_vision.py`.
   Return `APPROVED`, `REJECTED`, or `PENDING` (when the model is unsure, so a human decides).
2. Point the setting at it: `PROOF_VERIFIER=apps.actions.cloud_vision.verify_proof_image`.

Nothing else changes. Scoring, streaks and the admin review queue all keep working.
For production, consider running the check in a background worker (Celery/RQ) and leaving proofs `pending` until it finishes.

---

## Django admin

`/admin/` has every model: **Users** (with Profile and Stats inline), **Profiles**, **User stats**, **Actions** and **Proofs**.
In **Proofs**, select rows and use **Approve selected proofs** / **Reject selected proofs**. These go through the same service
code as the API, so points stay consistent. Proof status is intentionally read-only in the form for that reason.

---

## Tests

```bash
python manage.py test
```

58 tests cover registration/login/JWT, profiles (including picture replacement and cleanup), AQI (mocked Open-Meteo,
caching, errors), submission, image validation, points/streak/level logic, daily limits, duplicate photos,
manual approval/rejection, leaderboard ties and pagination, community impact, and that every admin page renders.

---

## PostgreSQL & production notes

```bash
# .env
DATABASE_URL=postgres://user:password@localhost:5432/releaf
```
`psycopg` is already in `requirements.txt`. Then run `python manage.py migrate`.

Before going live:
- `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY`, correct `DJANGO_ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS` for any web client.
- Serve over HTTPS; set `SECURE_SSL_REDIRECT=True` / `SECURE_HSTS_SECONDS` and uncomment `SECURE_PROXY_SSL_HEADER` in `settings.py` if behind a proxy.
- Run with gunicorn: `gunicorn config.wsgi --workers 3`, and `python manage.py collectstatic` (WhiteNoise serves admin static files).
- **Media files:** uploads are written to `MEDIA_ROOT` and only served by Django when `DEBUG=True`. In production serve `media/`
  with nginx or move to object storage (S3/GCS via `django-storages`).
- Set `REDIS_URL` so throttling and the AQI/impact caches are shared across workers.
- The first live Open-Meteo call could not be exercised from the build sandbox; it is covered by mocked tests built to Open-Meteo's
  documented response format, so run `curl "http://127.0.0.1:8000/api/aqi/?latitude=27.6&longitude=78.05"` once on your machine to confirm.

### Ideas for next steps
Weekly/monthly leaderboards · push notifications when AQI spikes · badges/achievements · async AI verification worker ·
per-city leaderboards using `Profile.city`.
