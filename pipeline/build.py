"""รันทั้งหมด: ดึงข้อมูล -> คำนวณ -> เขียนไฟล์ JSON ให้หน้าเว็บ

ตัวอย่าง:
    python -m pipeline.build                 # อัปเดตทุกตลาด
    python -m pipeline.build --markets th    # เฉพาะหุ้นไทย
    python -m pipeline.build --use-cache     # ใช้ข้อมูลที่ดึงไว้ภายใน 20 ชม. (รันซ้ำเร็ว)
    python -m pipeline.build --ai            # สรุปข่าวด้วย Claude (ต้องมี ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import (ai_news, config, fetch, fundamentals, news, probability, reasons, scoring,
               technicals, track)

log = logging.getLogger("stocklens")

SECTOR_TH = {
    "Technology": "เทคโนโลยี",
    "Financial Services": "การเงิน",
    "Healthcare": "การแพทย์",
    "Consumer Cyclical": "สินค้าฟุ่มเฟือย/ค้าปลีก",
    "Consumer Defensive": "สินค้าจำเป็น/อาหาร",
    "Energy": "พลังงาน",
    "Industrials": "อุตสาหกรรม/ขนส่ง",
    "Basic Materials": "วัสดุพื้นฐาน",
    "Real Estate": "อสังหาริมทรัพย์",
    "Utilities": "สาธารณูปโภค",
    "Communication Services": "สื่อสาร",
}


def clean(o):
    """แปลงเป็นชนิดที่เขียน JSON ได้ (NaN/inf -> null)"""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def write_json(path, obj, pretty=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(clean(obj), ensure_ascii=False,
                     indent=1 if pretty else None,
                     separators=None if pretty else (",", ":"))
    path.write_text(txt, encoding="utf-8")


def r4(v, d=4):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), d)


def load_prices(symbols: list[str], key: str, use_cache: bool) -> dict[str, pd.DataFrame]:
    if use_cache:
        cached = fetch.cache_load("prices", key, max_age_hours=20)
        if cached is not None and all(s in cached for s in symbols[:3]):
            return cached
    prices = fetch.download_prices(symbols)
    fetch.cache_save("prices", key, prices)
    return prices


def drop_partial_bar(prices: dict[str, pd.DataFrame], tz: str, close_time: tuple[int, int]) -> None:
    """ตัดแท่งราคาของวันนี้ออกถ้าตลาดยังไม่ปิด เพื่อให้ทุกอย่างคำนวณจากราคาปิดเท่านั้น"""
    now = pd.Timestamp.now(tz=tz)
    if (now.hour, now.minute) >= close_time:
        return
    today = now.tz_localize(None).normalize()
    for sym, df in prices.items():
        if len(df) and df.index[-1] >= today:
            prices[sym] = df.iloc[:-1]


def regime(bench: pd.Series | None, closes: dict[str, pd.Series]) -> dict:
    above = [float(c.iloc[-1] > c.rolling(200).mean().iloc[-1])
             for c in closes.values() if len(c) >= 200]
    breadth = sum(above) / len(above) if above else None
    out = {"breadth": r4(breadth, 3)}
    if bench is not None and len(bench) >= 200:
        ma200 = bench.rolling(200).mean().iloc[-1]
        out.update({
            "index_above_ma200": bool(bench.iloc[-1] > ma200),
            "index_dist_ma200": r4(bench.iloc[-1] / ma200 - 1),
            "index_ret_3m": r4(bench.iloc[-1] / bench.iloc[-64] - 1) if len(bench) > 64 else None,
        })
    up = out.get("index_above_ma200")
    if up and (breadth or 0) >= 0.5:
        out["state"], out["text"] = "bull", "ตลาดขาขึ้น: ดัชนีอยู่เหนือเส้นค่าเฉลี่ย 200 วัน และหุ้นส่วนใหญ่ยังเป็นขาขึ้น"
    elif up is False and (breadth or 1) < 0.4:
        out["state"], out["text"] = "bear", "ตลาดขาลง: ดัชนีอยู่ใต้เส้นค่าเฉลี่ย 200 วัน และหุ้นส่วนใหญ่อ่อนแอ ควรระมัดระวังเป็นพิเศษ"
    else:
        out["state"], out["text"] = "mixed", "ตลาดแกว่งตัว/ไม่มีทิศทางชัด: ควรเลือกหุ้นรายตัวและกระจายความเสี่ยง"
    return out


def build_market(mk: str, use_cache: bool, use_ai: bool, limit: int | None) -> dict:
    cfg = config.MARKETS[mk]
    symbols = dict(list(cfg["stocks"].items())[:limit]) if limit else dict(cfg["stocks"])
    t0 = time.time()
    log.info("[%s] ดึงราคาย้อนหลัง %d ตัว ...", mk, len(symbols))
    prices = load_prices(list(symbols) + [cfg["benchmark"], cfg["benchmark_fallback"]],
                         f"{mk}_{len(symbols)}", use_cache)
    prices = dict(prices)
    drop_partial_bar(prices, cfg["timezone"], cfg["close_time"])
    bench_df = prices.get(cfg["benchmark"])
    if bench_df is None:
        bench_df = prices.get(cfg["benchmark_fallback"])
    bench = bench_df["Close"].astype(float) if bench_df is not None else None

    log.info("[%s] ดึงข้อมูลบริษัท งบการเงิน และข่าว ...", mk)
    companies = fetch.fetch_all_companies(symbols, mk, use_cache=use_cache)

    as_of = max((df.index[-1] for s, df in prices.items() if s in symbols), default=None)
    rows, details, failed = {}, {}, []
    for sym, name in symbols.items():
        df = prices.get(sym)
        if df is None or len(df) < 60:
            failed.append({"sym": sym, "reason": "ไม่มีข้อมูลราคา (อาจถูกเพิกถอน/เปลี่ยนชื่อ)"})
            continue
        if as_of is not None and (as_of - df.index[-1]).days > 10:
            failed.append({"sym": sym, "reason": f"ไม่มีการซื้อขายตั้งแต่ {df.index[-1]:%Y-%m-%d}"})
            continue
        raw = companies.get(sym) or {}
        tech = technicals.compute(df, bench)
        fund = fundamentals.compute(raw, tech["price"])
        items = raw.get("news") or []
        ns = news.score_news(items)
        row = {**tech, **fund, "news_sentiment": ns["sentiment"],
               "n_news": ns["n_news"], "n_pos": ns["n_pos"], "n_neg": ns["n_neg"]}
        dy = tech.get("div_yield_ttm")
        row["div_yield"] = dy if (dy == dy and dy and dy > 0) else fund.get("div_yield_info")
        rows[sym] = row
        details[sym] = {"raw": raw, "news": items, "df": df}

    if not rows:
        raise RuntimeError(f"ไม่มีข้อมูลหุ้นในตลาด {mk}")

    log.info("[%s] คำนวณสถิติโอกาสขึ้น/ลง ...", mk)
    closes = {s: prices[s]["Close"].astype(float) for s in rows}
    prob = probability.run(closes, config.HORIZONS)

    frame = pd.DataFrame.from_dict(rows, orient="index")
    scored, ranks = scoring.score(frame)
    med = scoring.market_medians(scoring.prepare(frame))

    ai_results = {}
    if use_ai:
        top = scored.sort_values("score_3m", ascending=False).index[: config.AI_TOP_N_PER_MARKET]
        log.info("[%s] วิเคราะห์ข่าวด้วย AI %d ตัว ...", mk, len(top))
        ai_results = ai_news.analyze([
            {"symbol": s, "name": rows[s].get("name_en") or symbols[s],
             "sector": rows[s].get("sector"), "news": details[s]["news"]} for s in top])

    stocks, detail_payloads = [], {}
    for sym, m in rows.items():
        sc = scored.loc[sym]
        rk = {k: r4(v, 3) for k, v in ranks.loc[sym].items()}
        facts = reasons.build(m, rk, med, cfg["currency"])
        ph = prob["stocks"][sym]["horizons"]
        code = sym.replace(".BK", "")
        c = closes[sym]
        stock = {
            "sym": sym, "code": code, "name": symbols[sym], "name_en": m.get("name_en"),
            "sector": m.get("sector"), "sector_th": SECTOR_TH.get(m.get("sector"), m.get("sector")),
            "industry": m.get("industry"),
            "price": r4(m["price"]), "date": m["date"],
            "ret_1d": r4(m["ret_1d"]), "ret_1w": r4(m["ret_1w"]), "ret_1m": r4(m["ret_1m"]),
            "ret_3m": r4(m["ret_3m"]), "ret_6m": r4(m["ret_6m"]), "ret_12m": r4(m["ret_12m"]),
            "ret_ytd": r4(m["ret_ytd"]),
            "mcap": r4(m.get("market_cap"), 0), "pe": r4(m.get("pe"), 2) if not m.get("loss_making") else None,
            "loss": bool(m.get("loss_making")),
            "fpe": r4(m.get("forward_pe"), 2), "pb": r4(m.get("pb"), 2), "dy": r4(m.get("div_yield")),
            "roe": r4(m.get("roe")), "nm": r4(m.get("net_margin")), "de": r4(m.get("de"), 3),
            "rev_g": r4(m.get("rev_growth_q")), "earn_g": r4(m.get("earn_growth_q")),
            "vol": r4(m.get("vol_1y")), "upside": r4(m.get("upside")),
            "n_analysts": m.get("n_analysts"), "turnover": r4(m.get("turnover_20d"), 0),
            "above_ma200": bool(m["dist_ma200"] > 0) if m["dist_ma200"] == m["dist_ma200"] else None,
            "groups": {g: round(float(sc[f"g_{g}"]) * 100, 1) for g in config.GROUPS},
            "coverage": r4(sc["data_coverage"], 2),
            "h": {hk: {
                "score": round(float(sc[f"score_{hk}"]) * 100, 1),
                "rank": int(sc[f"rank_{hk}"]),
                "label": sc[f"label_{hk}"],
                "prob": ph[hk]["prob"], "median": ph[hk]["median"],
                "p10": ph[hk]["p10"], "p90": ph[hk]["p90"],
            } for hk in config.HORIZONS},
            "state": prob["stocks"][sym]["state"],
            "news": {"sentiment": m["news_sentiment"], "n": m["n_news"],
                     "pos": m["n_pos"], "neg": m["n_neg"]},
            "facts": facts,
            "ai": sym in ai_results,
            "spark": [round(float(v), 4) for v in c.iloc[-66:]],
        }
        stocks.append(stock)

        raw = details[sym]["raw"]
        detail_payloads[sym] = {
            "sym": sym,
            "chart": technicals.chart_series(details[sym]["df"]),
            "statements": fundamentals.statement_tables(raw),
            "financial_currency": m.get("financial_currency") or m.get("currency"),
            "metrics": {k: (technicals.clean(v) if not isinstance(v, (str, bool, type(None))) else v)
                        for k, v in m.items() if k not in ("summary",)},
            "ranks": rk,
            "prob": ph,
            "state": prob["stocks"][sym]["state"],
            "news": [{k: n.get(k) for k in ("title", "source", "url", "time", "sent", "lang")}
                     for n in details[sym]["news"]],
            "ai": ai_results.get(sym),
            "summary": m.get("summary"),
            "website": m.get("website"),
        }

    stocks.sort(key=lambda s: s["h"]["3m"]["rank"])
    date = as_of.strftime("%Y-%m-%d") if as_of is not None else datetime.now().strftime("%Y-%m-%d")

    # ประวัติคะแนนรายวัน -> การเปลี่ยนแปลงคะแนนใน 7 วัน (ใช้ในรายการติดตาม) + กราฟในหน้ารายละเอียด
    hist = track.update_score_history(mk, date, stocks)
    week_ago = (pd.Timestamp(date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    for s in stocks:
        rows_h = hist.get(s["sym"], [])
        prev = next((r for r in reversed(rows_h) if r[0] <= week_ago), None)
        s["chg7"] = ({hk: round(s["h"][hk]["score"] - prev[1 + i], 1)
                      for i, hk in enumerate(config.HORIZONS)} if prev else None)
        payload = detail_payloads[s["sym"]]
        payload["history"] = rows_h
        write_json(config.WEB_DATA / "stocks" / f"{s['sym']}.json", payload)

    summary = {
        "market": mk, "label": cfg["label"], "currency": cfg["currency"],
        "as_of": date, "generated_at": datetime.now(timezone.utc).isoformat(),
        "medians": med, "stocks": stocks,
    }
    write_json(config.WEB_DATA / f"{mk}.json", summary)

    track.save_snapshot(date, mk, stocks)
    track.update_track(mk, closes, bench)

    bench_info = None
    if bench is not None:
        bench_info = {"label": cfg["benchmark_label"], "price": r4(bench.iloc[-1], 2),
                      "ret_1d": r4(bench.iloc[-1] / bench.iloc[-2] - 1) if len(bench) > 1 else None}
    log.info("[%s] เสร็จ %d ตัว (ข้าม %d) ใช้เวลา %.0f วินาที", mk, len(stocks), len(failed), time.time() - t0)
    return {
        "label": cfg["label"], "currency": cfg["currency"], "as_of": date, "count": len(stocks),
        "failed": failed, "benchmark": bench_info, "regime": regime(bench, closes),
        "prob_model": prob["market"],
        "mom_thresholds": prob["mom_thresholds"],
        "factor_backtest": probability.factor_backtest(closes, config.HORIZONS),
        "sectors": sorted({s["sector_th"] for s in stocks if s["sector_th"]}),
        "ai_count": len(ai_results),
    }


def _contiguous(c: pd.Series, days: int = 60, max_gap: int = 7) -> bool:
    """ข้อมูลช่วงล่าสุดไม่ขาดหาย (Yahoo บางดัชนีข้อมูลหายเป็นช่วงๆ)"""
    tail = c.iloc[-days:]
    gaps = tail.index.to_series().diff().dt.days.dropna()
    return len(tail) >= days * 0.6 and (gaps <= max_gap).all()


def market_strip() -> list[dict]:
    syms = [s for row in config.MARKET_STRIP for s in (row[0], row[2]) if s]
    prices = fetch.download_prices(syms, period="2y")
    out = []
    for sym, label, alt, alt_label in config.MARKET_STRIP:
        df = prices.get(sym)
        if (df is None or not _contiguous(df["Close"])) and alt and prices.get(alt) is not None:
            sym, label, df = alt, alt_label, prices[alt]
        if df is None:
            continue
        c = df["Close"].astype(float)
        ma200 = c.rolling(200).mean().iloc[-1]
        out.append({
            "sym": sym, "label": label, "price": r4(c.iloc[-1], 2),
            "ret_1d": r4(c.iloc[-1] / c.iloc[-2] - 1), "ret_1m": r4(c.iloc[-1] / c.iloc[-22] - 1),
            "above_ma200": bool(c.iloc[-1] > ma200) if ma200 == ma200 else None,
            "date": c.index[-1].strftime("%Y-%m-%d"),
            "spark": [round(float(v), 2) for v in c.iloc[-66:]],
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="อัปเดตข้อมูลหุ้นสำหรับเว็บ StockLens")
    ap.add_argument("--markets", default="th,us", help="th,us")
    ap.add_argument("--use-cache", action="store_true", help="ใช้ข้อมูลดิบที่ดึงไว้ภายใน 20 ชม.")
    ap.add_argument("--ai", action="store_true", help="สรุปข่าวด้วย Claude API")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนหุ้นต่อตลาด (ทดสอบ)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("yfinance", "urllib3", "peewee", "httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)

    meta_p = config.WEB_DATA / "meta.json"
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {"markets": {}}

    for mk in [m.strip() for m in args.markets.split(",") if m.strip()]:
        if mk not in config.MARKETS:
            log.error("ไม่รู้จักตลาด %s", mk)
            continue
        meta["markets"][mk] = build_market(mk, args.use_cache, args.ai, args.limit)

    log.info("อัปเดตแถบภาวะตลาด ...")
    meta.update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strip": market_strip(),
        "horizons": config.HORIZON_LABELS,
        "weights": config.WEIGHTS,
        "groups": config.GROUPS,
        "labels": {key: text for _, key, text in config.LABELS},
        "ai_enabled": any(m.get("ai_count") for m in meta["markets"].values()),
    })
    write_json(meta_p, meta, pretty=True)
    log.info("เสร็จสิ้น -> %s", config.WEB_DATA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
