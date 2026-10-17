
import json
import re
from datetime import date

from flask import Blueprint, g, jsonify, request

import auth
import db
from api_chat import err, not_found
from learning import coding, exams, ingest, planner, progress, quizgen, retrieval, summaries, textproc

bp = Blueprint("api_learning", __name__)


def uid() -> int:
    return g.user["id"]


def body() -> dict:
    return request.get_json(silent=True) or {}


def owned(table: str, row_id) -> dict | None:
    """One row of a student-owned table, or None. `table` is always a literal
    from this file, never user input."""
    if row_id is None:
        return None
    return db.fetchone(f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (row_id, uid()))


def int_or_none(v):
    try:
        return int(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def like(q: str) -> str:
    return "%" + re.sub(r"[%_\\]", "", q) + "%"


# ================================================================ courses

@bp.route("/api/courses")
@auth.login_required
def courses_list():
    rows = db.fetchall(
        "SELECT c.id, c.name, (SELECT COUNT(*) FROM documents d WHERE d.course_id = c.id AND d.user_id = c.user_id) AS documents "
        "FROM courses c WHERE c.user_id = ? ORDER BY c.name", (uid(),))
    return jsonify(courses=rows)


@bp.route("/api/courses", methods=["POST"])
@auth.login_required
def courses_create():
    name = " ".join(str(body().get("name", "")).split())[:80]
    if not name:
        return err("Enter a course name.")
    if db.fetchone("SELECT id FROM courses WHERE user_id = ? AND name = ? COLLATE NOCASE", (uid(), name)):
        return err("You already have a course with that name.")
    return jsonify(course={"id": db.execute("INSERT INTO courses (user_id, name) VALUES (?, ?)", (uid(), name)), "name": name})


@bp.route("/api/courses/<int:cid>/rename", methods=["POST"])
@auth.login_required
def courses_rename(cid):
    if not owned("courses", cid):
        return not_found()
    name = " ".join(str(body().get("name", "")).split())[:80]
    if not name:
        return err("Enter a course name.")
    if db.fetchone("SELECT id FROM courses WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?", (uid(), name, cid)):
        return err("You already have a course with that name.")
    db.execute("UPDATE courses SET name = ? WHERE id = ? AND user_id = ?", (name, cid, uid()))
    return jsonify(ok=True, name=name)


@bp.route("/api/courses/<int:cid>", methods=["DELETE"])
@auth.login_required
def courses_delete(cid):
    if not owned("courses", cid):
        return not_found()
    for table in ("documents", "document_chunks", "quizzes", "flashcards", "study_plans", "notes"):
        db.execute(f"UPDATE {table} SET course_id = NULL WHERE course_id = ? AND user_id = ?", (cid, uid()))
    db.execute("DELETE FROM courses WHERE id = ? AND user_id = ?", (cid, uid()))
    return jsonify(ok=True)


# ============================================================== documents

def _doc_row(d: dict) -> dict:
    return {k: d[k] for k in ("id", "filename", "kind", "status", "stage", "error", "pages", "chunk_count", "course_id", "created_at")}


@bp.route("/api/documents", methods=["POST"])
@auth.login_required
def documents_upload():
    f = request.files.get("file")
    if f is None or not f.filename:
        return err("Choose a file to upload.")
    kind = request.form.get("kind", "material")
    if kind not in ("material", "past_exam"):
        return err("Unknown document type.")
    course_id = int_or_none(request.form.get("course_id"))
    if course_id is not None and not owned("courses", course_id):
        return not_found()
    data = f.read(ingest.MAX_BYTES + 1)
    try:
        doc_id = ingest.submit(uid(), f.filename, data, course_id=course_id, kind=kind)
    except ingest.IngestError as e:
        return err(str(e))
    return jsonify(document=_doc_row(owned("documents", doc_id))), 202


@bp.route("/api/documents")
@auth.login_required
def documents_list():
    sql = ("SELECT d.*, c.name AS course_name FROM documents d LEFT JOIN courses c ON c.id = d.course_id "
           "WHERE d.user_id = ?")
    params = [uid()]
    course_id = int_or_none(request.args.get("course_id"))
    if course_id is not None:
        sql += " AND d.course_id = ?"
        params.append(course_id)
    if request.args.get("kind") in ("material", "past_exam"):
        sql += " AND d.kind = ?"
        params.append(request.args["kind"])
    rows = db.fetchall(sql + " ORDER BY d.id DESC", params)
    return jsonify(documents=[{**_doc_row(r), "course_name": r["course_name"]} for r in rows])


@bp.route("/api/documents/<int:did>")
@auth.login_required
def documents_get(did):
    d = owned("documents", did)
    if not d:
        return not_found()
    sections = db.fetchall(
        "SELECT section, MIN(page) AS page, COUNT(*) AS chunks FROM document_chunks WHERE document_id = ? AND user_id = ? AND section IS NOT NULL "
        "GROUP BY section ORDER BY MIN(ord) LIMIT 60", (did, uid()))
    return jsonify(document=_doc_row(d), sections=sections)


@bp.route("/api/documents/<int:did>/text")
@auth.login_required
def documents_text(did):
    if not owned("documents", did):
        return not_found()
    offset = max(0, int_or_none(request.args.get("offset")) or 0)
    rows = db.fetchall(
        "SELECT section, page, text FROM document_chunks WHERE document_id = ? AND user_id = ? ORDER BY ord LIMIT 12 OFFSET ?", (did, uid(), offset))
    return jsonify(chunks=rows, next_offset=offset + len(rows) if len(rows) == 12 else None)


@bp.route("/api/documents/<int:did>", methods=["DELETE"])
@auth.login_required
def documents_delete(did):
    if not owned("documents", did):
        return not_found()
    db.execute("UPDATE conversations SET document_id = NULL WHERE document_id = ? AND user_id = ?", (did, uid()))
    db.execute("UPDATE quizzes SET document_id = NULL WHERE document_id = ? AND user_id = ?", (did, uid()))
    db.execute("UPDATE flashcards SET document_id = NULL WHERE document_id = ? AND user_id = ?", (did, uid()))
    db.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (did, uid()))
    return jsonify(ok=True)


