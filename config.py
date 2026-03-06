import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")   # api-sports.io — real-time lineups
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")            # the-odds-api.com — Pinnacle CLV

SP_ODDS_URL = "https://www.singaporepools.com.sg/en/product/Pages/football_odds.aspx"
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

# Poisson model: max goals to simulate per team
MAX_GOALS = 7

# Claude model for predictions
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Gemini model for John (conversational agent)
GEMINI_MODEL = "gemini-2.5-flash"

# Scheduler: daily report time (SGT = UTC+8)
DAILY_REPORT_HOUR = 8
DAILY_REPORT_MINUTE = 0
SCHEDULER_TIMEZONE = "Asia/Singapore"

# Odds movement alert threshold — % change that triggers a Telegram alert
ODDS_MOVE_THRESHOLD = 8.0

# Value bet push threshold — minimum Kelly edge (%) to trigger an immediate alert
VALUE_BET_KELLY_THRESHOLD = 5.0

# Odds monitor polling interval (minutes)
ODDS_MONITOR_INTERVAL_MINUTES = 30
