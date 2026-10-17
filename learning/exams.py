"""
Past-exam analysis and mock exams.

Questions are split out of the uploaded papers, grouped by the key terms they
share, and counted by how many papers each term appears in. The wording is
deliberately cautious: this reports what is FREQUENTLY TESTED IN THE PAPERS
THE STUDENT PROVIDED. It cannot say what a future exam will contain.
"""

import json
import re
from collections import Counter

import db
from learning import quizgen, retrieval, textproc

_Q_START = re.compile(r"(?m)^[ \t]*(?:Q(?:uestion)?\.?[ \t]*)?(\d{1,2})[ \t]*[.):][ \t]+(?=\S)")
_MARKS = re.compile(r"\(?\[?(\d{1,2})\s*marks?\)?\]?", re.I)
_EASY = {"define", "state", "list", "identify", "give", "name", "what", "which", "who", "when"}
_HARD = {"discuss", "evaluate", "design", "derive", "justify", "prove", "analyse", "analyze", "critically", "assess", "develop"}
_COMMAND = _EASY | _HARD | {"explain", "describe", "outline", "compare", "differentiate", "distinguish", "illustrate",
                            "calculate", "write", "draw", "how", "why", "show", "construct", "convert", "find", "solve", "briefly"}
_EXAM_WORDS = set("""question questions marks mark answer answers section paper exam examination candidate candidates
following given below above part parts attempt compulsory choose time hours hour total instructions note""".split())


def split_questions(text: str):
    text = textproc.clean(text)
    matches = list(_Q_START.finditer(text))
    out = []
    if len(matches) >= 3:
        for i, m in enumerate(matches):
            seg = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            seg = " ".join(seg.split())
            if len(seg) >= 20:
                out.append(seg)
    else:
        for s in textproc.sentences(text, min_len=20, max_len=300):
            first = (tokens := textproc.tokens(s))[:1]
            if s.endswith("?") or (first and first[0] in _COMMAND):
                out.append(s)
    return out


def _difficulty(q: str) -> str:
    first = (textproc.tokens(q) or [""])[0]
    if first in _HARD:
        return "hard"
    if first in _EASY:
        return "easy"
    marks = _MARKS.search(q)
    if marks and int(marks.group(1)) >= 8:
        return "hard"
    return "medium"


def _terms(q: str):
    words = [w for w in textproc.content_tokens(q) if w not in _EXAM_WORDS and w not in quizgen._GENERIC and w not in _COMMAND]
    uni = set(words)
    bi = {f"{a} {b}" for a, b in zip(words, words[1:])}
    return uni | bi