@bp.route("/api/documents/<int:did>/course", methods=["POST"])
@auth.login_required
def documents_set_course(did):
    if not owned("documents", did):
        return not_found()
    cid = int_or_none(body().get("course_id"))
    if cid is not None and not owned("courses", cid):
        return not_found()
    db.execute("UPDATE documents SET course_id = ? WHERE id = ? AND user_id = ?", (cid, did, uid()))
    db.execute("UPDATE document_chunks SET course_id = ? WHERE document_id = ? AND user_id = ?", (cid, did, uid()))
    return jsonify(ok=True)


@bp.route("/api/documents/<int:did>/summary", methods=["POST"])
@auth.login_required
def documents_summary(did):
    mode = body().get("mode", "quick")
    if mode not in summaries.MODES:
        return err("Unknown summary type.")
    if not owned("documents", did):
        return not_found()
    out = summaries.summarize(uid(), did, mode)
    if not out:
        return err("This document isn't ready or has no readable text.")
    progress.record_event(uid(), "doc_summary", did)
    return jsonify(out)


@bp.route("/api/documents/<int:did>/notes", methods=["POST"])
@auth.login_required
def documents_to_notes(did):
    d = owned("documents", did)
    if not d:
        return not_found()
    out = summaries.summarize(uid(), did, body().get("mode", "detailed") if body().get("mode") in summaries.MODES else "detailed")
    if not out:
        return err("This document isn't ready or has no readable text.")
    nid = db.add_note(uid(), out["markdown"], title=f"Notes: {d['filename']}"[:80], course_id=d["course_id"], document_id=did)
    return jsonify(note=_note_row(owned("notes", nid)))


# ================================================================== notes

def _note_row(n: dict, full=True) -> dict:
    row = {"id": n["id"], "title": n["title"] or "Untitled note", "course_id": n["course_id"], "document_id": n["document_id"],
           "updated_at": n["updated_at"] or n["created_at"]}
    row["content"] = n["content"] if full else n["content"][:160]
    return row


@bp.route("/api/notes")
@auth.login_required
def notes_list():
    sql, params = "SELECT * FROM notes WHERE user_id = ?", [uid()]
    q = request.args.get("q", "").strip()[:100]
    if q:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        params += [like(q), like(q)]
    for key in ("course_id", "document_id"):
        v = int_or_none(request.args.get(key))
        if v is not None:
            sql += f" AND {key} = ?"
            params.append(v)
    rows = db.fetchall(sql + " ORDER BY COALESCE(updated_at, created_at) DESC, id DESC LIMIT 200", params)
    return jsonify(notes=[_note_row(r, full=False) for r in rows])


