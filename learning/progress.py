"""
Study events, topic mastery, weak topics, streaks and the spaced-repetition
scheduler for flashcards.

"Mastery" is simply the share of answers the student got right, per topic,
across quiz questions and flashcard reviews. A topic counts as weak when the
student has at least `min_samples` answers on it and under 60% are right.
That is a plain statistic, not a prediction of exam results.
"""

import json
from datetime import date, datetime, timedelta, timezone

import db


def today() -> date:
    return datetime.now(timezone.utc).date()


def record_event(user_id: int, kind: str, ref=None) -> None:
    db.execute("INSERT INTO study_events (user_id, kind, ref) VALUES (?, ?, ?)", (user_id, kind, ref))


# ------------------------------------------------------------- scheduler

def schedule(card: dict, rating: int) -> dict:
    """Simplified SM-2. rating: 1 again, 2 hard, 3 good, 4 easy.
    Returns the new ease / interval_days / reps / lapses / due_date."""
    ease, interval, reps, lapses = card["ease"], card["interval_days"], card["reps"], card["lapses"]
    if rating == 1:
        reps, interval, lapses = 0, 0, lapses + 1
        ease = max(1.3, ease - 0.2)
    elif rating == 2:
        interval = 1 if reps == 0 else max(1, round(interval * 1.2))
        reps += 1
        ease = max(1.3, ease - 0.15)
    elif rating == 3:
        interval = 1 if reps == 0 else (3 if reps == 1 else max(1, round(interval * ease)))
        reps += 1
    else:
        interval = 3 if reps == 0 else max(2, round(interval * ease * 1.3))
        reps += 1
        ease += 0.15
    due = today() + timedelta(days=interval)
    return {"ease": round(ease, 2), "interval_days": interval, "reps": reps, "lapses": lapses, "due_date": due.isoformat()}


# ---------------------------------------------------------- topic stats

def topic_stats(user_id: int, course_id=None):
    """{topic: {"correct": float, "total": int}} from quiz answers and flashcard reviews."""
    stats = {}

    def add(topic, score):
        if not topic:
            return
        e = stats.setdefault(topic, {"correct": 0.0, "total": 0})
        e["correct"] += score
        e["total"] += 1

    sql = "SELECT a.results FROM quiz_attempts a JOIN quizzes q ON q.id = a.quiz_id WHERE a.user_id = ? AND q.user_id = ?"
    params = [user_id, user_id]
    if course_id is not None:
        sql += " AND q.course_id = ?"
        params.append(course_id)
    for row in db.fetchall(sql, params):
        try:
            for r in json.loads(row["results"]):
                if r.get("score") is not None:
                    add(r.get("topic"), float(r["score"]))
        except (ValueError, TypeError):
            continue

    sql = "SELECT r.rating, r.topic FROM flashcard_reviews r JOIN flashcards f ON f.id = r.card_id WHERE r.user_id = ? AND f.user_id = ?"
    params = [user_id, user_id]
    if course_id is not None:
        sql += " AND f.course_id = ?"
        params.append(course_id)
    for r in db.fetchall(sql, params):
        add(r["topic"], 1.0 if r["rating"] >= 3 else 0.0)
    return stats


def mastery_list(user_id: int, course_id=None):
    out = []
    for topic, e in topic_stats(user_id, course_id).items():
        out.append({"topic": topic, "mastery": round(e["correct"] / e["total"], 2), "answers": e["total"]})
    return sorted(out, key=lambda x: (x["mastery"], -x["answers"]))


def weak_topics(user_id: int, course_id=None, min_samples=2, threshold=0.6):
    return [m for m in mastery_list(user_id, course_id) if m["answers"] >= min_samples and m["mastery"] < threshold]


# --------------------------------------------------------------- streak

def streak(user_id: int) -> dict:
    rows = db.fetchall("SELECT DISTINCT date(created_at) AS d FROM study_events WHERE user_id = ? ORDER BY d DESC LIMIT 400", (user_id,))
    days = {date.fromisoformat(r["d"]) for r in rows if r["d"]}
    cur, d = 0, today()
    if d not in days:
        d -= timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for day in sorted(days):
        run = run + 1 if prev and (day - prev).days == 1 else 1
        best, prev = max(best, run), day
    return {"current": cur, "best": best, "study_days": len(days)}


