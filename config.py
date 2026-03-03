# Конфигурация бота
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Affise API
AFFISE_API_URL = os.getenv("AFFISE_API_URL", "https://api-xpartners.affise.com")
AFFISE_API_KEY = os.getenv("AFFISE_API_KEY", "")

# Postback base URL
POSTBACK_BASE_URL = "https://offers.x-partners.com/postback"

# Таймауты
REQUEST_TIMEOUT = 30

# Прокси для открытия ссылок (опционально)
# Формат: http://user:pass@host:port или socks5://user:pass@host:port
# Если не задан — ссылки открываются напрямую
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

# Базовый URL для трекинг-ссылок (click). Используется для формирования ссылок вида /click?pid=X&offer_id=Y
TRACKING_CLICK_BASE = os.getenv("TRACKING_CLICK_BASE", "https://trk.xplink")

# Домены трекеров: click_id в следующем редиректе после этих доменов, offer_id и pid — из URL этих доменов
TRACKER_DOMAINS = [
    "trk.xplink",
    "trk.goxp.tech",
    "trk.xpgoal.io",
    "trk.xplead.io",
]

# Файл со списком админов (создаётся автоматически)
ADMINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admins.json")

# Лог запросов доступа (для лимита 3 в день)
REQUEST_ACCESS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "request_access_log.json")

# Лимит запросов доступа в день
REQUEST_ACCESS_LIMIT_PER_DAY = 3

# SQLite для логов постбеков
POSTBACKS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postbacks.db")