@bp.route("/api/notes", methods=["POST"])
@auth.login_required
def notes_create():
    b = body()
    content = str(b.get("content", "")).strip()[:20000]
    if not content:
        return err("A note can't be empty.")
    course_id, document_id = int_or_none(b.get("course_id")), int_or_none(b.get("document_id"))
    if (course_id and not owned("courses", course_id)) or (document_id and not owned("documents", document_id)):
        return not_found()
    nid = db.add_note(uid(), content, title=str(b.get("title", "")).strip()[:80], course_id=course_id, document_id=document_id)
    return jsonify(note=_note_row(owned("notes", nid))), 201


@bp.route("/api/notes/<int:nid>")
@auth.login_required
def notes_get(nid):
    n = owned("notes", nid)
    return jsonify(note=_note_row(n)) if n else not_found()


@bp.route("/api/notes/<int:nid>", methods=["POST"])
@auth.login_required
def notes_update(nid):
    n = owned("notes", nid)
    if not n:
        return not_found()
    b = body()
    title = str(b.get("title", n["title"])).strip()[:80]
    content = str(b.get("content", n["content"])).strip()[:20000]
    if not content:
        return err("A note can't be empty.")
    course_id = int_or_none(b["course_id"]) if "course_id" in b else n["course_id"]
    if course_id and not owned("courses", course_id):
        return not_found()
    db.execute("UPDATE notes SET title = ?, content = ?, course_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
               (title, content, course_id, nid, uid()))
    return jsonify(note=_note_row(owned("notes", nid)))


@bp.route("/api/notes/<int:nid>", methods=["DELETE"])
@auth.login_required
def notes_delete(nid):
    if not owned("notes", nid):
        return not_found()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (nid, uid()))
    return jsonify(ok=True)


@bp.route("/api/notes/<int:nid>/summarize", methods=["POST"])
@auth.login_required
def notes_summarize(nid):
    n = owned("notes", nid)
    if not n:
        return not_found()
    pts = textproc.extractive_summary(n["content"], 4)
    return jsonify(markdown="**Key points from this note**\n\n" + "\n".join(f"- {p}" for p in pts) if pts else "This note is too short to summarise.")


# ================================================== sources for quiz/cards

def chunks_for_source(source: dict):
    """-> (chunks, title, document_id, course_id) or raises ValueError(message)."""
    t = (source or {}).get("type")
    if t == "document":
        d = owned("documents", int_or_none(source.get("id")))
        if not d:
            raise LookupError
        return retrieval.scoped_chunks(uid(), document_id=d["id"], kinds=("material", "past_exam")), d["filename"], d["id"], d["course_id"]
    if t == "course":
        c = owned("courses", int_or_none(source.get("id")))
        if not c:
            raise LookupError
        return retrieval.scoped_chunks(uid(), course_id=c["id"]), c["name"], None, c["id"]
    if t == "note":
        n = owned("notes", int_or_none(source.get("id")))
        if not n:
            raise LookupError
        return [{"section": n["title"] or "Note", "filename": "Note", "text": n["content"], "page": None, "document_id": n["document_id"]}], n["title"] or "Note", n["document_id"], n["course_id"]
    if t == "topic":
        topic = str(source.get("topic", "")).strip()[:100]
        if not topic:
            raise ValueError("Enter a topic.")
        course_id = int_or_none(source.get("course_id"))
        if course_id and not owned("courses", course_id):
            raise LookupError
        chunks = retrieval.search_chunks(uid(), topic, course_id=course_id, k=10, min_score=0.06)
        if not chunks:
            raise ValueError(f"I couldn't find \"{topic}\" in your documents. Upload material on it first.")
        return chunks, topic, None, course_id
    if t == "weak":
        weak = progress.weak_topics(uid(), int_or_none(source.get("course_id")))
        if not weak:
            raise ValueError("No weak topics yet. Take a few quizzes or review some flashcards first, then I can focus on what you got wrong.")
        names = {w["topic"] for w in weak}
        chunks = [c for c in retrieval.scoped_chunks(uid()) if c["section"] in names]
        if not chunks:
            raise ValueError("I can't find the material for your weak topics any more.")
        return chunks, "Weak topics", None, None
    if t == "all":
        chunks = retrieval.scoped_chunks(uid())
        if not chunks:
            raise ValueError("Upload some study material first.")
        return chunks, "All my material", None, None
    raise ValueError("Choose what to use: a document, a course, a note, a topic or your weak topics.")


