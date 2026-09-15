"""รวมตัวชี้วัดเป็นคะแนนกลุ่มปัจจัย และคะแนนแนะนำตามระยะเวลาลงทุน

ทุกตัวชี้วัดแปลงเป็น "เปอร์เซ็นไทล์" เทียบกับหุ้นในตลาดเดียวกัน (0 = แย่สุด, 1 = ดีสุด)
ตัวชี้วัดด้านมูลค่า/คุณภาพเทียบทั้งกับตลาดและกับกลุ่มอุตสาหกรรมเดียวกัน (ถ้ามีหุ้นในกลุ่มพอ)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config

# (ตัวชี้วัด, สูงยิ่งดี?, เทียบกับกลุ่มอุตสาหกรรมด้วย?)
METRICS = {
    "value": [("pe", False, True), ("forward_pe", False, True), ("pb", False, True),
              ("ev_ebitda", False, True), ("div_yield", True, False), ("fcf_yield", True, False)],
    "quality": [("roe", True, True), ("roa", True, True), ("net_margin", True, True),
                ("op_margin", True, True), ("de", False, True), ("current_ratio", True, False),
                ("fscore_norm", True, False)],
    "growth": [("rev_growth_q", True, False), ("earn_growth_q", True, False),
               ("rev_cagr3", True, False), ("ni_cagr3", True, False)],
    "momentum": [("ret_12_1", True, False), ("ret_6m", True, False), ("ret_3m", True, False),
                 ("dist_ma200", True, False)],
    "risk": [("vol_1y", False, False), ("maxdd_1y", True, False), ("beta", False, False),
             ("turnover_20d", True, False)],
}
MIN_SECTOR_SIZE = 5


def _rank(s: pd.Series, higher_better: bool) -> pd.Series:
    return s.rank(pct=True, ascending=higher_better)


def _blend_rank(df: pd.DataFrame, col: str, higher_better: bool, by_sector: bool) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    mkt = _rank(s, higher_better)
    if not by_sector:
        return mkt
    sec = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby("sector").groups.items():
        sub = s.loc[idx]
        if sub.notna().sum() >= MIN_SECTOR_SIZE:
            sec.loc[idx] = _rank(sub, higher_better)
    return (0.5 * mkt + 0.5 * sec).where(sec.notna(), mkt)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """ปรับค่าที่ต้องจัดการเป็นพิเศษก่อนจัดอันดับ"""
    df = df.copy()
    # ขาดทุน / ส่วนผู้ถือหุ้นติดลบ -> ถือว่าแพงที่สุด
    df.loc[df["loss_making"].fillna(False).astype(bool), "pe"] = math.inf
    for col in ("pe", "forward_pe", "pb", "ev_ebitda"):
        v = pd.to_numeric(df[col], errors="coerce")
        df[col] = v.where(~(v <= 0), math.inf)
    df["current_ratio"] = pd.to_numeric(df["current_ratio"], errors="coerce").clip(upper=3)
    df["beta"] = pd.to_numeric(df["beta_1y"], errors="coerce").fillna(
        pd.to_numeric(df["beta_info"], errors="coerce"))
    return df


def score(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """คืน (คะแนนกลุ่ม/คะแนนแนะนำ/ป้ายกำกับ, เปอร์เซ็นไทล์ของแต่ละตัวชี้วัด)"""
    df = prepare(df)
    ranks = pd.DataFrame(index=df.index)
    groups = pd.DataFrame(index=df.index)
    coverage = pd.DataFrame(index=df.index)
    for g, metrics in METRICS.items():
        cols = []
        for col, hb, sec in metrics:
            r = _blend_rank(df, col, hb, sec)
            ranks[col] = r
            cols.append(col)
        groups[g] = ranks[cols].mean(axis=1, skipna=True)
        coverage[g] = ranks[cols].notna().sum(axis=1) / len(cols)

    # นักวิเคราะห์: ราคาเป้าหมาย + คำแนะนำเฉลี่ย ความเชื่อมั่นตามจำนวนนักวิเคราะห์
    up_r = _rank(pd.to_numeric(df["upside"], errors="coerce"), True)
    rec_r = _rank(pd.to_numeric(df["rec_mean"], errors="coerce"), False)
    ranks["upside"], ranks["rec_mean"] = up_r, rec_r
    raw = pd.concat([up_r, rec_r], axis=1).mean(axis=1, skipna=True)
    conf = (pd.to_numeric(df["n_analysts"], errors="coerce").fillna(0) / 5).clip(upper=1)
    groups["analyst"] = 0.5 + (raw.fillna(0.5) - 0.5) * conf
    coverage["analyst"] = conf

    # ข่าว: โทนข่าว x ความครอบคลุม จัดอันดับเทียบกับหุ้นอื่น ข่าวน้อยถูกดึงเข้าหาค่ากลาง
    n_signal = (pd.to_numeric(df["n_pos"], errors="coerce").fillna(0)
                + pd.to_numeric(df["n_neg"], errors="coerce").fillna(0))
    news_cov = (n_signal / 4).clip(upper=1)
    news_raw = pd.to_numeric(df["news_sentiment"], errors="coerce").fillna(0) * news_cov
    groups["news"] = 0.5 + (_rank(news_raw, True) - 0.5) * news_cov
    coverage["news"] = news_cov

    groups = groups.fillna(0.5)
    out = pd.DataFrame(index=df.index)
    for g in config.GROUPS:
        out[f"g_{g}"] = groups[g]
    fundamental_cov = coverage[["value", "quality", "growth"]].mean(axis=1)
    out["data_coverage"] = fundamental_cov

    low = fundamental_cov < 0.3
    for hk, w in config.WEIGHTS.items():
        composite = sum(groups[g] * wt for g, wt in w.items())
        out[f"score_{hk}"] = composite
        out[f"rank_{hk}"] = composite.rank(ascending=False, method="min").astype(int)
        out[f"label_{hk}"] = [_label(p) for p in composite.rank(pct=True)]
        # ข้อมูลพื้นฐานน้อยมาก -> ไม่ให้ขึ้นกลุ่ม "เด่นมาก"
        out.loc[low & (out[f"label_{hk}"] == "strong"), f"label_{hk}"] = "good"
    return out, ranks


def _label(p: float) -> str:
    for thr, key, _ in config.LABELS:
        if p >= thr:
            return key
    return config.LABELS[-1][1]


def market_medians(df: pd.DataFrame) -> dict:
    def med(col, positive=False):
        s = pd.to_numeric(df[col], errors="coerce").replace([math.inf, -math.inf], np.nan).dropna()
        if positive:
            s = s[s > 0]
        return float(s.median()) if len(s) else math.nan

    return {
        "pe": med("pe", True), "forward_pe": med("forward_pe", True), "pb": med("pb", True),
        "ev_ebitda": med("ev_ebitda", True), "div_yield": med("div_yield"),
        "roe": med("roe"), "net_margin": med("net_margin"), "de": med("de"),
        "vol_1y": med("vol_1y"), "turnover_20d": med("turnover_20d"),
        "ret_6m": med("ret_6m"), "rev_growth_q": med("rev_growth_q"),
    }
