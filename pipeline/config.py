"""ค่าตั้งต้นของระบบ — ปรับน้ำหนักปัจจัยและพารามิเตอร์ต่างๆ ได้ที่นี่"""
from pathlib import Path

from .universe import FOREIGN_STOCKS, THAI_STOCKS

ROOT = Path(__file__).resolve().parent.parent
WEB_DATA = ROOT / "web" / "data"
CACHE_DIR = ROOT / "cache"

MARKETS = {
    "th": {
        "label": "หุ้นไทย",
        "currency": "THB",
        "stocks": {f"{s}.BK": name for s, name in THAI_STOCKS.items()},
        # ข้อมูลดัชนี ^SET.BK ของ Yahoo มีช่วงขาดหาย จึงใช้ ETF ที่อ้างอิง SET50 เป็นตัวเทียบ
        "benchmark": "TDEX.BK",
        "benchmark_fallback": "^SET.BK",
        "benchmark_label": "SET50 (ETF TDEX)",
        "news_lang": "th",
        # ใช้เฉพาะราคาปิด: ถ้ารันก่อนเวลานี้ (เวลาท้องถิ่นของตลาด) จะตัดแท่งราคาของวันนี้ที่ยังไม่จบออก
        "timezone": "Asia/Bangkok",
        "close_time": (16, 45),
    },
    "us": {
        "label": "หุ้นต่างประเทศ",
        "currency": "USD",
        "stocks": dict(FOREIGN_STOCKS),
        "benchmark": "^GSPC",
        "benchmark_fallback": "SPY",
        "benchmark_label": "S&P 500",
        "news_lang": "en",
        "timezone": "America/New_York",
        "close_time": (16, 15),
    },
}

# ดัชนีที่แสดงบนแถบภาวะตลาด: (สัญลักษณ์, ชื่อ, สัญลักษณ์สำรองถ้าข้อมูลขาดช่วง, ชื่อสำรอง)
MARKET_STRIP = [
    ("^SET.BK", "SET", "TDEX.BK", "SET50 (TDEX)"),
    ("^GSPC", "S&P 500", "SPY", "S&P 500 (SPY)"),
    ("^IXIC", "Nasdaq", "QQQ", "Nasdaq 100 (QQQ)"),
    ("THB=X", "USD/THB", None, None),
]

# ระยะเวลาลงทุน -> จำนวนวันทำการโดยประมาณ
HORIZONS = {"1m": 21, "3m": 63, "6m": 126, "9m": 189}
HORIZON_LABELS = {"1m": "1 เดือน", "3m": "3 เดือน", "6m": "6 เดือน", "9m": "9 เดือน"}

# กลุ่มปัจจัย
GROUPS = {
    "value": "มูลค่า (ถูก/แพง)",
    "quality": "คุณภาพกิจการ",
    "growth": "การเติบโต",
    "momentum": "แนวโน้มราคา",
    "analyst": "มุมมองนักวิเคราะห์",
    "news": "ข่าวล่าสุด",
    "risk": "ความเสี่ยงต่ำ",
}

# น้ำหนักของแต่ละกลุ่มปัจจัยตามระยะเวลาลงทุน (รวม = 1) -> คะแนนแนะนำ
# ระยะสั้นให้น้ำหนักแนวโน้มราคาและข่าวมาก ระยะยาวให้น้ำหนักปัจจัยพื้นฐานมาก
# (ทดสอบย้อนหลัง 2017-2026: โมเมนตัมช่วยได้ชัดในหุ้นไทย, หุ้นผันผวนต่ำไม่ได้ให้ผลตอบแทนดีกว่า
#  จึงให้น้ำหนักกลุ่มความเสี่ยงต่ำไว้เพื่อคุมความเสี่ยงเท่านั้น)
WEIGHTS = {
    "1m": {"momentum": 0.25, "news": 0.15, "analyst": 0.10, "risk": 0.08,
           "value": 0.12, "quality": 0.15, "growth": 0.15},
    "3m": {"momentum": 0.22, "news": 0.10, "analyst": 0.13, "risk": 0.07,
           "value": 0.16, "quality": 0.17, "growth": 0.15},
    "6m": {"momentum": 0.18, "news": 0.06, "analyst": 0.14, "risk": 0.06,
           "value": 0.20, "quality": 0.20, "growth": 0.16},
    "9m": {"momentum": 0.15, "news": 0.04, "analyst": 0.14, "risk": 0.05,
           "value": 0.24, "quality": 0.22, "growth": 0.16},
}

# เกณฑ์ป้ายกำกับ (เปอร์เซ็นไทล์ของคะแนนแนะนำภายในตลาดเดียวกัน)
LABELS = [
    (0.85, "strong", "เด่นมาก"),
    (0.60, "good", "น่าสนใจ"),
    (0.30, "neutral", "ปานกลาง"),
    (0.00, "weak", "ควรระวัง"),
]

PRICE_HISTORY_PERIOD = "10y"
NEWS_LOOKBACK_DAYS = 30
NEWS_HALF_LIFE_DAYS = 7
MAX_NEWS_PER_STOCK = 20
FETCH_WORKERS = 6
SCORE_HISTORY_DAYS = 400
TOP_PICKS_TRACKED = 10

# วิเคราะห์ข่าวด้วย Claude (ไม่บังคับ) — เปิดด้วย --ai และต้องมี ANTHROPIC_API_KEY
AI_DEFAULT_MODEL = "claude-opus-5"
AI_TOP_N_PER_MARKET = 15