def _quiz_public(quiz: dict, questions=None) -> dict:
    qs = questions if questions is not None else db.fetchall("SELECT id, qtype, prompt, options, topic FROM quiz_questions WHERE quiz_id = ? AND user_id = ? ORDER BY id", (quiz["id"], uid()))
    return {"quiz": {"id": quiz["id"], "title": quiz["title"], "kind": quiz["kind"], "duration_min": quiz["duration_min"]},
            "questions": [{"id": q["id"], "qtype": q["qtype"], "prompt": q["prompt"], "options": json.loads(q["options"]) if isinstance(q["options"], str) else q["options"], "topic": q["topic"]} for q in qs]}


def _create_quiz(title, source, settings, course_id, document_id, items, kind="quiz", duration=None):
    qid = db.execute("INSERT INTO quizzes (user_id, kind, title, source, course_id, document_id, duration_min) VALUES (?,?,?,?,?,?,?)",
                     (uid(), kind, title[:100], json.dumps({"source": source, **settings}), course_id, document_id, duration))
    db.executemany("INSERT INTO quiz_questions (quiz_id, user_id, qtype, prompt, options, answer, explanation, topic, reference) VALUES (?,?,?,?,?,?,?,?,?)",
                   [(qid, uid(), q["qtype"], q["prompt"], json.dumps(q["options"]), q["answer"], q["explanation"], q["topic"], q.get("reference", "")) for q in items])
    return qid


def _parse_settings(b):
    count = min(30, max(1, int_or_none(b.get("count")) or 10))
    difficulty = b.get("difficulty") if b.get("difficulty") in quizgen.TYPE_WEIGHTS else "medium"
    types = [t for t in (b.get("types") or ["mcq", "tf", "short"]) if t in ("mcq", "tf", "short")] or ["mcq"]
    return {"count": count, "difficulty": difficulty, "types": types}


# ================================================================= quizzes

@bp.route("/api/quizzes/generate", methods=["POST"])
@auth.login_required
def quizzes_generate():
    return _do_quiz(body())


def _do_quiz(b):
    settings = _parse_settings(b)
    source = b.get("source") or {}
    if source.get("type") == "mistakes":
        rows = db.fetchall(
            "SELECT a.results FROM quiz_attempts a WHERE a.user_id = ? ORDER BY a.id DESC LIMIT 10", (uid(),))
        missed = []
        for r in rows:
            for res in json.loads(r["results"]):
                if res.get("score") is not None and res["score"] < 1 and res.get("question_id") not in missed:
                    missed.append(res["question_id"])
        qs = [q for q in (owned("quiz_questions", i) for i in missed[:settings["count"]]) if q]
        if not qs:
            return err("You haven't got any questions wrong yet.")
        items = [{"qtype": q["qtype"], "prompt": q["prompt"], "options": json.loads(q["options"]), "answer": q["answer"], "explanation": q["explanation"], "topic": q["topic"], "reference": q["reference"]} for q in qs]
        qid = _create_quiz("Review of my mistakes", source, settings, None, None, items)
        return jsonify(_quiz_public(owned("quizzes", qid))), 201
    try:
        chunks, title, doc_id, course_id = chunks_for_source(source)
    except LookupError:
        return not_found()
    except ValueError as e:
        return err(str(e))
    items = quizgen.generate(chunks, settings["count"], settings["difficulty"], settings["types"])
    if not items:
        return err("I couldn't build questions from that material. The rule-based generator needs definition-style sentences (\"X is ...\"). Try a text-heavy document or a topic with clear definitions.")
    qid = _create_quiz(f"Quiz: {title}", source, settings, course_id, doc_id, items)
    if doc_id:
        progress.record_event(uid(), "doc_quiz", doc_id)
    out = _quiz_public(owned("quizzes", qid))
    if len(items) < settings["count"]:
        out["note"] = f"I could only build {len(items)} good questions from this material."
    return jsonify(out), 201


@bp.route("/api/quizzes")
@auth.login_required
def quizzes_list():
    rows = db.fetchall(
        "SELECT q.id, q.title, q.kind, q.created_at, "
        "(SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = q.id) AS questions, "
        "(SELECT ROUND(100.0 * score / NULLIF(total, 0)) FROM quiz_attempts WHERE quiz_id = q.id ORDER BY id DESC LIMIT 1) AS last_score "
        "FROM quizzes q WHERE q.user_id = ? ORDER BY q.id DESC LIMIT 50", (uid(),))
    return jsonify(quizzes=rows)


@bp.route("/api/quizzes/<int:qid>")
@auth.login_required
def quizzes_get(qid):
    q = owned("quizzes", qid)
    return jsonify(_quiz_public(q)) if q else not_found()


