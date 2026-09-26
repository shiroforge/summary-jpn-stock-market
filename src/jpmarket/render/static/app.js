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
