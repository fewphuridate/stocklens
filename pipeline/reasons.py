"""สร้างเหตุผลภาษาไทย (จุดเด่น/ข้อควรระวัง) จากตัวเลขจริงของหุ้นแต่ละตัว

แต่ละข้อมีกลุ่มปัจจัย (g), ทิศทาง (s: +1 จุดเด่น / -1 ข้อควรระวัง), ความสำคัญ (w: 0..1)
หน้าเว็บจะเรียงเหตุผลตามน้ำหนักของกลุ่มปัจจัยในระยะเวลาลงทุนที่เลือก
"""
from __future__ import annotations

import math


def _ok(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and not (math.isnan(v) or math.isinf(v))


def pct(v, d=1, sign=False) -> str:
    s = f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%"
    return s


def money(v, ccy: str | None) -> str:
    if not _ok(v):
        return "-"
    if ccy == "THB":
        if abs(v) >= 1e9:
            return f"{v / 1e9:,.1f} พันล้านบาท"
        return f"{v / 1e6:,.1f} ล้านบาท"
    sym = "$" if ccy in (None, "USD") else f"{ccy} "
    if abs(v) >= 1e9:
        return f"{sym}{v / 1e9:,.1f}B"
    return f"{sym}{v / 1e6:,.1f}M"


def build(m: dict, r: dict, med: dict, ccy: str) -> list[dict]:
    """m = ตัวชี้วัดดิบ, r = เปอร์เซ็นไทล์ (0..1), med = ค่ากลางของตลาด"""
    facts: list[dict] = []

    def add(g, s, w, t):
        facts.append({"g": g, "s": s, "w": round(max(0.05, min(1.0, w)), 2), "t": t})

    rk = lambda k: r.get(k) if _ok(r.get(k)) else None  # noqa: E731

    # ---------------- มูลค่า
    pe, fpe = m.get("pe"), m.get("forward_pe")
    if m.get("loss_making"):
        add("value", -1, 0.8, "บริษัทยังขาดทุน (กำไรต่อหุ้น 12 เดือนล่าสุดติดลบ) จึงประเมินมูลค่าด้วย P/E ไม่ได้")
    elif _ok(pe) and pe > 0 and rk("pe") is not None:
        if rk("pe") >= 0.7:
            add("value", +1, rk("pe"), f"P/E {pe:.1f} เท่า ต่ำกว่าค่ากลางตลาด ({med['pe']:.1f} เท่า) — ราคาไม่แพงเมื่อเทียบกับกำไร")
        elif rk("pe") <= 0.25:
            add("value", -1, 1 - rk("pe"), f"P/E {pe:.1f} เท่า สูงกว่าค่ากลางตลาด ({med['pe']:.1f} เท่า) — ราคาสะท้อนความคาดหวังไปมากแล้ว")
    if _ok(pe) and _ok(fpe) and pe > 0 and 0 < fpe < pe * 0.88:
        add("value", +1, 0.55, f"P/E ล่วงหน้า {fpe:.1f} เท่า ต่ำกว่า P/E ปัจจุบัน — นักวิเคราะห์คาดกำไรปีหน้าเพิ่มขึ้น")
    elif _ok(pe) and _ok(fpe) and pe > 0 and fpe > pe * 1.15:
        add("value", -1, 0.45, f"P/E ล่วงหน้า {fpe:.1f} เท่า สูงกว่า P/E ปัจจุบัน — ตลาดคาดกำไรลดลง")
    pb = m.get("pb")
    if _ok(pb) and pb > 0 and rk("pb") is not None and rk("pb") >= 0.75:
        extra = " (ต่ำกว่ามูลค่าทางบัญชี)" if pb < 1 else ""
        add("value", +1, rk("pb") * 0.8, f"P/BV {pb:.2f} เท่า ต่ำกว่าค่ากลาง ({med['pb']:.2f} เท่า){extra}")
    dy = m.get("div_yield")
    if _ok(dy) and dy >= 0.03 and _ok(med.get("div_yield")) and dy >= med["div_yield"] * 1.3:
        add("value", +1, min(1, dy / 0.08), f"อัตราปันผลย้อนหลัง 12 เดือน {pct(dy)} สูงกว่าค่ากลางตลาด ({pct(med['div_yield'])})")
    ev = m.get("ev_ebitda")
    if _ok(ev) and ev > 0 and rk("ev_ebitda") is not None and rk("ev_ebitda") >= 0.8:
        add("value", +1, 0.5, f"EV/EBITDA {ev:.1f} เท่า อยู่ในกลุ่มต่ำของตลาด")
    fy = m.get("fcf_yield")
    if _ok(fy):
        if fy >= 0.06:
            add("value", +1, min(1, fy / 0.12), f"กระแสเงินสดอิสระคิดเป็น {pct(fy)} ของมูลค่าตลาด — สร้างเงินสดได้ดี")
        elif fy < 0:
            add("value", -1, 0.45, "กระแสเงินสดอิสระติดลบ — ใช้เงินลงทุนมากกว่าเงินสดที่หาได้")

    # ---------------- คุณภาพ
    roe = m.get("roe")
    if _ok(roe):
        if roe >= 0.15:
            add("quality", +1, min(1, roe / 0.3), f"ROE {pct(roe)} — ใช้เงินของผู้ถือหุ้นสร้างกำไรได้ดี")
        elif roe < 0:
            add("quality", -1, 0.8, f"ROE ติดลบ ({pct(roe)}) — ส่วนของผู้ถือหุ้นลดลงจากผลขาดทุน")
        elif roe < 0.05:
            add("quality", -1, 0.5, f"ROE ต่ำเพียง {pct(roe)}")
    nm = m.get("net_margin")
    if _ok(nm):
        if nm < 0:
            add("quality", -1, 0.7, f"อัตรากำไรสุทธิติดลบ ({pct(nm)})")
        elif rk("net_margin") is not None and rk("net_margin") >= 0.75:
            add("quality", +1, rk("net_margin") * 0.8, f"อัตรากำไรสุทธิ {pct(nm)} สูงเมื่อเทียบกับบริษัทในกลุ่มเดียวกัน")
    de = m.get("de")
    if _ok(de) and not m.get("is_financial"):
        if de <= 0.5:
            add("quality", +1, 0.55, f"หนี้สินต่ำ (หนี้สินที่มีภาระดอกเบี้ยต่อทุน {de:.2f} เท่า)")
        elif de >= 2:
            add("quality", -1, min(1, de / 4), f"หนี้สินค่อนข้างสูง (หนี้สินที่มีภาระดอกเบี้ยต่อทุน {de:.2f} เท่า)")
    cr = m.get("current_ratio")
    if _ok(cr) and not m.get("is_financial") and cr < 1:
        add("quality", -1, 0.4, f"สภาพคล่องระยะสั้นตึงตัว (Current ratio {cr:.2f} เท่า)")
    fs, fn = m.get("fscore"), m.get("fscore_n") or 0
    if fs is not None and fn >= 7:
        if fs >= 7:
            add("quality", +1, 0.7, f"Piotroski F-Score {fs}/{fn} — ฐานะการเงินแข็งแรงขึ้นจากปีก่อน")
        elif fs <= 3:
            add("quality", -1, 0.6, f"Piotroski F-Score {fs}/{fn} — ฐานะการเงินอ่อนลงจากปีก่อน")

    # ---------------- การเติบโต
    rg = m.get("rev_growth_q")
    if _ok(rg):
        if rg >= 0.10:
            add("growth", +1, min(1, rg / 0.3), f"รายได้ไตรมาสล่าสุดโต {pct(rg)} เทียบกับปีก่อน")
        elif rg <= -0.05:
            add("growth", -1, min(1, -rg / 0.2), f"รายได้ไตรมาสล่าสุดลดลง {pct(-rg)} เทียบกับปีก่อน")
    eg = m.get("earn_growth_q")
    if _ok(eg):
        if eg >= 0.15:
            add("growth", +1, min(1, eg / 0.5), f"กำไรไตรมาสล่าสุดโต {pct(eg)} เทียบกับปีก่อน")
        elif eg <= -0.15:
            add("growth", -1, min(1, -eg / 0.5), f"กำไรไตรมาสล่าสุดลดลง {pct(-eg)} เทียบกับปีก่อน")
    rc = m.get("rev_cagr3")
    if _ok(rc):
        if rc >= 0.08:
            add("growth", +1, min(1, rc / 0.25), f"รายได้เติบโตเฉลี่ย {pct(rc)} ต่อปี (ย้อนหลังสูงสุด 3 ปี)")
        elif rc < -0.03:
            add("growth", -1, min(1, -rc / 0.15), f"รายได้หดตัวเฉลี่ย {pct(-rc)} ต่อปี (ย้อนหลังสูงสุด 3 ปี)")
    nc = m.get("ni_cagr3")
    if _ok(nc):
        if nc == 0.5:
            add("growth", +1, 0.5, "พลิกจากขาดทุนกลับมามีกำไรในช่วง 3 ปีที่ผ่านมา")
        elif nc == -1.0:
            add("growth", -1, 0.8, "จากเคยมีกำไร กลายเป็นขาดทุนในปีล่าสุด")
        elif nc >= 0.10:
            add("growth", +1, min(1, nc / 0.3), f"กำไรสุทธิเติบโตเฉลี่ย {pct(nc)} ต่อปี (ย้อนหลังสูงสุด 3 ปี)")
        elif nc <= -0.10:
            add("growth", -1, min(1, -nc / 0.3), f"กำไรสุทธิลดลงเฉลี่ย {pct(-nc)} ต่อปี (ย้อนหลังสูงสุด 3 ปี)")

    # ---------------- แนวโน้มราคา
    d200, golden = m.get("dist_ma200"), m.get("ma50_above_ma200")
    if _ok(d200):
        if d200 > 0 and golden:
            add("momentum", +1, min(1, 0.5 + d200), f"ราคาอยู่เหนือเส้นค่าเฉลี่ย 200 วัน {pct(d200)} และเส้น 50 วันอยู่เหนือเส้น 200 วัน — แนวโน้มขาขึ้น")
        elif d200 < 0 and golden is False:
            add("momentum", -1, min(1, 0.5 - d200), f"ราคาอยู่ใต้เส้นค่าเฉลี่ย 200 วัน {pct(-d200)} และเส้น 50 วันอยู่ใต้เส้น 200 วัน — แนวโน้มขาลง")
    r6 = m.get("ret_6m")
    if _ok(r6) and rk("ret_6m") is not None:
        if rk("ret_6m") >= 0.8:
            add("momentum", +1, rk("ret_6m") * 0.8, f"ผลตอบแทน 6 เดือน {pct(r6, sign=True)} ดีกว่า {rk('ret_6m') * 100:.0f}% ของหุ้นในตลาด")
        elif rk("ret_6m") <= 0.2:
            add("momentum", -1, (1 - rk("ret_6m")) * 0.7, f"ผลตอบแทน 6 เดือน {pct(r6, sign=True)} แย่กว่าหุ้นส่วนใหญ่ในตลาด")
    rsi = m.get("rsi14")
    if _ok(rsi):
        if rsi >= 75:
            add("momentum", -1, 0.4, f"RSI {rsi:.0f} — ราคาขึ้นแรงต่อเนื่อง อาจพักตัวระยะสั้น")
        elif rsi <= 28:
            add("momentum", -1, 0.3, f"RSI {rsi:.0f} — มีแรงขายหนัก ควรรอสัญญาณกลับตัว")
    dh = m.get("dist_high")
    if _ok(dh):
        if dh >= -0.03:
            add("momentum", +1, 0.45, "ราคาอยู่ใกล้จุดสูงสุดในรอบ 52 สัปดาห์")
        elif dh <= -0.40:
            add("momentum", -1, min(1, -dh), f"ราคาต่ำกว่าจุดสูงสุดรอบ 52 สัปดาห์ {pct(-dh, 0)}")

    # ---------------- นักวิเคราะห์
    na, up, rec = m.get("n_analysts") or 0, m.get("upside"), m.get("rec_mean")
    if na >= 3 and _ok(up):
        if up >= 0.10:
            add("analyst", +1, min(1, up / 0.3) * min(1, na / 8), f"นักวิเคราะห์ {na} ราย ให้ราคาเป้าหมายเฉลี่ย {m['target_mean']:,.2f} สูงกว่าราคาปัจจุบัน {pct(up)}")
        elif up <= -0.05:
            add("analyst", -1, min(1, -up / 0.2), f"ราคาปัจจุบันสูงกว่าราคาเป้าหมายเฉลี่ยของนักวิเคราะห์ ({m['target_mean']:,.2f}) อยู่ {pct(-up)}")
    if na >= 3 and _ok(rec):
        if rec <= 2.0:
            add("analyst", +1, 0.5, f"คำแนะนำเฉลี่ยของนักวิเคราะห์อยู่ในระดับ \"ซื้อ\" ({rec:.1f} จาก 1=ซื้อมาก ถึง 5=ขาย)")
        elif rec >= 3.0:
            add("analyst", -1, 0.5, f"คำแนะนำเฉลี่ยของนักวิเคราะห์อยู่ในระดับ \"ถือ/ขาย\" ({rec:.1f} จาก 5)")

    # ---------------- ข่าว
    s, npos, nneg = m.get("news_sentiment") or 0, m.get("n_pos") or 0, m.get("n_neg") or 0
    if npos + nneg >= 3:
        if s >= 0.15:
            add("news", +1, min(1, 0.4 + s), f"ข่าวช่วง 30 วันล่าสุดโทนบวก (บวก {npos} ข่าว / ลบ {nneg} ข่าว)")
        elif s <= -0.15:
            add("news", -1, min(1, 0.4 - s), f"ข่าวช่วง 30 วันล่าสุดโทนลบ (ลบ {nneg} ข่าว / บวก {npos} ข่าว)")

    # ---------------- ความเสี่ยง
    vol = m.get("vol_1y")
    if _ok(vol) and rk("vol_1y") is not None:
        if rk("vol_1y") >= 0.75:
            add("risk", +1, 0.45, f"ราคาผันผวนต่ำ ({pct(vol, 0)} ต่อปี) เหมาะกับการถือแบบสบายใจ")
        elif rk("vol_1y") <= 0.2:
            add("risk", -1, 0.6, f"ราคาผันผวนสูง ({pct(vol, 0)} ต่อปี) — ขึ้นลงแรง ควรจำกัดสัดส่วนการลงทุน")
    tv = m.get("turnover_20d")
    if _ok(tv) and rk("turnover_20d") is not None and rk("turnover_20d") <= 0.12:
        add("risk", -1, 0.5, f"สภาพคล่องต่ำ (มูลค่าซื้อขายเฉลี่ย {money(tv, ccy)} ต่อวัน)")
    dd = m.get("maxdd_1y")
    if _ok(dd) and dd <= -0.35:
        add("risk", -1, min(1, -dd), f"ในรอบ 1 ปี ราคาเคยปรับลงจากจุดสูงสุดลึกถึง {pct(-dd, 0)}")

    facts.sort(key=lambda f: -f["w"])
    return facts