@bp.route("/api/quizzes/<int:qid>", methods=["DELETE"])
@auth.login_required
def quizzes_delete(qid):
    if not owned("quizzes", qid):
        return not_found()
    db.execute("DELETE FROM quizzes WHERE id = ? AND user_id = ?", (qid, uid()))
    return jsonify(ok=True)


@bp.route("/api/quizzes/<int:qid>/similar", methods=["POST"])
@auth.login_required
def quizzes_similar(qid):
    q = owned("quizzes", qid)
    if not q:
        return not_found()
    saved = json.loads(q["source"])
    request_body = {"source": saved.get("source", {}), "count": saved.get("count", 10), "difficulty": saved.get("difficulty", "medium"), "types": saved.get("types")}
    if q["kind"] == "mock_exam":
        return err("Build a new mock exam from the past-exam tools.")
    return _do_quiz(request_body)   # same source and settings, new questions


@bp.route("/api/quizzes/<int:qid>/submit", methods=["POST"])
@auth.login_required
def quizzes_submit(qid):
    quiz = owned("quizzes", qid)
    if not quiz:
        return not_found()
    answers = body().get("answers") or {}
    questions = db.fetchall("SELECT * FROM quiz_questions WHERE quiz_id = ? AND user_id = ? ORDER BY id", (qid, uid()))
    results, score, graded = [], 0.0, 0
    for q in questions:
        resp = str(answers.get(str(q["id"]), "") or "")[:2000]
        s = None if q["qtype"] == "open" else quizgen.grade(q, resp)
        if s is not None:
            score += s
            graded += 1
        results.append({"question_id": q["id"], "topic": q["topic"], "qtype": q["qtype"], "prompt": q["prompt"], "response": resp,
                        "score": s, "correct_answer": q["answer"], "explanation": q["explanation"], "reference": q["reference"]})
    aid = db.execute("INSERT INTO quiz_attempts (quiz_id, user_id, score, total, results) VALUES (?,?,?,?,?)", (qid, uid(), score, graded, json.dumps(results)))
    progress.record_event(uid(), "quiz", qid)
    return jsonify(_attempt_payload(aid, quiz, results, score, graded))


def _attempt_payload(aid, quiz, results, score, graded):
    by_topic = {}
    for r in results:
        if r["score"] is None or not r["topic"]:
            continue
        e = by_topic.setdefault(r["topic"], [0.0, 0])
        e[0] += r["score"]
        e[1] += 1
    topics = [{"topic": t, "percent": round(100 * v[0] / v[1])} for t, v in by_topic.items()]
    weak = [t for t in topics if t["percent"] < 60]
    strong = [t for t in topics if t["percent"] >= 80]
    waiting = sum(1 for r in results if r["score"] is None)
    recs = progress.recommendations(uid(), [{"topic": t["topic"], "mastery": t["percent"] / 100} for t in weak[:3]])
    return {"attempt_id": aid, "quiz": {"id": quiz["id"], "title": quiz["title"], "kind": quiz["kind"]}, "score": score, "total": graded,
            "percent": round(100 * score / graded) if graded else None, "waiting_for_self_mark": waiting, "results": results,
            "topics": topics, "weak": weak, "strong": strong, "recommendations": recs}


@bp.route("/api/quiz-attempts/<int:aid>/selfmark", methods=["POST"])
@auth.login_required
def attempts_selfmark(aid):
    a = owned("quiz_attempts", aid)
    if not a:
        return not_found()
    b = body()
    qid, mark = int_or_none(b.get("question_id")), b.get("score")
    if mark not in (0, 0.5, 1):
        return err("Mark must be 0, 0.5 or 1.")
    results = json.loads(a["results"])
    hit = next((r for r in results if r["question_id"] == qid and r["qtype"] == "open"), None)
    if not hit:
        return not_found()
    hit["score"] = float(mark)
    scored = [r["score"] for r in results if r["score"] is not None]
    db.execute("UPDATE quiz_attempts SET results = ?, score = ?, total = ? WHERE id = ? AND user_id = ?", (json.dumps(results), sum(scored), len(scored), aid, uid()))
    quiz = owned("quizzes", a["quiz_id"])
    return jsonify(_attempt_payload(aid, quiz, results, sum(scored), len(scored)))


# ============================================================== flashcards

def _card_row(c: dict) -> dict:
    return {k: c[k] for k in ("id", "front", "back", "topic", "due_date", "reps", "interval_days", "document_id", "course_id")}


@bp.route("/api/flashcards/generate", methods=["POST"])
@auth.login_required
def flashcards_generate():
    return _do_cards(body())


