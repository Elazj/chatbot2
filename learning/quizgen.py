"""
Rule-based question and flashcard generation from a student's own text.

IMPORTANT: this is not an AI model. It finds definition sentences
("X is ..."), picks key terms, blanks them out, and builds wrong options from
other terms in the same material. That works well for definitional,
term-heavy material and poorly for worked examples, diagrams or maths. Every
question carries the source sentence as its explanation so the student can
always check it against their own material.
"""

import random
import re

from learning import textproc

TYPE_WEIGHTS = {
    "easy":   {"mcq": 0.60, "tf": 0.30, "short": 0.10},
    "medium": {"mcq": 0.45, "tf": 0.25, "short": 0.30},
    "hard":   {"mcq": 0.40, "tf": 0.25, "short": 0.35},
}


def _topic_of(chunk):
    return (chunk.get("section") or chunk.get("filename") or "General").strip()[:80]


_GENERIC = set("""occurs occur ensures ensure guarantees guarantee means mean requires require removes remove holds hold
survive survives happen happens performed perform references reference creates create provides provide allows allow
contains contain includes include represents represent describes describe defines define uses shows show gives give
makes make takes take helps help called based known whether either each every other another same different various several
many much most more less large small important common following given certain particular specific general example examples
process value values thing things way ways case cases part parts number type types kind kinds""".split())


def good_term(t: str) -> bool:
    words = t.lower().split()
    if not words or len(t) < 3:
        return False
    for w in words:
        if w in _GENERIC or w in textproc.STOP or w.endswith(("ed", "ing", "ly")):
            return False
    return True


def build_pool(chunks):
    units, defs, all_text = [], [], []
    for c in chunks:
        topic = _topic_of(c)
        all_text.append(c["text"])
        for s in textproc.sentences(c["text"]):
            units.append({"s": s, "topic": topic, "chunk": c})
        for term, sent in textproc.definitions(c["text"]):
            defs.append({"term": term, "s": sent, "topic": topic})
    defined = [d["term"] for d in defs]
    extra = [t for t in textproc.keyphrases("\n".join(all_text), 80)
             if 3 <= len(t) <= 32 and good_term(t) and t.lower() not in {d.lower() for d in defined}]
    return {"units": units, "defs": defs, "terms": defined + extra, "defined": defined}


def _distractors(correct, pool, topic, n=3, same_topic_first=False, rng=random, avoid_in=""):
    base = pool["defined"] if len(pool["defined"]) >= n + 1 else pool["terms"]
    cands = [t for t in base if t.lower() != correct.lower() and t.lower() not in avoid_in.lower()]
    if same_topic_first:
        same = [d["term"] for d in pool["defs"] if d["topic"] == topic and d["term"].lower() != correct.lower()]
        cands = same + [c for c in cands if c not in same]
    seen, out = set(), []
    pool_list = cands[:] if same_topic_first else rng.sample(cands, len(cands))
    for c in pool_list:
        if c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
        if len(out) == n:
            break
    return out


def _def_body(d):
    m = textproc.DEF_RE.match(d["s"])
    body = (m.group("body") if m else d["s"]).rstrip(".")
    return re.sub(r"^that\s+", "", body)


def _mcq_from_def(d, pool, difficulty, rng):
    body = _def_body(d)
    ds = _distractors(d["term"], pool, d["topic"], same_topic_first=(difficulty == "hard"), rng=rng)
    if len(ds) < 3:
        return None
    opts = ds + [d["term"]]
    rng.shuffle(opts)
    return {"qtype": "mcq", "prompt": f"Which term is described by: \"{body}\"?", "options": opts,
            "answer": d["term"], "explanation": d["s"], "topic": d["topic"], "reference": d["s"]}


def _short_from_def(d):
    return {"qtype": "short", "prompt": f"In your own words, what is {d['term']}?", "options": [],
            "answer": _def_body(d), "explanation": d["s"], "topic": d["topic"], "reference": d["s"]}


def _find_term(sentence, terms):
    best = None
    low = sentence.lower()
    for t in terms:
        i = low.find(t.lower())
        if i > 0 and (best is None or len(t) > len(best[0])):
            if re.search(r"\b" + re.escape(t.lower()) + r"\b", low):
                best = (t, i)
    return best[0] if best else None


def _mcq_cloze(u, pool, difficulty, rng):
    n = len(u["s"].split())
    if not 8 <= n <= (22 if difficulty == "easy" else 34):
        return None
    term = _find_term(u["s"], pool["terms"])
    if not term:
        return None
    blanked = re.sub(re.escape(term), "_____", u["s"], count=1, flags=re.I)
    ds = _distractors(term, pool, u["topic"], same_topic_first=(difficulty == "hard"), rng=rng, avoid_in=u["s"])
    if len(ds) < 3:
        return None
    opts = ds + [term]
    rng.shuffle(opts)
    return {"qtype": "mcq", "prompt": "Fill in the blank: " + blanked, "options": opts, "answer": term,
            "explanation": u["s"], "topic": u["topic"], "reference": u["s"]}


