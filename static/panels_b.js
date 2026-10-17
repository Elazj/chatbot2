/* Panels opened from inside the chat: study plan, progress, past exams, coding help, search and settings (General, Documents / RAG, User Profile / Account). */
(function () {
  const { el, api, toast, md, clear, field, select } = N;
  N.panels = N.panels || {};
  const pct = (v) => Math.round(v * 100);
  const lvl = (p) => (p >= 80 ? "ok" : p < 60 ? "bad" : "");
  const bar = (p, cls) => el("div", { class: "bar " + (cls || lvl(p)) }, el("i", { style: `width:${Math.max(0, Math.min(100, p))}%` }));

  // -------------------------------------------------------------- study plan
  N.panels.study_plan = async function () {
    const m = N.modal({ title: "Study plan", wide: true }), host = el("div"); m.body.append(host);
    async function home(planId) {
      await N.load(host, async (box) => {
        const plans = (await api("/api/study-plans")).plans;
        const id = planId || (plans[0] && plans[0].id);
        if (!id) return form(box);
        const sel = select(plans.map((p) => [p.id, `${p.title} · exam ${p.exam_date}`]), id);
        sel.addEventListener("change", () => home(Number(sel.value)));
        box.append(el("div", { class: "row between" }, field("Plan", sel), el("button", { type: "button", class: "ghost", text: "New plan", onclick: () => { clear(box); form(box); } })), el("div", { id: "plan-view" }));
        view((await api("/api/study-plans/" + id)).plan, box.querySelector("#plan-view"));
      });
    }
    function view(plan, host2) {
      clear(host2);
      const done = el("div", { class: "bar ok" }, el("i", { style: `width:${plan.completion}%` })), label = el("small", { text: plan.completion + "% complete" });
      host2.append(el("h3", { text: plan.title }), el("small", { text: `Exam ${plan.exam_date} · ${plan.hours_per_day} h/day · ${plan.level}` + (plan.struggling.length ? " · extra time: " + plan.struggling.join(", ") : "") }), done, label,
        el("div", { class: "row" },
          el("button", { type: "button", class: "ghost", text: "Adapt to my results", onclick: (e) => N.busy(e.target, "Adapting...", async () => { try { const r = await api(`/api/study-plans/${plan.id}/adapt`, { json: {} }); toast(r.weak_topics.length ? "Added time for: " + r.weak_topics.join(", ") : "Plan refreshed. No weak topics yet."); view(r.plan, host2); } catch (er) { toast(er.message, "error"); } }) }),
          el("button", { type: "button", class: "danger", text: "Delete plan", onclick: async () => { if (await N.confirm({ title: "Delete this plan?", message: "Your progress and quiz results are kept.", confirmText: "Delete", danger: true })) { await api("/api/study-plans/" + plan.id, { method: "DELETE" }); home(); } } })),
        el("p", { class: "note-box", text: "A plan is a starting point built from your topics and the time you have. It doesn't predict what the exam will contain." }));
      plan.days.forEach((d) => host2.append(el("div", { class: "day" }, el("h4", { text: `Day ${d.day} · ${d.date}` }), d.tasks.map((t) => el("label", { class: "task" + (t.done ? " done" : "") },
        el("input", { type: "checkbox", checked: !!t.done, onchange: async (e) => { try { const r = await api(`/api/study-tasks/${t.id}/toggle`, { json: {} }); e.target.parentElement.classList.toggle("done", r.done); done.firstChild.style.width = r.plan.completion + "%"; label.textContent = r.plan.completion + "% complete"; } catch (er) { toast(er.message, "error"); e.target.checked = !e.target.checked; } } }),
        el("span", { text: t.label }),
        t.kind === "quiz" && t.topic ? el("button", { type: "button", class: "mini", text: "Start", onclick: () => N.openPanel("quiz", { topic: t.topic }) }) : null,
        t.kind === "exam" ? el("button", { type: "button", class: "mini", text: "Open exam tools", onclick: () => N.openPanel("past_exams") }) : null)))));
    }
    async function form(box) {
      const courses = await N.loadCourses();
      // The student TYPES the course name or title. Courses they already have are offered as suggestions.
      const suggestions = el("datalist", { id: "plan-course-list" }, courses.map((c) => el("option", { value: c.name })));
      const course = el("input", { type: "text", maxlength: "80", list: "plan-course-list", autocomplete: "off", required: true,
        placeholder: "Type the course name or title, e.g. Database Systems II", "aria-label": "Course name or title" });
      const date = el("input", { type: "date", min: new Date(Date.now() + 864e5).toISOString().slice(0, 10) });
      const hours = el("input", { type: "number", min: "0.5", max: "12", step: "0.5", value: "2" });
      const level = select([["beginner", "Beginner: just starting"], ["intermediate", "Intermediate"], ["advanced", "Advanced: mostly revising"]], "intermediate");
      const topics = el("textarea", { rows: "3", placeholder: "Optional. One per line. Leave empty to use the section headings from this course's documents." });
      const struggle = el("input", { type: "text", placeholder: "Topics you find hard, separated by commas" });
      const split = (t) => t.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
      box.append(el("p", { text: "Tell me about your exam and I'll spread your topics over the days you have." }), field("Course name / title", course, "Required. A new course is added to your courses automatically; a name you already have is reused."), suggestions, field("Exam date", date),
        el("div", { class: "row" }, field("Study hours per day", hours), field("Current level", level)), field("Topics", topics), field("Topics I struggle with", struggle),
        el("div", { class: "row end" }, el("button", { type: "button", class: "primary", text: "Create study plan", onclick: (e) => N.busy(e.target, "Creating...", async () => {
          if (!course.value.trim()) { course.focus(); return toast("Type the course name or title.", "error"); }
          try { const r = await api("/api/study-plans", { json: { course_name: course.value, exam_date: date.value, hours_per_day: Number(hours.value), level: level.value, topics: split(topics.value), struggling: split(struggle.value) } }); home(r.plan.id); }
          catch (er) { toast(er.message, "error"); }
        }) })));
    }
    home();
  };

  // ---------------------------------------------------------------- progress
  N.panels.progress = async function (opts) {
    const m = N.modal({ title: "Your progress", wide: true }), host = el("div"); m.body.append(host);
    async function load(courseId) {
      await N.load(host, async (box) => {
        const courses = await N.loadCourses();
        const cSel = select([["", "All courses"]].concat(courses.map((c) => [c.id, c.name])), courseId || ""); cSel.addEventListener("change", () => load(cSel.value));
        const p = (await api("/api/progress" + (courseId ? "?course_id=" + courseId : ""))).progress;
        const tile = (b, s) => el("div", { class: "tile" }, el("b", { text: b }), el("small", { text: s }));
        box.append(field("Course", cSel), el("div", { class: "tiles" },
          tile(String(p.streak.current), `day streak (best ${p.streak.best})`), tile(p.average_score === null ? "–" : p.average_score + "%", "average quiz score"), tile(p.quizzes_taken, "quizzes taken"), tile(p.questions_answered, "questions answered"),
          tile(p.flashcards_reviewed, `flashcards reviewed (${p.flashcards_due} due)`), tile(`${p.documents_studied}/${p.documents}`, "documents studied"), tile(p.plan_completion === null ? "–" : p.plan_completion + "%", "study plan done"), tile(p.streak.study_days, "days studied")));
        if (p.recent_scores.length) box.append(el("div", { class: "section-title", text: "Recent quiz scores" }), el("div", { class: "spark", role: "img", "aria-label": "Recent quiz scores: " + p.recent_scores.join(", ") + " percent" }, p.recent_scores.map((s) => el("i", { style: `height:${Math.max(4, s)}%`, title: s + "%" }))));
        box.append(el("div", { class: "section-title", text: "Mastery by topic" }));
        if (!p.mastery.length) box.append(N.empty("No results yet", "Take a quiz or review some flashcards and your topics will show up here."));
        p.mastery.slice(0, 14).forEach((t) => { const v = pct(t.mastery); box.append(el("div", { class: "mastery" }, el("span", { text: t.topic, title: `${t.answers} answers` }), bar(v), el("span", { text: v + "%" }))); });
        if (p.mastery.length) box.append(el("small", { text: "Mastery = the share of your answers on that topic that were right. Topics need at least 2 answers to count as weak." }));
        if (p.recommendations.length) {
          box.append(el("div", { class: "section-title", text: "Recommended for you" }));
          p.recommendations.forEach((r) => box.append(el("div", { class: "card" }, el("h3", { text: `${r.topic} (${pct(r.mastery)}%)` }), el("div", { class: "card-actions" }, r.steps.map((s) => el("button", { type: "button", class: "ghost", text: s.label, onclick: () => N.stepAction(s, m) }))))));
        }
      });
    }
    load(opts.course_id);
  };

  // -------------------------------------------------------------- past exams
  N.panels.past_exams = async function (opts) {
    const m = N.modal({ title: "Past exam analyzer", wide: true, onClose: () => clearInterval(m.timer) }), host = el("div"); m.body.append(host);
    async function home() {
      await N.load(host, async (box) => {
        const docs = ready(await N.loadDocs()).filter((d) => d.kind === "past_exam");
        function ready(a) { return a.filter((d) => d.status === "ready"); }
        const checks = docs.map((d) => ({ d, c: el("input", { type: "checkbox", checked: opts.select ? d.id === opts.select : true }) }));
        const out = el("div");
        box.append(el("p", { text: "Upload past papers, then see which topics come up most across them. Papers work best when each question starts with 1., 2., 3. …" }),
          el("div", { class: "row between" }, el("strong", { text: docs.length ? "Your past papers" : "No past papers yet" }), el("button", { type: "button", class: "primary", text: "Upload past paper", onclick: () => { m.close(); N.openPanel("upload", { kind: "past_exam" }); } })),
          el("div", { class: "list" }, checks.map(({ d, c }) => el("label", { class: "card check" }, c, el("span", { text: d.filename })))),
          docs.length ? el("div", { class: "row" }, el("button", { type: "button", class: "primary", text: "Analyze selected papers", onclick: (e) => N.busy(e.target, "Analyzing...", async () => {
            const ids = checks.filter((x) => x.c.checked).map((x) => x.d.id);
            try { const r = await api("/api/past-exams/analyze", { json: { document_ids: ids } }); show(r.analysis_id, r.analysis, out); } catch (er) { toast(er.message, "error"); }
          }) })) : "", out);
      });
    }
    function show(analysisId, a, out) {
      clear(out).append(el("div", { class: "section-title", text: "Past Exam Analysis" }), el("p", { class: "note-box", text: a.note }),
        el("div", { class: "tiles" }, el("div", { class: "tile" }, el("b", { text: a.papers.length }), el("small", { text: "papers" })), el("div", { class: "tile" }, el("b", { text: a.question_count }), el("small", { text: "questions found" }))),
        el("div", { class: "section-title", text: "Frequently tested topics" }));
      if (!a.topics.length) out.append(N.empty("No repeating topics found", "Try adding more papers."));
      a.topics.forEach((t) => out.append(el("div", { class: "mastery" }, el("span", { text: t.term }), bar(t.percent, ""), el("span", { text: t.percent + "%", title: t.note }))));
      if (a.topics.length) out.append(el("small", { text: a.papers.length > 1 ? "Percent = share of the papers in which the topic appears." : "Percent = share of the questions that mention the topic." }));
      const d = a.difficulty; out.append(el("div", { class: "section-title", text: "Question mix" }), el("p", { text: `Easy ${d.easy || 0} · Medium ${d.medium || 0} · Hard ${d.hard || 0} (judged from the command word, e.g. Define = easy, Discuss = hard).` }));
      if (a.patterns.length) out.append(el("p", { text: "Most common command words: " + a.patterns.map((p) => `${p.verb} (${p.count})`).join(", ") }));
      if (a.repeated.length) { out.append(el("div", { class: "section-title", text: "Near-repeated questions" })); a.repeated.forEach((r) => out.append(el("div", { class: "card" }, el("small", { text: r.papers.join(" ↔ ") }), el("p", { text: r.a })))); }
      const count = el("input", { type: "number", min: "3", max: "40", value: "10" }), dur = el("input", { type: "number", min: "10", max: "240", value: "60" });
      out.append(el("div", { class: "section-title", text: "Mock exam" }), el("div", { class: "row" }, field("Questions", count), field("Minutes", dur)),
        el("button", { type: "button", class: "primary", text: "Generate Mock Exam", onclick: (e) => N.busy(e.target, "Building...", async () => {
          try { const q = await api("/api/past-exams/mock", { json: { analysis_id: analysisId, count: Number(count.value), duration_min: Number(dur.value) } }); m.close(); N.runQuizPanel(q); } catch (er) { toast(er.message, "error"); }
        }) }), el("small", { text: "Questions come from your papers, with a passage from your own material as the reference answer. You mark the written ones yourself." }));
    }
    home();
  };

  // ------------------------------------------------------------------ coding
  N.panels.coding = async function () {
    const m = N.modal({ title: "Coding help", wide: true });
    const lang = select([["python", "Python"], ["javascript", "JavaScript"], ["java", "Java"], ["c", "C / C++"], ["other", "Other"]], "python");
    const code = el("textarea", { rows: "10", placeholder: "Paste your code here", maxlength: "12000", spellcheck: "false", style: "font-family:ui-monospace,Consolas,monospace" });
    const err = el("textarea", { rows: "4", placeholder: "Paste the error message or traceback (optional)", maxlength: "4000", spellcheck: "false", style: "font-family:ui-monospace,Consolas,monospace" });
    const out = el("div");
    m.body.append(el("p", { class: "note-box", text: "Your code is only read, never run. Python gets a full check; for other languages I can explain common error messages. Logic errors are out of scope: Nocturna uses no AI model." }),
      field("Language", lang), field("Code", code), field("Error message", err),
      el("div", { class: "row end" }, el("button", { type: "button", class: "primary", text: "Analyze", onclick: (e) => N.busy(e.target, "Analyzing...", async () => {
        try { show((await api("/api/coding/analyze", { json: { code: code.value, error: err.value, language: lang.value } }))); } catch (er) { toast(er.message, "error"); }
      }) })), out);
    function show(r) {
      clear(out);
      const sec = (title, ...kids) => out.append(el("div", { class: "section-title", text: title }), ...kids);
      if (r.error) sec("What the error means", el("div", { class: "card" }, el("h3", { text: r.error.kind + (r.error.message ? ": " + r.error.message : "") }), el("p", { text: r.error.what }), r.error.line ? el("small", { text: "Look at line " + r.error.line }) : null, el("ul", {}, r.error.causes.map((c) => el("li", { text: c })))));
      const py = r.python;
      if (py && py.syntax_error) { const s = py.syntax_error; sec("Syntax error", el("div", { class: "card" }, el("p", { text: `Line ${s.line}${s.column ? ", column " + s.column : ""}: ${s.message}` }), md("```\n" + s.source + "\n```"), s.hint ? el("p", { class: "note-box", text: "Hint: " + s.hint }) : null)); }
      if (py && py.outline) {
        if (py.outline.length) sec("Structure", el("ul", {}, py.outline.map((o) => el("li", { text: o }))));
        sec("Things worth checking", py.issues.length ? el("ul", {}, py.issues.map((i) => el("li", { text: (i.line ? "Line " + i.line + ": " : "") + i.message }))) : el("p", { text: "I didn't spot any of the common mistakes I look for. That doesn't mean the logic is right." }));
        if (py.line_by_line.length) sec("Line by line", el("div", { class: "tablewrap" }, el("table", { class: "mdtable" }, el("tbody", {}, py.line_by_line.map((l) => el("tr", {}, el("td", { text: l.line }), el("td", {}, el("code", { text: l.code })), el("td", { text: l.explanation })))))));
        if (py.tests.length) sec("Test skeleton (fill in the expected results)", md("```python\nimport unittest\n\nclass TestMyCode(unittest.TestCase):\n" + py.tests.join("\n\n") + "\n```"));
        if (py.docstrings.length) sec("Docstring drafts", md("```python\n" + py.docstrings.join("\n\n") + "\n```"));
      }
      sec("Notes", el("ul", {}, r.notes.map((n) => el("li", { text: n }))));
    }
  };

  // ------------------------------------------------------------------ search
  N.panels.search = function (opts) {
    const m = N.modal({ title: "Search", wide: true });
    const input = el("input", { type: "search", placeholder: "Search chats, documents, notes, courses, quiz questions, flashcards… or type a command", "aria-label": "Search", value: opts.query || "", maxlength: "100" });
    const out = el("div");
    const COMMANDS = [["New chat", () => N.chat.newChat()], ["Upload study material", () => N.openPanel("upload")], ["My documents", () => N.openPanel("documents")], ["Generate a quiz", () => N.openPanel("quiz")], ["Flashcards", () => N.openPanel("flashcards")],
      ["Notes", () => N.openPanel("notes")], ["Create a study plan", () => N.openPanel("study_plan")], ["Show my progress", () => N.openPanel("progress")], ["Analyze past exams", () => N.openPanel("past_exams")], ["Coding help", () => N.openPanel("coding")], ["Settings", () => N.openPanel("settings")], ["User Profile", () => N.openPanel("settings", { tab: "account" })]];
    const item = (label, sub, fn) => el("button", { type: "button", class: "card", style: "text-align:left;cursor:pointer;width:100%;color:inherit", onclick: () => { m.close(); fn(); } }, el("h3", { text: label }), sub ? el("small", { text: sub }) : null);
    async function run() {
      const q = input.value.trim(); clear(out);
      const cmds = COMMANDS.filter(([l]) => !q || l.toLowerCase().includes(q.toLowerCase()));
      if (cmds.length) out.append(el("div", { class: "section-title", text: "Commands" }), el("div", { class: "list" }, cmds.map(([l, f]) => item(l, "", f))));
      if (q.length < 2) return;
      N.load(out.appendChild(el("div")), async (box) => {
        const r = (await api("/api/search?q=" + encodeURIComponent(q))).results;
        const groups = [["documents", "Documents", (x) => item(x.title, (x.section || "") + (x.page ? " · page " + x.page : "") + " · " + x.snippet, () => N.openPanel("documents", { open: x.document_id }))],
          ["conversations", "Conversations", (x) => item(x.title, "", () => N.chat.openConversation(x.id))], ["notes", "Notes", (x) => item(x.title, "", () => N.openPanel("notes", { open: x.id }))],
          ["courses", "Courses", (x) => item(x.title, "Open progress for this course", () => N.openPanel("progress", { course_id: x.id }))],
          ["quiz_questions", "Quiz questions", (x) => item(x.title.slice(0, 120), "Open this quiz", async () => { try { N.runQuizPanel(await api("/api/quizzes/" + x.quiz_id)); } catch (e) { toast(e.message, "error"); } })],
          ["flashcards", "Flashcards", (x) => item(x.title, x.back, () => N.openPanel("flashcards", {}))]];
        let any = false;
        groups.forEach(([k, label, mk]) => { if (r[k]) { any = true; box.append(el("div", { class: "section-title", text: label }), el("div", { class: "list" }, r[k].map(mk))); } });
        if (!any) box.append(N.empty("No matches", "Try different words."));
        box.append(el("small", { text: "Search matches words and TF-IDF similarity. It isn't an AI semantic search." }));
      });
    }
    let t; input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 250); });
    m.body.append(input, out); input.focus(); run();
  };

  // ---------------------------------------------------------------- settings
  // One dialog, three tabs:
  //   General            theme (light / dark / system) and timestamps
  //   Documents / RAG    how answers are retrieved from the student's documents
  //   User Profile / Account   profile, password, privacy & data, clear history, delete account
  const SETTINGS_TABS = [["general", "General", "sliders"], ["documents", "Documents / RAG", "file"], ["account", "User Profile / Account", "user"]];

  N.panels.settings = function (opts) {
    opts = opts || {};
    const m = N.modal({ title: "Settings", wide: true });
    const tabBar = el("div", { class: "stabs", role: "tablist", "aria-label": "Settings sections" });
    const pane = el("div", { class: "spane", role: "tabpanel" });
    m.body.append(tabBar, pane);
    let current = null;

    const show = (key) => {
      current = key;
      [...tabBar.children].forEach((b) => { const on = b.dataset.key === key; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; });
      clear(pane);
      ({ general: drawGeneral, documents: drawDocuments, account: drawAccount })[key](pane, m);
    };
    SETTINGS_TABS.forEach(([key, label, icon]) => tabBar.append(el("button", { type: "button", class: "stab", role: "tab", dataset: { key }, onclick: () => show(key) }, N.icon(icon, 16), el("span", { text: label }))));
    tabBar.addEventListener("keydown", (e) => {
      const i = SETTINGS_TABS.findIndex(([k]) => k === current);
      if (e.key === "ArrowRight") { e.preventDefault(); show(SETTINGS_TABS[(i + 1) % SETTINGS_TABS.length][0]); tabBar.children[(i + 1) % SETTINGS_TABS.length].focus(); }
      if (e.key === "ArrowLeft") { e.preventDefault(); const j = (i - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length; show(SETTINGS_TABS[j][0]); tabBar.children[j].focus(); }
    });
    show(["general", "documents", "account"].includes(opts.tab) ? opts.tab : "general");
  };
  // "User Profile" used to be its own dialog; it now lives in Settings.
  N.panels.profile = function () { return N.panels.settings({ tab: "account" }); };

  const save = async (key, val) => {
    try { const r = await api("/api/settings", { json: { [key]: val } }); N.state.settings = r.settings; N.applyVoiceSettings(); N.applyTimestamps(); toast("Saved"); }
    catch (e) { toast(e.message, "error"); }
  };
  const toggle = (key, label, hint) => {
    const c = el("input", { type: "checkbox", checked: !!N.state.settings[key], onchange: () => save(key, c.checked) });
    return el("div", { class: "setting" }, el("label", { class: "check" }, c, label), hint ? el("small", { text: hint }) : null);
  };
  const heading = (text) => el("div", { class: "section-title", text });

  // ------------------------------------------------------------ 1. General
  function drawGeneral(pane) {
    const themeLabels = [["light", "Light"], ["dark", "Dark"], ["system", "System"]];
    const seg = el("div", { class: "seg", role: "radiogroup", "aria-label": "Theme" }, themeLabels.map(([t, label]) => el("button", {
      type: "button", role: "radio", "aria-checked": String(window.nocturnaTheme.get() === t), class: window.nocturnaTheme.get() === t ? "on" : "", text: label,
      onclick: () => { window.nocturnaTheme.set(t); [...seg.children].forEach((b, i) => { const on = themeLabels[i][0] === t; b.classList.toggle("on", on); b.setAttribute("aria-checked", String(on)); }); },
    })));
    pane.append(
      heading("Appearance"),
      field("Theme", seg, "Light is white, Dark is black, and System follows your device's setting. Saved in this browser."),
      heading("Messages"),
      toggle("show_timestamps", "Show timestamps", "Shows the time under every message (and the date for older ones)."));
  }

  // --------------------------------------------------- 2. Documents / RAG
  function drawDocuments(pane, m) {
    const S = N.state.settings;
    const passages = select([["1", "1 passage"], ["2", "2 passages"], ["3", "3 passages (default)"], ["4", "4 passages"], ["5", "5 passages"]], String(S.rag_passages));
    passages.addEventListener("change", () => save("rag_passages", Number(passages.value)));
    const strict = select([["relaxed", "Relaxed: show loosely related passages"], ["balanced", "Balanced (default)"], ["strict", "Strict: only close matches"]], S.rag_strictness);
    strict.addEventListener("change", () => save("rag_strictness", strict.value));

    pane.append(
      el("p", { class: "note-box", text: "RAG means retrieval-augmented answers: when you ask about your documents, Nocturna searches them with TF-IDF and shows the best matching passages with their page and section. No AI or language model is used, and nothing leaves this server." }),
      heading("How answers are retrieved"),
      field("Passages per answer", passages, "How many matching passages are retrieved for each question."),
      field("Search strictness", strict, "Strict shows fewer, closer matches. Relaxed shows more, but some may be only loosely related."),
      toggle("show_sources", "Show sources under answers", "Lists the document, page and section each answer came from."),
      toggle("rag_fallback", "Search my documents when UTG information has no answer", "Questions are answered from the UTG knowledge base first. Turn this off to keep your documents out of general questions (a document opened in the chat is always searched)."));

    const lib = el("div");
    pane.append(heading("Document library"), lib);
    const drawLib = () => N.load(lib, async (box) => {
      const docs = (await api("/api/documents")).documents;
      const ready = docs.filter((d) => d.status === "ready");
      const passagesTotal = ready.reduce((n, d) => n + (d.chunk_count || 0), 0);
      box.append(el("div", { class: "tiles" },
        el("div", { class: "tile" }, el("b", { text: String(docs.length) }), el("small", { text: "documents" })),
        el("div", { class: "tile" }, el("b", { text: String(ready.length) }), el("small", { text: "indexed and searchable" })),
        el("div", { class: "tile" }, el("b", { text: String(passagesTotal) }), el("small", { text: "passages indexed" }))));
      if (!docs.length) box.append(N.empty("No documents yet", "Upload PDF, Word, PowerPoint, text or Markdown files to chat with them."));
      else {
        box.append(el("div", { class: "list" }, docs.slice(0, 8).map((d) => el("div", { class: "row between card" },
          el("span", { text: d.filename + (d.kind === "past_exam" ? " (past paper)" : "") }),
          el("small", { text: d.status === "ready" ? (d.chunk_count || 0) + " passages" : d.status === "failed" ? "Failed" : "Processing" })))));
        if (docs.length > 8) box.append(el("small", { text: "and " + (docs.length - 8) + " more. Open Manage documents to see them all." }));
      }
      const wipeDocs = async () => {
        if (!(await N.confirm({ title: "Delete all documents?", message: "Every uploaded document and its indexed passages will be deleted. Notes, quizzes and chats are kept. This can't be undone.", confirmText: "Delete", danger: true, requireText: "DELETE" }))) return;
        try { await api("/api/data/delete", { json: { what: "documents", confirm: "DELETE" } }); toast("Documents deleted"); drawLib(); } catch (e) { toast(e.message, "error"); }
      };
      box.append(el("div", { class: "row" },
        el("button", { type: "button", class: "ghost", text: "Upload a document", onclick: () => { m.close(); N.openPanel("upload"); } }),
        el("button", { type: "button", class: "ghost", text: "Manage documents", onclick: () => { m.close(); N.openPanel("documents"); } }),
        el("button", { type: "button", class: "danger", text: "Delete all my documents", disabled: !docs.length, onclick: wipeDocs })));
    });
    drawLib();

    // courses group documents, so they are managed next to them
    const list = el("div", { class: "list" }), newName = el("input", { type: "text", placeholder: "New course, e.g. Database Systems II", maxlength: "80", "aria-label": "New course name" });
    const drawCourses = async () => {
      const cs = await N.loadCourses(); clear(list);
      if (!cs.length) list.append(N.empty("No courses yet", "Add your courses, then pick one when you upload material or make a study plan."));
      cs.forEach((c) => list.append(el("div", { class: "row between card" }, el("span", { text: c.name + (c.documents ? ` (${c.documents} document${c.documents > 1 ? "s" : ""})` : "") }), el("span", {},
        el("button", { type: "button", class: "mini", text: "Rename", onclick: async () => { const n = await N.prompt({ title: "Rename course", label: "Course name", value: c.name }); if (n) { try { await api(`/api/courses/${c.id}/rename`, { json: { name: n } }); drawCourses(); } catch (e) { toast(e.message, "error"); } } } }),
        el("button", { type: "button", class: "mini", text: "Delete", onclick: async () => { if (await N.confirm({ title: "Delete this course?", message: "Its documents stay in your library, just without a course.", confirmText: "Delete", danger: true })) { try { await api("/api/courses/" + c.id, { method: "DELETE" }); drawCourses(); } catch (e) { toast(e.message, "error"); } } } })))));
    };
    pane.append(heading("My courses"), list, el("div", { class: "row" }, el("div", { class: "grow" }, newName),
      el("button", { type: "button", class: "ghost", text: "Add course", onclick: async () => { try { await api("/api/courses", { json: { name: newName.value } }); newName.value = ""; drawCourses(); } catch (e) { toast(e.message, "error"); } } })));
    drawCourses().catch((e) => toast(e.message, "error"));
  }

  // ------------------------------------------- 3. User Profile / Account
  async function drawAccount(pane, m) {
    const host = el("div"); pane.append(host);
    await N.load(host, async (box) => {
      const { profile: p } = await api("/api/profile");
      const name = el("input", { type: "text", value: p.full_name, maxlength: "80" });
      const goals = el("textarea", { rows: "3", maxlength: "500", placeholder: "e.g. Pass Database Systems II with a B" });
      const style = el("input", { type: "text", value: p.learning_style, maxlength: "100", placeholder: "e.g. short summaries, lots of practice questions" });
      goals.value = p.study_goals;
      box.append(heading("Profile"), field("Name", name), field("Email", el("input", { type: "email", value: p.email, readonly: true, disabled: true }), "Your email is your login and can't be changed here."),
        field("Study goals", goals), field("Learning preferences", style),
        el("div", { class: "row end" }, el("button", { type: "button", class: "primary", text: "Save profile", onclick: (e) => N.busy(e.target, "Saving...", async () => {
          try { await api("/api/profile", { json: { full_name: name.value, study_goals: goals.value, learning_style: style.value } }); toast("Profile saved"); } catch (er) { toast(er.message, "error"); }
        }) })));

      // password
      const cur = el("input", { type: "password", autocomplete: "current-password" }), nw = el("input", { type: "password", autocomplete: "new-password", minlength: "8" });
      box.append(heading("Password"), el("div", { class: "row" }, el("div", { class: "grow" }, field("Current password", cur)), el("div", { class: "grow" }, field("New password (8+ characters)", nw))),
        el("button", { type: "button", class: "ghost", text: "Change password", onclick: async () => { try { await api("/api/profile/password", { json: { current: cur.value, new: nw.value } }); cur.value = nw.value = ""; toast("Password changed"); } catch (e) { toast(e.message, "error"); } } }));

      // privacy & data
      const wipe = (what, label, message) => el("button", { type: "button", class: "danger", text: label, onclick: async () => {
        if (!(await N.confirm({ title: label + "?", message: message + " This can't be undone.", confirmText: "Delete", danger: true, requireText: "DELETE" }))) return;
        try { await api("/api/data/delete", { json: { what, confirm: "DELETE" } }); toast("Deleted"); } catch (e) { toast(e.message, "error"); }
      } });
      box.append(heading("Privacy and data"),
        el("p", { text: "Your chats, documents, notes, quizzes, flashcards and progress belong to your account and are not visible to other students. Passwords are stored only as salted hashes. Documents are stored as extracted text only, never as the original file, and nothing is sent to any AI service." }),
        el("div", { class: "row" }, el("a", { class: "action-btn", href: "/api/export", download: "nocturna-my-data.json" }, N.icon("download", 16), "Download my data")),
        el("div", { class: "row" }, wipe("notes", "Delete all my notes", "All your notes will be deleted."), wipe("learning", "Delete quizzes, flashcards and progress", "Your quizzes, flashcards, study plans and progress will be deleted.")));

      // clear history
      box.append(heading("Chat history"), el("p", { text: "Deletes every conversation. Your documents, notes, quizzes, flashcards, plans and progress are kept." }),
        el("div", { class: "row" }, el("button", { type: "button", class: "danger", text: "Clear chat history", onclick: async () => { if (await N.chat.clearHistory()) m.close(); } })));

      // account
      box.append(heading("Account"), el("div", { class: "row" },
        el("button", { type: "button", class: "ghost", text: "Log out", onclick: () => document.getElementById("logout-form").submit() }),
        el("button", { type: "button", class: "danger", text: "Delete my account", onclick: () => deleteAccount() })));
      function deleteAccount() {
        const dm = N.modal({ title: "Delete your account?" }), pw = el("input", { type: "password", autocomplete: "current-password" }), conf = el("input", { type: "text", autocomplete: "off" });
        dm.body.append(el("p", { text: "This permanently deletes your account, chats, documents, notes, quizzes, flashcards and plans. It can't be undone." }), field("Your password", pw), field("Type DELETE to confirm", conf),
          el("div", { class: "row end" }, el("button", { type: "button", class: "ghost", text: "Cancel", onclick: () => dm.close() }), el("button", { type: "button", class: "danger", text: "Delete everything", onclick: async () => {
            if (conf.value.trim() !== "DELETE") return toast("Type DELETE to confirm.", "error");
            try { await api("/api/data/delete", { json: { what: "account", confirm: "DELETE", password: pw.value } }); window.location.href = "/login"; } catch (e) { toast(e.message, "error"); }
          } })));
      }
    });
  }
})();