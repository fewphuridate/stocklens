"""ให้คะแนนโทนข่าว (บวก/ลบ) ด้วยพจนานุกรมคำ ภาษาไทยและอังกฤษ

เป็นวิธีแบบง่ายและโปร่งใส ใช้ได้ทุกวันโดยไม่มีค่าใช้จ่าย
ถ้าต้องการสรุปข่าวเชิงลึก ให้เปิดโหมด --ai (ดู ai_news.py)
"""
from __future__ import annotations

import re

import pandas as pd

from . import config

POS_EN = [
    "beat", "beats", "surpass", "surge", "surges", "soar", "soars", "jump", "jumps", "rally",
    "rallies", "gain", "gains", "record", "upgrade", "upgraded", "upgrades", "outperform",
    "bullish", "strong", "stronger", "growth", "raises", "raised", "boost", "boosts", "expand",
    "expands", "expansion", "wins", "approval", "approved", "tops", "rebound", "rebounds",
    "overweight", "buyback", "repurchase", "breakthrough", "partnership", "accelerate",
    "accelerates", "profit rises", "higher", "climbs", "climb", "optimistic", "favorable",
    "all-time high", "buy rating", "top pick",
]
NEG_EN = [
    "miss", "misses", "missed", "fall", "falls", "fell", "plunge", "plunges", "drop", "drops",
    "slump", "slumps", "tumble", "tumbles", "sink", "sinks", "slide", "slides", "downgrade",
    "downgraded", "downgrades", "underperform", "bearish", "weak", "weaker", "weakness",
    "cuts", "lowers", "lowered", "loss", "losses", "lawsuit", "sued", "probe", "investigation",
    "fraud", "recall", "warning", "warns", "layoffs", "layoff", "decline", "declines",
    "delay", "delays", "halt", "bankruptcy", "default", "fined", "penalty", "antitrust",
    "tariff", "tariffs", "concern", "concerns", "crash", "lower", "slowdown", "sell rating",
    "underweight", "disappoint", "disappoints", "disappointing",
]
POS_TH = [
    "กำไรพุ่ง", "กำไรโต", "กำไรเพิ่ม", "กำไรสุทธิเพิ่ม", "โตต่อเนื่อง", "เติบโต", "ทะยาน", "พุ่ง",
    "นิวไฮ", "ทำสถิติ", "สูงสุดเป็นประวัติการณ์", "แนะนำซื้อ", "น่าซื้อ", "ฟื้นตัว", "ฟื้น",
    "สดใส", "โดดเด่น", "แกร่ง", "ขยายตัว", "ได้งาน", "คว้า", "ชนะประมูล", "อัพเกรด", "ปรับเพิ่มเป้า",
    "เพิ่มเป้า", "เชียร์", "หนุน", "ได้รับอนุมัติ", "ซื้อหุ้นคืน", "ปันผลสูง", "ทุบสถิติ", "เด้ง",
    "บวกแรง", "บวกสูงสุด", "ปรับขึ้น", "ขึ้นแรง", "อัพเป้า", "ชูปันผล", "กำไรสูงสุด", "ออเดอร์",
    "outperform", "upside", "ท็อปพิก", "top pick",
]
NEG_TH = [
    "ขาดทุน", "ร่วง", "ดิ่ง", "ทรุด", "ลดลง", "หดตัว", "ติดลบ", "ขายทิ้ง", "แนะนำขาย", "ปรับลดเป้า",
    "หั่นเป้า", "ลดเป้า", "ต่ำสุด", "วิกฤต", "ฟ้อง", "ผิดนัดชำระ", "ผิดนัด", "หนี้เสีย", "npl",
    "กล่าวโทษ", "สอบสวน", "กดดัน", "ชะลอ", "ซบเซา", "อ่อนแอ", "ระงับการซื้อขาย", "เทขาย",
    "แรงขาย", "เพิ่มทุน", "underperform", "downside", "หลุดแนวรับ", "ถูกปรับ", "ลบแรง",
    "ลบสูงสุด", "ปรับลง", "ร่วงแรง", "ดิ่งหนัก", "ขาดทุนสุทธิ", "ต่ำกว่าคาด", "หั่นกำไร",
]

_EN_PATTERNS = [(re.compile(rf"\b{re.escape(w)}\b", re.I), +1) for w in POS_EN] + \
               [(re.compile(rf"\b{re.escape(w)}\b", re.I), -1) for w in NEG_EN]


def headline_sentiment(text: str) -> float:
    """คืนค่า -1..1 (0 = เป็นกลาง/ไม่พบคำสำคัญ)"""
    t = text.lower()
    pos = neg = 0
    for pat, sign in _EN_PATTERNS:
        if pat.search(t):
            pos += sign > 0
            neg += sign < 0
    for w in POS_TH:
        pos += w in t
    for w in NEG_TH:
        neg += w in t
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def score_news(items: list[dict]) -> dict:
    """ใส่คะแนนให้แต่ละข่าว และสรุปเป็นคะแนนรวมแบบถ่วงน้ำหนักข่าวใหม่มากกว่า"""
    now = pd.Timestamp.now(tz="UTC")
    num = den = 0.0
    n_pos = n_neg = 0
    for it in items:
        s = headline_sentiment(f'{it["title"]} {it.get("summary", "")}')
        it["sent"] = round(s, 2)
        if s > 0:
            n_pos += 1
        elif s < 0:
            n_neg += 1
        if s != 0:
            age = (now - pd.Timestamp(it["time"])).total_seconds() / 86400 if it.get("time") else 15
            w = 0.5 ** (max(age, 0) / config.NEWS_HALF_LIFE_DAYS)
            num += w * s
            den += w
    avg = num / den if den > 0 else 0.0
    return {"sentiment": round(avg, 3), "n_news": len(items), "n_pos": n_pos, "n_neg": n_neg}
