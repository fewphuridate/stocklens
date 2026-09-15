"""(ไม่บังคับ) ใช้ Claude สรุปข่าวเป็นภาษาไทย พร้อมปัจจัยบวก/ความเสี่ยงของหุ้นแต่ละตัว

เปิดใช้งาน:  python -m pipeline.build --ai
ต้องติดตั้ง `pip install anthropic` และตั้งค่า ANTHROPIC_API_KEY (หรือ `ant auth login`)
เปลี่ยนโมเดลได้ด้วยตัวแปรแวดล้อม STOCKLENS_AI_MODEL

ผลวิเคราะห์นี้ใช้แสดงผลประกอบเท่านั้น ไม่นำไปคำนวณคะแนน เพื่อให้คะแนนของหุ้นทุกตัวเทียบกันได้อย่างยุติธรรม
"""
from __future__ import annotations

import json
import logging
import os

from . import config

log = logging.getLogger(__name__)

SYSTEM = (
    "You are an equity research assistant for Thai retail investors. "
    "Given recent news headlines about one listed company, assess what the news implies for the "
    "stock over the next 1-9 months. Be factual and balanced; only use information present in the "
    "headlines. Write every text field in Thai, concise and plain. "
    "If headlines are irrelevant or too thin to judge, say so and keep sentiment near 0."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "number", "description": "-1 (very negative) .. 1 (very positive)"},
        "summary_th": {"type": "string", "description": "2-3 sentence Thai summary of the key news"},
        "catalysts_th": {"type": "array", "items": {"type": "string"}},
        "risks_th": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sentiment", "summary_th", "catalysts_th", "risks_th"],
    "additionalProperties": False,
}


def analyze(stocks: list[dict]) -> dict[str, dict]:
    """stocks: [{symbol, name, sector, news:[{title, summary, source, time}]}] -> {symbol: result}"""
    try:
        import anthropic
    except ImportError:
        log.warning("ยังไม่ได้ติดตั้งแพ็กเกจ anthropic (pip install anthropic) — ข้ามการวิเคราะห์ข่าวด้วย AI")
        return {}

    client = anthropic.Anthropic()
    model = os.environ.get("STOCKLENS_AI_MODEL", config.AI_DEFAULT_MODEL)
    results: dict[str, dict] = {}
    for st in stocks:
        if not st["news"]:
            continue
        lines = [f'{i + 1}. [{(n.get("time") or "")[:10]}] {n["title"]}'
                 + (f' — {n["summary"][:200]}' if n.get("summary") else "")
                 + f' ({n.get("source", "")})'
                 for i, n in enumerate(st["news"][:15])]
        prompt = (f"Company: {st['name']} ({st['symbol']}), sector: {st.get('sector') or '-'}\n"
                  f"Recent headlines (newest first):\n" + "\n".join(lines))
        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=2000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low",
                               "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            log.warning("ไม่พบ/ไม่ถูกต้อง: ANTHROPIC_API_KEY — ข้ามการวิเคราะห์ข่าวด้วย AI")
            return results
        except anthropic.RateLimitError:
            log.warning("ติด rate limit ของ API — หยุดวิเคราะห์ข่าวด้วย AI รอบนี้")
            return results
        except anthropic.APIStatusError as e:
            log.warning("AI error %s สำหรับ %s: %s", e.status_code, st["symbol"], e.message)
            continue
        except anthropic.APIConnectionError:
            log.warning("เชื่อมต่อ API ไม่ได้ — ข้าม %s", st["symbol"])
            continue

        if resp.stop_reason == "refusal":
            continue
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        data["sentiment"] = max(-1.0, min(1.0, float(data.get("sentiment", 0))))
        data["model"] = resp.model
        results[st["symbol"]] = data
        log.info("  AI วิเคราะห์ข่าว %s เสร็จ", st["symbol"])
    return results
