"""ปัจจัยพื้นฐาน: อัตราส่วนทางการเงิน งบการเงินย้อนหลัง การเติบโต และ Piotroski F-Score"""
from __future__ import annotations

import math

import pandas as pd

FINANCIAL_SECTORS = {"Financial Services"}

ROWS = {
    "income": {
        "revenue": ["Total Revenue", "Operating Revenue"],
        "gross_profit": ["Gross Profit"],
        "operating_income": ["Operating Income", "Total Operating Income As Reported"],
        "net_income": ["Net Income", "Net Income Common Stockholders",
                       "Net Income From Continuing Operation Net Minority Interest"],
        "eps": ["Diluted EPS", "Basic EPS"],
        "ebitda": ["EBITDA", "Normalized EBITDA"],
    },
    "balance": {
        "total_assets": ["Total Assets"],
        "total_liabilities": ["Total Liabilities Net Minority Interest"],
        "equity": ["Stockholders Equity", "Common Stock Equity"],
        "total_debt": ["Total Debt"],
        "cash": ["Cash And Cash Equivalents",
                 "Cash Cash Equivalents And Short Term Investments"],
        "current_assets": ["Current Assets"],
        "current_liabilities": ["Current Liabilities"],
        "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
        "shares": ["Ordinary Shares Number", "Share Issued"],
    },
    "cashflow": {
        "ocf": ["Operating Cash Flow"],
        "capex": ["Capital Expenditure"],
        "fcf": ["Free Cash Flow"],
    },
}

# รายการที่แสดงในตารางงบการเงินบนเว็บ (ตามลำดับ)
TABLE_ROWS = ["revenue", "gross_profit", "operating_income", "net_income", "eps", "ebitda",
              "total_assets", "total_liabilities", "equity", "total_debt", "cash",
              "ocf", "capex", "fcf"]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return math.nan
    return f if not (math.isnan(f) or math.isinf(f)) else math.nan


