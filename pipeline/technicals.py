"""ตัวชี้วัดทางราคา: ผลตอบแทน เส้นค่าเฉลี่ย RSI ความผันผวน ฯลฯ"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _ret(c: pd.Series, n: int) -> float:
    if len(c) <= n:
        return math.nan
    return float(c.iloc[-1] / c.iloc[-1 - n] - 1)


def rsi(c: pd.Series, n: int = 14) -> float:
    d = c.diff().dropna()
    if len(d) < n + 1:
        return math.nan
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up.iloc[-1] / dn.iloc[-1] if dn.iloc[-1] > 0 else math.inf
    return float(100 - 100 / (1 + rs))


def compute(df: pd.DataFrame, bench: pd.Series | None = None) -> dict:
    c = df["Close"].astype(float)
    last = float(c.iloc[-1])
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()
    daily = c.pct_change().dropna()
    last_year = c.iloc[-252:]

    out = {
        "price": last,
        "date": c.index[-1].strftime("%Y-%m-%d"),
        "ret_1d": _ret(c, 1),
        "ret_1w": _ret(c, 5),
        "ret_1m": _ret(c, 21),
        "ret_3m": _ret(c, 63),
        "ret_6m": _ret(c, 126),
        "ret_12m": _ret(c, 252),
        "ret_12_1": float(c.iloc[-22] / c.iloc[-253] - 1) if len(c) > 253 else math.nan,
        "ma50": float(ma50.iloc[-1]) if not math.isnan(ma50.iloc[-1]) else math.nan,
        "ma200": float(ma200.iloc[-1]) if not math.isnan(ma200.iloc[-1]) else math.nan,
        "rsi14": rsi(c),
        "vol_1y": float(daily.iloc[-252:].std() * math.sqrt(252)) if len(daily) > 60 else math.nan,
        "maxdd_1y": float((last_year / last_year.cummax() - 1).min()),
        "high_52w": float(last_year.max()),
        "low_52w": float(last_year.min()),
    }
    out["dist_ma200"] = last / out["ma200"] - 1 if out["ma200"] == out["ma200"] else math.nan
    out["ma50_above_ma200"] = (bool(out["ma50"] > out["ma200"])
                               if out["ma200"] == out["ma200"] else None)
    out["dist_high"] = last / out["high_52w"] - 1

    prev_year = c[c.index < pd.Timestamp(c.index[-1].year, 1, 1)]
    out["ret_ytd"] = float(last / prev_year.iloc[-1] - 1) if len(prev_year) else math.nan

    if "Volume" in df:
        tv = (df["Close"] * df["Volume"]).iloc[-20:]
        out["turnover_20d"] = float(tv.mean()) if len(tv) else math.nan
    else:
        out["turnover_20d"] = math.nan

    if "Dividends" in df:
        divs = df["Dividends"]
        divs = divs[divs.index > c.index[-1] - pd.Timedelta(days=365)]
        out["div_ttm"] = float(divs.sum())
        out["div_yield_ttm"] = out["div_ttm"] / last if last > 0 else math.nan
    else:
        out["div_ttm"] = math.nan
        out["div_yield_ttm"] = math.nan

    out["beta_1y"] = math.nan
    if bench is not None and len(bench) > 60:
        b = bench.pct_change()
        joined = pd.concat([daily, b], axis=1, join="inner").dropna().iloc[-252:]
        if len(joined) > 60 and joined.iloc[:, 1].var() > 0:
            out["beta_1y"] = float(joined.cov().iloc[0, 1] / joined.iloc[:, 1].var())
    return out


def chart_series(df: pd.DataFrame) -> dict:
    """ข้อมูลกราฟราคา: รายวัน 1 ปี (+MA50/MA200) และรายสัปดาห์ 5 ปี"""
    c = df["Close"].astype(float)
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()

    def pack(idx, *series):
        rows = []
        for i in idx:
            rows.append([i.strftime("%Y-%m-%d")] +
                        [None if (v := s.loc[i]) != v else round(float(v), 4) for s in series])
        return rows

    daily_idx = c.index[-260:]
    weekly = c[c.index >= c.index[-1] - pd.Timedelta(days=365 * 5 + 7)]
    weekly_idx = weekly.groupby(weekly.index.to_period("W")).tail(1).index
    return {
        "d": pack(daily_idx, c, ma50, ma200),
        "w": pack(weekly_idx, c, ma50, ma200),
    }


def clean(v):
    """แปลงค่า NaN/inf เป็น None เพื่อเขียน JSON"""
    if isinstance(v, (float, np.floating)):
        return None if (math.isnan(v) or math.isinf(v)) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v
