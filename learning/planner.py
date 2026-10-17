"""
Study planner: spreads a course's topics over the days before an exam.

It is a deterministic scheduler, not an AI: topics the student says they
struggle with (or that their quiz results show as weak) get extra sessions,
the day before the exam is revision, and the last plan day is a full mock
exam. The plan is a starting point to adjust, not a prediction of the exam.
"""

import json
from datetime import date, timedelta

import db
from learning import progress, quizgen

MAX_DAYS = 60


def course_topics(user_id: int, course_id=None, limit=40):
    """Section headings from the student's course documents, in reading order."""
    sql = ("SELECT c.section, c.document_id, MIN(c.ord) AS first_ord, COUNT(*) AS n FROM document_chunks c "
           "JOIN documents d ON d.id = c.document_id WHERE c.user_id = ? AND d.user_id = ? AND d.kind = 'material' "
           "AND c.section IS NOT NULL")
    params = [user_id, user_id]
    if course_id is not None:
        sql += " AND d.course_id = ?"
        params.append(course_id)
    sql += " GROUP BY c.document_id, c.section ORDER BY c.document_id, first_ord"
    rows = db.fetchall(sql, params)
    total_chunks = db.fetchone(
        "SELECT COUNT(*) AS n FROM document_chunks WHERE user_id = ?", (user_id,))["n"] or 1
    topics, seen = [], set()
    for r in rows:
        name = r["section"].strip()
        low = name.lower()
        # a heading repeated on most pages is a running header, not a topic
        if low in seen or len(name) > 70 or r["n"] > 0.5 * total_chunks > 4:
            continue
        seen.add(low)
        topics.append(name)
        if len(topics) >= limit:
            break
    return topics


def _task(day_index, due, label, topic=None, kind="study"):
    return {"day_index": day_index, "due_date": due.isoformat(), "label": label, "topic": topic, "kind": kind}


