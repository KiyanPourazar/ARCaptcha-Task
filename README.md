# Extensible Browser Bot Platform

Platform for defining, running, and monitoring browser bots.

The first bot targets [demo.arcaptcha.co](https://demo.arcaptcha.co) with **Selenium** + **UC Mode**:

1. Opens the demo page  
2. Fills username / password (`demo` / `demo` by default)  
3. Clicks **I'm not a robot**  
4. Solves the slider puzzle when ArCaptcha shows it  
5. Extracts `challenge_id` and stores it in run history  
6. Submits login and reports **success only after real verification**  
   (form submit alone is never treated as success)

Failed / blocked / timeout runs stay visible in history, including any `challenge_id` already obtained.

**Local and server use the same driver path:** `DRIVER_MODE=uc` (SeleniumBase UC Mode). Docker Compose embeds Chrome + Xvfb + noVNC so the server path is not limited to classic Selenium Grid fingerprinting.

---

## Quick start (Docker — local or server)

```bash
git clone https://github.com/KiyanPourazar/ARCaptcha-Task.git
cd ARCaptcha-Task
cp .env.example .env
docker compose up --build -d
```

| URL | Purpose |
| --- | --- |
| http://localhost:8080 | Web UI + API |
| http://localhost:7900 | noVNC (watch **Headful** Chrome) |

```bash
docker compose ps
curl -s http://localhost:8080/api/health
# → {"status":"ok"}
```

On a remote server, open the UI on `:8080`, or tunnel Headful viewing:

```bash
ssh -L 8080:localhost:8080 -L 7900:localhost:7900 user@server
```

Stop:

```bash
docker compose down
```

History is kept in the `bot_data` volume across restarts. Wipe it with `docker compose down -v`.

### Run a successful flow in Docker

1. Open http://localhost:8080  
2. Open http://localhost:7900 → **Connect** (optional, for watching)  
3. Choose **Headful** → **Start run**  
4. Watch checkbox / slider on noVNC; history should move to `success` when login verifies  

ArCaptcha can still block some sessions (fingerprint / network). Retries and Headful usually fare better than Headless.

---

## Local desktop (without Docker)

Requirements: Python 3.11+, Google Chrome, network access to `demo.arcaptcha.co` and `*.arcaptcha.ir`.

```bash
cd ARCaptcha-Task
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
mkdir -p data

cp .env.example .env
# Edit .env:
#   DRIVER_MODE=uc
#   SELENIUM_REMOTE_URL=
#   DATABASE_URL=sqlite:///./data/runs.db

export DRIVER_MODE=uc
export SELENIUM_REMOTE_URL=
export DATABASE_URL=sqlite:///./data/runs.db

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080 → **Headful** → **Start run**.  
A real Chrome window opens on the desktop (no need for port 7900).

---

## Web UI

1. Open http://localhost:8080  
2. Select `ARCaptcha Demo (Selenium)`  
3. Choose **Headless** or **Headful**  
4. Click **Start run**  
5. Watch **Run history** (auto-refreshes while running)

Stored per run: run ID, bot id/name, browser mode, start/end times, `challenge_id`, final status, error details.

### Headful viewing

| Mode | How to watch |
| --- | --- |
| Docker Headful | Open http://localhost:7900 → Connect → then Start run in the UI |
| Docker on a server | `ssh -L 7900:localhost:7900 user@server` then open local `:7900` |
| Local UC (no Docker) | Chrome window appears on the host display |

Headless Docker runs use a private Xvfb and are not shown on `:7900` (expected).

---

## Configuration

Copy `.env.example` → `.env`. Secrets stay out of git.

| Variable | Default | Meaning |
| --- | --- | --- |
| `BOT_USERNAME` / `BOT_PASSWORD` | `demo` / `demo` | Demo credentials |
| `TARGET_URL` | `https://demo.arcaptcha.co` | Bot target |
| `DATABASE_URL` | `sqlite:////data/runs.db` | SQLite path (Compose volume) |
| `SELENIUM_REMOTE_URL` | empty | Only for classic Grid; leave empty with UC |
| `DRIVER_MODE` | `uc` | `uc` (recommended) or `remote` |
| `CHROME_BINARY` | auto / Compose sets path | Optional Chrome binary override |
| `BOT_STEALTH` | `true` | Anti-automation Chrome flags (remote path) |
| `HUMANIZE_DELAYS` | `true` | Small random pauses |
| `PAGE_LOAD_TIMEOUT` / `CAPTCHA_WAIT_TIMEOUT` / `LOGIN_WAIT_TIMEOUT` | see `.env.example` | Timeouts (seconds) |

Compose sets `DRIVER_MODE=uc`, clears `SELENIUM_REMOTE_URL`, and runs Chrome inside the `platform` container (same anti-detect stack as local).

---

## Architecture (extensible by design)

```
UI / API  →  BotRunner  →  BotRegistry  →  BrowserBot implementations
   ↓                              ↓
SQLite                      Selenium / UC Mode
(Docker volume)
```

| Piece | Role |
| --- | --- |
| `app/bots/base.py` | Bot interface (`BrowserBot`, `BotContext`, `BotResult`) |
| `app/bots/registry.py` | Registration |
| `app/bots/arcaptcha_selenium.py` | Required ArCaptcha bot |
| `app/bots/puzzle.py` | Slider puzzle solver |
| `app/bots/uc_session.py` | SeleniumBase UC session helper |
| `app/services/runner.py` | Run lifecycle + persistence |
| `app/db` | SQLAlchemy models |
| `app/api` | REST API |
| `app/static` | Web UI |

Bot implementations are separated from execution, storage, and UI. New bots / engines can be added without rewriting the core.

### Add a new bot

1. Create `app/bots/my_bot.py` implementing `BrowserBot`  
2. Call `register_bot(MyBot())` at import time  
3. Import it from `app/bots/__init__.py`  
4. Restart — it appears in UI/API  

Minimal example: [`docs/examples/minimal_bot.py`](docs/examples/minimal_bot.py)

```python
from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.registry import register_bot

class MyBot(BrowserBot):
    id = "my_bot"
    name = "My Bot"
    description = "Does one thing"
    engine = "selenium"

    def run(self, context: BotContext) -> BotResult:
        return BotResult(outcome=RunOutcome.SUCCESS, message="ok")

register_bot(MyBot())
```

---

## Tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

```text
...............
15 passed
```

Covered cases include: success path, missing `challenge_id`, CAPTCHA blocked, timeouts, unsuccessful verification, `challenge_id` persistence on failure, registry/API, and puzzle offset helper.

---

## Bonus: reducing CAPTCHA blocking

ArCaptcha fingerprints automation. Measured behavior during development:

| Driver | Typical result |
| --- | --- |
| Classic Selenium Grid (`DRIVER_MODE=remote`) | Often `Blocked! Are you robot?` |
| UC Mode headed / Xvfb (`DRIVER_MODE=uc`) — local **and** Docker | Checkbox + slider can complete; login verified with `You are logged in successfully!` |

Techniques:

- SeleniumBase UC Mode (`uc_click`, chromedriver disconnect during critical clicks)
- Slider puzzle solve via image edge-correlation + drag of `.draggable`
- Stealth Chrome flags + humanized delays
- Prefer Headful / headed (or Xvfb) over Chrome `--headless`
- Docker runs UC Chrome in-container (not remote Grid) so server matches local

Bench helper:

```bash
DRIVER_MODE=uc python scripts/bench_block_rate.py --runs 5 --headed
```

Blocked/failed attempts are still reported accurately.

---

## Prerequisites / platforms

| OS | Arch | Notes |
| --- | --- | --- |
| Linux | x86_64 / amd64 | Primary server target |
| macOS | amd64 / arm64 | Docker Desktop; Compose pins `linux/amd64` for Chrome |
| Windows | amd64 | Docker Desktop + WSL2 recommended |

Needs: Docker Compose v2 **or** Python 3.11+ with Chrome, plus HTTPS access to the ArCaptcha demo endpoints.

---

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Port `8000` already in use | Compose maps UI to **8080** |
| Still `blocked` occasionally | Retry Headful; check VPN/network to `*.arcaptcha.ir` |
| Site / widget timeout | Check VPN/network to `demo.arcaptcha.co` and `*.arcaptcha.ir` |
| Headful blank on `:7900` | Connect noVNC first, then start a **Headful** run |
| Empty history after restart | Do not use `docker compose down -v` |
| Apple Silicon slow Chrome | Give Docker ≥4 GB RAM; image is `linux/amd64` |

```bash
docker compose logs -f platform
curl -s http://localhost:8080/api/bots
curl -s http://localhost:8080/api/runs
```

---

## Project layout

```text
app/
  api/            # FastAPI routes
  bots/           # Interface, registry, ArCaptcha bot, puzzle, UC helper
  db/             # SQLAlchemy + SQLite
  services/       # Run orchestration
  static/         # Web UI
docs/examples/    # Minimal new-bot sample
scripts/          # Entrypoint + block-rate bench
tests/
docker-compose.yml
Dockerfile
.env.example
```

## API cheatsheet

```bash
curl -s http://localhost:8080/api/bots
curl -s -X POST http://localhost:8080/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"bot_id":"arcaptcha_demo_selenium","browser_mode":"headful"}'
curl -s http://localhost:8080/api/runs
```
