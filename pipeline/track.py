"""บันทึกหุ้นที่ระบบแนะนำในแต่ละวัน แล้ววัดผลจริงย้อนหลังเทียบกับดัชนี (track record)
และเก็บประวัติคะแนนรายวันของหุ้นทุกตัว (ใช้ติดตามสถานะในหน้า "รายการติดตาม")
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def save_snapshot(date: str, market: str, stocks: list[dict]) -> None:
    """เก็บหุ้นอันดับต้นๆ ของแต่ละระยะเวลาลงทุนในวันนี้"""
    p = config.WEB_DATA / "snapshots" / f"{date}.json"
    snap = _read(p, {"date": date, "markets": {}})
    snap["markets"][market] = {
        hk: [{"sym": s["sym"], "price": s["price"], "score": s["h"][hk]["score"],
              "prob": s["h"][hk]["prob"]}
             for s in sorted(stocks, key=lambda x: x["h"][hk]["rank"])[: config.TOP_PICKS_TRACKED]]
        for hk in config.HORIZONS
    }
    _write(p, snap)
    index_p = config.WEB_DATA / "snapshots" / "index.json"
    idx = _read(index_p, [])
    if date not in idx:
        idx = sorted(idx + [date])
    _write(index_p, idx)


def _ret_after(c: pd.Series, date: pd.Timestamp, entry: float, days: int | None):
    """ผลตอบแทนจากราคาเข้า ถึงวันที่ครบ `days` วันทำการ (None = ถึงวันล่าสุด)"""
    pos = c.index.searchsorted(date, side="right") - 1
    if pos < 0 or not entry:
        return None, False
    if days is None or pos + days >= len(c):
        return float(c.iloc[-1] / entry - 1), False
    return float(c.iloc[pos + days] / entry - 1), True


def update_track(market: str, closes: dict[str, pd.Series], bench: pd.Series | None) -> dict:
    idx = _read(config.WEB_DATA / "snapshots" / "index.json", [])
    out = {}
    for hk, h in config.HORIZONS.items():
        rows = []
        for d in idx:
            snap = _read(config.WEB_DATA / "snapshots" / f"{d}.json", {})
            picks = (snap.get("markets", {}).get(market) or {}).get(hk) or []
            if not picks:
                continue
            date = pd.Timestamp(d)
            rets, matured_all = [], True
            for pk in picks:
                c = closes.get(pk["sym"])
                if c is None:
                    continue
                r, matured = _ret_after(c, date, pk["price"], h)
                if r is not None:
                    rets.append({"sym": pk["sym"], "ret": round(r, 4)})
                    matured_all &= matured
            if not rets:
                continue
            b_ret = None
            if bench is not None and len(bench):
                pos = bench.index.searchsorted(date, side="right") - 1
                if pos >= 0:
                    b_ret, _ = _ret_after(bench, date, float(bench.iloc[pos]), h)
            avg = sum(x["ret"] for x in rets) / len(rets)
            rows.append({
                "date": d, "n": len(rets), "avg_ret": round(avg, 4),
                "bench_ret": round(b_ret, 4) if b_ret is not None else None,
                "hit_rate": round(sum(x["ret"] > 0 for x in rets) / len(rets), 3),
                "matured": matured_all, "picks": rets,
            })
        matured = [r for r in rows if r["matured"]]

        def summarize(rs):
            if not rs:
                return None
            ex = [r["avg_ret"] - r["bench_ret"] for r in rs if r["bench_ret"] is not None]
            return {
                "n": len(rs),
                "avg_ret": round(sum(r["avg_ret"] for r in rs) / len(rs), 4),
                "avg_excess": round(sum(ex) / len(ex), 4) if ex else None,
                "beat_bench_rate": round(sum(e > 0 for e in ex) / len(ex), 3) if ex else None,
                "hit_rate": round(sum(r["hit_rate"] for r in rs) / len(rs), 3),
            }

        out[hk] = {"all": summarize(rows), "matured": summarize(matured),
                   "snapshots": rows[-120:]}
    track = _read(config.WEB_DATA / "track.json", {"markets": {}})
    track["markets"][market] = out
    _write(config.WEB_DATA / "track.json", track)
    return out


def update_score_history(market: str, date: str, stocks: list[dict]) -> dict:
    """เพิ่มคะแนนของวันนี้ -> คืน {sym: [[date, score1m, score3m, score6m, score9m, price], ...]}"""
    p = config.WEB_DATA / "history" / f"{market}.json"
    hist = _read(p, {})
    for s in stocks:
        rows = [r for r in hist.get(s["sym"], []) if r[0] != date]
        rows.append([date] + [round(s["h"][hk]["score"], 1) for hk in config.HORIZONS]
                    + [s["price"]])
        hist[s["sym"]] = sorted(rows)[-config.SCORE_HISTORY_DAYS:]
    _write(p, hist)
    return hist