def _do_cards(b):
    count = min(60, max(1, int_or_none(b.get("count")) or 20))
    source = b.get("source") or {}
    try:
        chunks, title, doc_id, course_id = chunks_for_source(source)
    except LookupError:
        return not_found()
    except ValueError as e:
        return err(str(e))
    cards = []
    if source.get("type") == "note":
        cards = quizgen.cards_from_note_text(chunks[0]["text"], chunks[0]["section"])
    if not cards:
        cards = quizgen.flashcards(chunks, count)
    have = {r["front"].lower() for r in db.fetchall("SELECT front FROM flashcards WHERE user_id = ?", (uid(),))}
    today = progress.today().isoformat()
    new = [c for c in cards[:count] if c["front"].lower() not in have]
    db.executemany("INSERT INTO flashcards (user_id, front, back, topic, course_id, document_id, due_date) VALUES (?,?,?,?,?,?,?)",
                   [(uid(), c["front"][:500], c["back"][:1000], (c.get("topic") or title)[:80], course_id, doc_id, today) for c in new])
    if not cards:
        return err("I couldn't find definitions or key terms to turn into flashcards. Try a text-heavy document, or write notes as \"Term: definition\" lines.")
    if doc_id:
        progress.record_event(uid(), "doc_cards", doc_id)
    return jsonify(created=len(new), skipped_duplicates=len(cards[:count]) - len(new))


@bp.route("/api/flashcards/due")
@auth.login_required
def flashcards_due():
    sql, params = "SELECT * FROM flashcards WHERE user_id = ? AND due_date <= ?", [uid(), progress.today().isoformat()]
    for key in ("course_id", "document_id"):
        v = int_or_none(request.args.get(key))
        if v is not None:
            sql += f" AND {key} = ?"
            params.append(v)
    topic = request.args.get("topic", "").strip()[:80]
    if topic:
        sql += " AND topic LIKE ?"
        params.append(like(topic))
    rows = db.fetchall(sql + " ORDER BY due_date, ease LIMIT ?", params + [min(50, int_or_none(request.args.get("limit")) or 20)])
    total = db.fetchone("SELECT COUNT(*) AS n FROM flashcards WHERE user_id = ?", (uid(),))["n"]
    return jsonify(cards=[_card_row(r) for r in rows], total=total)


@bp.route("/api/flashcards")
@auth.login_required
def flashcards_list():
    q = request.args.get("q", "").strip()[:100]
    sql, params = "SELECT * FROM flashcards WHERE user_id = ?", [uid()]
    if q:
        sql += " AND (front LIKE ? OR back LIKE ?)"
        params += [like(q), like(q)]
    return jsonify(cards=[_card_row(r) for r in db.fetchall(sql + " ORDER BY id DESC LIMIT 200", params)])


@bp.route("/api/flashcards", methods=["POST"])
@auth.login_required
def flashcards_create():
    b = body()
    front, back = str(b.get("front", "")).strip()[:500], str(b.get("back", "")).strip()[:1000]
    if not front or not back:
        return err("A card needs a front and a back.")
    cid = db.execute("INSERT INTO flashcards (user_id, front, back, topic, due_date) VALUES (?,?,?,?,?)",
                     (uid(), front, back, str(b.get("topic", "")).strip()[:80] or None, progress.today().isoformat()))
    return jsonify(card=_card_row(owned("flashcards", cid))), 201


@bp.route("/api/flashcards/<int:cid>/review", methods=["POST"])
@auth.login_required
def flashcards_review(cid):
    c = owned("flashcards", cid)
    if not c:
        return not_found()
    rating = body().get("rating")
    if rating not in (1, 2, 3, 4):
        return err("Rating must be 1 (again), 2 (hard), 3 (good) or 4 (easy).")
    new = progress.schedule(c, rating)
    db.execute("UPDATE flashcards SET ease = ?, interval_days = ?, reps = ?, lapses = ?, due_date = ? WHERE id = ? AND user_id = ?",
               (new["ease"], new["interval_days"], new["reps"], new["lapses"], new["due_date"], cid, uid()))
    db.execute("INSERT INTO flashcard_reviews (card_id, user_id, rating, topic) VALUES (?,?,?,?)", (cid, uid(), rating, c["topic"]))
    progress.record_event(uid(), "flashcards", cid)
    return jsonify(card=_card_row(owned("flashcards", cid)))


@bp.route("/api/flashcards/<int:cid>", methods=["DELETE"])
@auth.login_required
def flashcards_delete(cid):
    if not owned("flashcards", cid):
        return not_found()
    db.execute("DELETE FROM flashcards WHERE id = ? AND user_id = ?", (cid, uid()))
    return jsonify(ok=True)


