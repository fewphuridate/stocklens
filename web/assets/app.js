/* StockLens — หน้าเว็บหลัก (ไม่ต้อง build ใช้ได้ทันที) */
(function () {
  'use strict';
  const C = window.SLCharts;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };

  const HK = ['1m', '3m', '6m', '9m'];
  const HLABEL = { '1m': '1 เดือน', '3m': '3 เดือน', '6m': '6 เดือน', '9m': '9 เดือน' };
  const LABELS = {
    strong: { t: 'เด่นมาก', ic: '▲▲', cls: 'lb-strong' },
    good: { t: 'น่าสนใจ', ic: '▲', cls: 'lb-good' },
    neutral: { t: 'ปานกลาง', ic: '●', cls: 'lb-neutral' },
    weak: { t: 'ควรระวัง', ic: '▼', cls: 'lb-weak' },
  };
  const LABEL_ORDER = { strong: 0, good: 1, neutral: 2, weak: 3 };
  const GROUPS = ['value', 'quality', 'growth', 'momentum', 'analyst', 'news', 'risk'];
  const REC_KEY = { strong_buy: 'ซื้อมาก', buy: 'ซื้อ', hold: 'ถือ', underperform: 'ต่ำกว่าตลาด', sell: 'ขาย' };
  const TABS = ['th', 'us', 'watch', 'track', 'method'];
  const STATE_SHORT = {
    0: 'ใต้ MA200 · โมเมนตัมอ่อน', 1: 'ใต้ MA200 · โมเมนตัมกลาง', 2: 'ใต้ MA200 · โมเมนตัมแรง',
    3: 'เหนือ MA200 · โมเมนตัมอ่อน', 4: 'เหนือ MA200 · โมเมนตัมกลาง', 5: 'เหนือ MA200 · โมเมนตัมแรง',
  };

  const S = {
    tab: 'th', horizon: store.get('sl-h', '3m'), sector: '', q: '', label: '', sort: null,
    meta: null, markets: {}, details: {}, track: null,
    watch: store.get('sl-watch', {}), openSym: null, range: '1y', viewKey: null, lastFocus: null,
  };
  if (!HK.includes(S.horizon)) S.horizon = '3m';

  // ------------------------------------------------------------ format
  const isNum = v => typeof v === 'number' && isFinite(v);
  function num(v, d = 2) {
    return isNum(v) ? v.toLocaleString('th-TH', { minimumFractionDigits: d, maximumFractionDigits: d }) : '–';
  }
  function pct(v, d = 1, sign = false) {
    if (!isNum(v)) return '–';
    const r = Math.round(v * 100 * 10 ** d) / 10 ** d || 0;  // || 0 ตัด -0
    const s = r.toLocaleString('th-TH', { minimumFractionDigits: d, maximumFractionDigits: d });
    return (sign && r > 0 ? '+' : '') + s + '%';
  }
  function price(v) { return isNum(v) ? num(v, v >= 10000 ? 0 : 2) : '–'; }
  function compact(v, ccy) {
    if (!isNum(v)) return '–';
    const a = Math.abs(v);
    if (ccy === 'THB') {
      if (a >= 1e12) return num(v / 1e12, 2) + ' ล้านล้านบาท';
      if (a >= 1e9) return num(v / 1e9, 1) + ' พันล้านบาท';
      if (a >= 1e6) return num(v / 1e6, 1) + ' ล้านบาท';
      return num(v, 0) + ' บาท';
    }
    const p = ccy && ccy !== 'USD' ? ccy + ' ' : '$';
    if (a >= 1e12) return p + num(v / 1e12, 2) + 'T';
    if (a >= 1e9) return p + num(v / 1e9, 1) + 'B';
    if (a >= 1e6) return p + num(v / 1e6, 1) + 'M';
    return p + num(v, 0);
  }
  function dateTH(iso, withTime = false) {
    if (!iso) return '–';
    const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
    if (isNaN(d)) return iso;
    const o = { day: 'numeric', month: 'short', year: 'numeric' };
    if (withTime) Object.assign(o, { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleString('th-TH', o);
  }
  function ago(iso) {
    if (!iso) return '';
    const days = (Date.now() - new Date(iso).getTime()) / 864e5;
    if (days < 1 / 24) return 'เมื่อสักครู่';
    if (days < 1) return Math.round(days * 24) + ' ชม.ที่แล้ว';
    if (days < 30) return Math.round(days) + ' วันที่แล้ว';
    return dateTH(iso);
  }
  function chg(v, d = 1) {
    if (!isNum(v)) return '<span class="chg flat">–</span>';
    const cls = v > 0.0005 ? 'up' : v < -0.0005 ? 'down' : 'flat';
    const ic = cls === 'up' ? '▲' : cls === 'down' ? '▼' : '•';
    return `<span class="chg ${cls}">${ic} ${pct(Math.abs(v), d)}</span>`;
  }
  function badge(label) {
    const L = LABELS[label] || LABELS.neutral;
    return `<span class="badge ${L.cls}"><span class="ic" aria-hidden="true">${L.ic}</span>${L.t}</span>`;
  }
  function meter(v, mid = false) {
    const w = Math.max(0, Math.min(100, v));
    return `<span class="meter" role="img" aria-label="${num(v, 0)} จาก 100"><i style="width:${w}%"></i>${mid ? '<span class="mid"></span>' : ''}</span>`;
  }
  const ccyOf = mk => (S.meta && S.meta.markets[mk] ? S.meta.markets[mk].currency : 'USD');

  // ------------------------------------------------------------ data
  async function getJSON(path, bust = true) {
    const v = S.meta ? encodeURIComponent(S.meta.generated_at || '') : Date.now();
    const r = await fetch(`data/${path}${bust ? `?v=${v}` : ''}`, bust ? {} : { cache: 'no-store' });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  }
  async function loadMarket(mk) {
    if (!S.markets[mk]) {
      const d = await getJSON(`${mk}.json`);
      d.bySym = Object.fromEntries(d.stocks.map(s => [s.sym, s]));
      S.markets[mk] = d;
    }
    return S.markets[mk];
  }
  async function loadDetail(sym) {
    if (!S.details[sym]) S.details[sym] = await getJSON(`stocks/${encodeURIComponent(sym)}.json`);
    return S.details[sym];
  }
  function marketOf(sym) { return /\.BK$/.test(sym) ? 'th' : 'us'; }
  function findStock(sym) {
    const d = S.markets[marketOf(sym)];
    return d ? d.bySym[sym] : null;
  }

  // ------------------------------------------------------------ watchlist
  function isWatched(sym) { return !!S.watch[sym]; }
  function toggleWatch(sym) {
    if (S.watch[sym]) delete S.watch[sym];
    else {
      const s = findStock(sym);
      S.watch[sym] = { at: new Date().toISOString().slice(0, 10), price: s ? s.price : null };
    }
    store.set('sl-watch', S.watch);
    $$(`[data-star="${CSS.escape(sym)}"]`).forEach(b => setStar(b, isWatched(sym)));
    updateWatchCount();
    if (S.tab === 'watch') renderView(true);
  }
  function starBtn(sym, small = false) {
    const on = isWatched(sym);
    return `<button class="star${small ? ' sm' : ''}" data-star="${esc(sym)}" aria-pressed="${on}" title="${on ? 'เลิกติดตาม' : 'เพิ่มในรายการติดตาม'}">${on ? '★' : '☆'}${small ? '' : (on ? ' ติดตามอยู่' : ' ติดตาม')}</button>`;
  }
  function setStar(b, on) {
    b.setAttribute('aria-pressed', on);
    b.title = on ? 'เลิกติดตาม' : 'เพิ่มในรายการติดตาม';
    b.textContent = (on ? '★' : '☆') + (b.classList.contains('sm') ? '' : (on ? ' ติดตามอยู่' : ' ติดตาม'));
  }
  function updateWatchCount() {
    const n = Object.keys(S.watch).length;
    $('#watch-count').textContent = n ? String(n) : '';
  }

  // ------------------------------------------------------------ reasons
  function factsFor(s, h, nPos = 4, nNeg = 3) {
    const w = S.meta.weights[h] || {};
    const k = f => f.w * (w[f.g] ?? 0.1);
    const pos = s.facts.filter(f => f.s > 0).sort((a, b) => k(b) - k(a)).slice(0, nPos);
    const neg = s.facts.filter(f => f.s < 0).sort((a, b) => k(b) - k(a)).slice(0, nNeg);
    return { pos, neg };
  }
  function reasonsList(facts) {
    return facts.map(f => `<li class="${f.s < 0 ? 'neg' : ''}">${esc(f.t)}</li>`).join('');
  }

  // ------------------------------------------------------------ routing
  function parseHash() {
    const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
    const tab = TABS.includes(parts[0]) ? parts[0] : 'th';
    let h = S.horizon, sym = null;
    parts.slice(1).forEach(p => { if (HK.includes(p)) h = p; else sym = p; });
    return { tab, h, sym };
  }
  function hashFor(tab, h, sym) {
    const withH = tab === 'th' || tab === 'us' || tab === 'watch';
    return '#/' + [tab, withH ? h : null, sym].filter(Boolean).map(encodeURIComponent).join('/');
  }
  function go(tab = S.tab, h = S.horizon, sym = null) { location.hash = hashFor(tab, h, sym); }

  async function route() {
    const { tab, h, sym } = parseHash();
    const key = tab + '|' + h;
    S.tab = tab; S.horizon = h; store.set('sl-h', h);
    $$('#tabs button').forEach(b => b.setAttribute('aria-current', b.dataset.tab === tab ? 'page' : 'false'));
    if (key !== S.viewKey) {
      if (S.viewKey && S.viewKey.split('|')[0] !== tab) { S.sector = ''; S.q = ''; S.label = ''; S.sort = null; }
      S.viewKey = key;
      await renderView();
    }
    if (sym) openDetail(sym); else closeDrawer(true);
  }

  // ------------------------------------------------------------ header / strip
  function renderStrip() {
    const el = $('#strip');
    const items = S.meta.strip || [];
    el.innerHTML = items.map(x => `
      <div class="tile">
        <div>
          <div class="t-label">${esc(x.label)}${x.above_ma200 == null ? '' : `<span class="pill" title="เทียบเส้นค่าเฉลี่ย 200 วัน">${x.above_ma200 ? 'เหนือ MA200' : 'ใต้ MA200'}</span>`}</div>
          <div class="t-value num">${num(x.price, x.price >= 1000 ? 0 : 2)}</div>
          <div class="t-sub">${chg(x.ret_1d, 2)} <span class="note">1 เดือน ${pct(x.ret_1m, 1, true)}</span></div>
        </div>
        ${C.spark(x.spark, { width: 88, height: 34 })}
      </div>`).join('');
    $('#updated').textContent = 'อัปเดต ' + dateTH(S.meta.generated_at, true);
  }

  // ------------------------------------------------------------ views
  async function renderView(keepScroll = false) {
    const view = $('#view');
    const y = window.scrollY;
    try {
      if (S.tab === 'th' || S.tab === 'us') await renderMarket(S.tab);
      else if (S.tab === 'watch') await renderWatch();
      else if (S.tab === 'track') await renderTrack();
      else renderMethod();
    } catch (e) {
      console.error(e);
      view.innerHTML = `<div class="empty">โหลดข้อมูลไม่สำเร็จ: ${esc(e.message)}</div>`;
    }
    if (keepScroll) window.scrollTo(0, y);
  }

  function segHorizon() {
    return `<div class="seg" role="group" aria-label="ระยะเวลาลงทุน">${HK.map(h =>
      `<button data-h="${h}" aria-pressed="${h === S.horizon}">${HLABEL[h]}</button>`).join('')}</div>`;
  }
  function bindHorizon(root) {
    $$('[data-h]', root).forEach(b => b.addEventListener('click', () => go(S.tab, b.dataset.h)));
  }

  async function renderMarket(mk) {
    const view = $('#view');
    const data = await loadMarket(mk);
    const mm = S.meta.markets[mk];
    const reg = mm.regime || {};
    view.innerHTML = `
      <section class="regime ${esc(reg.state || 'mixed')}">
        <span class="r-ic" aria-hidden="true"></span>
        <div>
          <b>ภาวะตลาด${esc(mm.label)}:</b> ${esc(reg.text || '')}
          <div class="r-meta">หุ้นในรายการ ${num((reg.breadth || 0) * 100, 0)}% อยู่เหนือเส้นค่าเฉลี่ย 200 วัน ·
          ${mm.benchmark ? `${esc(mm.benchmark.label)} ${chg(mm.benchmark.ret_1d, 2)} วันล่าสุด · ` : ''}ราคา ณ ${dateTH(data.as_of)}</div>
        </div>
      </section>
      <div class="controls">
        <span class="seg-label">ถือหุ้นประมาณ</span>${segHorizon()}
        <select class="select" id="f-sector" aria-label="กลุ่มอุตสาหกรรม">
          <option value="">ทุกกลุ่มอุตสาหกรรม</option>
          ${(mm.sectors || []).map(s => `<option ${s === S.sector ? 'selected' : ''}>${esc(s)}</option>`).join('')}
        </select>
        <input class="search" id="f-q" type="search" placeholder="ค้นหาชื่อหรือตัวย่อหุ้น" value="${esc(S.q)}" aria-label="ค้นหาหุ้น">
        <div class="chips" role="group" aria-label="กรองตามป้าย">
          ${[['', 'ทั้งหมด'], ['strong', 'เด่นมาก'], ['good', 'น่าสนใจ'], ['neutral', 'ปานกลาง'], ['weak', 'ควรระวัง']].map(([k, t]) =>
            `<button class="chip" data-label="${k}" aria-pressed="${S.label === k}">${t}</button>`).join('')}
        </div>
      </div>
      <div id="results"></div>`;
    bindHorizon(view);
    $('#f-sector').addEventListener('change', e => { S.sector = e.target.value; renderResults(mk); });
    $('#f-q').addEventListener('input', e => { S.q = e.target.value; renderResults(mk); });
    $$('[data-label]', view).forEach(b => b.addEventListener('click', () => {
      S.label = b.dataset.label;
      $$('[data-label]', view).forEach(x => x.setAttribute('aria-pressed', x === b));
      renderResults(mk);
    }));
    renderResults(mk);
  }

  function filterStocks(list) {
    const h = S.horizon, q = S.q.trim().toLowerCase();
    return list.filter(s =>
      (!S.sector || s.sector_th === S.sector) &&
      (!S.label || s.h[h].label === S.label) &&
      (!q || s.code.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q) || (s.name_en || '').toLowerCase().includes(q)));
  }

  const SORTS = {
    rank: s => s.h[S.horizon].rank, code: s => s.code, price: s => s.price, ret_1d: s => s.ret_1d,
    ret_3m: s => s.ret_3m, score: s => s.h[S.horizon].score, prob: s => s.h[S.horizon].prob,
    median: s => s.h[S.horizon].median, pe: s => (s.loss ? Infinity : s.pe), dy: s => s.dy, roe: s => s.roe,
    label: s => LABEL_ORDER[s.h[S.horizon].label], sector: s => s.sector_th, chg7: s => (s.chg7 || {})[S.horizon],
  };
  function sortStocks(list) {
    const sort = S.sort || { key: 'rank', dir: 1 };
    const f = SORTS[sort.key] || SORTS.rank;
    return list.slice().sort((a, b) => {
      const x = f(a), y = f(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === 'string' ? x.localeCompare(y, 'th') : x - y) * sort.dir;
    });
  }

  function renderResults(mk) {
    const data = S.markets[mk];
    const h = S.horizon;
    const list = filterStocks(data.stocks);
    const picks = list.slice().sort((a, b) => a.h[h].rank - b.h[h].rank).slice(0, 6);
    const el = $('#results');
    el.innerHTML = `
      <div class="sec-h">
        <h2>หุ้นเด่นสำหรับถือ ${HLABEL[h]}</h2>
        <p>จัดอันดับจากปัจจัยพื้นฐาน งบการเงิน นักวิเคราะห์ ข่าว และแนวโน้มราคา · <a href="#/method">วิธีคิดคะแนน</a></p>
      </div>
      ${picks.length ? `<div class="cards">${picks.map(s => card(s, mk)).join('')}</div>` : '<div class="empty">ไม่พบหุ้นตามเงื่อนไขที่เลือก</div>'}
      <div class="sec-h">
        <h2>ตารางจัดอันดับ (${list.length} ตัว)</h2>
        <p>คลิกหัวตารางเพื่อเรียงลำดับ · คลิกแถวเพื่อดูรายละเอียด</p>
      </div>
      <div class="table-wrap">${table(list, mk)}</div>
      <p class="note" style="margin-top:10px">* โอกาสขึ้น = สัดส่วนครั้งในอดีต 10 ปี ที่หุ้นในตลาดเดียวกันซึ่งอยู่ใน "สภาวะราคา" แบบเดียวกับวันนี้
      ถือครบ ${HLABEL[h]} แล้วราคาสูงขึ้น (ตัวเลขนี้ตรวจสอบย้อนหลังแล้วว่าสอดคล้องกับความจริง แต่ใช้แยกหุ้นดี/ไม่ดีได้น้อย — ดูหน้า "ผลงานย้อนหลัง")
      · ช่วงผลตอบแทน = ผลตอบแทน ${HLABEL[h]} ของหุ้นตัวนั้นในอดีต (10% แย่สุด ถึง 10% ดีสุด)</p>`;
    bindResults(el, mk);
  }

  function card(s, mk) {
    const h = s.h[S.horizon];
    const { pos, neg } = factsFor(s, S.horizon, 3, 1);
    return `
      <article class="card" data-open="${esc(s.sym)}" tabindex="0" aria-label="${esc(s.code)} อันดับ ${h.rank}">
        <div class="card-top">
          <div style="min-width:0">
            <div class="card-rank">อันดับ ${h.rank} · ${esc(s.sector_th || '')}</div>
            <div class="card-code">${esc(s.code)}</div>
            <div class="card-name">${esc(s.name)}</div>
          </div>
          ${badge(h.label)}
        </div>
        <div class="card-price"><span class="p num">${price(s.price)}</span>${chg(s.ret_1d)}<span class="note">วันล่าสุด · 3 เดือน ${pct(s.ret_3m, 1, true)}</span></div>
        <div class="card-spark">${C.spark(s.spark, { width: 300, height: 44 })}</div>
        <div class="card-stats">
          <div class="stat"><div class="s-label">คะแนนแนะนำ</div><div class="s-value">${num(h.score, 0)}<span class="note"> /100</span></div>${meter(h.score)}</div>
          <div class="stat"><div class="s-label">โอกาสขึ้นใน ${HLABEL[S.horizon]}*</div><div class="s-value">${pct(h.prob, 0)}</div>
            <div class="s-sub">อดีต: ${pct(h.p10, 0, true)} ถึง ${pct(h.p90, 0, true)}</div></div>
        </div>
        <ul class="reasons">${reasonsList(pos)}${reasonsList(neg)}</ul>
        <div class="card-foot"><button class="link-btn" data-open="${esc(s.sym)}">ดูเหตุผลและข้อมูลทั้งหมด →</button>${starBtn(s.sym)}</div>
      </article>`;
  }

  function table(list, mk) {
    if (!list.length) return '<div class="empty">ไม่พบหุ้นตามเงื่อนไขที่เลือก</div>';
    const sort = S.sort || { key: 'rank', dir: 1 };
    const th = (key, text, cls = '') => `<th class="${cls}" data-sort="${key}" ${sort.key === key ? `aria-sort="${sort.dir > 0 ? 'ascending' : 'descending'}"` : ''} scope="col">${text}</th>`;
    const rows = sortStocks(list).map(s => {
      const h = s.h[S.horizon];
      return `<tr data-open="${esc(s.sym)}" tabindex="0">
        <td class="n">${h.rank}</td>
        <td><span class="t-code">${esc(s.code)}</span><span class="t-name">${esc(s.name)}</span></td>
        <td class="hide-md">${esc(s.sector_th || '')}</td>
        <td class="n">${price(s.price)}</td>
        <td class="n">${chg(s.ret_1d)}</td>
        <td class="n hide-sm">${chg(s.ret_3m)}</td>
        <td><span class="scorebar">${meter(h.score)}<b class="num">${num(h.score, 0)}</b></span></td>
        <td class="n">${pct(h.prob, 0)}</td>
        <td class="n hide-md">${pct(h.median, 1, true)}</td>
        <td class="n hide-sm">${s.loss ? '<span class="note">ขาดทุน</span>' : num(s.pe, 1)}</td>
        <td class="n hide-sm">${pct(s.dy, 1)}</td>
        <td class="n hide-md">${pct(s.roe, 1)}</td>
        <td>${badge(h.label)}</td>
        <td>${starBtn(s.sym, true)}</td>
      </tr>`;
    }).join('');
    return `<table class="grid">
      <thead><tr>
        ${th('rank', 'อันดับ', 'n')}${th('code', 'หุ้น')}${th('sector', 'กลุ่ม', 'hide-md')}${th('price', 'ราคา', 'n')}
        ${th('ret_1d', 'วันล่าสุด', 'n')}${th('ret_3m', '3 เดือน', 'n hide-sm')}${th('score', 'คะแนนแนะนำ')}
        ${th('prob', 'โอกาสขึ้น*', 'n')}${th('median', 'ผลตอบแทนกลาง*', 'n hide-md')}${th('pe', 'P/E', 'n hide-sm')}
        ${th('dy', 'ปันผล', 'n hide-sm')}${th('roe', 'ROE', 'n hide-md')}${th('label', 'สัญญาณ')}<th class="nosort"><span class="sr">ติดตาม</span></th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  }

  function bindResults(root, mk) {
    $$('[data-open]', root).forEach(n => {
      n.addEventListener('click', e => {
        if (e.target.closest('[data-star]')) return;
        e.stopPropagation();
        go(S.tab, S.horizon, n.dataset.open);
      });
      n.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target === n) go(S.tab, S.horizon, n.dataset.open); });
    });
    $$('[data-star]', root).forEach(b => b.addEventListener('click', e => { e.stopPropagation(); toggleWatch(b.dataset.star); }));
    $$('th[data-sort]', root).forEach(th => th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const cur = S.sort || { key: 'rank', dir: 1 };
      const numericDesc = ['score', 'prob', 'median', 'dy', 'roe', 'ret_1d', 'ret_3m', 'price', 'chg7'];
      S.sort = { key, dir: cur.key === key ? -cur.dir : (numericDesc.includes(key) ? -1 : 1) };
      if (S.tab === 'watch') renderView(true); else renderResults(mk);
    }));
  }

  // ------------------------------------------------------------ detail drawer
  async function openDetail(sym) {
    const drawer = $('#drawer');
    const mk = marketOf(sym);
    if (!drawer.classList.contains('open')) S.lastFocus = document.activeElement;
    S.openSym = sym;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    $('#scrim').classList.add('open');
    document.body.style.overflow = 'hidden';
    let s, d;
    try {
      await loadMarket(mk);
      s = findStock(sym);
      if (!s) throw new Error('ไม่พบหุ้น ' + sym);
      drawer.innerHTML = detailHead(s, mk) + '<div class="d-body"><div class="loading">กำลังโหลดรายละเอียด…</div></div>';
      bindHead(drawer, s);
      d = await loadDetail(sym);
    } catch (e) {
      drawer.innerHTML = `<div class="d-head"><div class="d-title"><div class="d-code">${esc(sym)}</div></div><button class="icon-btn" data-close aria-label="ปิด">✕</button></div><div class="d-body"><div class="empty">${esc(e.message)}</div></div>`;
      $('[data-close]', drawer).addEventListener('click', () => go(S.tab, S.horizon));
      return;
    }
    if (S.openSym !== sym) return;
    $('.d-body', drawer).innerHTML = detailBody(s, d, mk);
    bindBody(drawer, s, d, mk);
    $('[data-close]', drawer).focus({ preventScroll: true });
  }

  function closeDrawer(silent) {
    const drawer = $('#drawer');
    if (!drawer.classList.contains('open')) return;
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    $('#scrim').classList.remove('open');
    document.body.style.overflow = '';
    S.openSym = null;
    C.hideTip();
    if (S.lastFocus && document.contains(S.lastFocus)) S.lastFocus.focus({ preventScroll: true });
    if (!silent) go(S.tab, S.horizon);
  }

  function detailHead(s, mk) {
    return `<div class="d-head">
      <div class="d-title">
        <div class="d-code">${esc(s.code)} <span style="font-size:14px;font-weight:500">${badge(s.h[S.horizon].label)}</span></div>
        <div class="d-name">${esc(s.name)}${s.name_en && s.name_en !== s.name ? ' · ' + esc(s.name_en) : ''}</div>
      </div>
      ${starBtn(s.sym)}
      <button class="icon-btn" data-close aria-label="ปิด">✕</button>
    </div>`;
  }
  function bindHead(root, s) {
    $('[data-close]', root).addEventListener('click', () => go(S.tab, S.horizon));
    $$('.d-head [data-star]', root).forEach(b => b.addEventListener('click', () => toggleWatch(s.sym)));
  }

  const METRIC_DEFS = [
    ['P/E', m => (m.loss_making ? 'ขาดทุน' : num(m.pe, 1) + ' เท่า'), 'pe', v => num(v, 1) + ' เท่า'],
    ['P/E ล่วงหน้า', m => num(m.forward_pe, 1) + ' เท่า', 'forward_pe', v => num(v, 1) + ' เท่า'],
    ['P/BV', m => num(m.pb, 2) + ' เท่า', 'pb', v => num(v, 2) + ' เท่า'],
    ['EV/EBITDA', m => num(m.ev_ebitda, 1) + ' เท่า', 'ev_ebitda', v => num(v, 1) + ' เท่า'],
    ['อัตราปันผล (12 เดือน)', m => pct(m.div_yield, 2), 'div_yield', v => pct(v, 1)],
    ['ROE', m => pct(m.roe, 1), 'roe', v => pct(v, 1)],
    ['ROA', m => pct(m.roa, 1)],
    ['อัตรากำไรสุทธิ', m => pct(m.net_margin, 1), 'net_margin', v => pct(v, 1)],
    ['อัตรากำไรจากการดำเนินงาน', m => pct(m.op_margin, 1)],
    ['หนี้ที่มีดอกเบี้ย/ทุน (D/E)', m => (m.is_financial ? 'ไม่ใช้กับธุรกิจการเงิน' : num(m.de, 2) + ' เท่า'), 'de', v => num(v, 2) + ' เท่า'],
    ['Current ratio', m => (m.is_financial ? '–' : num(m.current_ratio, 2) + ' เท่า')],
    ['รายได้ไตรมาสล่าสุด (YoY)', m => pct(m.rev_growth_q, 1, true), 'rev_growth_q', v => pct(v, 1, true)],
    ['กำไรไตรมาสล่าสุด (YoY)', m => pct(m.earn_growth_q, 1, true)],
    ['รายได้โตเฉลี่ย/ปี (3 ปี)', m => pct(m.rev_cagr3, 1, true)],
    ['กำไรโตเฉลี่ย/ปี (3 ปี)', m => (m.ni_cagr3 === -1 ? 'กลายเป็นขาดทุน' : m.ni_cagr3 === 0.5 ? 'พลิกเป็นกำไร' : pct(m.ni_cagr3, 1, true))],
    ['Piotroski F-Score', m => (m.fscore == null ? '–' : `${m.fscore}/${m.fscore_n}`)],
    ['เบต้า (1 ปี)', m => num(m.beta_1y ?? m.beta_info, 2)],
    ['ความผันผวน (1 ปี)', m => pct(m.vol_1y, 0), 'vol_1y', v => pct(v, 0)],
    ['ลดลงลึกสุดใน 1 ปี', m => pct(m.maxdd_1y, 0)],
    ['RSI (14 วัน)', m => num(m.rsi14, 0)],
  ];

  function detailBody(s, d, mk) {
    const ccy = ccyOf(mk);
    const m = d.metrics || {};
    const med = S.markets[mk].medians || {};
    const h = S.horizon;
    const { pos, neg } = factsFor(s, h, 8, 6);
    const w = S.meta.weights[h];
    const ph = d.prob || {};
    const cal = (S.meta.markets[mk].prob_model || {})[h];

    const hTiles = HK.map(k => `
      <button class="h-tile" data-h="${k}" aria-pressed="${k === h}">
        <div class="ht-h">ถือ ${HLABEL[k]} · อันดับ ${s.h[k].rank}</div>
        <div class="ht-p">${num(s.h[k].score, 0)}<span class="note"> คะแนน</span></div>
        <div class="ht-s">โอกาสขึ้น ${pct(s.h[k].prob, 0)} · ${LABELS[s.h[k].label].t}</div>
      </button>`).join('');

    const groupBars = GROUPS.map(g => `
      <div class="gb"><span>${esc(S.meta.groups[g])}</span>${meter(s.groups[g])}
      <span class="gb-v num">${num(s.groups[g], 0)} <span class="gb-w">×${num(w[g] * 100, 0)}%</span></span></div>`).join('');

    const metrics = METRIC_DEFS.map(([k, f, mk2, fm]) => {
      const mv = mk2 && isNum(med[mk2]) ? `<div class="m-s">ค่ากลางตลาด ${fm(med[mk2])}</div>` : '';
      return `<div class="metric"><div class="m-k">${k}</div><div class="m-v num">${f(m)}</div>${mv}</div>`;
    }).join('') +
      `<div class="metric"><div class="m-k">มูลค่าตลาด</div><div class="m-v">${compact(m.market_cap, m.currency || ccy)}</div></div>` +
      `<div class="metric"><div class="m-k">มูลค่าซื้อขายเฉลี่ย/วัน</div><div class="m-v">${compact(m.turnover_20d, ccy)}</div></div>`;

    const probRows = HK.map(k => {
      const p = ph[k] || {};
      return `<tr${k === h ? ' style="font-weight:600"' : ''}><td>${HLABEL[k]}</td>
        <td>${pct(p.prob, 0)}</td><td>${pct(p.base_rate, 0)}</td>
        <td>${p.state_rate == null ? '–' : pct(p.state_rate, 0)}</td>
        <td>${pct(p.median, 1, true)}</td><td>${pct(p.p10, 0, true)} ถึง ${pct(p.p90, 0, true)}</td></tr>`;
    }).join('');

    const news = (d.news || []).slice(0, 15).map(n => {
      const cls = n.sent > 0 ? 'pos' : n.sent < 0 ? 'neg' : 'neu';
      const t = n.sent > 0 ? 'บวก' : n.sent < 0 ? 'ลบ' : 'กลาง';
      const url = /^https?:\/\//i.test(n.url || '') ? n.url : null;
      const title = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>` : esc(n.title);
      return `<li><span class="sent ${cls}">${t}</span><div>${title}<div class="news-meta">${esc(n.source || '')} · ${esc(ago(n.time))}</div></div></li>`;
    }).join('');
    const ai = d.ai ? `<div class="ai-box"><div class="ai-t">สรุปข่าวโดย AI (${esc(d.ai.model || 'Claude')})</div>${esc(d.ai.summary_th)}
      ${(d.ai.catalysts_th || []).length ? `<div style="margin-top:6px"><b>ปัจจัยบวก</b><ul>${d.ai.catalysts_th.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
      ${(d.ai.risks_th || []).length ? `<div style="margin-top:6px"><b>ความเสี่ยง</b><ul>${d.ai.risks_th.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}</div>` : '';

    const tgt = analystBlock(m, s);
    const hist = (d.history || []).filter(r => r[1 + HK.indexOf(h)] != null);

    return `
      <section class="panel">
        <div class="d-price"><span class="big num">${price(s.price)}</span><span class="note">${esc(ccy)}</span>${chg(s.ret_1d, 2)}
          <span class="note">ราคาปิด ${dateTH(s.date)} · ${esc(s.sector_th || '')}${m.industry ? ' · ' + esc(m.industry) : ''}</span></div>
        <div class="chg-row">
          ${[['1 สัปดาห์', s.ret_1w], ['1 เดือน', s.ret_1m], ['3 เดือน', s.ret_3m], ['6 เดือน', s.ret_6m], ['1 ปี', s.ret_12m], ['ตั้งแต่ต้นปี', s.ret_ytd]]
            .map(([k, v]) => `<span><span class="k">${k}</span>${chg(v)}</span>`).join('')}
        </div>
      </section>

      <section class="panel">
        <h3>คะแนนตามระยะเวลาลงทุน <small>อันดับเทียบกับ ${S.markets[mk].stocks.length} หุ้นใน${esc(S.meta.markets[mk].label)} · คลิกเพื่อเปลี่ยนระยะเวลา</small></h3>
        <div class="h-tiles">${hTiles}</div>
        ${hist.length >= 2 ? `<div style="margin-top:12px"><div class="mini-title">คะแนน ${HLABEL[h]} ย้อนหลัง <small>(${hist.length} วันที่บันทึก)</small></div><div id="score-hist"></div></div>` : ''}
      </section>

      <section class="two-col">
        <div class="panel"><h3>ทำไมถึงน่าสนใจ <small>ถือ ${HLABEL[h]}</small></h3>
          ${pos.length ? `<ul class="reasons">${reasonsList(pos)}</ul>` : '<p class="note">ยังไม่พบจุดเด่นที่ชัดเจน</p>'}</div>
        <div class="panel"><h3>ข้อควรระวัง</h3>
          ${neg.length ? `<ul class="reasons">${reasonsList(neg)}</ul>` : '<p class="note">ยังไม่พบข้อควรระวังที่ชัดเจนจากข้อมูล</p>'}</div>
      </section>

      <section class="panel">
        <h3>คะแนนแต่ละกลุ่มปัจจัย <small>0–100 เทียบกับหุ้นอื่นในตลาด · ×น้ำหนักสำหรับถือ ${HLABEL[h]}</small></h3>
        <div class="group-bars">${groupBars}</div>
        ${isNum(s.coverage) && s.coverage < 0.5 ? '<p class="note" style="margin-top:10px">⚠ ข้อมูลงบการเงินของหุ้นนี้มีไม่ครบ คะแนนอาจคลาดเคลื่อน</p>' : ''}
      </section>

      <section class="panel">
        <h3>กราฟราคา <span class="seg sm" role="group" aria-label="ช่วงเวลา">
          <button data-range="1y" aria-pressed="${S.range === '1y'}">1 ปี</button><button data-range="5y" aria-pressed="${S.range === '5y'}">5 ปี</button></span></h3>
        <div class="legend" id="legend"></div>
        <div id="price-chart"></div>
        <p class="note">MA50/MA200 = ราคาเฉลี่ย 50 และ 200 วันทำการ ใช้ดูแนวโน้ม · ราคาปรับปันผลและการแตกพาร์แล้ว</p>
      </section>

      <section class="panel">
        <h3>สถิติโอกาสขึ้น <small>${s.state ? esc(s.state.text) : 'ประวัติราคายังสั้นเกินไป'}</small></h3>
        <div class="scroll-x"><table class="kv">
          <thead><tr><th>ถือ</th><th>โอกาสขึ้น*</th><th>หุ้นนี้ขึ้นในอดีต</th><th>หุ้นนี้ เมื่ออยู่สภาวะเดียวกัน</th><th>ผลตอบแทนกลาง</th><th>ช่วง 10%–90%</th></tr></thead>
          <tbody>${probRows}</tbody></table></div>
        <p class="note">* โอกาสขึ้น = สถิติของหุ้นทุกตัวใน${esc(S.meta.markets[mk].label)} เมื่ออยู่ในสภาวะเดียวกับวันนี้ (ข้อมูล ~10 ปี)
          ${cal && cal.calibration ? `· ทดสอบย้อนหลังช่วง ${dateTH(cal.calibration.test_from)} – ${dateTH(cal.calibration.test_to)} ค่าคลาดเฉลี่ย ${pct(cal.calibration.mae, 1)}` : ''}
          · สถิติราคาในอดีตไม่ได้รับประกันอนาคต</p>
      </section>

      <section class="panel"><h3>ตัวเลขสำคัญ</h3><div class="metrics">${metrics}</div></section>

      <section class="panel" id="fin-panel">
        <h3>งบการเงินย้อนหลัง <small id="fin-unit"></small></h3>
        <div class="minis"><div><div class="mini-title">รายได้รวม</div><div id="rev-chart"></div></div>
          <div><div class="mini-title">กำไรสุทธิ</div><div id="ni-chart"></div></div></div>
        <div class="scroll-x" id="fin-table"></div>
        <div class="scroll-x" id="q-table" style="margin-top:14px"></div>
      </section>

      <section class="panel"><h3>มุมมองนักวิเคราะห์</h3>${tgt}</section>

      <section class="panel"><h3>ข่าวล่าสุด <small>${(d.news || []).length} ข่าวใน 30 วัน · โทนข่าววัดจากคำสำคัญในหัวข่าว</small></h3>
        ${ai}${news ? `<ul class="news-list">${news}</ul>` : '<p class="note">ไม่พบข่าวในช่วง 30 วันที่ผ่านมา</p>'}</section>

      ${d.summary ? `<section class="panel"><h3>เกี่ยวกับบริษัท <small>ข้อมูลจาก Yahoo Finance (ภาษาอังกฤษ)</small></h3>
        <p class="note" style="font-size:13.5px;color:var(--text-2)">${esc(d.summary)}</p>
        ${d.website && /^https?:\/\//.test(d.website) ? `<a href="${esc(d.website)}" target="_blank" rel="noopener noreferrer">${esc(d.website)}</a>` : ''}</section>` : ''}`;
  }

  function analystBlock(m, s) {
    const n = m.n_analysts || 0;
    if (!n || !isNum(m.target_mean)) return '<p class="note">ไม่มีข้อมูลราคาเป้าหมายจากนักวิเคราะห์</p>';
    const lo = Math.min(m.target_low ?? m.target_mean, s.price), hi = Math.max(m.target_high ?? m.target_mean, s.price);
    const pos = v => ((v - lo) / (hi - lo || 1)) * 100;
    const band = isNum(m.target_low) && isNum(m.target_high)
      ? `<div class="tr-band" style="left:${pos(m.target_low)}%;width:${pos(m.target_high) - pos(m.target_low)}%"></div>` : '';
    return `
      <div class="metrics" style="margin-bottom:6px">
        <div class="metric"><div class="m-k">ราคาเป้าหมายเฉลี่ย</div><div class="m-v">${price(m.target_mean)}</div><div class="m-s">${pct(m.upside, 1, true)} จากราคาปัจจุบัน</div></div>
        <div class="metric"><div class="m-k">ต่ำสุด – สูงสุด</div><div class="m-v">${price(m.target_low)} – ${price(m.target_high)}</div></div>
        <div class="metric"><div class="m-k">คำแนะนำเฉลี่ย</div><div class="m-v">${esc(REC_KEY[m.rec_key] || m.rec_key || '–')}</div><div class="m-s">${num(m.rec_mean, 1)} (1=ซื้อมาก … 5=ขาย)</div></div>
        <div class="metric"><div class="m-k">จำนวนนักวิเคราะห์</div><div class="m-v">${n} ราย</div></div>
      </div>
      <div class="target-range" role="img" aria-label="ช่วงราคาเป้าหมายเทียบราคาปัจจุบัน">
        <div class="tr-track"></div>${band}
        <div class="tr-dot" style="left:${pos(m.target_mean)}%;background:var(--series-1)" title="เป้าหมายเฉลี่ย"></div>
        <div class="tr-dot" style="left:${pos(s.price)}%;background:var(--text)" title="ราคาปัจจุบัน"></div>
        <div class="tr-lbl" style="left:${pos(s.price)}%">ราคาปัจจุบัน</div>
      </div>
      <p class="note">จุดสีน้ำเงิน = ราคาเป้าหมายเฉลี่ย · จุดสีเข้ม = ราคาปัจจุบัน · แถบ = ช่วงเป้าหมายต่ำสุดถึงสูงสุด</p>`;
  }

  function bindBody(root, s, d, mk) {
    $$('.d-body [data-h]', root).forEach(b => b.addEventListener('click', () => go(S.tab, b.dataset.h, s.sym)));
    $$('[data-range]', root).forEach(b => b.addEventListener('click', () => {
      S.range = b.dataset.range;
      $$('[data-range]', root).forEach(x => x.setAttribute('aria-pressed', x === b));
      drawPrice(d);
    }));
    drawPrice(d);
    drawFinancials(d, mk);
    const hc = $('#score-hist', root);
    if (hc) {
      const idx = 1 + HK.indexOf(S.horizon);
      const rows = (d.history || []).filter(r => r[idx] != null);
      C.line(hc, {
        dates: rows.map(r => r[0]), height: 120, label: 'คะแนนย้อนหลัง', fmt: v => num(v, 0),
        fmtDate: x => dateTH(x), fmtAxisDate: x => dateTH(x).replace(/ \d{4}$/, ''),
        series: [{ name: 'คะแนน', color: 'var(--series-1)', values: rows.map(r => r[idx]) }],
      });
    }
  }

  function drawPrice(d) {
    const rows = (d.chart || {})[S.range === '5y' ? 'w' : 'd'] || [];
    const el = $('#price-chart');
    if (!el) return;
    const last = rows[rows.length - 1] || [];
    const series = [
      { name: 'ราคา', color: 'var(--series-1)', values: rows.map(r => r[1]), area: true },
      { name: 'MA50', color: 'var(--series-2)', values: rows.map(r => r[2]), width: 1.5 },
      { name: 'MA200', color: 'var(--series-3)', values: rows.map(r => r[3]), width: 1.5 },
    ];
    $('#legend').innerHTML = series.map((s, i) =>
      `<span><i class="lk" style="background:${s.color}"></i>${s.name}<b class="num">${price(last[i + 1])}</b></span>`).join('');
    const fmtAxis = S.range === '5y' ? x => String(new Date(x).getFullYear() + 543) : x => dateTH(x).replace(/ \d{4}$/, '');
    C.line(el, { dates: rows.map(r => r[0]), series, height: 260, fmt: v => price(v), fmtDate: x => dateTH(x), fmtAxisDate: fmtAxis, label: 'กราฟราคาหุ้น' });
  }

  const FIN_LABELS = {
    revenue: 'รายได้รวม', gross_profit: 'กำไรขั้นต้น', operating_income: 'กำไรจากการดำเนินงาน', net_income: 'กำไรสุทธิ',
    eps: 'กำไรต่อหุ้น (EPS)', ebitda: 'EBITDA', total_assets: 'สินทรัพย์รวม', total_liabilities: 'หนี้สินรวม',
    equity: 'ส่วนของผู้ถือหุ้น', total_debt: 'หนี้สินที่มีภาระดอกเบี้ย', cash: 'เงินสด', ocf: 'กระแสเงินสดจากการดำเนินงาน',
    capex: 'รายจ่ายลงทุน (CapEx)', fcf: 'กระแสเงินสดอิสระ (FCF)',
  };
  function drawFinancials(d, mk) {
    const st = d.statements || {};
    const a = st.annual || { periods: [], rows: {} };
    const ccy = d.financial_currency || ccyOf(mk);
    if (!a.periods.length) { $('#fin-panel').innerHTML = '<h3>งบการเงินย้อนหลัง</h3><p class="note">ไม่มีข้อมูลงบการเงิน</p>'; return; }
    const maxAbs = Math.max(...Object.entries(a.rows).filter(([k]) => k !== 'eps').flatMap(([, v]) => v).filter(isNum).map(Math.abs), 0);
    const [div, unitTxt] = maxAbs >= 1e9 ? [1e9, ccy === 'THB' ? 'พันล้านบาท' : `พันล้าน ${ccy}`] : [1e6, ccy === 'THB' ? 'ล้านบาท' : `ล้าน ${ccy}`];
    $('#fin-unit').textContent = `หน่วย: ${unitTxt} (ยกเว้น EPS)`;
    const years = a.periods.map(p => p.slice(0, 4));
    const fmtU = v => num(v / div, Math.abs(v / div) >= 100 ? 0 : 1);
    C.bars($('#rev-chart'), { labels: years, values: a.rows.revenue || [], color: 'var(--series-1)', fmt: fmtU, label: 'รายได้รวม' });
    C.bars($('#ni-chart'), { labels: years, values: a.rows.net_income || [], color: 'var(--series-1)', fmt: fmtU, label: 'กำไรสุทธิ' });
    const body = Object.keys(FIN_LABELS).filter(k => (a.rows[k] || []).some(isNum)).map(k =>
      `<tr><td>${FIN_LABELS[k]}</td>${a.rows[k].map(v => `<td class="num">${isNum(v) ? (k === 'eps' ? num(v, 2) : fmtU(v)) : '–'}</td>`).join('')}</tr>`).join('');
    $('#fin-table').innerHTML = `<table class="kv"><thead><tr><th>งบปี (สิ้นสุด)</th>${a.periods.map(p => `<th>${esc(p.slice(5, 7))}/${esc(p.slice(0, 4))}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
    const q = st.quarterly || { periods: [] };
    if (q.periods && q.periods.length) {
      $('#q-table').innerHTML = `<table class="kv"><thead><tr><th>รายไตรมาส (สิ้นสุด)</th>${q.periods.map(p => `<th>${esc(p.slice(5, 7))}/${esc(p.slice(0, 4))}</th>`).join('')}</tr></thead><tbody>
        <tr><td>รายได้รวม</td>${q.rows.revenue.map(v => `<td class="num">${isNum(v) ? fmtU(v) : '–'}</td>`).join('')}</tr>
        <tr><td>กำไรสุทธิ</td>${q.rows.net_income.map(v => `<td class="num">${isNum(v) ? fmtU(v) : '–'}</td>`).join('')}</tr></tbody></table>`;
    }
  }

  // ------------------------------------------------------------ watchlist view
  async function renderWatch() {
    const view = $('#view');
    const syms = Object.keys(S.watch);
    await Promise.all([...new Set(syms.map(marketOf))].map(loadMarket));
    const h = S.horizon;
    const items = syms.map(sym => ({ sym, w: S.watch[sym], s: findStock(sym) }));
    const rows = items.map(({ sym, w, s }) => {
      if (!s) return `<tr><td colspan="9">${esc(sym)} <span class="note">— ไม่มีข้อมูลในรอบล่าสุด</span></td><td>${starBtn(sym, true)}</td></tr>`;
      const since = isNum(w.price) && w.price ? s.price / w.price - 1 : null;
      const c7 = (s.chg7 || {})[h];
      return `<tr data-open="${esc(sym)}" tabindex="0">
        <td><span class="t-code">${esc(s.code)}</span><span class="t-name">${esc(s.name)}</span></td>
        <td class="hide-sm">${marketOf(sym) === 'th' ? 'ไทย' : 'ต่างประเทศ'}</td>
        <td class="n hide-sm">${dateTH(w.at)}</td>
        <td class="n">${price(w.price)} → ${price(s.price)}</td>
        <td class="n">${chg(since)}</td>
        <td><span class="scorebar">${meter(s.h[h].score)}<b class="num">${num(s.h[h].score, 0)}</b></span></td>
        <td class="n hide-sm">${isNum(c7) ? `<span class="chg ${c7 > 0 ? 'up' : c7 < 0 ? 'down' : 'flat'}">${c7 > 0 ? '+' : ''}${num(c7, 1)}</span>` : '<span class="note">–</span>'}</td>
        <td>${badge(s.h[h].label)}</td>
        <td><div class="alerts">${alertsFor(s, w, since, c7).map(a => `<span class="alert ${a[0]}"><span class="a-ic">${a[0] === 'bad' ? '▼' : a[0] === 'good' ? '▲' : '●'}</span>${esc(a[1])}</span>`).join('') || '<span class="note">ปกติ</span>'}</div></td>
        <td>${starBtn(sym, true)}</td>
      </tr>`;
    }).join('');
    view.innerHTML = `
      <div class="controls" style="margin-top:14px"><span class="seg-label">ดูคะแนนสำหรับถือ</span>${segHorizon()}</div>
      <div class="sec-h"><h2>รายการติดตาม</h2><p>บันทึกไว้ในเบราว์เซอร์นี้เท่านั้น · สัญญาณเตือนคำนวณจากข้อมูลล่าสุดทุกครั้งที่อัปเดต</p></div>
      ${items.length ? `<div class="table-wrap"><table class="grid"><thead><tr>
        <th class="nosort">หุ้น</th><th class="nosort hide-sm">ตลาด</th><th class="nosort n hide-sm">เริ่มติดตาม</th><th class="nosort n">ราคาตอนเริ่ม → ล่าสุด</th>
        <th class="nosort n">ผลตอบแทน</th><th class="nosort">คะแนน ${HLABEL[h]}</th><th class="nosort n hide-sm">เปลี่ยนใน 7 วัน</th>
        <th class="nosort">สัญญาณ</th><th class="nosort">สถานะ/แจ้งเตือน</th><th class="nosort"></th></tr></thead><tbody>${rows}</tbody></table></div>`
        : `<div class="panel empty">ยังไม่มีหุ้นในรายการติดตาม<br>กดปุ่ม <b>☆ ติดตาม</b> ที่การ์ดหรือตารางหุ้น เพื่อติดตามคะแนน ราคา และสัญญาณเตือนได้ที่นี่</div>`}`;
    bindHorizon(view);
    bindResults(view, null);
  }

  function alertsFor(s, w, since, c7) {
    const out = [];
    const h = s.h[S.horizon];
    if (h.label === 'weak') out.push(['bad', 'คะแนนอยู่กลุ่ม "ควรระวัง"']);
    if (isNum(c7) && c7 <= -8) out.push(['bad', `คะแนนลดลง ${num(-c7, 0)} จุดใน 7 วัน`]);
    if (isNum(c7) && c7 >= 8) out.push(['good', `คะแนนเพิ่มขึ้น ${num(c7, 0)} จุดใน 7 วัน`]);
    if (s.above_ma200 === false) out.push(['bad', 'ราคาอยู่ใต้เส้นค่าเฉลี่ย 200 วัน']);
    if (s.news && s.news.pos + s.news.neg >= 3 && s.news.sentiment <= -0.15) out.push(['bad', 'ข่าวช่วงนี้โทนลบ']);
    if (isNum(since) && since <= -0.10) out.push(['bad', `ขาดทุน ${pct(-since, 0)} — ทบทวนเหตุผลที่ถือ`]);
    if (isNum(since) && since >= 0.15) out.push(['good', `กำไร ${pct(since, 0)} — พิจารณาแบ่งขาย/ตั้งจุดตัดขาดทุน`]);
    if (h.label === 'strong') out.push(['good', 'คะแนนอยู่กลุ่ม "เด่นมาก"']);
    return out;
  }

  // ------------------------------------------------------------ track record view
  async function renderTrack() {
    const view = $('#view');
    if (!S.track) {
      try { S.track = await getJSON('track.json'); } catch (e) { S.track = { markets: {} }; }
    }
    const sections = ['th', 'us'].filter(mk => S.meta.markets[mk]).map(mk => {
      const mm = S.meta.markets[mk];
      const tr = (S.track.markets || {})[mk] || {};
      const trackRows = HK.map(k => {
        const t = tr[k] || {};
        const a = t.all, m = t.matured;
        return `<tr><td>${HLABEL[k]}</td><td>${a ? a.n : 0}</td>
          <td>${a ? pct(a.avg_ret, 1, true) : '–'}</td><td>${a && isNum(a.avg_excess) ? pct(a.avg_excess, 1, true) : '–'}</td>
          <td>${a && isNum(a.beat_bench_rate) ? pct(a.beat_bench_rate, 0) : '–'}</td>
          <td>${m ? `${m.n} ครั้ง · ${pct(m.avg_excess, 1, true)}` : 'ยังไม่มี'}</td></tr>`;
      }).join('');
      const cal = Object.fromEntries(HK.map(k => [k, ((mm.prob_model || {})[k] || {}).calibration]));
      const calRows = Object.entries(STATE_SHORT).map(([id, label]) => `<tr><td>${label}</td>${HK.map(k => {
        const b = cal[k] && cal[k].by_state.find(x => String(x.state) === id);
        return `<td>${b ? `${pct(b.pred, 0)} → <b>${pct(b.actual, 0)}</b>` : '–'}</td>`;
      }).join('')}</tr>`).join('') +
        `<tr><td><b>ขึ้นจริงเฉลี่ยทั้งตลาด</b></td>${HK.map(k => `<td>${cal[k] ? pct(cal[k].base_rate, 0) : '–'}</td>`).join('')}</tr>` +
        `<tr><td><b>คลาดเคลื่อนเฉลี่ย</b></td>${HK.map(k => `<td>${cal[k] ? pct(cal[k].mae, 1) : '–'}</td>`).join('')}</tr>`;
      const anyCal = HK.find(k => cal[k]);
      const fb = (mm.factor_backtest || {}).factors || {};
      const fbRows = HK.map(k => {
        const mo = (fb.momentum || {})[k], rk = (fb.risk || {})[k];
        if (!mo) return '';
        return `<tr><td>${HLABEL[k]}</td><td>${pct(mo.top, 1, true)}</td><td>${pct(mo.bottom, 1, true)}</td><td>${pct(mo.win, 0)}</td>
          <td>${rk ? pct(rk.top, 1, true) : '–'}</td><td>${rk ? pct(rk.bottom, 1, true) : '–'}</td></tr>`;
      }).join('');
      const snaps = ((tr[S.horizon] || {}).snapshots || []).slice().reverse().slice(0, 30);
      return `
        <div class="sec-h"><h2>${esc(mm.label)}</h2><p>เทียบกับ ${esc(mm.benchmark ? mm.benchmark.label : 'ดัชนี')}</p></div>
        <div class="stack">
          <div class="panel"><h3>ผลงานหุ้น 10 อันดับแรกที่ระบบเลือกในแต่ละวัน</h3>
            <div class="scroll-x"><table class="kv"><thead><tr><th>ถือ</th><th>วันที่บันทึก</th><th>ผลตอบแทนเฉลี่ย</th><th>ชนะดัชนี (เฉลี่ย)</th><th>% ครั้งที่ชนะดัชนี</th><th>ครบกำหนดแล้ว</th></tr></thead><tbody>${trackRows}</tbody></table></div>
            <p class="note">ระบบเก็บ "หุ้น 10 อันดับแรก" ทุกวันที่อัปเดต แล้ววัดผลจริงจากราคาวันนั้นจนถึงวันนี้/วันครบกำหนด เป็นตัวชี้วัดที่ซื่อสัตย์ที่สุดว่าคะแนนใช้ได้จริงหรือไม่ — ต้องสะสมข้อมูลหลายเดือนจึงจะมีความหมาย</p>
            ${snaps.length ? `<div class="scroll-x" style="margin-top:10px"><table class="kv"><thead><tr><th>วันที่เลือก (${HLABEL[S.horizon]})</th><th>ผลตอบแทน</th><th>ดัชนี</th><th>หุ้นที่บวก</th><th>สถานะ</th></tr></thead><tbody>
              ${snaps.map(r => `<tr><td>${dateTH(r.date)}</td><td>${chg(r.avg_ret)}</td><td>${chg(r.bench_ret)}</td><td>${pct(r.hit_rate, 0)}</td><td>${r.matured ? 'ครบกำหนด' : 'ยังถืออยู่'}</td></tr>`).join('')}</tbody></table></div>` : ''}
          </div>
          <div class="panel"><h3>ทดสอบย้อนหลัง: ปัจจัยราคา <small>ตั้งแต่ ${dateTH((mm.factor_backtest || {}).from)} ปรับพอร์ตทุกเดือน</small></h3>
            <div class="scroll-x"><table class="kv"><thead><tr><th>ถือ</th><th>โมเมนตัมสูงสุด 20%</th><th>ต่ำสุด 20%</th><th>% เดือนที่ชนะ</th><th>ผันผวนต่ำสุด 20%</th><th>ผันผวนสูงสุด 20%</th></tr></thead><tbody>${fbRows}</tbody></table></div>
            <p class="note">ผลตอบแทนเฉลี่ยของกลุ่มหุ้นที่มีคะแนน "แนวโน้มราคา" สูงสุด/ต่ำสุด และ "ความเสี่ยงต่ำ" (ผันผวนต่ำ) — ใช้หุ้นในรายการปัจจุบันจึงมี survivorship bias (ดูดีกว่าความจริงเล็กน้อย)
            · ปัจจัยพื้นฐานย้อนหลังแบบ ณ วันนั้นไม่มีให้ใช้ฟรี จึงยังทดสอบไม่ได้</p>
          </div>
          <div class="panel"><h3>ความแม่นยำของ "โอกาสขึ้น" <small>ทดสอบกับข้อมูลช่วงหลังที่โมเดลไม่เคยเห็น</small></h3>
            <div class="scroll-x"><table class="kv"><thead><tr><th>สภาวะราคา (ทำนาย → <b>เกิดจริง</b>)</th>${HK.map(k => `<th>ถือ ${HLABEL[k]}</th>`).join('')}</tr></thead><tbody>${calRows}</tbody></table></div>
            <p class="note">สร้างตัวเลขจากข้อมูลช่วงแรก แล้วทดสอบกับช่วง ${anyCal ? `${dateTH(cal[anyCal].test_from)} – ${dateTH(cal[anyCal].test_to)}` : 'หลัง'} ที่โมเดลไม่เคยเห็น:
            ตัวเลขใกล้เคียงความจริง (ใช้ประเมินความน่าจะเป็นพื้นฐานได้) แต่แต่ละสภาวะต่างกันไม่มาก จึงไม่ใช้จัดอันดับหุ้น</p>
          </div>
        </div>`;
    }).join('');
    view.innerHTML = `<div class="controls" style="margin-top:14px"><span class="seg-label">แสดงรายการของ</span>${segHorizon()}</div>${sections}`;
    $$('[data-h]', view).forEach(b => b.addEventListener('click', () => { S.horizon = b.dataset.h; store.set('sl-h', S.horizon); renderView(true); }));
  }

  // ------------------------------------------------------------ method view
  function renderMethod() {
    const w = S.meta.weights;
    const wRows = GROUPS.map(g => `<tr><td>${esc(S.meta.groups[g])}</td>${HK.map(h => `<td>${num(w[h][g] * 100, 0)}%</td>`).join('')}</tr>`).join('');
    $('#view').innerHTML = `<div class="prose">
      <div class="sec-h"><h2>วิธีคิดคะแนน</h2><p>โปร่งใส ตรวจสอบได้ ปรับแต่งได้ในไฟล์ pipeline/config.py</p></div>
      <div class="warn-box">คะแนนนี้คือการ <b>คัดกรองเชิงสถิติ</b> เพื่อช่วยหาหุ้นที่ควรศึกษาต่อ ไม่ใช่คำแนะนำให้ซื้อขาย และไม่มีระบบใดทำนายราคาหุ้นได้แน่นอน
      ควรอ่านเหตุผล ตรวจงบการเงิน/ข่าวจากแหล่งทางการ กระจายการลงทุน และกำหนดจุดตัดขาดทุนเสมอ</div>
      <h3>1. ข้อมูลที่ใช้ (อัปเดตทุกวัน)</h3>
      <ul><li><b>ราคาย้อนหลัง ~10 ปี</b> (ปรับปันผล/แตกพาร์) → ผลตอบแทน เส้นค่าเฉลี่ย ความผันผวน สถิติ</li>
        <li><b>อัตราส่วนทางการเงิน</b> P/E, P/BV, EV/EBITDA, ROE, ROA, อัตรากำไร, หนี้สิน, ปันผล</li>
        <li><b>งบการเงินรายปี/รายไตรมาส</b> → การเติบโต 3 ปี และ Piotroski F-Score (9 ข้อ วัดความแข็งแรงของงบ)</li>
        <li><b>ราคาเป้าหมายและคำแนะนำของนักวิเคราะห์</b></li>
        <li><b>ข่าว 30 วัน</b> จาก Yahoo Finance และ Google News (ภาษาไทยสำหรับหุ้นไทย) วัดโทนบวก/ลบจากคำสำคัญ ${S.meta.ai_enabled ? 'และสรุปด้วย AI สำหรับหุ้นอันดับต้นๆ' : '(เปิดสรุปข่าวด้วย AI ได้ด้วย --ai)'}</li></ul>
      <h3>2. คะแนน 7 กลุ่มปัจจัย (0–100)</h3>
      <p>ทุกตัวชี้วัดแปลงเป็นเปอร์เซ็นไทล์เทียบกับหุ้นอื่นในตลาดเดียวกัน (มูลค่าและคุณภาพเทียบกับกลุ่มอุตสาหกรรมเดียวกันด้วย เช่น ธนาคารเทียบกับธนาคาร) แล้วเฉลี่ยในกลุ่ม</p>
      <div class="scroll-x"><table class="kv"><thead><tr><th>กลุ่มปัจจัย</th>${HK.map(h => `<th>ถือ ${HLABEL[h]}</th>`).join('')}</tr></thead><tbody>${wRows}</tbody></table></div>
      <p>ระยะสั้นให้น้ำหนักแนวโน้มราคาและข่าวมากกว่า ระยะยาวให้น้ำหนักมูลค่า คุณภาพ และการเติบโตมากกว่า · <b>คะแนนแนะนำ</b> = ผลรวมถ่วงน้ำหนัก ·
      ป้าย: <b>เด่นมาก</b> = 15% บนสุด, <b>น่าสนใจ</b> = ถัดมา 25%, <b>ปานกลาง</b> = ถัดมา 30%, <b>ควรระวัง</b> = 30% ล่างสุดของตลาด</p>
      <h3>3. โอกาสขึ้นตามสถิติ</h3>
      <p>แบ่งสภาวะราคาเป็น 6 แบบ (อยู่เหนือ/ใต้เส้นค่าเฉลี่ย 200 วัน × โมเมนตัม 3 เดือน อ่อน/กลาง/แรง) แล้วนับว่าในอดีต 10 ปี หุ้นทุกตัวในตลาดเดียวกันที่อยู่ในสภาวะนั้น
      ถือครบ 1/3/6/9 เดือนแล้วราคาสูงขึ้นกี่เปอร์เซ็นต์ของครั้ง พร้อมแสดงสถิติของหุ้นตัวนั้นเองและช่วงผลตอบแทนที่เคยเกิดขึ้น</p>
      <p><b>ผลทดสอบที่ต้องรู้:</b> ตัวเลขนี้แม่นในแง่ "ความน่าจะเป็นพื้นฐาน" แต่แยกหุ้นที่จะขึ้น/ไม่ขึ้นได้น้อยมาก
      (สถิติของหุ้นแต่ละตัวในอดีตยิ่งแย่กว่า — หุ้นที่เคยขึ้นบ่อยไม่ได้ขึ้นบ่อยต่อ) จึงแสดงเป็นข้อมูลประกอบ ไม่นำไปรวมในคะแนน ดูรายละเอียดที่หน้า <a href="#/track">ผลงานย้อนหลัง</a></p>
      <h3>4. ข้อจำกัด</h3>
      <ul><li>ข้อมูลฟรีจาก Yahoo Finance อาจล่าช้า ไม่ครบ หรือผิดพลาดบางตัว โดยเฉพาะหุ้นไทยขนาดกลาง-เล็ก</li>
        <li>งบการเงินอัปเดตตามรอบประกาศ (รายไตรมาส) ข่าวเชิงลึก/ข่าวในห้องค้าไม่ได้ถูกนับรวม</li>
        <li>โทนข่าวจากคำสำคัญเป็นการประมาณ อาจตีความผิดในบางหัวข่าว</li>
        <li>ไม่ได้คำนึงถึงสถานการณ์ส่วนตัว เช่น เป้าหมาย ภาษี ความเสี่ยงที่รับได้ หรือค่าเงิน (หุ้นต่างประเทศมีความเสี่ยงอัตราแลกเปลี่ยน)</li></ul>
    </div>`;
  }

  // ------------------------------------------------------------ boot
  function bindGlobal() {
    $$('#tabs button').forEach(b => b.addEventListener('click', () => go(b.dataset.tab)));
    $('#scrim').addEventListener('click', () => go(S.tab, S.horizon));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.openSym) go(S.tab, S.horizon); });
    $('#theme-btn').addEventListener('click', () => {
      const cur = document.documentElement.dataset.theme ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      store.set('sl-theme', next);
      if (S.openSym && S.details[S.openSym]) drawPrice(S.details[S.openSym]);
    });
    let t;
    window.addEventListener('resize', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (S.openSym && S.details[S.openSym]) {
          drawPrice(S.details[S.openSym]);
          drawFinancials(S.details[S.openSym], marketOf(S.openSym));
        }
      }, 200);
    });
    window.addEventListener('hashchange', route);
  }

  async function boot() {
    bindGlobal();
    updateWatchCount();
    try {
      const r = await fetch('data/meta.json', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      S.meta = await r.json();
    } catch (e) {
      $('#view').innerHTML = `<div class="panel empty" style="margin-top:24px">
        <b>ยังไม่มีข้อมูล</b><br>ดับเบิลคลิกไฟล์ <code>update.bat</code> เพื่อดึงข้อมูลครั้งแรก (ใช้เวลาประมาณ 3–5 นาที)
        แล้วเปิดเว็บผ่าน <code>serve.bat</code><br><span class="note">${esc(e.message)}</span></div>`;
      return;
    }
    renderStrip();
    await route();
  }
  boot();
})();
