"""ดึงข้อมูลดิบจาก Yahoo Finance (ราคา งบการเงิน ข้อมูลบริษัท ข่าว) และ Google News RSS"""
from __future__ import annotations

import email.utils
import logging
import pickle
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

from . import config
from .universe import THAI_NEWS_ALIASES

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockLens/1.0"}


# ---------------------------------------------------------------- cache (สำหรับพัฒนา/รันซ้ำเร็ว)

def _cache_path(kind: str, key: str):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return config.CACHE_DIR / kind / f"{safe}.pkl"


def cache_load(kind: str, key: str, max_age_hours: float):
    p = _cache_path(kind, key)
    if not p.exists() or (time.time() - p.stat().st_mtime) > max_age_hours * 3600:
        return None
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def cache_save(kind: str, key: str, obj) -> None:
    p = _cache_path(kind, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump(obj, f)


# ---------------------------------------------------------------- prices

def download_prices(symbols: list[str], period: str = config.PRICE_HISTORY_PERIOD,
                    chunk: int = 40) -> dict[str, pd.DataFrame]:
    """ราคาปรับปันผล/แตกพาร์รายวัน -> {symbol: DataFrame[Open, High, Low, Close, Volume, Dividends]}"""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        for attempt in range(3):
            try:
                df = yf.download(batch, period=period, auto_adjust=True, actions=True,
                                 group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:  # network hiccup
                log.warning("download batch failed (%s), retry %d", e, attempt + 1)
                time.sleep(3 * (attempt + 1))
        else:
            continue
        for sym in batch:
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            sub = sub.dropna(subset=["Close"])
            if len(sub) < 30:
                continue
            sub.index = pd.to_datetime(sub.index).tz_localize(None)
            out[sym] = sub
    return out


# ---------------------------------------------------------------- fundamentals

def _retry(fn, tries=3, default=None):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:
            if attempt == tries - 1:
                log.debug("fetch failed: %s", e)
                return default
            time.sleep(1.5 * (attempt + 1))
    return default


def fetch_company(symbol: str) -> dict:
    """ข้อมูลบริษัท อัตราส่วน งบการเงิน และข่าวจาก Yahoo"""
    t = yf.Ticker(symbol)
    return {
        "info": _retry(lambda: t.info, default={}) or {},
        "income": _retry(lambda: t.income_stmt),
        "income_q": _retry(lambda: t.quarterly_income_stmt),
        "balance": _retry(lambda: t.balance_sheet),
        "cashflow": _retry(lambda: t.cashflow),
        "yahoo_news": _retry(lambda: t.news, default=[]) or [],
        "fetched_at": time.time(),
    }


# ---------------------------------------------------------------- news

def parse_yahoo_news(items: list) -> list[dict]:
    out = []
    for it in items or []:
        c = it.get("content", it) if isinstance(it, dict) else {}
        title = (c.get("title") or "").strip()
        if not title:
            continue
        url = ((c.get("canonicalUrl") or {}).get("url")
               or (c.get("clickThroughUrl") or {}).get("url") or "")
        pub = c.get("pubDate") or c.get("displayTime")
        try:
            ts = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None
        except ValueError:
            ts = None
        out.append({
            "title": title,
            "summary": (c.get("summary") or "")[:400],
            "source": (c.get("provider") or {}).get("displayName", "Yahoo Finance"),
            "url": url,
            "time": ts.isoformat() if ts else None,
            "lang": "en",
        })
    return out


def fetch_google_news(query: str, lang: str = "th", limit: int = 15) -> list[dict]:
    if lang == "th":
        params = "hl=th&gl=TH&ceid=TH:th"
    else:
        params = "hl=en-US&gl=US&ceid=US:en"
    q = urllib.parse.quote(f"{query} when:{config.NEWS_LOOKBACK_DAYS}d")
    url = f"https://news.google.com/rss/search?q={q}&{params}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        log.debug("google news failed for %s: %s", query, e)
        return []
    out = []
    for it in root.findall(".//item")[:limit * 2]:
        title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        source = src_el.text.strip() if src_el is not None and src_el.text else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3].strip()
        try:
            ts = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            ts = None
        out.append({
            "title": title,
            "summary": "",
            "source": source or "Google News",
            "url": it.findtext("link") or "",
            "time": ts.astimezone(timezone.utc).isoformat() if ts else None,
            "lang": lang,
        })
    return out


def _mentions(title: str, terms: list[str]) -> bool:
    for term in terms:
        if re.fullmatch(r"[A-Za-z0-9&.-]+", term):
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", title):
                return True
        elif term in title:
            return True
    return False


def gather_news(symbol: str, name: str, market: str, yahoo_items: list) -> list[dict]:
    """รวมข่าวจาก Yahoo + Google News ตัดข่าวซ้ำ เรียงจากใหม่ไปเก่า"""
    base = symbol.replace(".BK", "")
    news = parse_yahoo_news(yahoo_items)
    if market == "th":
        terms = THAI_NEWS_ALIASES.get(base) or [base]
        query = " OR ".join(f'"{t}"' for t in terms) + " หุ้น"
        g = fetch_google_news(query, "th")
        news += [n for n in g if _mentions(n["title"], terms)]
    else:
        company = name.split(" (")[0]
        news += fetch_google_news(f'"{company}" {base} stock', "en", limit=10)

    seen, dedup = set(), []
    for n in news:
        key = re.sub(r"\W+", "", n["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(n)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=config.NEWS_LOOKBACK_DAYS)
    dedup = [n for n in dedup if n["time"] is None or pd.Timestamp(n["time"]) >= cutoff]
    dedup.sort(key=lambda n: n["time"] or "", reverse=True)
    return dedup[: config.MAX_NEWS_PER_STOCK]


# ---------------------------------------------------------------- orchestration

def fetch_all_companies(symbols: dict[str, str], market: str, use_cache: bool = False,
                        workers: int = config.FETCH_WORKERS) -> dict[str, dict]:
    """ดึงข้อมูลบริษัท + ข่าว แบบขนาน -> {symbol: raw}"""
    results: dict[str, dict] = {}

    def job(sym: str):
        if use_cache:
            cached = cache_load("company", sym, max_age_hours=20)
            if cached is not None:
                return sym, cached
        raw = fetch_company(sym)
        raw["news"] = gather_news(sym, symbols[sym], market, raw.pop("yahoo_news", []))
        if raw["info"]:
            cache_save("company", sym, raw)
        return sym, raw

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(job, s) for s in symbols]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                sym, raw = f.result()
                results[sym] = raw
            except Exception as e:
                log.warning("company fetch error: %s", e)
            if i % 20 == 0:
                log.info("  [%s] ข้อมูลบริษัท %d/%d", market, i, len(symbols))
    return results