@bp.route("/api/notes/<int:nid>/flashcards", methods=["POST"])
@auth.login_required
def notes_to_flashcards(nid):
    if not owned("notes", nid):
        return not_found()
    return _do_cards({"source": {"type": "note", "id": nid}, "count": 30})


@bp.route("/api/notes/<int:nid>/quiz", methods=["POST"])
@auth.login_required
def notes_to_quiz(nid):
    if not owned("notes", nid):
        return not_found()
    b = dict(body())
    b["source"] = {"type": "note", "id": nid}
    return _do_quiz(b)


# ============================================================ study plans

def _plan_payload(p: dict) -> dict:
    tasks = db.fetchall("SELECT id, day_index, due_date, label, topic, kind, done FROM study_tasks WHERE plan_id = ? AND user_id = ? ORDER BY day_index, id", (p["id"], uid()))
    days = {}
    for t in tasks:
        days.setdefault(t["day_index"], {"day": t["day_index"], "date": t["due_date"], "tasks": []})["tasks"].append(t)
    done = sum(t["done"] for t in tasks)
    return {"id": p["id"], "title": p["title"], "exam_date": p["exam_date"], "hours_per_day": p["hours_per_day"], "level": p["level"],
            "struggling": json.loads(p["struggling"]), "days": list(days.values()), "completion": round(100 * done / len(tasks)) if tasks else 0}


@bp.route("/api/study-plans", methods=["POST"])
@auth.login_required
def plans_create():
    b = body()
    try:
        exam = date.fromisoformat(str(b.get("exam_date", ""))[:10])
    except ValueError:
        return err("Enter the exam date.")
    hours = min(12.0, max(0.5, float(b.get("hours_per_day") or 2)))
    level = b.get("level") if b.get("level") in ("beginner", "intermediate", "advanced") else "intermediate"
    # The student types the course name. An existing course with that name (any capitalisation) is reused,
    # otherwise a new course is created, so it also shows up under Settings > Documents / RAG > My courses.
    course_name = " ".join(str(b.get("course_name") or "").split())[:80]
    if course_name:
        course = db.fetchone("SELECT id, name FROM courses WHERE user_id = ? AND name = ? COLLATE NOCASE", (uid(), course_name))
        if not course:
            course = {"id": db.execute("INSERT INTO courses (user_id, name) VALUES (?, ?)", (uid(), course_name)), "name": course_name}
        course_id = course["id"]
    else:                                           # older clients may still send a course id
        course_id = int_or_none(b.get("course_id"))
        course = owned("courses", course_id) if course_id else None
        if course_id and not course:
            return not_found()
    struggling = [str(s).strip()[:80] for s in (b.get("struggling") or []) if str(s).strip()][:20]
    topics = [str(s).strip()[:80] for s in (b.get("topics") or []) if str(s).strip()][:40]
    title = str(b.get("title") or (course["name"] if course else "Study plan")).strip()[:80]
    try:
        pid = planner.create_plan(uid(), title, course_id, exam, hours, level, struggling, topics)
    except ValueError as e:
        return err(str(e))
    return jsonify(plan=_plan_payload(owned("study_plans", pid))), 201