def _tf(u, pool, difficulty, rng):
    n = len(u["s"].split())
    if not 8 <= n <= 30:
        return None
    term = _find_term(u["s"], pool["terms"])
    make_false = rng.random() < 0.5
    if make_false and term:
        same = [d["term"] for d in pool["defs"] if d["topic"] == u["topic"]]
        base = same if difficulty == "hard" and len(same) > 2 else (pool["defined"] if len(pool["defined"]) > 2 else pool["terms"])
        cands = [t for t in base
                 if t.lower() != term.lower() and t.lower() not in u["s"].lower()]
        if cands:
            swap = rng.choice(cands)
            stmt = re.sub(re.escape(term), swap, u["s"], count=1, flags=re.I)
            return {"qtype": "tf", "prompt": stmt, "options": ["True", "False"], "answer": "False",
                    "explanation": "Not quite. Your material says: " + u["s"], "topic": u["topic"], "reference": u["s"]}
    return {"qtype": "tf", "prompt": u["s"], "options": ["True", "False"], "answer": "True",
            "explanation": "Correct. This is from your material.", "topic": u["topic"], "reference": u["s"]}


def generate(chunks, count=10, difficulty="medium", types=("mcq", "tf", "short"), rng=None):
    """Returns up to `count` questions (fewer if the material is too short)."""
    rng = rng or random.Random()
    difficulty = difficulty if difficulty in TYPE_WEIGHTS else "medium"
    types = [t for t in types if t in ("mcq", "tf", "short")] or ["mcq"]
    pool = build_pool(chunks)
    if not pool["units"]:
        return []

    cands = {"mcq": [], "tf": [], "short": []}
    defs = pool["defs"][:]
    rng.shuffle(defs)
    for d in defs:
        q = _mcq_from_def(d, pool, difficulty, rng)
        if q:
            cands["mcq"].append(q)
        cands["short"].append(_short_from_def(d))
    units = pool["units"][:]
    rng.shuffle(units)
    for u in units:
        q = _mcq_cloze(u, pool, difficulty, rng)
        if q:
            cands["mcq"].append(q)
        q = _tf(u, pool, difficulty, rng)
        if q:
            cands["tf"].append(q)
    if "short" in types and len(cands["short"]) < 3:   # not enough definitions: ask about key sentences
        for u in units[:10]:
            term = _find_term(u["s"], pool["terms"])
            if term:
                cands["short"].append({"qtype": "short", "prompt": f"Explain what your material says about {term}.",
                                       "options": [], "answer": u["s"], "explanation": u["s"], "topic": u["topic"], "reference": u["s"]})

    weights = {t: TYPE_WEIGHTS[difficulty][t] for t in types}
    total = sum(weights.values())
    quota = {t: max(1, round(count * w / total)) for t, w in weights.items()}
    chosen, used = [], set()

    def take(kind, k):
        got = 0
        for q in cands[kind]:
            key = re.sub(r"\W+", " ", q["prompt"]).lower()[:90]
            if key in used:
                continue
            used.add(key)
            chosen.append(q)
            got += 1
            if got == k:
                break
        return got

    for t in types:
        take(t, quota[t])
    for t in types:                                   # top up from any requested type
        if len(chosen) >= count:
            break
        take(t, count - len(chosen))
    chosen = chosen[:count]
    rng.shuffle(chosen)
    return chosen


# --------------------------------------------------------------- grading

def grade(question, response) -> float:
    """Score 0..1 for one answer. MCQ/true-false are exact; short answers are
    scored by how many of the key words of the model answer the student used."""
    resp = (response or "").strip()
    if not resp:
        return 0.0
    if question["qtype"] in ("mcq", "tf"):
        return 1.0 if resp.lower() == question["answer"].strip().lower() else 0.0
    key = {t for t in textproc.content_tokens(question["answer"])}
    if not key:
        return 0.0
    got = len(key & set(textproc.content_tokens(resp))) / len(key)
    return 1.0 if got >= 0.5 else (0.5 if got >= 0.3 else 0.0)


# ------------------------------------------------------------ flashcards

def flashcards(chunks, count=20, rng=None):
    """[{front, back, topic}] from definitions, then fill-in-the-blank cards."""
    rng = rng or random.Random()
    pool = build_pool(chunks)
    cards, seen = [], set()
    for d in pool["defs"]:
        if d["term"].lower() in seen:
            continue
        seen.add(d["term"].lower())
        cards.append({"front": f"What is {d['term']}?", "back": _def_body(d) + ".", "topic": d["topic"]})
    units = pool["units"][:]
    rng.shuffle(units)
    for u in units:
        if len(cards) >= count:
            break
        term = _find_term(u["s"], pool["terms"])
        if term and 8 <= len(u["s"].split()) <= 28 and term.lower() not in seen:
            seen.add(term.lower())
            cards.append({"front": re.sub(re.escape(term), "_____", u["s"], count=1, flags=re.I), "back": term, "topic": u["topic"]})
    return cards[:count]


def cards_from_note_text(text, topic=None):
    """Lines like 'Term: definition' or 'Q: ... A: ...' become cards."""
    cards = []
    for line in text.splitlines():
        line = line.strip(" -*\t")
        m = re.match(r"^(?:Q:|Question:)\s*(.+?)\s+(?:A:|Answer:)\s*(.+)$", line, re.I)
        if m:
            cards.append({"front": m.group(1), "back": m.group(2), "topic": topic})
            continue
        m = re.match(r"^([A-Za-z][\w \-/()]{1,50}):\s+(.{8,300})$", line)
        if m:
            cards.append({"front": f"What is {m.group(1).strip()}?", "back": m.group(2).strip(), "topic": topic})
    return cards