def analyze(user_id: int, doc_ids):
    papers = []
    for did in doc_ids:
        doc = db.fetchone("SELECT id, filename FROM documents WHERE id = ? AND user_id = ? AND status = 'ready'", (did, user_id))
        if not doc:
            continue
        text = "\n".join(c["text"] for c in db.fetchall(
            "SELECT text FROM document_chunks WHERE document_id = ? AND user_id = ? ORDER BY ord", (did, user_id)))
        papers.append({"id": doc["id"], "filename": doc["filename"], "questions": split_questions(text)})
    papers = [p for p in papers if p["questions"]]
    if not papers:
        return None

    all_q = [(p["id"], p["filename"], q) for p in papers for q in p["questions"]]
    n_papers, n_q = len(papers), len(all_q)
    term_papers, term_qs = {}, Counter()
    for pid, _, q in all_q:
        for t in _terms(q):
            term_papers.setdefault(t, set()).add(pid)
            term_qs[t] += 1

    def score(t):
        return (len(term_papers[t]), term_qs[t], len(t.split()))

    cands = [t for t in term_papers if quizgen.good_term(t) and term_qs[t] >= (2 if n_q >= 6 else 1) and term_qs[t] <= 0.6 * n_q]
    cands.sort(key=score, reverse=True)
    topics = []
    for t in cands:
        if any(t in c or c in t for c in (x["term"] for x in topics)):
            continue
        if n_papers > 1:
            pct = round(100 * len(term_papers[t]) / n_papers)
            note = f"in {len(term_papers[t])} of {n_papers} papers"
        else:
            pct = round(100 * term_qs[t] / n_q)
            note = f"in {term_qs[t]} of {n_q} questions"
        topics.append({"term": t, "percent": pct, "note": note, "questions": term_qs[t]})
        if len(topics) >= 8:
            break

    questions = []
    for pid, fname, q in all_q:
        topic = next((t["term"] for t in topics if t["term"] in _terms(q)), "Other")
        questions.append({"paper_id": pid, "paper": fname, "text": q, "topic": topic, "difficulty": _difficulty(q)})

    verbs = Counter((textproc.tokens(q["text"]) or [""])[0] for q in questions)
    patterns = [{"verb": v, "count": c} for v, c in verbs.most_common(6) if v in _COMMAND]
    diff = Counter(q["difficulty"] for q in questions)

    repeated = []
    if n_papers > 1 and n_q > 1:
        from sklearn.feature_extraction.text import TfidfVectorizer
        try:
            m = TfidfVectorizer(stop_words=list(textproc.STOP)).fit_transform([q["text"] for q in questions])
            sim = (m @ m.T).toarray()
            for i in range(n_q):
                for j in range(i + 1, n_q):
                    if questions[i]["paper_id"] != questions[j]["paper_id"] and sim[i][j] >= 0.75:
                        repeated.append({"a": questions[i]["text"][:140], "b": questions[j]["text"][:140],
                                         "papers": [questions[i]["paper"], questions[j]["paper"]]})
        except ValueError:
            pass

    return {
        "papers": [{"id": p["id"], "filename": p["filename"], "questions": len(p["questions"])} for p in papers],
        "question_count": n_q,
        "topics": topics,
        "difficulty": dict(diff),
        "patterns": patterns,
        "repeated": repeated[:5],
        "questions": questions,
        "note": "Frequently tested in the provided past papers. This does not predict what a future exam will contain.",
    }


def build_mock_exam(user_id: int, analysis: dict, course_id=None, count=10, duration_min=60, rng=None):
    """Creates a quiz row (kind='mock_exam'). Past-paper questions become open
    questions, ordered towards the most frequent topics, each with the best
    matching passage from the student's own material as a reference answer."""
    import random
    rng = rng or random.Random()
    qs = analysis["questions"][:]
    weight = {t["term"]: t["percent"] for t in analysis["topics"]}
    qs.sort(key=lambda q: -(weight.get(q["topic"], 0) + rng.random() * 15))
    n_open = max(1, round(count * 0.7))
    open_qs = qs[:n_open]

    items = []
    for q in open_qs:
        ref = retrieval.search_chunks(user_id, q["text"], course_id=course_id, k=1, min_score=0.15)
        reference = ""
        if ref:
            c = ref[0]
            reference = " ".join(c["text"].split())[:600] + f" (from {c['filename']}" + (f", page {c['page']}" if c["page"] else "") + ")"
        items.append({"qtype": "open", "prompt": q["text"], "options": [], "answer": reference, "explanation": "",
                      "topic": q["topic"] if q["topic"] != "Other" else None, "reference": reference})

    # fill the rest with generated multiple-choice questions from the student's material
    need = count - len(items)
    if need > 0:
        chunks = retrieval.scoped_chunks(user_id, course_id=course_id)
        items += quizgen.generate(chunks, need, "medium", ("mcq", "tf"), rng=rng)[:need]
    if not items:
        return None
    rng.shuffle(items)

    quiz_id = db.execute(
        "INSERT INTO quizzes (user_id, kind, title, source, course_id, duration_min) VALUES (?, 'mock_exam', ?, ?, ?, ?)",
        (user_id, "Mock exam", json.dumps({"type": "past_exams"}), course_id, duration_min),
    )
    db.executemany(
        "INSERT INTO quiz_questions (quiz_id, user_id, qtype, prompt, options, answer, explanation, topic, reference) VALUES (?,?,?,?,?,?,?,?,?)",
        [(quiz_id, user_id, q["qtype"], q["prompt"], json.dumps(q["options"]), q["answer"], q["explanation"], q["topic"], q["reference"]) for q in items],
    )
    return quiz_id
