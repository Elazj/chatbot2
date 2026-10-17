/* Panels opened from inside the chat: upload, documents, notes, quizzes/exams, flashcards. */
(function () {
  const { el, api, toast, md, clear, field, select } = N;
  N.panels = N.panels || {};
  const MAX_BYTES = 15 * 1024 * 1024, EXT = [".pdf", ".docx", ".pptx", ".txt", ".md", ".markdown"];

  const courseOptions = (courses, none) => [["", none || "No course"]].concat(courses.map((c) => [c.id, c.name]));
  N.loadCourses = async () => (N.state.courses = (await api("/api/courses")).courses);
  N.loadDocs = async () => (N.state.docs = (await api("/api/documents")).documents);
  const ready = (docs, kind) => docs.filter((d) => d.status === "ready" && (!kind || d.kind === kind));
  const stageLabel = (d) => (d.status === "ready" ? "✓ Ready" : d.status === "failed" ? "Failed" : d.stage);

  // ------------------------------------------------------------------ upload
  function xhrUpload(file, kind, courseId, onProgress) {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      fd.append("file", file); fd.append("kind", kind); if (courseId) fd.append("course_id", courseId);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/documents");
      xhr.setRequestHeader("X-CSRF-Token", document.querySelector('meta[name="csrf-token"]').content);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((100 * e.loaded) / e.total));
      xhr.onload = () => { let d = {}; try { d = JSON.parse(xhr.responseText); } catch (_) {} xhr.status < 300 ? resolve(d.document) : reject(new Error(d.error || (xhr.status === 413 ? "That file is too large." : "Upload failed."))); };
      xhr.onerror = () => reject(new Error("Can't reach Nocturna. Check that it is still running."));
      xhr.send(fd);
    });
  }

  N.panels.upload = async function (opts) {
    const m = N.modal({ title: "Attach study material" });
    let courses = [];
    try { courses = await N.loadCourses(); } catch (_) {}
    const courseSel = select(courseOptions(courses), opts.course_id || "");
    const kindSel = select([["material", "Study material (notes, slides, textbook)"], ["past_exam", "Past exam paper"]], opts.kind || "material");
    const rows = el("div", { class: "list" });
    const fileInput = el("input", { type: "file", multiple: true, hidden: true, accept: EXT.join(",") });
    const drop = el("div", { class: "drop", tabindex: "0", role: "button", "aria-label": "Drop files here or browse" },
      el("div", { class: "big", "aria-hidden": "true" }, N.icon("file", 40)), el("p", { text: "Drag & drop your document here" }),
      el("button", { type: "button", class: "primary", text: "Browse Files", onclick: () => fileInput.click() }),
      el("p", { class: "hint", text: "PDF • DOCX • PPTX • TXT • Markdown (up to 15 MB)" }));
    m.body.append(field("Course (optional)", courseSel), field("Type", kindSel), drop, fileInput, rows,
      el("p", { class: "note-box", text: "Your files are read on this server and only their text is kept. They're private to your account." }));

    const finished = [];
    function addFile(file) {
      const row = el("div", { class: "card" });
      const status = el("small", { text: "Uploading..." }), barFill = el("i"), actions = el("div", { class: "card-actions" });
      row.append(el("h3", { text: file.name }), status, el("div", { class: "bar", style: "margin:.4rem 0" }, barFill), actions);
      rows.append(row);
      const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
      if (!EXT.includes(ext)) return fail("That file type isn't supported. Use PDF, DOCX, PPTX, TXT or Markdown.");
      if (file.size > MAX_BYTES) return fail("That file is larger than 15 MB.");
      if (!file.size) return fail("That file is empty.");
      run();
      function fail(msg) {
        status.textContent = msg; barFill.parentElement.classList.add("bad"); barFill.style.width = "100%"; clear(actions);
        actions.append(el("button", { type: "button", class: "ghost", text: "Try Again", onclick: () => { row.remove(); addFile(file); } }));
      }
      async function run() {
        try {
          const doc = await xhrUpload(file, kindSel.value, courseSel.value, (p) => { barFill.style.width = p + "%"; status.textContent = "Uploading... " + p + "%"; });
          barFill.style.width = "100%";
          for (;;) {
            const d = (await api("/api/documents/" + doc.id)).document;
            status.textContent = stageLabel(d);
            if (d.status === "ready") {
              barFill.parentElement.classList.add("ok");
              status.textContent = `✓ Ready · ${d.chunk_count} passages indexed`;
              finished.push(d);
              if (d.kind === "material") actions.append(el("button", { type: "button", class: "primary", text: "Chat with this document", onclick: () => { m.close(); N.chat.setDocument(d.id); } }),
                el("button", { type: "button", class: "ghost", text: "Summarize", onclick: () => { m.close(); N.openPanel("documents", { open: d.id, summary: true }); } }));
              else actions.append(el("button", { type: "button", class: "primary", text: "Analyze past exam", onclick: () => { m.close(); N.openPanel("past_exams", { select: d.id }); } }));
              return;
            }
            if (d.status === "failed") return fail(d.error || "Unable to process this document.");
            await new Promise((r) => setTimeout(r, 900));
          }
        } catch (e) { fail(e.message); }
      }
    }
    const take = (list) => [...list].forEach(addFile);
    fileInput.addEventListener("change", () => { take(fileInput.files); fileInput.value = ""; });
    ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => take(e.dataTransfer.files));
    drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
    if (opts.file) take([opts.file]);
  };

  // --------------------------------------------------------------- documents
  N.panels.documents = async function (opts) {
    const m = N.modal({ title: opts.choose ? "Choose a document to chat with" : "Documents", wide: true });
    let pollTimer = null;
    m.overlay.addEventListener("remove", () => clearTimeout(pollTimer));
    const origClose = m.close; m.close = () => { clearTimeout(pollTimer); origClose(); };
    const host = el("div"); m.body.append(host);

    async function showList() {
      m.setTitle(opts.choose ? "Choose a document to chat with" : "Documents");
      await N.load(host, async (box) => {
        const [docs, courses] = await Promise.all([N.loadDocs(), N.loadCourses()]);
        const cSel = select([["", "All courses"]].concat(courses.map((c) => [c.id, c.name])), "");
        const list = el("div", { class: "list" });
        const draw = () => {
          clear(list);
          const shown = docs.filter((d) => !cSel.value || String(d.course_id) === cSel.value);
          if (!shown.length) list.append(N.empty("No documents yet", "Use Upload to add notes, slides or a textbook."));
          shown.forEach((d) => list.append(docCard(d)));
          if (shown.some((d) => d.status === "processing")) { clearTimeout(pollTimer); pollTimer = setTimeout(async () => { if (!host.isConnected) return; docs.splice(0, docs.length, ...(await N.loadDocs())); draw(); }, 1500); }
        };
        const docCard = (d) => el("div", { class: "card" },
          el("h3", { text: d.filename + (d.kind === "past_exam" ? " (past paper)" : "") }),
          el("small", {}, d.kind === "past_exam" ? "Past exam · " : "", d.course_name ? d.course_name + " · " : "", d.status === "ready" ? `${d.chunk_count} passages` : "", " "),
          el("span", { class: "badge " + (d.status === "ready" ? "ok" : d.status === "failed" ? "bad" : ""), text: stageLabel(d) }),
          d.error ? el("p", { class: "note-box", text: d.error }) : null,
          d.status === "ready" ? el("div", { class: "card-actions" },
            el("button", { type: "button", class: opts.choose ? "primary" : "ghost", text: "Ask questions", onclick: () => { m.close(); N.chat.setDocument(d.id); } }),
            el("button", { type: "button", class: "ghost", text: "Open", onclick: () => showDoc(d.id) }),
            el("button", { type: "button", class: "ghost", text: "Summarize", onclick: () => showDoc(d.id, true) }),
            el("button", { type: "button", class: "ghost", text: "Generate Quiz", onclick: () => N.openPanel("quiz", { document_id: d.id }) }),
            el("button", { type: "button", class: "ghost", text: "Generate Flashcards", onclick: () => N.openPanel("flashcards", { document_id: d.id, generate: true }) }),
            el("button", { type: "button", class: "ghost", text: "Create Notes", onclick: async (e) => N.busy(e.target, "Creating...", async () => { try { await api(`/api/documents/${d.id}/notes`, { json: {} }); toast("Notes saved"); } catch (er) { toast(er.message, "error"); } }) }),
            el("button", { type: "button", class: "danger", text: "Delete", onclick: () => del(d) })) :
            d.status === "failed" ? el("div", { class: "card-actions" }, el("button", { type: "button", class: "danger", text: "Remove", onclick: () => del(d) })) : null);
        async function del(d) {
          if (!(await N.confirm({ title: "Delete this document?", message: `"${d.filename}" and its indexed text will be deleted. Notes, quizzes and flashcards you made from it are kept.`, confirmText: "Delete", danger: true }))) return;
          try { await api("/api/documents/" + d.id, { method: "DELETE" }); if (N.state.conv && N.state.conv.document && N.state.conv.document.id === d.id) N.chat.reload(); showList(); } catch (e) { toast(e.message, "error"); }
        }
        cSel.addEventListener("change", draw);
        box.append(el("div", { class: "row between" }, field("Course", cSel), el("button", { type: "button", class: "primary", text: "Upload", onclick: () => { m.close(); N.openPanel("upload"); } })), list);
        draw();
      });
    }

    async function showDoc(id, summary) {
      N.load(host, async (box) => {
        const d = await api("/api/documents/" + id);
        m.setTitle(d.document.filename);
        const tabs = el("div", { class: "tabs" }), pane = el("div");
        const back = el("button", { type: "button", class: "ghost", text: "← All documents", onclick: showList });
        const actions = el("div", { class: "row" },
          el("button", { type: "button", class: "primary", text: "Ask questions", onclick: () => { m.close(); N.chat.setDocument(id); } }),
          el("button", { type: "button", class: "ghost", text: "Generate Quiz", onclick: () => N.openPanel("quiz", { document_id: id }) }),
          el("button", { type: "button", class: "ghost", text: "Generate Flashcards", onclick: () => N.openPanel("flashcards", { document_id: id, generate: true }) }));
        box.append(back, actions, tabs, pane);
        const setTab = (name) => { [...tabs.children].forEach((t) => t.classList.toggle("on", t.dataset.n === name)); clear(pane); name === "overview" ? overview() : name === "text" ? text() : summaryTab(); };
        [["overview", "Overview"], ["summary", "Summary"], ["text", "Text"]].forEach(([n, l]) => tabs.append(el("button", { type: "button", class: "tab", dataset: { n }, text: l, onclick: () => setTab(n) })));
        function overview() {
          pane.append(el("div", { class: "tiles" }, el("div", { class: "tile" }, el("b", { text: d.document.pages || "–" }), el("small", { text: "pages / slides" })), el("div", { class: "tile" }, el("b", { text: d.document.chunk_count }), el("small", { text: "passages indexed" })), el("div", { class: "tile" }, el("b", { text: d.sections.length }), el("small", { text: "sections found" }))));
          pane.append(el("div", { class: "section-title", text: "Sections" }));
          if (!d.sections.length) pane.append(N.empty("No section headings found", "You can still ask questions about the whole document."));
          d.sections.forEach((s) => pane.append(el("div", { class: "row between" }, el("span", { text: s.section + (s.page ? " · page " + s.page : "") }),
            el("button", { type: "button", class: "mini", text: "Ask about this", onclick: () => { m.close(); N.chat.setDocument(id).then(() => N.chat.send("Explain " + s.section)); } }))));
        }
        function summaryTab() {
          const out = el("div", { class: "note-box" }), modes = [["quick", "Quick summary"], ["detailed", "Detailed summary"], ["chapter", "Chapter summary"], ["exam", "Exam summary"]];
          const bar = el("div", { class: "seg" }); let lastMd = "";
          modes.forEach(([k, l]) => bar.append(el("button", { type: "button", text: l, onclick: async (e) => {
            [...bar.children].forEach((b) => b.classList.toggle("on", b === e.target));
            N.load(out, async (o) => { const r = await api(`/api/documents/${id}/summary`, { json: { mode: k } }); lastMd = r.markdown; o.append(md(r.markdown),
              el("div", { class: "row" }, el("button", { type: "button", class: "ghost", text: "Save to notes", onclick: async () => { try { await api("/api/notes", { json: { content: lastMd, title: l + ": " + d.document.filename, document_id: id } }); toast("Saved to notes"); } catch (er) { toast(er.message, "error"); } } }))); });
          } })));
          pane.append(el("p", { text: "These summaries pick the most important sentences from your document. They don't rewrite it." }), bar, out);
          if (summary) bar.firstChild.click();
        }
        async function text() {
          let off = 0; const holder = el("div"), more = el("button", { type: "button", class: "ghost", text: "Show more" });
          const loadMore = async () => { const t = await api(`/api/documents/${id}/text?offset=${off}`); t.chunks.forEach((c) => holder.append(el("div", { class: "card" }, el("small", { text: (c.section || "") + (c.page ? " · page " + c.page : "") }), el("p", { text: c.text })))); off = t.next_offset; more.hidden = off === null; };
          pane.append(holder, more); more.addEventListener("click", () => N.busy(more, "Loading...", loadMore)); await loadMore();
        }
        setTab(summary ? "summary" : "overview");
      });
    }
    if (opts.open) showDoc(opts.open, opts.summary); else showList();
  };

  // ------------------------------------------------------------------- notes
  N.panels.notes = async function (opts) {
    const m = N.modal({ title: "Notes", drawer: true }), host = el("div"); m.body.append(host);
    async function list() {
      m.setTitle("Notes");
      await N.load(host, async (box) => {
        const courses = await N.loadCourses();
        const q = el("input", { type: "search", placeholder: "Search notes", "aria-label": "Search notes" });
        const cSel = select([["", "All courses"]].concat(courses.map((c) => [c.id, c.name])), "");
        const out = el("div", { class: "list" });
        const draw = async () => {
          N.load(out, async (o) => {
            const r = await api(`/api/notes?q=${encodeURIComponent(q.value)}${cSel.value ? "&course_id=" + cSel.value : ""}`);
            if (!r.notes.length) return o.append(N.empty(q.value ? "No notes match" : "No notes yet", "Create one, or use “Save to notes” on any reply."));
            r.notes.forEach((n) => o.append(el("button", { type: "button", class: "card", style: "text-align:left;cursor:pointer;color:inherit;width:100%", onclick: () => edit(n.id) },
              el("h3", { text: n.title }), el("small", { text: N.fmtDate(n.updated_at) + " · " + n.content.slice(0, 90) }))));
          });
        };
        let t; q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(draw, 250); }); cSel.addEventListener("change", draw);
        box.append(el("div", { class: "row" }, el("div", { class: "grow" }, q), el("button", { type: "button", class: "primary", text: "New note", onclick: () => edit(null) })), field("Course", cSel), out);
        draw();
      });
    }
    async function edit(id) {
      N.load(host, async (box) => {
        const [courses, note] = await Promise.all([N.loadCourses(), id ? api("/api/notes/" + id) : Promise.resolve({ note: { title: "", content: "", course_id: null, document_id: opts.document_id || null } })]);
        const n = note.note;
        m.setTitle(id ? "Edit note" : "New note");
        const title = el("input", { type: "text", value: n.title === "Untitled note" ? "" : n.title, maxlength: "80", placeholder: "Title" });
        const body = el("textarea", { rows: "10", placeholder: "Write your note. Tip: lines like “Term: definition” can become flashcards.", maxlength: "20000" }); body.value = n.content;
        const cSel = select(courseOptions(courses), n.course_id || ""), preview = el("div", { class: "note-box", hidden: true }), result = el("div");
        const save = async (btn) => N.busy(btn, "Saving...", async () => {
          try {
            const payload = { title: title.value, content: body.value, course_id: cSel.value || null, document_id: n.document_id };
            const r = id ? await api("/api/notes/" + id, { json: payload }) : await api("/api/notes", { json: payload });
            toast("Note saved"); return r.note;
          } catch (e) { toast(e.message, "error"); }
        });
        const saveBtn = el("button", { type: "button", class: "primary", text: "Save", onclick: async (e) => { const r = await save(e.target); if (r && !id) edit(r.id); } });
        const needSaved = (fn) => async (e) => { if (!id) return toast("Save the note first.", "error"); await N.busy(e.target, "Working...", () => fn().catch((er) => toast(er.message, "error"))); };
        box.append(el("button", { type: "button", class: "ghost", text: "← All notes", onclick: list }), field("Title", title), field("Course", cSel), field("Note (Markdown)", body),
          el("div", { class: "row" }, saveBtn,
            el("button", { type: "button", class: "ghost", text: "Preview", onclick: (e) => { preview.hidden = !preview.hidden; clear(preview).append(md(body.value || "_Nothing to preview_")); e.target.textContent = preview.hidden ? "Preview" : "Hide preview"; } }),
            id ? el("button", { type: "button", class: "danger", text: "Delete", onclick: async () => { if (await N.confirm({ title: "Delete this note?", message: "This can't be undone.", confirmText: "Delete", danger: true })) { await api("/api/notes/" + id, { method: "DELETE" }); toast("Note deleted"); list(); } } }) : null),
          preview,
          el("div", { class: "section-title", text: "Turn this note into…" }),
          el("div", { class: "row" },
            el("button", { type: "button", class: "ghost", text: "Summary", onclick: needSaved(async () => { const r = await api(`/api/notes/${id}/summarize`, { json: {} }); clear(result).append(el("div", { class: "note-box" }, md(r.markdown))); }) }),
            el("button", { type: "button", class: "ghost", text: "Flashcards", onclick: needSaved(async () => { const r = await api(`/api/notes/${id}/flashcards`, { json: {} }); toast(`Created ${r.created} flashcards`); }) }),
            el("button", { type: "button", class: "ghost", text: "Quiz", onclick: needSaved(async () => { const q = await api(`/api/notes/${id}/quiz`, { json: { count: 8 } }); m.close(); N.runQuizPanel(q); }) })),
          result);
        title.focus();
      });
    }
    if (opts.open) edit(opts.open); else if (opts.create) edit(null); else list();
  };

  // ------------------------------------------------------------ quiz & exam
  N.runQuizPanel = (data) => { const m = N.modal({ title: data.quiz.title, wide: true, onClose: () => clearInterval(m.timer) }); m.timer = null; runQuiz(m, data); };

  function runQuiz(m, data) {
    clearInterval(m.timer);
    const { quiz, questions } = data, exam = quiz.kind === "mock_exam";
    let idx = 0, submitted = false; const answers = {}, flags = new Set();
    let endAt = quiz.duration_min ? Date.now() + quiz.duration_min * 60000 : null;
    m.setTitle(quiz.title);
    const timer = el("span", { class: "timer", "aria-live": "off" }), body = m.body;
    const draw = () => {
      clear(body);
      const q = questions[idx];
      const head = el("div", { class: "qhead" }, el("span", { text: `Question ${idx + 1} of ${questions.length}` }), endAt ? timer : null);
      const opts = el("div");
      if (q.qtype === "mcq" || q.qtype === "tf") q.options.forEach((o) => { const sel = answers[q.id] === o; opts.append(el("label", { class: "opt" + (sel ? " sel" : "") }, el("input", { type: "radio", name: "q" + q.id, checked: sel, onchange: () => { answers[q.id] = o; draw(); } }), el("span", { text: o }))); });
      else { const ta = el("textarea", { rows: "5", placeholder: q.qtype === "open" ? "Write your answer, as you would in the exam…" : "Your answer…" }); ta.value = answers[q.id] || ""; ta.addEventListener("input", () => { answers[q.id] = ta.value; paintNav(); }); opts.append(ta); }
      const nav = el("div", { class: "qnav", role: "group", "aria-label": "Question navigator" });
      function paintNav() { clear(nav); questions.forEach((x, i) => nav.append(el("button", { type: "button", class: [answers[x.id] ? "answered" : "", flags.has(x.id) ? "flag" : "", i === idx ? "cur" : ""].join(" "), "aria-label": `Question ${i + 1}${flags.has(x.id) ? ", flagged" : ""}${answers[x.id] ? ", answered" : ""}`, text: i + 1, onclick: () => { idx = i; draw(); } }))); }
      paintNav();
      body.append(head, q.topic ? el("div", { class: "qtopic", text: q.topic }) : "", el("div", { class: "qprompt" }, ...(q.qtype === "tf" ? ["True or false: ", q.prompt] : [q.prompt])), opts, nav,
        el("div", { class: "row between" },
          el("div", { class: "row", style: "margin:0" },
            el("button", { type: "button", class: "ghost", text: "← Previous", disabled: idx === 0, onclick: () => { idx--; draw(); } }),
            el("button", { type: "button", class: "ghost", text: flags.has(q.id) ? "Unflag" : "Flag", onclick: () => { flags.has(q.id) ? flags.delete(q.id) : flags.add(q.id); draw(); } }),
            idx < questions.length - 1 ? el("button", { type: "button", class: "ghost", text: "Next →", onclick: () => { idx++; draw(); } }) : null),
          el("button", { type: "button", class: "primary", text: exam ? "Submit exam" : "Submit quiz", onclick: () => submit(false) })));
    };
    async function submit(auto) {
      if (submitted) return;
      const unanswered = questions.filter((q) => !answers[q.id]).length;
      if (!auto && (unanswered || flags.size) && !(await N.confirm({ title: exam ? "Submit the exam?" : "Submit the quiz?", message: `${unanswered} unanswered${flags.size ? ", " + flags.size + " flagged" : ""}. You can't change answers after submitting.`, confirmText: "Submit" }))) return;
      submitted = true; clearInterval(m.timer);
      N.load(body, async (box) => { const r = await api(`/api/quizzes/${quiz.id}/submit`, { json: { answers } }); results(r); }).then(() => {});
    }
    function results(r) {
      clear(body); m.setTitle(exam ? "Exam results" : "Quiz results");
      const wrong = r.results.filter((x) => x.score !== null && x.score < 1).length, right = r.results.filter((x) => x.score === 1).length;
      const show = el("div"), draw2 = (review) => { clear(show); if (!review) return; r.results.forEach((x) => show.append(el("div", { class: "result " + (x.score === 1 ? "right" : x.score === null ? "" : "wrong") },
        el("div", {}, el("strong", { text: x.prompt })), el("div", { class: "ans", text: "Your answer: " + (x.response || "(no answer)") }),
        x.qtype === "open" ? el("div", {}, el("div", { class: "note-box" }, el("strong", { text: "Reference from your material: " }), x.reference || "No matching passage found in your documents."),
          el("div", { class: "row" }, el("span", { text: "Mark yourself:" }), [["Right", 1], ["Partly", 0.5], ["Wrong", 0]].map(([l, v]) => el("button", { type: "button", class: "mini" + (x.score === v ? " on" : ""), text: l, onclick: async () => { try { r = await api(`/api/quiz-attempts/${r.attempt_id}/selfmark`, { json: { question_id: x.question_id, score: v } }); results(r); draw2(true); } catch (e) { toast(e.message, "error"); } } })))) :
          el("div", { class: "ans", text: x.score === 1 ? "✓ Correct. " + (x.explanation || "") : "Correct answer: " + x.correct_answer + (x.explanation ? ". " + x.explanation : "") })))); };
      body.append(el("div", { class: "row between" }, el("div", {}, el("div", { class: "score-ring", text: r.percent === null ? "–" : r.percent + "%" }), el("small", { text: `${r.score} of ${r.total} marks` + (r.waiting_for_self_mark ? ` · ${r.waiting_for_self_mark} written answer(s) waiting for you to mark them` : "") })),
        el("div", {}, el("div", { text: `✓ ${right} correct` }), el("div", { text: `✗ ${wrong} incorrect` }))));
      if (r.strong.length) body.append(el("div", { class: "section-title", text: "Strong areas" }), ...r.strong.map((t) => el("div", { class: "mastery" }, el("span", { text: "✓ " + t.topic }), el("div", { class: "bar ok" }, el("i", { style: `width:${t.percent}%` })), el("span", { text: t.percent + "%" }))));
      if (r.weak.length) body.append(el("div", { class: "section-title", text: "Needs improvement" }), ...r.weak.map((t) => el("div", { class: "mastery" }, el("span", { text: t.topic }), el("div", { class: "bar bad" }, el("i", { style: `width:${t.percent}%` })), el("span", { text: t.percent + "%" }))));
      if (r.recommendations.length) { body.append(el("div", { class: "section-title", text: "Recommended next steps" })); r.recommendations.forEach((rec) => body.append(el("div", { class: "card" }, el("h3", { text: rec.topic }), el("div", { class: "card-actions" }, rec.steps.map((s) => el("button", { type: "button", class: "ghost", text: s.label, onclick: () => stepAction(s, m) })))))); }
      body.append(el("div", { class: "row" },
        el("button", { type: "button", class: "primary", text: "Try Again", onclick: async () => { try { runQuiz(m, await api("/api/quizzes/" + quiz.id)); } catch (e) { toast(e.message, "error"); } } }),
        el("button", { type: "button", class: "ghost", text: "Review Answers", onclick: (e) => { const on = show.childElementCount === 0; draw2(on); e.target.textContent = on ? "Hide Answers" : "Review Answers"; } }),
        !exam ? el("button", { type: "button", class: "ghost", text: "Generate Similar Quiz", onclick: async (e) => N.busy(e.target, "Generating...", async () => { try { runQuiz(m, await api(`/api/quizzes/${quiz.id}/similar`, { json: {} })); } catch (er) { toast(er.message, "error"); } }) }) : null,
        r.weak.length ? el("button", { type: "button", class: "ghost", text: "Study Weak Topics", onclick: () => { m.close(); N.openPanel("flashcards", { topic: r.weak[0].topic, generate: true }); } }) : null), show);
    }
    const tick = () => { const left = Math.max(0, endAt - Date.now()), s = Math.ceil(left / 1000); timer.textContent = "⏱ " + String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); timer.classList.toggle("low", s < 300); if (!left) submit(true); };
    if (endAt) { tick(); m.timer = setInterval(tick, 500); }
    draw();
  }
  function stepAction(s, m) {
    if (s.type === "read") { m.close(); N.openPanel("documents", { open: s.document_id }); }
    else if (s.type === "explain") { m.close(); N.chat.send("Explain " + s.topic); }
    else if (s.type === "flashcards") { m.close(); N.openPanel("flashcards", { topic: s.topic, generate: true }); }
    else if (s.type === "quiz") { m.close(); N.openPanel("quiz", { topic: s.topic }); }
  }
  N.stepAction = stepAction;

  N.panels.quiz = async function (opts) {
    const m = N.modal({ title: "Generate a quiz", wide: true, onClose: () => clearInterval(m.timer) });
    await N.load(m.body, async (box) => {
      const [docs, courses, notes, hist] = await Promise.all([N.loadDocs(), N.loadCourses(), api("/api/notes"), api("/api/quizzes")]);
      const srcSel = select([["document", "A document"], ["course", "A course"], ["note", "A note"], ["topic", "A topic"], ["weak", "My weak topics"], ["mistakes", "My past mistakes"]], opts.topic ? "topic" : opts.document_id ? "document" : (docs.length ? "document" : "topic"));
      const docSel = select(ready(docs).map((d) => [d.id, d.filename]), opts.document_id || ""), courseSel = select(courses.map((c) => [c.id, c.name]), ""), noteSel = select(notes.notes.map((n) => [n.id, n.title]), "");
      const topic = el("input", { type: "text", value: opts.topic || "", placeholder: "e.g. Normalization", maxlength: "100" });
      const wrapSel = el("div"), count = el("input", { type: "number", min: "1", max: "30", value: "10" }), diff = { v: "medium" };
      const seg = el("div", { class: "seg" }, [["easy", "Easy"], ["medium", "Medium"], ["hard", "Hard"]].map(([v, l]) => el("button", { type: "button", class: v === "medium" ? "on" : "", text: l, onclick: (e) => { diff.v = v; [...seg.children].forEach((b) => b.classList.toggle("on", b === e.target)); } })));
      const types = ["mcq", "tf", "short"].map((t, i) => ({ t, box: el("input", { type: "checkbox", checked: true }) }));
      const labels = { mcq: "Multiple choice", tf: "True/False", short: "Short answer" };
      const paint = () => { clear(wrapSel); const v = srcSel.value; if (v === "document") wrapSel.append(docs.length ? field("Document", docSel) : N.empty("No documents yet", "Upload one first.")); if (v === "course") wrapSel.append(courses.length ? field("Course", courseSel) : N.empty("No courses yet", "Add courses in User Profile.")); if (v === "note") wrapSel.append(notes.notes.length ? field("Note", noteSel) : N.empty("No notes yet")); if (v === "topic") wrapSel.append(field("Topic", topic, "I'll look for it in your documents.")); if (v === "weak") wrapSel.append(el("p", { class: "note-box", text: "Questions come from topics where you got under 60% right (at least 2 answers)." })); if (v === "mistakes") wrapSel.append(el("p", { class: "note-box", text: "Re-asks questions you got wrong in recent quizzes." })); };
      srcSel.addEventListener("change", paint); paint();
      const gen = el("button", { type: "button", class: "primary", text: "Generate quiz", onclick: (e) => N.busy(e.target, "Generating...", async () => {
        const v = srcSel.value, source = { type: v };
        if (v === "document") source.id = docSel.value; if (v === "course") source.id = courseSel.value; if (v === "note") source.id = noteSel.value; if (v === "topic") source.topic = topic.value;
        try {
          const q = await api("/api/quizzes/generate", { json: { source, count: Number(count.value), difficulty: diff.v, types: types.filter((x) => x.box.checked).map((x) => x.t) } });
          if (q.note) toast(q.note); clear(m.body); runQuiz(m, q);
        } catch (er) { toast(er.message, "error"); }
      }) });
      box.append(el("p", { class: "note-box", text: "Questions are built from your own material by rules (definitions, key terms), not by an AI model, so some can be awkward. Each answer shows the sentence it came from." }),
        field("Make a quiz from", srcSel), wrapSel,
        el("div", { class: "row" }, field("Questions", count), field("Difficulty", seg)),
        el("div", { class: "field" }, el("span", { text: "Question types" }), types.map((x) => el("label", { class: "check" }, x.box, labels[x.t]))), el("div", { class: "row end" }, gen));
      if (hist.quizzes.length) {
        box.append(el("div", { class: "section-title", text: "Recent quizzes" }));
        hist.quizzes.slice(0, 6).forEach((h) => box.append(el("div", { class: "row between" }, el("span", {}, h.title, el("small", { text: ` · ${h.questions} questions${h.last_score !== null ? " · last " + h.last_score + "%" : ""}` })), el("button", { type: "button", class: "mini", text: "Retake", onclick: async () => { try { runQuiz(m, await api("/api/quizzes/" + h.id)); } catch (e) { toast(e.message, "error"); } } }))));
      }
    });
    if (opts.topic && opts.autostart) m.body.querySelector("button.primary").click();
  };

  // -------------------------------------------------------------- flashcards
  N.panels.flashcards = async function (opts) {
    const m = N.modal({ title: "Flashcards", wide: true }), host = el("div"); m.body.append(host);
    const q = () => [opts.document_id ? "document_id=" + opts.document_id : "", opts.topic ? "topic=" + encodeURIComponent(opts.topic) : ""].filter(Boolean).join("&");
    async function home() {
      m.setTitle("Flashcards");
      await N.load(host, async (box) => {
        const [due, docs, courses, notes] = await Promise.all([api("/api/flashcards/due?limit=30&" + q()), N.loadDocs(), N.loadCourses(), api("/api/notes")]);
        box.append(el("div", { class: "tiles" }, el("div", { class: "tile" }, el("b", { text: due.cards.length }), el("small", { text: "due now" + (opts.topic ? " · " + opts.topic : "") })), el("div", { class: "tile" }, el("b", { text: due.total }), el("small", { text: "cards in total" }))),
          el("div", { class: "row" }, el("button", { type: "button", class: "primary", text: due.cards.length ? "Study now" : "Nothing due", disabled: !due.cards.length, onclick: () => study(due.cards) })));
        const srcSel = select([["document", "A document"], ["course", "A course"], ["note", "A note"], ["topic", "A topic"], ["weak", "My weak topics"]], opts.topic ? "topic" : opts.document_id ? "document" : (docs.length ? "document" : "topic"));
        const docSel = select(ready(docs).map((d) => [d.id, d.filename]), opts.document_id || ""), courseSel = select(courses.map((c) => [c.id, c.name]), ""), noteSel = select(notes.notes.map((n) => [n.id, n.title]), ""), topic = el("input", { type: "text", value: opts.topic || "", maxlength: "100", placeholder: "e.g. Normalization" }), count = el("input", { type: "number", min: "1", max: "60", value: "20" }), pane = el("div");
        const paint = () => { clear(pane); const v = srcSel.value; pane.append(v === "document" ? field("Document", docSel) : v === "course" ? field("Course", courseSel) : v === "note" ? field("Note", noteSel) : v === "topic" ? field("Topic", topic) : el("p", { class: "note-box", text: "Cards come from topics where you got under 60% right." })); };
        srcSel.addEventListener("change", paint); paint();
        box.append(el("div", { class: "section-title", text: "Create flashcards" }), field("From", srcSel), pane, field("How many", count),
          el("button", { type: "button", class: "primary", text: "Generate flashcards", onclick: (e) => N.busy(e.target, "Generating...", async () => {
            const v = srcSel.value, source = { type: v }; if (v === "document") source.id = docSel.value; if (v === "course") source.id = courseSel.value; if (v === "note") source.id = noteSel.value; if (v === "topic") source.topic = topic.value;
            try { const r = await api("/api/flashcards/generate", { json: { source, count: Number(count.value) } }); toast(`Created ${r.created} new flashcards` + (r.skipped_duplicates ? ` (${r.skipped_duplicates} already existed)` : "")); home(); } catch (er) { toast(er.message, "error"); }
          }) }),
          el("div", { class: "section-title", text: "Add your own card" }), addForm(), el("div", { class: "section-title", text: "Browse cards" }), browser());
        if (opts.generate && !opts.__done) { opts.__done = true; }
      });
    }
    function addForm() {
      const f = el("input", { type: "text", maxlength: "500", placeholder: "Front (question)" }), b = el("input", { type: "text", maxlength: "1000", placeholder: "Back (answer)" });
      return el("div", { class: "row" }, el("div", { class: "grow" }, f), el("div", { class: "grow" }, b), el("button", { type: "button", class: "ghost", text: "Add", onclick: async () => { try { await api("/api/flashcards", { json: { front: f.value, back: b.value } }); f.value = b.value = ""; toast("Card added"); home(); } catch (e) { toast(e.message, "error"); } } }));
    }
    function browser() {
      const s = el("input", { type: "search", placeholder: "Search cards", "aria-label": "Search flashcards" }), list = el("div", { class: "list" });
      const draw = () => N.load(list, async (o) => { const r = await api("/api/flashcards?q=" + encodeURIComponent(s.value)); if (!r.cards.length) return o.append(N.empty("No cards")); r.cards.slice(0, 40).forEach((c) => o.append(el("div", { class: "card" }, el("h3", { text: c.front }), el("small", { text: c.back + (c.topic ? " · " + c.topic : "") + " · due " + c.due_date }), el("div", { class: "card-actions" }, el("button", { type: "button", class: "mini", text: "Delete", onclick: async () => { await api("/api/flashcards/" + c.id, { method: "DELETE" }); draw(); } }))))); });
      let t; s.addEventListener("input", () => { clearTimeout(t); t = setTimeout(draw, 250); }); draw();
      return el("div", {}, s, list);
    }
    function study(cards) {
      let i = 0; const counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
      const draw = () => {
        clear(host); m.setTitle(`Flashcards · ${Math.min(i + 1, cards.length)} / ${cards.length}`);
        if (i >= cards.length) {
          return host.append(el("div", { class: "state" }, el("strong", { text: "Session complete" }), el("span", { text: `Again ${counts[1]} · Hard ${counts[2]} · Good ${counts[3]} · Easy ${counts[4]}` }), el("div", { class: "row" }, el("button", { type: "button", class: "primary", text: "Back to flashcards", onclick: home }), el("button", { type: "button", class: "ghost", text: "Show my progress", onclick: () => { m.close(); N.openPanel("progress"); } }))));
        }
        const c = cards[i]; let shown = false;
        const back = el("div", { class: "qprompt", hidden: true }, md(c.back)), rate = el("div", { class: "rate", hidden: true }), reveal = el("button", { type: "button", class: "primary", text: "Show Answer" });
        [[1, "Again"], [2, "Hard"], [3, "Good"], [4, "Easy"]].forEach(([v, l]) => rate.append(el("button", { type: "button", text: l, onclick: async () => { try { await api(`/api/flashcards/${c.id}/review`, { json: { rating: v } }); counts[v]++; i++; draw(); } catch (e) { toast(e.message, "error"); } } })));
        reveal.addEventListener("click", () => { shown = true; back.hidden = false; rate.hidden = false; reveal.hidden = true; rate.firstChild.focus(); });
        host.append(el("div", { class: "bar", style: "margin-bottom:.8rem" }, el("i", { style: `width:${(100 * i) / cards.length}%` })), el("div", { class: "flash" }, c.topic ? el("small", { text: c.topic }) : null, el("div", { text: c.front }), back, reveal), rate);
        reveal.focus();
      };
      draw();
    }
    home();
  };
})();