@bp.route("/api/study-plans")
@auth.login_required
def plans_list():
    rows = db.fetchall("SELECT id FROM study_plans WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid(),))
    return jsonify(plans=[{k: p[k] for k in ("id", "title", "exam_date", "completion")} for p in (_plan_payload(owned("study_plans", r["id"])) for r in rows)])


@bp.route("/api/study-plans/<int:pid>")
@auth.login_required
def plans_get(pid):
    p = owned("study_plans", pid)
    return jsonify(plan=_plan_payload(p)) if p else not_found()


@bp.route("/api/study-plans/<int:pid>", methods=["DELETE"])
@auth.login_required
def plans_delete(pid):
    if not owned("study_plans", pid):
        return not_found()
    db.execute("DELETE FROM study_plans WHERE id = ? AND user_id = ?", (pid, uid()))
    return jsonify(ok=True)


@bp.route("/api/study-plans/<int:pid>/adapt", methods=["POST"])
@auth.login_required
def plans_adapt(pid):
    p = owned("study_plans", pid)
    if not p:
        return not_found()
    try:
        weak = planner.adapt_plan(uid(), p)
    except ValueError as e:
        return err(str(e))
    return jsonify(plan=_plan_payload(owned("study_plans", pid)), weak_topics=weak)


@bp.route("/api/study-tasks/<int:tid>/toggle", methods=["POST"])
@auth.login_required
def tasks_toggle(tid):
    t = owned("study_tasks", tid)
    if not t:
        return not_found()
    done = 0 if t["done"] else 1
    db.execute("UPDATE study_tasks SET done = ? WHERE id = ? AND user_id = ?", (done, tid, uid()))
    if done:
        progress.record_event(uid(), "task_done", tid)
    return jsonify(ok=True, done=bool(done), plan=_plan_payload(owned("study_plans", t["plan_id"])))


# ============================================================== progress

@bp.route("/api/progress")
@auth.login_required
def progress_get():
    course_id = int_or_none(request.args.get("course_id"))
    if course_id is not None and not owned("courses", course_id):
        return not_found()
    return jsonify(progress=progress.summary(uid(), course_id))


# ============================================================ past exams

@bp.route("/api/past-exams/analyze", methods=["POST"])
@auth.login_required
def pastexams_analyze():
    b = body()
    ids = [i for i in (int_or_none(x) for x in (b.get("document_ids") or [])) if i]
    if not ids:
        return err("Choose at least one uploaded past paper.")
    for i in ids:
        if not owned("documents", i):
            return not_found()
    analysis = exams.analyze(uid(), ids)
    if not analysis:
        return err("I couldn't find numbered questions in those files. Past papers work best when each question starts with 1., 2., 3. and so on.")
    course_id = int_or_none(b.get("course_id"))
    aid = db.execute("INSERT INTO past_exam_analyses (user_id, course_id, doc_ids, result) VALUES (?,?,?,?)",
                     (uid(), course_id if course_id and owned("courses", course_id) else None, json.dumps(ids), json.dumps(analysis)))
    return jsonify(analysis_id=aid, analysis=analysis)


@bp.route("/api/past-exams/mock", methods=["POST"])
@auth.login_required
def pastexams_mock():
    b = body()
    row = owned("past_exam_analyses", int_or_none(b.get("analysis_id")))
    if not row:
        return not_found()
    count = min(40, max(3, int_or_none(b.get("count")) or 10))
    duration = min(240, max(10, int_or_none(b.get("duration_min")) or 60))
    qid = exams.build_mock_exam(uid(), json.loads(row["result"]), row["course_id"], count, duration)
    if not qid:
        return err("I couldn't build a mock exam from that analysis.")
    return jsonify(_quiz_public(owned("quizzes", qid))), 201


# ================================================================ search

@bp.route("/api/search")
@auth.login_required
def search():
    q = request.args.get("q", "").strip()[:100]
    if len(q) < 2:
        return jsonify(results={})
    pat = like(q)
    res = {
        "documents": [{"document_id": c["document_id"], "title": c["filename"], "page": c["page"], "section": c["section"], "snippet": retrieval.citation(c)["snippet"]}
                      for c in retrieval.search_chunks(uid(), q, k=5, min_score=0.1, kinds=("material", "past_exam"))],
        "conversations": db.fetchall("SELECT DISTINCT c.id, c.title FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                                     "WHERE c.user_id = ? AND (c.title LIKE ? OR m.content LIKE ?) ORDER BY c.updated_at DESC LIMIT 5", (uid(), pat, pat)),
        "notes": db.fetchall("SELECT id, title FROM notes WHERE user_id = ? AND (title LIKE ? OR content LIKE ?) LIMIT 5", (uid(), pat, pat)),
        "courses": db.fetchall("SELECT id, name AS title FROM courses WHERE user_id = ? AND name LIKE ? LIMIT 5", (uid(), pat)),
        "quiz_questions": db.fetchall("SELECT id, quiz_id, prompt AS title FROM quiz_questions WHERE user_id = ? AND prompt LIKE ? LIMIT 5", (uid(), pat)),
        "flashcards": db.fetchall("SELECT id, front AS title, back FROM flashcards WHERE user_id = ? AND (front LIKE ? OR back LIKE ?) LIMIT 5", (uid(), pat, pat)),
    }
    return jsonify(results={k: v for k, v in res.items() if v}, method="keyword + TF-IDF (not an AI semantic search)")


# ================================================================ coding

@bp.route("/api/coding/analyze", methods=["POST"])
@auth.login_required
def coding_analyze():
    b = body()
    out = coding.analyze(str(b.get("code", "")), str(b.get("language", "python")).strip().lower()[:20], str(b.get("error", "")))
    return jsonify(out)