def build_schedule(topics, struggling, start: date, exam: date, hours_per_day: float, level: str):
    """Returns a list of task dicts, or raises ValueError with a message for the student."""
    n_days = (exam - start).days
    if n_days < 1:
        raise ValueError("The exam date must be in the future.")
    n_days = min(n_days, MAX_DAYS)
    start = exam - timedelta(days=n_days)
    if start < progress.today():
        start = progress.today()
        n_days = (exam - start).days
    if not topics:
        raise ValueError("I need topics to plan around. Add documents to this course, or list the topics yourself.")

    days = [start + timedelta(days=i) for i in range(n_days)]
    tasks = []
    struggling_l = {s.lower() for s in struggling}
    weak = [t for t in topics if t.lower() in struggling_l]

    mock_day = n_days >= 3
    revision_day = n_days >= 5
    study_days = n_days - (1 if mock_day else 0) - (1 if revision_day else 0)
    study_days = max(study_days, 1)

    slots = [(t, "study") for t in topics]
    spare = study_days - len(slots)
    extra = weak + [t for t in topics if t not in weak]
    i = 0
    while spare > 0 and extra:
        slots.append((extra[i % len(extra)], "practice"))
        spare -= 1
        i += 1
    if len(slots) < study_days:       # no topics to fill with
        study_days = len(slots)
    # distribute slots to the study days, in order
    per_day = [slots[(d * len(slots)) // study_days:((d + 1) * len(slots)) // study_days] for d in range(study_days)]

    long_day = hours_per_day >= 1.5
    for d, day_slots in enumerate(per_day):
        due = days[d]
        for topic, kind in day_slots:
            if kind == "study":
                if level == "beginner":
                    tasks.append(_task(d + 1, due, f"Read the summary of {topic}", topic, "study"))
                tasks.append(_task(d + 1, due, f"Study: {topic}", topic, "study"))
                if long_day:
                    tasks.append(_task(d + 1, due, f"Practice questions: {topic}", topic, "quiz"))
            else:
                tasks.append(_task(d + 1, due, f"Practice quiz: {topic}", topic, "quiz"))
                tasks.append(_task(d + 1, due, f"Review your mistakes on {topic}", topic, "review"))
        if hours_per_day >= 1:
            tasks.append(_task(d + 1, due, "Review today's flashcards", None, "flashcards"))
    next_day = len(per_day)
    if revision_day:
        focus = ", ".join(weak[:3]) if weak else "your weakest topics"
        tasks.append(_task(next_day + 1, days[next_day], f"Revision: {focus}", None, "review"))
        tasks.append(_task(next_day + 1, days[next_day], "Review your flashcards", None, "flashcards"))
        next_day += 1
    if mock_day:
        tasks.append(_task(next_day + 1, days[next_day], "Full mock exam", None, "exam"))
        tasks.append(_task(next_day + 1, days[next_day], "Review the mock exam results", None, "review"))
    return tasks


def create_plan(user_id, title, course_id, exam_date: date, hours_per_day, level, struggling, topics=None):
    topics = [t.strip() for t in (topics or []) if t.strip()] or course_topics(user_id, course_id)
    tasks = build_schedule(topics, struggling, progress.today(), exam_date, hours_per_day, level)
    plan_id = db.execute(
        "INSERT INTO study_plans (user_id, title, course_id, exam_date, hours_per_day, level, struggling) VALUES (?,?,?,?,?,?,?)",
        (user_id, title, course_id, exam_date.isoformat(), hours_per_day, level, json.dumps(struggling)),
    )
    db.executemany(
        "INSERT INTO study_tasks (plan_id, user_id, day_index, due_date, label, topic, kind) VALUES (?,?,?,?,?,?,?)",
        [(plan_id, user_id, t["day_index"], t["due_date"], t["label"], t["topic"], t["kind"]) for t in tasks],
    )
    progress.record_event(user_id, "plan_created", plan_id)
    return plan_id


def adapt_plan(user_id: int, plan: dict):
    """Rebuild the days that are still ahead, giving more time to topics the
    student's results show as weak. Tasks already ticked off are kept."""
    exam = date.fromisoformat(plan["exam_date"])
    weak = [w["topic"] for w in progress.weak_topics(user_id, plan["course_id"])]
    struggling = list(dict.fromkeys(json.loads(plan["struggling"]) + weak))
    mastered = {m["topic"].lower() for m in progress.mastery_list(user_id, plan["course_id"]) if m["answers"] >= 3 and m["mastery"] >= 0.85}
    topics = [t for t in course_topics(user_id, plan["course_id"]) if t.lower() not in mastered]
    done_topics = {r["topic"] for r in db.fetchall("SELECT topic FROM study_tasks WHERE plan_id = ? AND user_id = ? AND done = 1", (plan["id"], user_id))}
    topics = [t for t in topics if t not in done_topics] or topics
    new = build_schedule(topics, struggling, progress.today(), exam, plan["hours_per_day"], plan["level"])
    base = db.fetchone("SELECT COALESCE(MAX(day_index), 0) AS m FROM study_tasks WHERE plan_id = ? AND user_id = ? AND (done = 1 OR due_date < ?)",
                       (plan["id"], user_id, progress.today().isoformat()))["m"]
    db.execute("DELETE FROM study_tasks WHERE plan_id = ? AND user_id = ? AND done = 0 AND due_date >= ?",
               (plan["id"], user_id, progress.today().isoformat()))
    db.executemany(
        "INSERT INTO study_tasks (plan_id, user_id, day_index, due_date, label, topic, kind) VALUES (?,?,?,?,?,?,?)",
        [(plan["id"], user_id, base + t["day_index"], t["due_date"], t["label"], t["topic"], t["kind"]) for t in new],
    )
    db.execute("UPDATE study_plans SET struggling = ? WHERE id = ? AND user_id = ?", (json.dumps(struggling), plan["id"], user_id))
    return weak