def _row(df: pd.DataFrame | None, names: list[str]) -> pd.Series:
    """ดึงแถวจากงบการเงิน -> Series เรียงจากปีเก่าไปใหม่"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.Series(dtype=float)
    for n in names:
        if n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce")
            if isinstance(s, pd.DataFrame):
                s = s.iloc[0]
            s.index = pd.to_datetime(s.index)
            return s.sort_index()
    return pd.Series(dtype=float)


def statements(raw: dict) -> dict[str, pd.Series]:
    out = {}
    for kind, rows in ROWS.items():
        for key, names in rows.items():
            out[key] = _row(raw.get(kind), names)
    out["q_revenue"] = _row(raw.get("income_q"), ROWS["income"]["revenue"])
    out["q_net_income"] = _row(raw.get("income_q"), ROWS["income"]["net_income"])
    return out


def _cagr(s: pd.Series, years: int = 3):
    s = s.dropna()
    if len(s) < 2:
        return math.nan
    s = s.iloc[-(years + 1):]
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    n = len(s) - 1
    if first > 0 and last > 0:
        return (last / first) ** (1 / n) - 1
    if first > 0 >= last:
        return -1.0  # จากกำไรกลายเป็นขาดทุน
    if first <= 0 < last:
        return 0.5  # พลิกจากขาดทุนเป็นกำไร
    return math.nan


def piotroski(st: dict[str, pd.Series]) -> tuple[int | None, int]:
    """Piotroski F-Score จากงบ 2 ปีล่าสุด -> (คะแนนที่ผ่าน, จำนวนข้อที่ประเมินได้)"""
    def last2(key):
        s = st.get(key, pd.Series(dtype=float)).dropna()
        return (float(s.iloc[-1]), float(s.iloc[-2])) if len(s) >= 2 else (math.nan, math.nan)

    ni, ni0 = last2("net_income")
    ta, ta0 = last2("total_assets")
    ocf, _ = last2("ocf")
    ltd, ltd0 = last2("long_term_debt")
    ca, ca0 = last2("current_assets")
    cl, cl0 = last2("current_liabilities")
    sh, sh0 = last2("shares")
    gp, gp0 = last2("gross_profit")
    rev, rev0 = last2("revenue")

    tests = []

    def add(cond_values, cond):
        if all(v == v for v in cond_values):
            tests.append(bool(cond()))

    add([ni, ta], lambda: ni / ta > 0)
    add([ocf], lambda: ocf > 0)
    add([ni, ta, ni0, ta0], lambda: ni / ta > ni0 / ta0)
    add([ocf, ni], lambda: ocf > ni)
    add([ltd, ta, ltd0, ta0], lambda: ltd / ta <= ltd0 / ta0)
    add([ca, cl, ca0, cl0], lambda: cl > 0 and cl0 > 0 and ca / cl > ca0 / cl0)
    add([sh, sh0], lambda: sh <= sh0 * 1.005)
    add([gp, rev, gp0, rev0], lambda: rev > 0 and rev0 > 0 and gp / rev > gp0 / rev0)
    add([rev, ta, rev0, ta0], lambda: rev / ta > rev0 / ta0)
    if not tests:
        return None, 0
    return sum(tests), len(tests)


def compute(raw: dict, price: float) -> dict:
    info = raw.get("info") or {}
    st = statements(raw)
    sector = info.get("sector") or "อื่นๆ"
    is_fin = sector in FINANCIAL_SECTORS
    fin_ccy = info.get("financialCurrency")
    ccy = info.get("currency")
    same_ccy = not fin_ccy or not ccy or fin_ccy == ccy

    mcap = _num(info.get("marketCap"))
    eps = _num(info.get("trailingEps"))
    pe = _num(info.get("trailingPE"))
    loss_making = eps == eps and eps <= 0
    fpe = _num(info.get("forwardPE"))
    pb = _num(info.get("priceToBook"))
    de = _num(info.get("debtToEquity"))
    fcf = _num(info.get("freeCashflow"))

    f_pass, f_total = piotroski(st)

    out = {
        "name_en": info.get("longName") or info.get("shortName"),
        "sector": sector,
        "industry": info.get("industry"),
        "is_financial": is_fin,
        "currency": ccy,
        "financial_currency": fin_ccy,
        "market_cap": mcap,
        "pe": pe,
        "loss_making": bool(loss_making),
        "forward_pe": fpe,
        "pb": pb,
        "ev_ebitda": None if is_fin else _num(info.get("enterpriseToEbitda")),
        "div_yield_info": _num(info.get("dividendYield")) / 100 if info.get("dividendYield") is not None else math.nan,
        "payout_ratio": _num(info.get("payoutRatio")),
        "fcf_yield": fcf / mcap if (not is_fin and same_ccy and mcap and mcap > 0 and fcf == fcf) else math.nan,
        "roe": _num(info.get("returnOnEquity")),
        "roa": _num(info.get("returnOnAssets")),
        "net_margin": _num(info.get("profitMargins")),
        "op_margin": _num(info.get("operatingMargins")),
        "gross_margin": None if is_fin else _num(info.get("grossMargins")),
        "de": None if is_fin else (de / 100 if de == de else math.nan),
        "current_ratio": None if is_fin else _num(info.get("currentRatio")),
        "rev_growth_q": _num(info.get("revenueGrowth")),
        "earn_growth_q": _num(info.get("earningsGrowth")),
        "rev_cagr3": _cagr(st["revenue"]),
        "ni_cagr3": _cagr(st["net_income"]),
        "fscore": f_pass,
        "fscore_n": f_total,
        "fscore_norm": (f_pass / f_total) if f_pass is not None and f_total >= 6 else math.nan,
        "target_mean": _num(info.get("targetMeanPrice")),
        "target_high": _num(info.get("targetHighPrice")),
        "target_low": _num(info.get("targetLowPrice")),
        "rec_mean": _num(info.get("recommendationMean")),
        "rec_key": info.get("recommendationKey"),
        "n_analysts": int(info.get("numberOfAnalystOpinions") or 0),
        "beta_info": _num(info.get("beta")),
        "summary": (info.get("longBusinessSummary") or "")[:1200],
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
    }
    tm = out["target_mean"]
    out["upside"] = tm / price - 1 if (tm == tm and tm and price) else math.nan
    if out["pe"] != out["pe"] and eps == eps and eps > 0 and price:
        out["pe"] = price / eps
    return out


def statement_tables(raw: dict) -> dict:
    """ตารางงบการเงินย้อนหลังสำหรับหน้ารายละเอียด"""
    st = statements(raw)
    years = sorted({d for k in TABLE_ROWS for d in st[k].dropna().index})[-5:]
    annual = {
        "periods": [d.strftime("%Y-%m") for d in years],
        "rows": {k: [None if (v := _num(st[k].get(d))) != v else v for d in years]
                 for k in TABLE_ROWS},
    }
    qs = sorted(set(st["q_revenue"].dropna().index) | set(st["q_net_income"].dropna().index))[-6:]
    quarterly = {
        "periods": [d.strftime("%Y-%m") for d in qs],
        "rows": {
            "revenue": [None if (v := _num(st["q_revenue"].get(d))) != v else v for d in qs],
            "net_income": [None if (v := _num(st["q_net_income"].get(d))) != v else v for d in qs],
        },
    }
    return {"annual": annual, "quarterly": quarterly}
