(() => {
  "use strict";
  const root = document.documentElement;

  // 上昇色の好み（閲覧者ごと。保存できなくても表示は既定の「赤」で動く）
  const KEY = "jpmarket.updown";
  const applyUpdown = (mode) => {
    root.dataset.updown = mode;
    document.querySelectorAll("[data-updown]").forEach((b) => {
      if (b.tagName === "BUTTON") b.setAttribute("aria-pressed", String(b.dataset.updown === mode));
    });
  };
  let saved = "jp";
  try { saved = localStorage.getItem(KEY) || "jp"; } catch (e) { /* storage unavailable */ }
  applyUpdown(saved);
  document.querySelectorAll(".colorpref button").forEach((b) => {
    b.addEventListener("click", () => {
      applyUpdown(b.dataset.updown);
      try { localStorage.setItem(KEY, b.dataset.updown); } catch (e) { /* ignore */ }
    });
  });

  // タブ（ヒートマップ）
  document.querySelectorAll(".tabs").forEach((tabs) => {
    const buttons = [...tabs.querySelectorAll("[role=tab]")];
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => {
          const on = b === btn;
          b.setAttribute("aria-selected", String(on));
          document.getElementById(b.dataset.panel).hidden = !on;
        });
      });
    });
  });

  // ツールチップ: data-tip の「｜」区切りを行として表示
  const tip = document.getElementById("tip");
  if (!tip) return;
  let current = null;
  const show = (el, x, y) => {
    const text = el.getAttribute("data-tip");
    if (!text) return;
    if (current !== el) {
      tip.replaceChildren(...text.split("｜").map((t) => {
        const s = document.createElement("span");
        s.textContent = t;
        return s;
      }));
      current = el;
    }
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    const px = Math.min(Math.max(8, x + 14), window.innerWidth - r.width - 8);
    const py = y + 18 + r.height > window.innerHeight ? y - r.height - 12 : y + 18;
    tip.style.left = px + "px";
    tip.style.top = py + "px";
  };
  const hide = () => { tip.hidden = true; current = null; };
  document.addEventListener("pointermove", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) show(el, e.clientX, e.clientY); else if (current) hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) { const r = el.getBoundingClientRect(); show(el, r.left + 20, r.bottom - 10); }
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("scroll", hide, { passive: true });
})();

