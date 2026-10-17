/* Nocturna chat application: sidebar, conversations, messages, composer. */
(function () {
  const { el, api, toast, md, clear } = N;
  const $ = (id) => document.getElementById(id);
  const app = $("app"), messagesEl = $("messages"), input = $("chat-input"), form = $("chat-form"), sendBtn = $("send-btn");
  // How long Nocturna "thinks" before a reply appears. The request is sent at
  // once; the reply is simply held back until this much time has passed.
  const THINKING_MS = 5000;
  const tts = "speechSynthesis" in window;
  let sending = false;
  document.querySelectorAll("[data-icon]").forEach((n) => n.append(N.icon(n.dataset.icon, n.classList.contains("ico") ? 18 : 17)));

  N.panels = N.panels || {};
  N.openPanel = (name, opts) => {
    const open = N.panels[name];
    if (!open) return toast("That tool isn't available.", "error");
    return open(opts || {});
  };

  // ------------------------------------------------------------ messages
  function plain(text) { return text.replace(/[*_`#>]/g, "").replace(/\s+/g, " "); }
  function speak(text) {
    if (!tts) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(plain(text).slice(0, 1500));
    u.lang = N.state.settings.voice_lang || "en-GB";
    speechSynthesis.speak(u);
  }

  function sourcesBlock(sources) {
    if (!sources || !sources.length || N.state.settings.show_sources === false) return null;
    return el("div", { class: "sources" }, "Sources:", sources.map((s) => {
      if (s.kb) return el("span", { class: "source" }, N.icon("book", 13), s.filename);
      const label = s.filename + (s.page ? " · Page " + s.page : "") + (s.section ? " · " + s.section : "");
      return el("button", { type: "button", class: "source", title: s.snippet || "", onclick: () => N.openPanel("documents", { open: s.document_id }) }, N.icon("file", 13), label);
    }));
  }

  // ---------------------------------------------------------- timestamps
  // Times are always rendered; Settings > General > Show timestamps only
  // switches their visibility (CSS class on the message list).
  function parseTime(v) {
    if (!v) return new Date();
    if (v instanceof Date) return v;
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(v) ? v : String(v).replace(" ", "T") + "Z");   // the database stores UTC
    return isNaN(d) ? new Date() : d;
  }
  function formatTime(d) {
    const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return t;
    return d.toLocaleDateString([], { day: "numeric", month: "short", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) }) + ", " + t;
  }
  N.applyTimestamps = () => messagesEl.classList.toggle("hide-time", N.state.settings.show_timestamps === false);

  function addMessage(role, text, o = {}) {
    const wrap = el("div", { class: "msg " + role });
    if (o.id) wrap.dataset.id = o.id;
    wrap.append(el("span", { class: "who", text: role === "user" ? "You" : "Nocturna" }));
    const bubble = el("div", { class: "bubble" });
    if (role === "bot") bubble.append(md(text)); else bubble.textContent = text;
    wrap.append(bubble);
    const when = parseTime(o.time);
    wrap.append(el("time", { class: "msg-time", datetime: when.toISOString(), title: when.toLocaleString(), text: formatTime(when) }));
    if (role === "bot") {
      const src = sourcesBlock(o.sources);
      if (src) wrap.append(src);
      const bar = el("div", { class: "msg-actions" });
      if (o.bare) { messagesEl.append(wrap); messagesEl.scrollTop = messagesEl.scrollHeight; return wrap; }
      (o.actions || []).forEach((a) => {
        if (a.type === "open_panel") bar.append(el("button", { type: "button", class: "action-btn", text: "Open " + a.panel.replace(/_/g, " "), onclick: () => N.openPanel(a.panel, a) }));
        if (a.type === "save_note") bar.append(el("button", { type: "button", class: "action-btn", text: a.label || "Save to notes", onclick: () => saveNote(text) }));
      });
      if (o.retry) bar.append(el("button", { type: "button", class: "action-btn", text: "Try Again", onclick: () => { wrap.remove(); sendRaw(o.retry); } }));
      if (!o.error) {
        const copyLabel = el("span", { text: "Copy" });
        const copy = el("button", { type: "button", class: "mini", onclick: () => navigator.clipboard && navigator.clipboard.writeText(text).then(() => { copyLabel.textContent = "Copied"; setTimeout(() => (copyLabel.textContent = "Copy"), 1200); }) }, N.icon("copy", 14), copyLabel);
        bar.append(copy);
        if (o.id) {
          const up = el("button", { type: "button", class: "mini" + (o.feedback === 1 ? " on" : ""), "aria-label": "Helpful", title: "Helpful" }, N.icon("thumbup", 14));
          const down = el("button", { type: "button", class: "mini" + (o.feedback === -1 ? " on" : ""), "aria-label": "Not helpful", title: "Not helpful" }, N.icon("thumbdown", 14));
          const rate = async (val, btn, other) => {
            const next = btn.classList.contains("on") ? 0 : val;
            try { await api(`/api/messages/${o.id}/feedback`, { json: { value: next } }); btn.classList.toggle("on", next !== 0); other.classList.remove("on"); }
            catch (e) { toast(e.message, "error"); }
          };
          up.addEventListener("click", () => rate(1, up, down)); down.addEventListener("click", () => rate(-1, down, up));
          bar.append(up, down);
        }
        bar.append(el("button", { type: "button", class: "mini", onclick: () => saveNote(text) }, N.icon("note", 14), "Save to notes"));
        if (tts) bar.append(el("button", { type: "button", class: "mini", onclick: () => speak(text) }, N.icon("volume", 14), "Read aloud"));
        if (o.id) bar.append(el("button", { type: "button", class: "mini regen", onclick: regenerate }, N.icon("refresh", 14), "Regenerate"));
      }
      if (bar.children.length) wrap.append(bar);
    }
    messagesEl.append(wrap);
    refreshRegen();
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }
  function refreshRegen() {
    const bots = [...messagesEl.querySelectorAll(".msg.bot[data-id]")];
    bots.forEach((m, i) => { const b = m.querySelector(".regen"); if (b) b.hidden = i !== bots.length - 1; });
  }
  // "Thinking" indicator, shown under the student's message while Nocturna
  // works on the answer.
  function thinking() {
    const w = el("div", { class: "msg bot thinking", role: "status", "aria-label": "Nocturna is thinking" },
      el("span", { class: "who", text: "Nocturna" }),
      el("div", { class: "bubble" }, el("span", { class: "thinking-label", text: "Thinking" }), el("span", { class: "dots", "aria-hidden": "true" }, el("i"), el("i"), el("i"))));
    messagesEl.append(w); messagesEl.scrollTop = messagesEl.scrollHeight; return w;
  }
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  // Runs `task` (the real request) while showing "Thinking", and holds the
  // result back until THINKING_MS has passed, so a reply never appears sooner.
  async function withThinking(task) {
    const t = thinking(), started = Date.now();
    let result, failure = null;
    try { result = await task(); } catch (e) { failure = e; }
    const left = THINKING_MS - (Date.now() - started);
    if (left > 0) await wait(left);
    t.remove();
    if (failure) throw failure;
    return result;
  }
  async function saveNote(text) {
    try {
      const conv = N.state.conv;
      await api("/api/notes", { json: { content: text, title: plain(text).slice(0, 60), document_id: conv && conv.document ? conv.document.id : null } });
      toast("Saved to notes");
    } catch (e) { toast(e.message, "error"); }
  }
  N.saveNote = saveNote;

  function suggestions() {
    const chips = ["What student associations are there?", "What is the prerequisite for CPS 402?", "Quiz me", "Show my progress"];
    const row = el("div", { class: "msg-actions", id: "suggest-row" }, chips.map((c) => el("button", { type: "button", class: "action-btn", text: c, onclick: () => send(c) })),
      el("button", { type: "button", class: "action-btn", text: "Upload study material", onclick: () => N.openPanel("upload") }));
    messagesEl.append(row);
  }

  // ----------------------------------------------------- conversations
  function setConv(data) {
    N.state.conv = data.conversation;
    $("convo-title").textContent = data.conversation.title;
    clear(messagesEl);
    let seenUser = false;
    data.messages.forEach((m) => {
      if (m.role === "user") seenUser = true;
      addMessage(m.role, m.content, { id: m.role === "bot" ? m.id : null, sources: m.meta && m.meta.sources, actions: [], feedback: m.feedback, bare: m.role === "bot" && !seenUser, time: m.created_at });
    });
    // keep the "Save to notes" style buttons for saved replies, but don't re-open panels
    if (data.messages.length <= 1) suggestions();
    renderCtx();
    highlightActive();
  }
  async function openConversation(id) {
    try { setConv(await api("/api/conversations/" + id)); closeMenu(); } catch (e) { toast(e.message, "error"); }
  }
  async function newChat() {
    try { setConv(await api("/api/conversations", { method: "POST", json: {} })); await loadHistory(); closeMenu(); input.focus(); } catch (e) { toast(e.message, "error"); }
  }
  async function regenerate() {
    if (sending) return;
    const conv = N.state.conv;
    const bots = [...messagesEl.querySelectorAll(".msg.bot[data-id]")];
    const last = bots[bots.length - 1];
    if (last) last.remove();
    sending = true; sendBtn.disabled = true;
    try {
      const d = await withThinking(() => api("/api/chat/regenerate", { json: { conversation_id: conv.id } }));
      showReplies(d);
    } catch (e) { addMessage("bot", e.message, { error: true }); }
    finally { sending = false; sendBtn.disabled = false; input.focus(); }
  }
  N.chat = { newChat, clearHistory, openConversation, send: (t) => send(t), reload: () => openConversation(N.state.conv.id), loadHistory,
    setConv, addLocal: (t) => addMessage("bot", t) };

  // ---------------------------------------------------------- history list
  let histTimer;
  async function loadHistory() {
    const list = $("history-list"), q = $("history-search").value.trim();
    try {
      const d = await api("/api/conversations" + (q ? "?q=" + encodeURIComponent(q) : ""));
      clear(list);
      if (!d.groups.length) { list.append(N.empty(q ? "No matching chats" : "No chats yet")); return; }
      d.groups.forEach((g) => {
        list.append(el("div", { class: "hgroup", text: g.label }));
        g.items.forEach((c) => list.append(el("div", { class: "conv", dataset: { id: c.id } },
          el("button", { type: "button", class: "conv-title", text: c.title, title: c.title, onclick: () => openConversation(c.id) }),
          el("span", { class: "conv-btns" },
            el("button", { type: "button", class: "mini-icon", "aria-label": "Rename " + c.title, title: "Rename", onclick: () => renameConv(c) }, N.icon("pencil", 14)),
            el("button", { type: "button", class: "mini-icon", "aria-label": "Delete " + c.title, title: "Delete", onclick: () => deleteConv(c) }, N.icon("trash", 14))))));
      });
      highlightActive();
    } catch (e) { clear(list).append(N.errorBox(e.message, loadHistory)); }
  }
  function highlightActive() {
    document.querySelectorAll(".conv").forEach((n) => n.classList.toggle("active", N.state.conv && Number(n.dataset.id) === N.state.conv.id));
  }
  async function renameConv(c) {
    const name = await N.prompt({ title: "Rename conversation", label: "Name", value: c.title });
    if (!name) return;
    try { await api(`/api/conversations/${c.id}/rename`, { json: { title: name } }); if (N.state.conv.id === c.id) $("convo-title").textContent = name; loadHistory(); } catch (e) { toast(e.message, "error"); }
  }
  async function deleteConv(c) {
    if (!(await N.confirm({ title: "Delete this conversation?", message: `"${c.title}" will be deleted. Your documents, notes and progress are not affected.`, confirmText: "Delete", danger: true }))) return;
    try {
      await api("/api/conversations/" + c.id, { method: "DELETE" });
      if (N.state.conv.id === c.id) { const d = await api("/api/history"); setConv(d); }
      loadHistory();
    } catch (e) { toast(e.message, "error"); }
  }
  async function clearHistory() {
    const ok = await N.confirm({ title: "Clear all chat history?", message: "This action cannot be undone. Your documents, notes, quizzes, flashcards, study plans and progress are kept.", confirmText: "Clear History", danger: true });
    if (!ok) return false;
    try { setConv(await api("/api/history/clear", { json: {} })); loadHistory(); toast("Chat history cleared"); return true; } catch (e) { toast(e.message, "error"); return false; }
  }

  // --------------------------------------------------------- document bar
  function renderCtx() {
    const bar = $("ctxbar"), doc = N.state.conv && N.state.conv.document;
    if (!doc) { bar.hidden = true; clear(bar); return; }
    bar.hidden = false; clear(bar);
    const tab = (label, fn, on) => el("button", { type: "button", class: "tab" + (on ? " on" : ""), text: label, onclick: fn });
    bar.append(el("span", { class: "doc-name" }, N.icon("file", 15), doc.filename),
      el("div", { class: "tabs", role: "tablist" },
        tab("Overview", () => N.openPanel("documents", { open: doc.id })),
        tab("Chat", () => input.focus(), true),
        tab("Summary", () => N.openPanel("documents", { open: doc.id, summary: true })),
        tab("Quiz", () => N.openPanel("quiz", { document_id: doc.id })),
        tab("Flashcards", () => N.openPanel("flashcards", { document_id: doc.id }))),
      el("button", { type: "button", class: "mini", "aria-label": "Stop chatting with this document", onclick: () => setDocument(null) }, N.icon("close", 13), "Close document"));
  }
  async function setDocument(docId) {
    try {
      const d = await api(`/api/conversations/${N.state.conv.id}/context`, { json: { document_id: docId } });
      N.state.conv = d.conversation; renderCtx();
      if (docId) addMessage("bot", `You're now chatting with **${d.conversation.document.filename}**. I'll answer from this document first and cite the page or section. Ask a question, or say *summarise this document*.`);
    } catch (e) { toast(e.message, "error"); }
  }
  N.chat.setDocument = setDocument;

  // ---------------------------------------------------------------- send
  function showReplies(d) {
    d.replies.forEach((r, i) => {
      const last = i === d.replies.length - 1;
      addMessage("bot", r, { id: d.message_ids[i], sources: last ? d.sources : [], actions: last ? d.actions : [] });
    });
    if (N.state.settings.voice_output && d.replies.length) speak(d.replies[0]);
    (d.actions || []).filter((a) => a.type === "open_panel").forEach((a) => N.openPanel(a.panel, a));
  }
  async function sendRaw(text) {
    sending = true; sendBtn.disabled = true;
    try {
      const d = await withThinking(() => api("/api/chat", { json: { text, conversation_id: N.state.conv.id } }));
      showReplies(d);
      if (d.title) { $("convo-title").textContent = d.title; loadHistory(); } else highlightActive();
    } catch (e) { addMessage("bot", e.message, { error: true, retry: text }); }
    finally { sending = false; sendBtn.disabled = false; input.focus(); }
  }
  async function send(text) {
    text = text.trim();
    if (!text || sending) return;
    const sr = $("suggest-row"); if (sr) sr.remove();
    addMessage("user", text);
    await sendRaw(text);
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; autosize(); send(t); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 144) + "px"; }
  input.addEventListener("input", autosize);

  // ------------------------------------------------------- composer menu
  const plusBtn = $("plus-btn"), plusMenu = $("plus-menu");
  const docId = () => (N.state.conv && N.state.conv.document ? N.state.conv.document.id : null);
  const MENU = [
    ["paperclip", "Attach file", () => N.openPanel("upload")],
    ["file", "Ask about document", () => N.openPanel("documents", { choose: true })],
    ["pencil", "Create notes", () => N.openPanel("notes", { create: true })],
    ["quiz", "Generate quiz", () => N.openPanel("quiz", { document_id: docId() })],
    ["cards", "Create flashcards", () => N.openPanel("flashcards", { document_id: docId() })],
    ["calendar", "Create study plan", () => N.openPanel("study_plan")],
    ["chart", "Show progress", () => N.openPanel("progress")],
    ["clipboard", "Analyze past exam", () => N.openPanel("past_exams")],
    ["code", "Coding help", () => N.openPanel("coding")],
    ["mic", "Voice input", () => toggleMic()],
  ];
  MENU.forEach(([ico, label, fn]) => plusMenu.append(el("button", { type: "button", role: "menuitem", onclick: () => { closePlus(); fn(); } }, el("span", { class: "ico", "aria-hidden": "true" }, N.icon(ico, 17)), label)));
  function closePlus() { plusMenu.hidden = true; plusBtn.setAttribute("aria-expanded", "false"); }
  plusBtn.addEventListener("click", (e) => { e.stopPropagation(); plusMenu.hidden = !plusMenu.hidden; plusBtn.setAttribute("aria-expanded", String(!plusMenu.hidden)); if (!plusMenu.hidden) plusMenu.querySelector("button").focus(); });
  document.addEventListener("click", (e) => { if (!plusMenu.contains(e.target)) closePlus(); });
  plusMenu.addEventListener("keydown", (e) => {
    const items = [...plusMenu.querySelectorAll("button")], i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === "Escape") { closePlus(); plusBtn.focus(); }
  });

  // --------------------------------------------------------------- voice
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  const micBtn = $("mic-btn");
  function toggleMic() {
    if (!SR) return toast("Voice input isn't supported in this browser. You can still type.", "error");
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = N.state.settings.voice_lang || "en-GB"; rec.interimResults = true; rec.continuous = false;
    micBtn.classList.add("mic-on"); micBtn.setAttribute("aria-pressed", "true");
    rec.onresult = (e) => { input.value = [...e.results].map((r) => r[0].transcript).join(" "); autosize(); };
    rec.onerror = (e) => { if (e.error !== "aborted" && e.error !== "no-speech") toast("Voice input stopped: " + e.error, "error"); };
    rec.onend = () => { rec = null; micBtn.classList.remove("mic-on"); micBtn.setAttribute("aria-pressed", "false"); input.focus(); };
    try { rec.start(); } catch (_) { rec = null; }
  }
  micBtn.addEventListener("click", toggleMic);
  N.applyVoiceSettings = () => { micBtn.hidden = !(SR && N.state.settings.voice_input !== false); };

  // ------------------------------------------------------------- sidebar
  const histPanel = $("history-panel"), navHist = $("nav-history");
  navHist.addEventListener("click", () => {
    const open = histPanel.hidden; histPanel.hidden = !open;
    navHist.setAttribute("aria-expanded", String(open)); navHist.classList.toggle("active", open);
  });
  $("nav-new").addEventListener("click", newChat);
  $("nav-settings").addEventListener("click", () => { closeMenu(); N.openPanel("settings"); });
  $("history-search").addEventListener("input", () => { clearTimeout(histTimer); histTimer = setTimeout(loadHistory, 250); });
  $("search-btn").addEventListener("click", () => N.openPanel("search"));
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); N.openPanel("search"); } });

  const collapseKey = "nocturna-sidebar";
  function setCollapsed(c) { app.classList.toggle("collapsed", c); $("sb-open").hidden = !c; try { localStorage.setItem(collapseKey, c ? "1" : "0"); } catch (_) {} }
  $("sb-collapse").addEventListener("click", () => setCollapsed(true));
  $("sb-open").addEventListener("click", () => setCollapsed(false));
  function closeMenu() { app.classList.remove("menu-open"); }
  $("menu-btn").addEventListener("click", () => app.classList.toggle("menu-open"));
  $("scrim").addEventListener("click", closeMenu);
  try { if (localStorage.getItem(collapseKey) === "1" && window.innerWidth > 820) setCollapsed(true); } catch (_) {}

  // ---------------------------------------------------------------- start
  (async function init() {
    try {
      const [caps, settings] = await Promise.all([api("/api/capabilities"), api("/api/settings")]);
      N.state.caps = caps; N.state.settings = settings.settings;
      N.applyVoiceSettings(); N.applyTimestamps();
      setConv(await api("/api/history"));
      loadHistory();
      const due = await api("/api/due_reminders");
      (due.due || []).forEach((line) => addMessage("bot", "Reminder: " + line));
    } catch (e) {
      clear(messagesEl).append(N.errorBox(e.message, () => location.reload()));
    }
    input.focus();
  })();
})();
