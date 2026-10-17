/* Nocturna UI helpers: DOM builder, API calls, safe Markdown, modals, toasts.
 * Everything is built with DOM methods and text nodes, never innerHTML, so
 * text from documents, chats or the assistant can't inject markup. */
(function () {
  const N = (window.N = window.N || {});

  // ---------------------------------------------------------------- DOM
  N.el = function (tag, props, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(node.dataset, v);
      else if (k === "value") node.value = v;
      else if (v === true) node.setAttribute(k, "");
      else node.setAttribute(k, v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return node;
  };
  const el = N.el;
  N.clear = (node) => { node.replaceChildren(); return node; };

  // --------------------------------------------------------------- icons
  // One small set of line icons, drawn with SVG and `currentColor`, so every
  // icon takes the colour of the text around it (black on white, white on
  // black). There are no coloured emoji anywhere in the interface.
  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    plus: "M12 5v14M5 12h14",
    chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    settings: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
    user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
    trash: "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6",
    search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.3-4.3",
    paperclip: "M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48",
    file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8",
    pencil: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
    quiz: "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    cards: "M12 2l10 5-10 5L2 7zM2 17l10 5 10-5M2 12l10 5 10-5",
    calendar: "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM16 2v4M8 2v4M3 10h18",
    chart: "M18 20V10M12 20V4M6 20v-6",
    clipboard: "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 2h6v4H9z",
    code: "M16 18l6-6-6-6M8 6l-6 6 6 6",
    mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8",
    volume: "M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
    thumbup: "M7 10v12M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88z",
    thumbdown: "M17 14V2M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88z",
    copy: "M11 9h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
    refresh: "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
    close: "M18 6L6 18M6 6l12 12",
    panelclose: "M11 17l-5-5 5-5M18 17l-5-5 5-5",
    panelopen: "M13 17l5-5-5-5M6 17l5-5-5-5",
    menu: "M3 12h18M3 6h18M3 18h18",
    book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
    note: "M4 4h16v16H4zM8 9h8M8 13h8M8 17h5",
    download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
    shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
    logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  };
  N.icon = function (name, size) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size || 18));
    svg.setAttribute("height", String(size || 18));
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.classList.add("svg-icon");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", ICONS[name] || "");
    svg.append(path);
    return svg;
  };

  // ---------------------------------------------------------------- API
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  N.api = async function (path, opts = {}) {
    const init = { method: opts.method || (opts.json || opts.form ? "POST" : "GET"), headers: { "X-CSRF-Token": csrf() } };
    if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); }
    if (opts.form) init.body = opts.form;
    let res;
    try { res = await fetch(path, init); } catch (e) { throw new Error("Can't reach Nocturna. Check that it is still running."); }
    if (res.status === 401) { window.location.href = "/login"; throw new Error("Please log in."); }
    let data = {};
    try { data = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) throw new Error(data.error || (res.status === 413 ? "That file is too large." : "Something went wrong. Please try again."));
    return data;
  };

  // -------------------------------------------------------------- toasts
  N.toast = function (message, kind) {
    const root = document.getElementById("toast-root");
    const t = el("div", { class: "toast " + (kind || ""), role: kind === "error" ? "alert" : "status", text: message });
    root.append(t);
    setTimeout(() => t.classList.add("out"), 3200);
    setTimeout(() => t.remove(), 3700);
  };

  // -------------------------------------------------------------- modals
  N.modal = function ({ title, wide, drawer, onClose, labelledBy }) {
    const root = document.getElementById("modal-root");
    const prevFocus = document.activeElement;
    const body = el("div", { class: "modal-body" });
    const head = el("div", { class: "modal-head" }, el("h2", { text: title || "" }));
    const closeBtn = el("button", { type: "button", class: "icon-btn", "aria-label": "Close" }, N.icon("close", 18));
    head.append(closeBtn);
    const box = el("div", { class: "modal" + (wide ? " wide" : "") + (drawer ? " drawer" : ""), role: "dialog", "aria-modal": "true", "aria-label": title || "Dialog", tabindex: "-1" }, head, body);
    const overlay = el("div", { class: "overlay" }, box);
    const api = {
      body, box, overlay,
      setTitle: (t) => { head.querySelector("h2").textContent = t; box.setAttribute("aria-label", t); },
      close: () => {
        if (!overlay.isConnected) return;
        document.removeEventListener("keydown", onKey, true);
        overlay.remove();
        if (prevFocus && prevFocus.focus) prevFocus.focus();
        if (onClose) onClose();
      },
    };
    function onKey(e) {
      if (!overlay.isConnected || root.lastElementChild !== overlay) return;
      if (e.key === "Escape") { e.stopPropagation(); api.close(); }
      if (e.key === "Tab") {
        const f = [...box.querySelectorAll('button:not([disabled]),input:not([disabled]),select,textarea,a[href],[tabindex="0"]')].filter((n) => n.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    closeBtn.addEventListener("click", api.close);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) api.close(); });
    document.addEventListener("keydown", onKey, true);
    root.append(overlay);
    box.focus();
    return api;
  };

  N.confirm = function ({ title, message, confirmText, danger, requireText }) {
    return new Promise((resolve) => {
      let done = false;
      const m = N.modal({ title, onClose: () => { if (!done) resolve(false); } });
      const input = requireText ? el("input", { type: "text", "aria-label": "Type " + requireText + " to confirm", autocomplete: "off" }) : null;
      const ok = el("button", { type: "button", class: danger ? "danger" : "primary", text: confirmText || "Confirm", disabled: !!requireText });
      if (input) input.addEventListener("input", () => { ok.disabled = input.value.trim() !== requireText; });
      ok.addEventListener("click", () => { done = true; m.close(); resolve(true); });
      const cancel = el("button", { type: "button", class: "ghost", text: "Cancel", onclick: () => m.close() });
      m.body.append(el("p", { text: message }), input ? el("label", { class: "field" }, "Type " + requireText + " to confirm", input) : "", el("div", { class: "row end" }, cancel, ok));
      (input || cancel).focus();
    });
  };

  N.prompt = function ({ title, label, value, confirmText }) {
    return new Promise((resolve) => {
      let done = false;
      const m = N.modal({ title, onClose: () => { if (!done) resolve(null); } });
      const input = el("input", { type: "text", value: value || "", maxlength: "80" });
      const form = el("form", { onsubmit: (e) => { e.preventDefault(); done = true; m.close(); resolve(input.value.trim() || null); } },
        el("label", { class: "field" }, label, input),
        el("div", { class: "row end" }, el("button", { type: "button", class: "ghost", text: "Cancel", onclick: () => m.close() }), el("button", { type: "submit", class: "primary", text: confirmText || "Save" })));
      m.body.append(form);
      input.focus(); input.select();
    });
  };

  // ------------------------------------------------ loading / error states
  N.spinner = (text) => el("div", { class: "state loading", role: "status" }, el("span", { class: "spin", "aria-hidden": "true" }), text || "Loading...");
  N.errorBox = (message, retry) => el("div", { class: "state error", role: "alert" }, el("span", { text: message }), retry ? el("button", { type: "button", class: "ghost", text: "Try Again", onclick: retry }) : null);
  N.empty = (title, hint) => el("div", { class: "state empty" }, el("strong", { text: title }), hint ? el("span", { text: hint }) : null);

  /** Show a spinner in `box`, run `fn(box)`, and show a Try Again error if it fails. */
  N.load = async function (box, fn) {
    N.clear(box).append(N.spinner());
    try { N.clear(box); await fn(box); }
    catch (e) { N.clear(box).append(N.errorBox(e.message, () => N.load(box, fn))); }
  };

  /** Disable a button and show a busy label while `fn` runs. */
  N.busy = async function (btn, label, fn) {
    const old = btn.textContent; btn.disabled = true; btn.textContent = label;
    try { return await fn(); } finally { btn.disabled = false; btn.textContent = old; }
  };

  // -------------------------------------------------------------- Markdown
  const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>)"']+|\$[^$\n]{1,80}\$|\\\([^)\n]{1,80}\\\))/g;
  function inline(text, parent) {
    let last = 0;
    for (const m of text.matchAll(INLINE)) {
      if (m.index > last) parent.append(document.createTextNode(text.slice(last, m.index)));
      const t = m[0];
      if (t[0] === "`") parent.append(el("code", { text: t.slice(1, -1) }));
      else if (t.startsWith("**")) { const b = el("strong"); inline(t.slice(2, -2), b); parent.append(b); }
      else if (t[0] === "*") { const i = el("em"); inline(t.slice(1, -1), i); parent.append(i); }
      else if (t[0] === "[") { const mm = /^\[([^\]]+)\]\((.+)\)$/.exec(t); parent.append(el("a", { href: mm[2], target: "_blank", rel: "noopener noreferrer", text: mm[1] })); }
      else if (t[0] === "$" || t[0] === "\\") parent.append(el("span", { class: "math", text: t[0] === "$" ? t.slice(1, -1) : t.slice(2, -2) }));
      else parent.append(el("a", { href: t, target: "_blank", rel: "noopener noreferrer", text: t }));
      last = m.index + t.length;
    }
    if (last < text.length) parent.append(document.createTextNode(text.slice(last)));
  }
  const isRow = (l) => /^\s*\|.*\|\s*$/.test(l);
  const isSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
  const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  N.md = function (src) {
    const frag = document.createDocumentFragment();
    const lines = String(src).replace(/\r/g, "").split("\n");
    for (let i = 0; i < lines.length;) {
      const line = lines[i];
      if (/^```/.test(line)) {                                   // fenced code block
        const buf = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        i++;
        const pre = el("pre", { class: "codeblock" }, el("code", { text: buf.join("\n") }));
        const copy = el("button", { type: "button", class: "mini", text: "Copy", onclick: (e) => { navigator.clipboard && navigator.clipboard.writeText(buf.join("\n")).then(() => { e.target.textContent = "Copied"; setTimeout(() => (e.target.textContent = "Copy"), 1200); }); } });
        frag.append(el("div", { class: "codewrap" }, copy, pre));
      } else if (/^#{1,6}\s/.test(line)) {
        const level = Math.min(6, Math.max(3, line.match(/^#+/)[0].length + 2));
        const h = el("h" + level); inline(line.replace(/^#+\s*/, ""), h); frag.append(h); i++;
      } else if (isRow(line) && i + 1 < lines.length && isSep(lines[i + 1])) {   // table
        const head = cells(line); i += 2;
        const rows = [];
        while (i < lines.length && isRow(lines[i])) rows.push(cells(lines[i++]));
        const table = el("table", { class: "mdtable" }, el("thead", {}, el("tr", {}, head.map((h) => { const th = el("th"); inline(h, th); return th; }))),
          el("tbody", {}, rows.map((r) => el("tr", {}, r.map((c) => { const td = el("td"); inline(c, td); return td; })))));
        frag.append(el("div", { class: "tablewrap" }, table));
      } else if (/^\s*>\s?/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
        const bq = el("blockquote"); inline(buf.join(" "), bq); frag.append(bq);
      } else if (/^\s*([-*•])\s+/.test(line)) {
        const ul = el("ul");
        while (i < lines.length && /^\s*([-*•])\s+/.test(lines[i])) { const li = el("li"); inline(lines[i++].replace(/^\s*[-*•]\s+/, ""), li); ul.append(li); }
        frag.append(ul);
      } else if (/^\s*\d+[.)]\s+/.test(line)) {
        const ol = el("ol");
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { const li = el("li"); inline(lines[i++].replace(/^\s*\d+[.)]\s+/, ""), li); ol.append(li); }
        frag.append(ol);
      } else if (!line.trim()) { i++; }
      else {
        const buf = [];
        while (i < lines.length && lines[i].trim() && !/^(```|#{1,6}\s|\s*>|\s*([-*•]|\d+[.)])\s+)/.test(lines[i]) && !(isRow(lines[i]) && isSep(lines[i + 1] || ""))) buf.push(lines[i++]);
        const p = el("p");
        buf.forEach((l, k) => { if (k) p.append(el("br")); inline(l, p); });
        frag.append(p);
      }
    }
    return frag;
  };

  // ----------------------------------------------------------- misc helpers
  N.fmtDate = (s) => { try { return new Date(s.replace(" ", "T") + "Z").toLocaleDateString(undefined, { day: "numeric", month: "short" }); } catch (_) { return s; } };
  N.today = () => new Date().toISOString().slice(0, 10);
  N.state = { settings: {}, caps: {}, conv: null, docs: [], courses: [] };

  N.select = function (options, value, props) {
    const s = el("select", props || {});
    options.forEach(([val, label]) => s.append(el("option", { value: val, text: label, selected: String(val) === String(value) })));
    return s;
  };
  N.field = (label, control, hint) => el("label", { class: "field" }, el("span", { text: label }), control, hint ? el("small", { text: hint }) : null);
})();
