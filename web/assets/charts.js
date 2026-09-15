/* StockLens — กราฟ SVG น้ำหนักเบา (เส้นราคา แท่ง สปาร์กไลน์) พร้อม tooltip */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const tip = () => document.getElementById('tooltip');

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  function niceTicks(min, max, count) {
    if (!(isFinite(min) && isFinite(max))) return [];
    if (min === max) { min -= 1; max += 1; }
    const span = max - min;
    const step0 = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const norm = step0 / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const ticks = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(+v.toPrecision(12));
    return ticks;
  }

  function showTip(html, x, y) {
    const t = tip();
    t.innerHTML = html;
    t.classList.add('show');
    const r = t.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    t.style.left = Math.max(8, left) + 'px';
    t.style.top = Math.max(8, top) + 'px';
  }
  function hideTip() { tip().classList.remove('show'); }

  const escT = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /**
   * กราฟเส้นหลายชุดข้อมูล แกน y เดียว มี crosshair + tooltip
   * opts: {dates:[], series:[{name, color, values:[], area?}], height, fmt(v), fmtDate(d)}
   */
  function line(container, opts) {
    container.innerHTML = '';
    container.classList.add('chart');
    container.tabIndex = 0;
    const W = Math.max(280, container.clientWidth || 600);
    const H = opts.height || 260;
    const m = { l: 6, r: 58, t: 10, b: 26 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const n = opts.dates.length;
    const all = opts.series.flatMap(s => s.values).filter(v => v != null && isFinite(v));
    if (!n || !all.length) { container.innerHTML = '<div class="empty">ไม่มีข้อมูลกราฟ</div>'; return; }
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = (hi - lo) * 0.06 || hi * 0.05 || 1;
    lo -= pad; hi += pad;
    const ticks = niceTicks(lo, hi, 4).filter(t => t >= lo && t <= hi);
    const x = i => m.l + (n === 1 ? pw / 2 : (i / (n - 1)) * pw);
    const y = v => m.t + ph - ((v - lo) / (hi - lo)) * ph;
    const fmt = opts.fmt || (v => v.toFixed(2));

    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': opts.label || 'กราฟ' }, container);
    // grid + y ticks (ขวา)
    ticks.forEach(t => {
      el('line', { x1: m.l, x2: m.l + pw, y1: y(t), y2: y(t), stroke: 'var(--line)', 'stroke-width': 1 }, svg);
      const tx = el('text', { x: m.l + pw + 8, y: y(t) + 4, fill: 'var(--muted)', 'font-size': 11 }, svg);
      tx.textContent = fmt(t);
    });
    // x ticks: ~5 labels
    const every = Math.max(1, Math.round(n / 5));
    for (let i = 0; i < n; i += every) {
      const tx = el('text', { x: x(i), y: H - 6, fill: 'var(--muted)', 'font-size': 11, 'text-anchor': i === 0 ? 'start' : 'middle' }, svg);
      tx.textContent = (opts.fmtAxisDate || opts.fmtDate || (d => d))(opts.dates[i]);
    }
    el('line', { x1: m.l, x2: m.l + pw, y1: m.t + ph, y2: m.t + ph, stroke: 'var(--line-2)', 'stroke-width': 1 }, svg);

    // series (วาดชุดหลักทีหลังสุดให้อยู่บน)
    const order = opts.series.map((s, i) => i).reverse();
    order.forEach(si => {
      const s = opts.series[si];
      let d = '', started = false, first = -1, last = -1;
      s.values.forEach((v, i) => {
        if (v == null || !isFinite(v)) { started = false; return; }
        d += (started ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1);
        started = true;
        if (first < 0) first = i;
        last = i;
      });
      if (!d) return;
      if (s.area) {
        el('path', { d: d + `L${x(last).toFixed(1)},${m.t + ph}L${x(first).toFixed(1)},${m.t + ph}Z`, fill: s.color, 'fill-opacity': 0.08, stroke: 'none' }, svg);
      }
      el('path', { d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    });

    // crosshair layer
    const cross = el('line', { y1: m.t, y2: m.t + ph, stroke: 'var(--muted)', 'stroke-width': 1, opacity: 0 }, svg);
    const dots = opts.series.map(s => el('circle', { r: 4, fill: s.color, stroke: 'var(--surface)', 'stroke-width': 2, opacity: 0 }, svg));
    const hit = el('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent' }, svg);

    let cur = -1;
    function show(i, cx, cy) {
      cur = Math.max(0, Math.min(n - 1, i));
      cross.setAttribute('x1', x(cur)); cross.setAttribute('x2', x(cur)); cross.setAttribute('opacity', 1);
      let rows = '';
      opts.series.forEach((s, si) => {
        const v = s.values[cur];
        if (v == null || !isFinite(v)) { dots[si].setAttribute('opacity', 0); return; }
        dots[si].setAttribute('cx', x(cur)); dots[si].setAttribute('cy', y(v)); dots[si].setAttribute('opacity', 1);
        rows += `<div class="tt-r"><span><i class="tt-k" style="background:${s.color}"></i>${escT(s.name)}</span><b>${escT(fmt(v))}</b></div>`;
      });
      const r = svg.getBoundingClientRect();
      showTip(`<div class="tt-h">${escT((opts.fmtDate || (d => d))(opts.dates[cur]))}</div>${rows}`,
        cx ?? r.left + (x(cur) / W) * r.width, cy ?? r.top + r.height / 3);
    }
    function clear() { cross.setAttribute('opacity', 0); dots.forEach(d => d.setAttribute('opacity', 0)); hideTip(); }
    hit.addEventListener('pointermove', e => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      show(Math.round(((px - m.l) / pw) * (n - 1)), e.clientX, e.clientY);
    });
    hit.addEventListener('pointerleave', clear);
    container.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        show((cur < 0 ? n - 1 : cur) + (e.key === 'ArrowRight' ? 1 : -1));
      } else if (e.key === 'Escape') clear();
    });
    container.addEventListener('blur', clear);
  }

  /**
   * กราฟแท่งชุดเดียว (รองรับค่าติดลบ) ปลายแท่งมน 4px ฐานเหลี่ยม
   * opts: {labels:[], values:[], color, height, fmt(v), label}
   */
  function bars(container, opts) {
    container.innerHTML = '';
    container.classList.add('chart');
    const W = Math.max(220, container.clientWidth || 300);
    const H = opts.height || 170;
    const m = { l: 6, r: 50, t: 18, b: 24 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const vals = opts.values.map(v => (v == null || !isFinite(v) ? null : v));
    const real = vals.filter(v => v != null);
    if (!real.length) { container.innerHTML = '<div class="empty">ไม่มีข้อมูล</div>'; return; }
    let lo = Math.min(0, ...real), hi = Math.max(0, ...real);
    if (lo === hi) hi = lo + 1;
    const ticks = niceTicks(lo, hi, 3);
    lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
    const y = v => m.t + ph - ((v - lo) / (hi - lo)) * ph;
    const band = pw / vals.length;
    const bw = Math.min(24, band * 0.6);
    const fmt = opts.fmt || (v => String(v));
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': opts.label || 'กราฟแท่ง' }, container);
    ticks.forEach(t => {
      el('line', { x1: m.l, x2: m.l + pw, y1: y(t), y2: y(t), stroke: t === 0 ? 'var(--line-2)' : 'var(--line)', 'stroke-width': 1 }, svg);
      const tx = el('text', { x: m.l + pw + 6, y: y(t) + 4, fill: 'var(--muted)', 'font-size': 11 }, svg);
      tx.textContent = fmt(t);
    });
    let lastIdx = -1;
    vals.forEach((v, i) => { if (v != null) lastIdx = i; });
    vals.forEach((v, i) => {
      const cx = m.l + band * i + band / 2;
      const lb = el('text', { x: cx, y: H - 6, fill: 'var(--muted)', 'font-size': 11, 'text-anchor': 'middle' }, svg);
      lb.textContent = opts.labels[i];
      if (v == null) return;
      const x0 = cx - bw / 2, y0 = y(0), y1 = y(v);
      const h = Math.abs(y1 - y0), r = Math.min(4, bw / 2, h);
      let d;
      if (v >= 0) d = `M${x0},${y0}L${x0},${y1 + r}Q${x0},${y1} ${x0 + r},${y1}L${x0 + bw - r},${y1}Q${x0 + bw},${y1} ${x0 + bw},${y1 + r}L${x0 + bw},${y0}Z`;
      else d = `M${x0},${y0}L${x0},${y1 - r}Q${x0},${y1} ${x0 + r},${y1}L${x0 + bw - r},${y1}Q${x0 + bw},${y1} ${x0 + bw},${y1 - r}L${x0 + bw},${y0}Z`;
      const bar = el('path', { d, fill: v >= 0 ? opts.color : (opts.negColor || opts.color) }, svg);
      if (i === lastIdx) {
        const t = el('text', { x: cx, y: v >= 0 ? y1 - 5 : y1 + 13, fill: 'var(--text)', 'font-size': 11, 'font-weight': 600, 'text-anchor': 'middle' }, svg);
        t.textContent = fmt(v);
      }
      const hitR = el('rect', { x: m.l + band * i, y: m.t, width: band, height: ph, fill: 'transparent', tabindex: 0 }, svg);
      const on = e => {
        bar.setAttribute('fill-opacity', 0.8);
        const r2 = hitR.getBoundingClientRect();
        showTip(`<div class="tt-h">${escT(opts.labels[i])}</div><div class="tt-r"><span>${escT(opts.label || '')}</span><b>${escT(fmt(v))}</b></div>`,
          e.clientX ?? r2.left + r2.width / 2, e.clientY ?? r2.top);
      };
      const off = () => { bar.setAttribute('fill-opacity', 1); hideTip(); };
      hitR.addEventListener('pointermove', on);
      hitR.addEventListener('pointerleave', off);
      hitR.addEventListener('focus', on);
      hitR.addEventListener('blur', off);
    });
  }

  /** สปาร์กไลน์ (คืนเป็นสตริง SVG) */
  function spark(values, opts = {}) {
    const v = (values || []).filter(x => x != null && isFinite(x));
    if (v.length < 2) return '';
    const W = opts.width || 200, H = opts.height || 44, p = 3;
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = v.map((val, i) => [p + (i / (v.length - 1)) * (W - 2 * p), p + (H - 2 * p) * (1 - (val - lo) / span)]);
    const d = pts.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('');
    const color = opts.color || 'var(--series-1)';
    const lx = pts[pts.length - 1][0];
    const area = opts.area === false ? '' :
      `<path d="${d}L${lx.toFixed(1)},${H}L${p},${H}Z" fill="${color}" fill-opacity="0.08"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${area}` +
      `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;
  }

  window.SLCharts = { line, bars, spark, showTip, hideTip };
})();
