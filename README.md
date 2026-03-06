# Singapore Pools Football AI Agent

A Telegram bot that scrapes live odds from Singapore Pools, runs a Poisson statistical model, and routes every prediction through **John** — an autonomous AI sports betting agent powered by Gemini 2.5 Flash.

## What John Does

John is not a simple prediction script. For every match he:

1. **Runs the Poisson model** — computes expected goals (xG), win/draw/lose probabilities, and O/U probabilities using team stats and H2H records from football-data.org
2. **Searches for live intel** — autonomously queries DuckDuckGo for current injury news, suspensions, and lineup hints for both teams
3. **Adjusts his estimates** — explicitly states how player absences shift the Poisson baseline
4. **Calculates the edge** — computes implied probability vs his adjusted probability, Kelly stake, and BET/PASS/MARGINAL verdict
5. **Writes a reasoned verdict** — covering both model numbers and qualitative factors

John also maintains persistent memory across sessions (`MEMORY.md`, `BRAIN.md`, `LEARNINGS.md`) and runs a self-review every 4 hours.

## Architecture

```
singaporepools/
├── main.py                        # Entry point: Telegram bot + scheduler
├── config.py                      # Env vars
├── bot/
│   ├── handlers.py                # Telegram command handlers
│   ├── john.py                    # John's AI engine + prediction pipeline
│   └── formatter.py               # MarkdownV2 formatting helpers
├── scraper/pools_scraper.py       # Playwright scraper → Match objects
├── data/football_api.py           # football-data.org client
├── predictor/
│   ├── poisson.py                 # Poisson xG model
│   └── claude_predictor.py        # Claude fallback predictor
├── scheduler/daily_report.py      # APScheduler 08:00 SGT daily push
├── SOUL.md                        # John's identity and persona
├── MEMORY.md                      # Persistent memory across sessions
├── BRAIN.md                       # Live working memory
├── SKILLS.md                      # John's capability stack
├── LEARNINGS.md                   # Error log and self-generated rules
├── HEARTBEAT.md                   # Autonomous thinking loop definition
└── self-review.md                 # 4-hour self-audit template
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and command list |
| `/matches` | List upcoming SP fixtures with live odds |
| `/predict` | John's full analysis for all matches (Poisson + live research + edge calc) |
| `/reset` | Clear John's conversation history |
| Any message | Chat directly with John |

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/salvestr0/singapore-pools-football-ai-agent
cd singapore-pools-football-ai-agent
pip install -r requirements.txt
python3 -m playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real API keys
```

You need:
- **Telegram Bot Token** — from [@BotFather](https://t.me/BotFather)
- **Telegram Chat ID** — your personal or group chat ID (bot only responds to this)
- **Gemini API Key** — from [Google AI Studio](https://aistudio.google.com) (for John)
- **Anthropic API Key** — from [console.anthropic.com](https://console.anthropic.com) (for `/predict` fallback)
- **Football Data API Key** — from [football-data.org](https://www.football-data.org) (free tier works)

### 3. Run

```bash
python3 main.py
```

The bot starts polling Telegram and the scheduler fires John's daily report at **08:00 SGT**.

## Stack

- Python 3.14
- `google-genai` 1.x — Gemini 2.5 Flash (John's brain)
- `python-telegram-bot` 21.x — Telegram interface
- `playwright` — headless Chromium for SP odds scraping
- `scipy` / `numpy` — Poisson model
- `duckduckgo-search` — live football news search
- `apscheduler` — daily report scheduling
- `anthropic` — Claude Haiku fallback predictor
