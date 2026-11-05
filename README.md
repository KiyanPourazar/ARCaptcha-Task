# Extensible Browser Bot Platform

Web platform for defining, running, and monitoring browser bots. The first bot uses **Selenium** against [demo.arcaptcha.co](https://demo.arcaptcha.co): it clicks **I am not a robot**, extracts `challenge_id`, stores it in run history, submits configured credentials, and only reports **success** when login verification actually succeeds.

## Architecture

```
UI / API  ──►  BotRunner  ──►  BotRegistry  ──►  BrowserBot implementations
                  │                                  │
                  ▼                                  ▼
               SQLite                         Selenium WebDriver
            (Docker volume)                 (local or remote Chrome)
```

| Layer | Responsibility |
| --- | --- |
| `app/api` | HTTP API + launch endpoints |
| `app/services/runner.py` | Run lifecycle, persistence |
| `app/db` | SQLAlchemy models / SQLite |
| `app/bots/base.py` | Bot interface (`BrowserBot`) |
| `app/bots/registry.py` | Registration mechanism |
| `app/bots/arcaptcha_selenium.py` | First Selenium bot |
| `app/static` | Web UI |

Bots are isolated from storage and UI: add a new class, register it, import the module — no core rewrite.

## Prerequisites

- **Docker** + **Docker Compose v2** (recommended path for reviewers)
- Or locally: Python **3.11+**, Chrome/Chromium, matching ChromeDriver
- Network access to `demo.arcaptcha.co` and `widget.arcaptcha.ir`

### Supported platforms

| OS | Arch | Notes |
| --- | --- | --- |
| Linux | x86_64 / amd64 | Primary target |
| macOS | amd64 / arm64 | Docker Desktop; Chrome image is amd64 (emulated on Apple Silicon) |
| Windows | amd64 | Docker Desktop + WSL2 recommended |

> Apple Silicon: first pull of `selenium/standalone-chrome` may be slower under emulation. If sessions fail to start, allocate ≥4 GB RAM to Docker Desktop.

## Quick start (Docker — clean environment)

```bash
git clone <your-repo-url> bot-platform
cd bot-platform
cp .env.example .env
docker compose up --build -d
```

Open the UI: [http://localhost:8080](http://localhost:8080)

Services:

| Service | Port | Purpose |
| --- | --- | --- |
| `platform` | 8080→8000 | Web UI + API |
| `chrome` | 7900 | noVNC viewer for **Headful** runs |
| `chrome` | 4444 (internal) | Selenium WebDriver |

Stop:

```bash
docker compose down
```

Data survives `down`/`up` via the `bot_data` volume. To wipe history: `docker compose down -v`.

## Configuration

Copy `.env.example` → `.env`. Credentials stay out of source:

| Variable | Default | Meaning |
| --- | --- | --- |
| `BOT_USERNAME` / `BOT_PASSWORD` | `demo` / `demo` | Demo site login |
| `TARGET_URL` | `https://demo.arcaptcha.co` | Bot target |
| `DATABASE_URL` | `sqlite:////data/runs.db` | Persistent DB path in container |
| `SELENIUM_REMOTE_URL` | `http://chrome:4444/wd/hub` | Remote WebDriver (Compose) |
| `BOT_STEALTH` | `true` | Anti-automation hardening |
| `HUMANIZE_DELAYS` | `true` | Small random pauses |
| `*_TIMEOUT` | see `.env.example` | Page / CAPTCHA / login waits |

## Web UI usage

1. Open `http://localhost:8080`
2. Select a bot from the registry list
3. Choose **Headless** or **Headful**
4. Click **Start run**
5. Inspect **Run history** (auto-refreshes while a run is active)

Each history row stores: run ID, bot identity, browser mode, start/end times, `challenge_id` (when obtained), final status, and error details. Failed and blocked runs remain visible.

### API (optional)

```bash
curl -s http://localhost:8080/api/bots | jq
curl -s -X POST http://localhost:8080/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"bot_id":"arcaptcha_demo_selenium","browser_mode":"headless"}'
curl -s http://localhost:8080/api/runs | jq
```

## Headful vs Headless

### Headless

Chrome runs with `--headless=new` inside the Selenium container. No viewer needed.

### Headful — desktop (Docker)

1. Start Compose as usual
2. In the UI, select **Headful** and start a run
3. Open **[http://localhost:7900](http://localhost:7900)** (noVNC)
4. Connect (no password when `SE_VNC_NO_PASSWORD=1`)
5. Watch the live Chrome session

### Headful — server / remote host

Same as desktop: publish port `7900` (or tunnel it):

```bash
ssh -L 7900:localhost:7900 user@your-server
# then open http://localhost:7900 locally
```

Ensure the host firewall allows the forwarded port only to trusted clients.

### Headful — local Python (no Docker Chrome)

Leave `SELENIUM_REMOTE_URL` empty in `.env`, install Chrome, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
export DATABASE_URL=sqlite:///./data/runs.db
export SELENIUM_REMOTE_URL=
uvicorn app.main:app --reload --port 8080
```

A real Chrome window opens on the local display for Headful runs.

## Required bot scenario

The `arcaptcha_demo_selenium` bot:

1. Opens `TARGET_URL`
2. Enters `BOT_USERNAME` / `BOT_PASSWORD`
3. Clicks the **I am not a robot** checkbox (iframe-aware)
4. Extracts `challenge_id` (ArCaptcha token via `getArcToken` / widget helpers)
5. Submits the login form
6. Confirms success via UI toast / verification signals — **submit alone is never success**

Statuses: `success` | `failed` | `blocked` | `timeout` | `running` | `pending`.

## Adding a new bot

1. Create `app/bots/my_bot.py` implementing `BrowserBot`
2. Call `register_bot(MyBot())` at module import
3. Import the module from `app/bots/__init__.py`
4. Restart the platform — it appears in the UI/API automatically

Minimal contract example: [`docs/examples/minimal_bot.py`](docs/examples/minimal_bot.py)

```python
from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.registry import register_bot

class MyBot(BrowserBot):
    id = "my_bot"
    name = "My Bot"
    description = "Does one thing"
    engine = "selenium"  # or playwright, etc.

    def run(self, context: BotContext) -> BotResult:
        # ... automation ...
        return BotResult(outcome=RunOutcome.SUCCESS, challenge_id="...", message="ok")

register_bot(MyBot())
```

New browser engines (Playwright, Puppeteer, …) plug in the same way: implement `run()` with that engine; the runner/UI/DB stay unchanged.

## Tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Coverage includes:

| Case | Test |
| --- | --- |
| Main success path | `test_success_flow` |
| Missing `challenge_id` | `test_missing_challenge_id` |
| CAPTCHA blocked | `test_captcha_blocked` / `test_runner_records_blocked` |
| Timeouts | `test_timeout` |
| Unsuccessful verification | `test_submit_alone_is_not_success`, `test_verification_failed_keeps_challenge_id` |
| Persistence of `challenge_id` on failure | `test_runner_persists_challenge_id_on_failure` |
| Registry / API | `test_registry.py`, `test_api.py` |

Example result:

```text
pytest -q
..............                                                   [100%]
14 passed in 1.51s
```

## Bonus: reducing CAPTCHA blocking

ArCaptcha on `demo.arcaptcha.co` actively fingerprints Selenium. With the Docker **remote** WebDriver path, runs commonly end as:

`Blocked! Are you robot? Please refresh the page and try again`

**Approach used here (`DRIVER_MODE=uc`):**

1. **SeleniumBase UC Mode** (undetected-chromedriver lineage): patch chromedriver, attach after Chrome starts, and `uc_click` the checkbox while chromedriver is briefly disconnected
2. When ArCaptcha opens the **slider puzzle**, compute the piece offset with image edge-correlation and drag `.draggable` into place
3. Keep classic stealth flags for the remote path (`BOT_STEALTH`, humanized delays, Tehran TZ in Compose)
4. Prefer **headed/Headful** over headless for UC trials
5. Persist `challenge_id` whenever obtained, and still report `blocked` / `failed` accurately

**How to run the lower-block path (desktop):**

```bash
cp .env.example .env
# DRIVER_MODE=uc
# SELENIUM_REMOTE_URL=   (empty)
pip install -r requirements.txt
mkdir -p data
export DATABASE_URL=sqlite:///./data/runs.db
export SELENIUM_REMOTE_URL=
export DRIVER_MODE=uc
uvicorn app.main:app --port 8080
```

Then start runs as **Headful** in the UI.

**Bench helper:**

```bash
DRIVER_MODE=uc python scripts/bench_block_rate.py --runs 5 --headed
DRIVER_MODE=remote SELENIUM_REMOTE_URL=http://localhost:4444/wd/hub \
  python scripts/bench_block_rate.py --runs 5 --headed
```

**Evidence collected during development (demo.arcaptcha.co):**

| Driver | Immediate `Blocked! Are you robot?` |
| --- | --- |
| Docker Selenium Grid (remote, headful/headless) | Consistently yes |
| SeleniumBase UC Mode on macOS desktop (headed) | Not observed in repeated trials; `challenge_id` appeared after `uc_click` |

Docker Compose still defaults to `DRIVER_MODE=remote` for reproducible reviewer setup with noVNC. Use local UC Mode when optimizing anti-block rate. Accurate blocked/failed reporting remains mandatory.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `platform` unhealthy / cannot reach Chrome | Wait for Chrome healthcheck; `docker compose logs chrome` |
| Headful blank noVNC | Hard-refresh `:7900`; confirm a Headful run is active |
| Always `blocked` | Try Headful + stealth; check region/network access to `*.arcaptcha.ir` |
| `timeout` on page load | Increase `PAGE_LOAD_TIMEOUT`; verify outbound HTTPS |
| Empty history after restart | Do not use `docker compose down -v`; volume must remain |
| Local ChromeDriver mismatch | Use Compose remote WebDriver instead |
| Apple Silicon pull/start issues | Enable Rosetta / increase Docker memory |

```bash
docker compose ps
docker compose logs -f platform
docker compose logs -f chrome
curl -s http://localhost:8080/api/health
```

## Project layout

```text
app/
  api/           # FastAPI routes
  bots/          # Bot interface, registry, Selenium bot
  db/            # Models + SQLite
  services/      # Run orchestration
  static/        # Web UI
docs/examples/   # Minimal new-bot sample
tests/           # pytest suite
docker-compose.yml
Dockerfile
.env.example
```

## Submission checklist

- [x] Docker + Compose
- [x] Sample config without secrets (`.env.example`)
- [x] Tests + commands
- [x] README (setup, modes, UI, persistence, troubleshooting, extensibility)
- [x] Extensible bot interface + registration
- [x] Required Selenium scenario with real verification