# -------------------------------------------------------------- summary

def summary(user_id: int, course_id=None) -> dict:
    cf, cp = ("", [])
    if course_id is not None:
        cf, cp = " AND course_id = ?", [course_id]
    quizzes = db.fetchall(
        "SELECT a.score, a.total, a.created_at, q.title, q.kind FROM quiz_attempts a JOIN quizzes q ON q.id = a.quiz_id "
        "WHERE a.user_id = ? AND q.user_id = ?" + cf.replace("course_id", "q.course_id") + " ORDER BY a.id DESC LIMIT 50",
        [user_id, user_id] + cp,
    )
    pct = [round(100 * q["score"] / q["total"]) for q in quizzes if q["total"]]
    questions = sum(q["total"] for q in quizzes)
    reviews = db.fetchone("SELECT COUNT(*) AS n FROM flashcard_reviews WHERE user_id = ?", (user_id,))["n"]
    cards = db.fetchone("SELECT COUNT(*) AS n FROM flashcards WHERE user_id = ?" + cf, [user_id] + cp)["n"]
    due = db.fetchone("SELECT COUNT(*) AS n FROM flashcards WHERE user_id = ? AND due_date <= ?" + cf, [user_id, today().isoformat()] + cp)["n"]
    docs = db.fetchone("SELECT COUNT(*) AS n FROM documents WHERE user_id = ? AND kind = 'material'" + cf, [user_id] + cp)["n"]
    studied = db.fetchone(
        "SELECT COUNT(DISTINCT ref) AS n FROM study_events WHERE user_id = ? AND kind IN ('doc_chat','doc_quiz','doc_cards','doc_summary')", (user_id,))["n"]
    mastery = mastery_list(user_id, course_id)
    weak = [m for m in mastery if m["answers"] >= 2 and m["mastery"] < 0.6]
    strong = [m for m in mastery if m["answers"] >= 2 and m["mastery"] >= 0.8]

    plan_rows = db.fetchall(
        "SELECT t.done FROM study_tasks t JOIN study_plans p ON p.id = t.plan_id WHERE t.user_id = ? AND p.user_id = ?" + cf.replace("course_id", "p.course_id"),
        [user_id, user_id] + cp)
    plan_pct = round(100 * sum(r["done"] for r in plan_rows) / len(plan_rows)) if plan_rows else None

    return {
        "streak": streak(user_id),
        "quizzes_taken": len(quizzes),
        "average_score": round(sum(pct) / len(pct)) if pct else None,
        "recent_scores": list(reversed(pct[:10])),
        "questions_answered": questions,
        "flashcards_total": cards,
        "flashcards_due": due,
        "flashcards_reviewed": reviews,
        "documents": docs,
        "documents_studied": studied,
        "plan_completion": plan_pct,
        "mastery": mastery,
        "weak": weak[:6],
        "strong": strong[:6],
        "recommendations": recommendations(user_id, weak[:3], course_id),
    }


def recommendations(user_id: int, weak, course_id=None):
    recs = []
    for w in weak:
        topic = w["topic"]
        chunk = db.fetchone(
            "SELECT c.page, d.filename, d.id AS document_id FROM document_chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.user_id = ? AND d.user_id = ? AND c.section = ? LIMIT 1", (user_id, user_id, topic))
        steps = []
        if chunk:
            where = f"{chunk['filename']}" + (f", page {chunk['page']}" if chunk["page"] else "")
            steps.append({"type": "read", "label": f"Review the section in {where}", "document_id": chunk["document_id"], "topic": topic})
        steps.append({"type": "explain", "label": f"Ask Nocturna to explain {topic}", "topic": topic})
        steps.append({"type": "flashcards", "label": "Study flashcards on this topic", "topic": topic})
        steps.append({"type": "quiz", "label": "Take a practice quiz on this topic", "topic": topic})
        recs.append({"topic": topic, "mastery": w["mastery"], "steps": steps})
    return recs