// チャート（クリックで拡大表示）。ライブラリとデータは初回に1回だけ読み込む。
(() => {
  "use strict";
  const LIB = "https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js";
  const dlg = document.getElementById("chartdlg");
  const main = document.querySelector("main[data-charts-url]");
  if (!dlg || !main || typeof dlg.showModal !== "function") return;
  const $ = (id) => document.getElementById(id);
  const el = { title: $("cd-title"), legend: $("cd-legend"), box: $("cd-chart"), msg: $("cd-msg"),
               note: $("cd-note"), links: $("cd-links"), ma: $("cd-ma") };
  let libP = null, dataP = null, chart = null, current = null, range = 63;

  const loadLib = () => libP || (libP = new Promise((ok, ng) => {
    if (window.LightweightCharts) return ok(window.LightweightCharts);
    const s = document.createElement("script");
    s.src = LIB; s.async = true;
    s.onload = () => ok(window.LightweightCharts);
    s.onerror = () => { libP = null; ng(new Error("チャート部品を読み込めませんでした")); };
    document.head.appendChild(s);
  }));
  const loadData = () => dataP || (dataP = fetch(main.dataset.chartsUrl)
    .then((r) => { if (!r.ok) throw new Error("チャートデータがありません"); return r.json(); })
    .catch((e) => { dataP = null; throw e; }));

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmt = (v, d) => v == null ? "—" : v.toLocaleString("ja-JP", { minimumFractionDigits: d, maximumFractionDigits: d });
  const digits = (s) => s.unit === "%" ? 3 : (Math.abs(s.c[s.c.length - 1]) >= 1000 ? 0 : 2);
  const vol = (v) => v >= 1e8 ? fmt(v / 1e8, 2) + "億株" : fmt(v / 1e4, 0) + "万株";
  const sma = (c, t, n) => {
    const out = []; let sum = 0;
    for (let i = 0; i < c.length; i++) {
      sum += c[i]; if (i >= n) sum -= c[i - n];
      if (i >= n - 1) out.push({ time: t[i], value: +(sum / n).toFixed(4) });
    }
    return out;
  };

  // 銘柄コードなら、データが無くても外部チャートへのリンクは出せる
  const stockLinks = (id) => /^[0-9][0-9A-Z]{3}$/.test(id) ? {
    "株探": `https://kabutan.jp/stock/chart?code=${id}`,
    "Yahoo!ファイナンス": `https://finance.yahoo.co.jp/quote/${id}.T/chart`,
    "TradingView": `https://www.tradingview.com/chart/?symbol=TSE%3A${id}`,
  } : {};

  function setMsg(text) { el.msg.textContent = text || ""; el.msg.hidden = !text; }

  function setLinks(links) {
    el.links.replaceChildren(...Object.entries(links || {}).map(([label, url]) => {
      const a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener"; a.textContent = label + " ↗";
      return a;
    }));
  }

  function applyRange() {
    if (!chart || !current) return;
    const n = current.t.length;
    if (!range || range >= n) chart.timeScale().fitContent();
    else chart.timeScale().setVisibleLogicalRange({ from: n - range - 0.5, to: n - 0.5 });
    dlg.querySelectorAll("[data-range]").forEach((b) =>
      b.setAttribute("aria-selected", String(+b.dataset.range === range)));
  }

  function legendFor(s, i) {
    if (i == null || i < 0) i = s.t.length - 1;
    const d = digits(s), prev = i > 0 ? s.c[i - 1] : null;
    const chg = prev ? (s.unit === "%" ? `${((s.c[i] - prev) * 100).toFixed(1)}bp` : `${((s.c[i] / prev - 1) * 100).toFixed(2)}%`) : "";
    const sign = prev && s.c[i] - prev > 0 ? "+" : "";
    if (s.kind === "ohlc") {
      return `${s.t[i]}  始 ${fmt(s.o[i], d)}  高 ${fmt(s.h[i], d)}  安 ${fmt(s.l[i], d)}  終 ${fmt(s.c[i], d)}  ${sign}${chg}` +
        (s.v ? `  出来高 ${vol(s.v[i])}` : "");
    }
    return `${s.t[i]}  ${fmt(s.c[i], d)}${s.unit || ""}  ${sign}${chg}`;
  }

  function draw(LC, s) {
    if (chart) { chart.remove(); chart = null; }
    const up = css("--up"), down = css("--down");
    chart = LC.createChart(el.box, {
      autoSize: true,
      layout: { background: { type: "solid", color: css("--surface") }, textColor: css("--ink-2"),
                fontFamily: css("--f-mono") || "monospace", fontSize: 11 },
      grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
      rightPriceScale: { borderColor: css("--line") },
      timeScale: { borderColor: css("--line"), rightOffset: 2 },
      localization: { locale: "ja-JP", dateFormat: "yyyy/MM/dd" },
      crosshair: { mode: 0 },
    });
    const pf = { type: "price", precision: digits(s), minMove: 1 / 10 ** digits(s) };
    let main;
    if (s.kind === "ohlc") {
      main = chart.addSeries(LC.CandlestickSeries, {
        upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down,
        priceFormat: pf,
      });
      main.setData(s.t.map((t, i) => ({ time: t, open: s.o[i], high: s.h[i], low: s.l[i], close: s.c[i] })));
      [[5, "--ma5"], [25, "--ma25"], [75, "--ma75"]].forEach(([n, v]) => {
        if (s.c.length < n) return;
        const line = chart.addSeries(LC.LineSeries, { color: css(v), lineWidth: 1, priceLineVisible: false,
                                                      lastValueVisible: false, crosshairMarkerVisible: false });
        line.setData(sma(s.c, s.t, n));
      });
      if (s.v) {
        const hv = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol",
                                                         lastValueVisible: false, priceLineVisible: false });
        hv.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        hv.setData(s.t.map((t, i) => ({ time: t, value: s.v[i],
          color: (s.c[i] >= s.o[i] ? up : down) + "66" })));
        main.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.22 } });
      }
      el.ma.hidden = false;
    } else {
      main = chart.addSeries(LC.AreaSeries, {
        lineColor: css("--accent"), topColor: css("--accent") + "33", bottomColor: css("--accent") + "05",
        lineWidth: 2, priceFormat: pf,
      });
      main.setData(s.t.map((t, i) => ({ time: t, value: s.c[i] })).filter((p) => p.value != null));
      el.ma.hidden = true;
    }
    const idx = new Map(s.t.map((t, i) => [t, i]));
    chart.subscribeCrosshairMove((p) => {
      const key = p && p.time ? (typeof p.time === "string" ? p.time
        : `${p.time.year}-${String(p.time.month).padStart(2, "0")}-${String(p.time.day).padStart(2, "0")}`) : null;
      el.legend.textContent = legendFor(s, key ? idx.get(key) : null);
    });
    el.legend.textContent = legendFor(s);
    applyRange();
  }

  async function open(id) {
    el.title.textContent = /^[0-9][0-9A-Z]{3}$/.test(id) ? id : "チャート";
    el.legend.textContent = ""; el.note.textContent = ""; setLinks(stockLinks(id)); setMsg("読み込み中…");
    el.ma.hidden = true;
    if (!dlg.open) dlg.showModal();
    try {
      const data = await loadData();
      const s = data.series[id];
      if (s && s.t0 && !Array.isArray(s.t)) {  // expand compact dates: t0 + day offsets
        const d = new Date(s.t0 + "T00:00:00Z"); s.t = [s.t0];
        for (const off of s.dt) { d.setUTCDate(d.getUTCDate() + off); s.t.push(d.toISOString().slice(0, 10)); }
      }
      if (!s) { current = null; if (chart) { chart.remove(); chart = null; } setMsg("この項目のチャートデータはありません。"); return; }
      current = s;
      el.title.textContent = s.name + (/^\d/.test(id) ? `（${id}）` : "");
      el.note.textContent = [s.note, `データ: ${data.asof} 時点`].filter(Boolean).join("・");
      setLinks(Object.keys(s.links || {}).length ? s.links : stockLinks(id));
      const LC = await loadLib();
      setMsg("");
      draw(LC, s);
    } catch (e) {
      setMsg(e.message + "。外部サイトのリンクからご覧ください。");
    }
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest && e.target.closest("[data-chart]");
    if (!t || e.target.closest("a")) return;
    open(t.dataset.chart);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const t = e.target.closest && e.target.closest("[data-chart][role=button]");
    if (!t || t.tagName === "BUTTON") return;
    e.preventDefault(); open(t.dataset.chart);
  });
  $("cd-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => { if (chart) { chart.remove(); chart = null; } current = null; });
  dlg.querySelectorAll("[data-range]").forEach((b) => b.addEventListener("click", () => {
    range = +b.dataset.range; applyRange();
  }));
  // 上昇色の切り替えに追従
  document.querySelectorAll(".colorpref button").forEach((b) => b.addEventListener("click", () => {
    if (current && window.LightweightCharts) draw(window.LightweightCharts, current);
  }));
})();
