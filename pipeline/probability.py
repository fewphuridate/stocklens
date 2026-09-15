"""โอกาสที่ราคาจะสูงขึ้นภายใน 1/3/6/9 เดือน จากสถิติราคาย้อนหลัง ~10 ปี

แนวคิด (อธิบายได้ ตรวจสอบย้อนหลังได้):
- แบ่ง "สภาวะ" ของหุ้นเป็น 6 แบบ = ราคาอยู่เหนือ/ใต้เส้นค่าเฉลี่ย 200 วัน x โมเมนตัม 3 เดือน (อ่อน/กลาง/แรง)
- โอกาสขึ้น = สัดส่วนครั้งในอดีตที่หุ้น "ทุกตัวในตลาดเดียวกัน" เมื่ออยู่ในสภาวะเดียวกัน แล้วถือครบ N เดือนราคาสูงขึ้น
  (ใช้ข้อมูลทั้งตลาดเพราะมีตัวอย่างมาก ตัวเลขนิ่งและตรวจสอบย้อนหลังแล้วแม่นกว่าการใช้สถิติของหุ้นตัวเดียว)
- แสดงสถิติของหุ้นตัวนั้นเองควบคู่ (อัตราขึ้นในอดีต ช่วงผลตอบแทน) เพื่อประกอบการตัดสินใจ
- ทดสอบย้อนหลัง: สร้างตัวเลขจากข้อมูล 70% แรก แล้ววัดผลกับ 30% หลัง

ข้อค้นพบจากการทดสอบ: สถิติราคาย้อนหลังบอก "ความน่าจะเป็นพื้นฐาน" ได้ตรง แต่แยกหุ้นที่จะขึ้น/ไม่ขึ้นได้น้อยมาก
จึงแสดงเป็นข้อมูลประกอบ และไม่นำไปรวมในคะแนนแนะนำ
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MOM_LOOKBACK = 63
CLIP = (0.03, 0.97)

TREND_TEXT = {1: "ราคาอยู่เหนือเส้นค่าเฉลี่ย 200 วัน", 0: "ราคาอยู่ใต้เส้นค่าเฉลี่ย 200 วัน"}
MOM_TEXT = {0: "โมเมนตัม 3 เดือนอ่อน", 1: "โมเมนตัม 3 เดือนปานกลาง", 2: "โมเมนตัม 3 เดือนแรง"}


def _features(c: pd.Series):
    ma200 = c.rolling(200).mean()
    trend = (c > ma200).astype(float).where(ma200.notna())
    mom = c / c.shift(MOM_LOOKBACK) - 1
    return trend, mom


def _panel(closes: dict[str, pd.Series], h: int, q: np.ndarray) -> pd.DataFrame:
    frames = []
    for sym, c in closes.items():
        trend, mom = _features(c)
        fwd = c.shift(-h) / c - 1
        df = pd.DataFrame({"sym": sym, "trend": trend, "mom": mom, "fwd": fwd}).dropna()
        df["date"] = df.index
        frames.append(df)
    p = pd.concat(frames, ignore_index=True)
    p["state"] = (p["trend"].astype(int) * 3 + np.digitize(p["mom"], q)).astype(int)
    p["up"] = (p["fwd"] > 0).astype(float)
    return p


def _fit(p: pd.DataFrame) -> dict:
    st = p.groupby("state")["up"].agg(["mean", "count"])
    return {"p0": float(p["up"].mean()), "state_rate": st}


def _predict(model: dict, states: pd.Series) -> np.ndarray:
    return np.clip(states.map(model["state_rate"]["mean"]).fillna(model["p0"]).to_numpy(), *CLIP)


def _calibrate(p: pd.DataFrame, h: int) -> dict | None:
    dates = np.sort(p["date"].unique())
    if len(dates) < 500:
        return None
    split = pd.Timestamp(dates[int(len(dates) * 0.7)])
    train = p[p["date"] <= split - pd.Timedelta(days=int(h * 1.45) + 1)]
    test = p[p["date"] > split]
    if len(train) < 2000 or len(test) < 500:
        return None
    model = _fit(train)
    pred = _predict(model, test["state"])
    up = test["up"].to_numpy()
    brier_m = float(np.mean((pred - up) ** 2))
    brier_b = float(np.mean((model["p0"] - up) ** 2))
    t = test.assign(pred=pred)
    by_state = []
    for s, g in t.groupby("state"):
        by_state.append({"state": int(s), "n": int(len(g)), "pred": round(float(g["pred"].mean()), 3),
                         "actual": round(float(g["up"].mean()), 3),
                         "avg_ret": round(float(g["fwd"].mean()), 4)})
    return {
        "test_from": split.strftime("%Y-%m-%d"),
        "test_to": pd.Timestamp(dates[-1]).strftime("%Y-%m-%d"),
        "test_n": int(len(test)),
        "base_rate": round(float(up.mean()), 3),
        "train_base_rate": round(model["p0"], 3),
        "brier_model": round(brier_m, 4),
        "brier_base": round(brier_b, 4),
        "skill": round(1 - brier_m / brier_b, 4) if brier_b > 0 else None,
        "mae": round(float(np.mean([abs(b["pred"] - b["actual"]) for b in by_state])), 3) if by_state else None,
        "by_state": by_state,
    }


def run(closes: dict[str, pd.Series], horizons: dict[str, int]) -> dict:
    """คืน {"stocks": {sym: {...}}, "market": {h: {...}}}"""
    moms = pd.concat([_features(c)[1] for c in closes.values()]).dropna()
    q = np.quantile(moms, [1 / 3, 2 / 3]) if len(moms) else np.array([-0.05, 0.05])

    stocks: dict[str, dict] = {}
    for sym, c in closes.items():
        trend, mom = _features(c)
        t, m = trend.iloc[-1], mom.iloc[-1]
        state = None
        if t == t and m == m:
            b = int(np.digitize([m], q)[0])
            state = {"trend": int(t), "mom_bucket": b, "mom_3m": round(float(m), 4),
                     "id": int(t) * 3 + b, "text": f"{TREND_TEXT[int(t)]} และ{MOM_TEXT[b]}"}
        stocks[sym] = {"state": state, "horizons": {}}

    market: dict[str, dict] = {}
    for hk, h in horizons.items():
        p = _panel(closes, h, q)
        if p.empty:
            continue
        model = _fit(p)
        own = p.groupby(["sym", "state"])["up"].agg(["mean", "count"])
        market[hk] = {
            "base_rate": round(model["p0"], 3),
            "states": {int(k): {"rate": round(float(r["mean"]), 3), "n": int(r["count"])}
                       for k, r in model["state_rate"].iterrows()},
            "calibration": _calibrate(p, h),
        }
        for sym, c in closes.items():
            st = stocks[sym]["state"]
            fwd = (c.shift(-h) / c - 1).dropna()
            prob = float(_predict(model, pd.Series([st["id"] if st else -1]))[0])
            s_rate, s_n = None, 0
            if st is not None and (sym, st["id"]) in own.index:
                r = own.loc[(sym, st["id"])]
                s_rate, s_n = round(float(r["mean"]), 4), int(r["count"])
            enough = len(fwd) >= 60
            stocks[sym]["horizons"][hk] = {
                "prob": round(prob, 4),
                "base_rate": round(float((fwd > 0).mean()), 4) if enough else None,
                "n": int(len(fwd)),
                "years": round(len(c) / 252, 1),
                "state_rate": s_rate if s_n >= 60 else None,
                "state_n": s_n,
                "median": round(float(fwd.median()), 4) if enough else None,
                "p10": round(float(fwd.quantile(0.10)), 4) if enough else None,
                "p90": round(float(fwd.quantile(0.90)), 4) if enough else None,
            }
    return {"stocks": stocks, "market": market,
            "mom_thresholds": [round(float(x), 4) for x in q]}


def factor_backtest(closes: dict[str, pd.Series], horizons: dict[str, int]) -> dict:
    """ทดสอบย้อนหลังเฉพาะปัจจัยที่ใช้ราคา (ปรับพอร์ตทุกเดือน):
    หุ้นกลุ่มคะแนนสูงสุด 20% เทียบกลุ่มต่ำสุด 20% — ข้อมูลพื้นฐานย้อนหลังแบบ ณ วันนั้นไม่มีให้ใช้ฟรี จึงทดสอบไม่ได้"""
    px = pd.DataFrame(closes).sort_index().ffill(limit=5)
    if px.shape[1] < 20 or len(px) < 400:
        return {}
    ret = px.pct_change(fill_method=None)
    ma200 = px.rolling(200).mean()
    mom = pd.concat([
        (px.shift(21) / px.shift(252) - 1).rank(axis=1, pct=True),
        (px / px.shift(126) - 1).rank(axis=1, pct=True),
        (px / px.shift(63) - 1).rank(axis=1, pct=True),
        (px / ma200 - 1).rank(axis=1, pct=True),
    ], keys=range(4)).groupby(level=1).mean()
    lowvol = (-ret.rolling(252).std()).rank(axis=1, pct=True)
    dates = px.index[260::21]
    out = {"from": dates[0].strftime("%Y-%m-%d") if len(dates) else None, "factors": {}}
    for name, f in (("momentum", mom), ("risk", lowvol)):
        res = {}
        for hk, h in horizons.items():
            fwd = px.shift(-h) / px - 1
            top, bot, allr = [], [], []
            for d in dates:
                x, y = f.loc[d], fwd.loc[d]
                ok = x.notna() & y.notna()
                if ok.sum() < 20:
                    continue
                r = x[ok].rank(pct=True)
                top.append(y[ok][r >= 0.8].mean())
                bot.append(y[ok][r <= 0.2].mean())
                allr.append(y[ok].mean())
            if top:
                res[hk] = {"top": round(float(np.mean(top)), 4), "bottom": round(float(np.mean(bot)), 4),
                           "all": round(float(np.mean(allr)), 4), "n": len(top),
                           "win": round(float(np.mean(np.array(top) > np.array(bot))), 3)}
        out["factors"][name] = res
    return out
