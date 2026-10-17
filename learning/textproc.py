"""
Plain text-processing helpers shared by summaries, quizzes and flashcards.

Everything here is rule-based or classical statistics (word counts, TF-IDF,
PageRank over sentence similarity). There is no language model, so results
are *extractive*: they select and rearrange sentences that are really in the
student's material, they never write new facts.
"""

import re
from collections import Counter

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

STOP = set(ENGLISH_STOP_WORDS) | {"also", "may", "using", "use", "used", "one", "two", "etc", "eg", "ie", "figure", "table", "page"}

_WS = re.compile(r"[ \t\u00a0]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")

DEF_RE = re.compile(
    r"^(?P<term>[A-Z][A-Za-z0-9\-/ ()]{2,60}?)\s+"
    r"(?:is|are|refers to|refer to|means|is defined as|are defined as|can be defined as|is known as|are known as)\s+"
    r"(?P<body>.{15,300})$"
)
_BAD_TERM_START = ("this", "that", "these", "those", "it", "there", "which", "who", "what", "here", "the following", "another", "each", "one")


def clean(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)          # re-join words hyphenated across lines
    text = _WS.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sentences(text: str, min_len: int = 25, max_len: int = 400):
    out = []
    for para in re.split(r"\n\s*\n|\n(?=[-•*\u2022] )", clean(text)):
        para = " ".join(para.split())
        for s in _SENT_SPLIT.split(para):
            s = s.strip(" -•*\u2022")
            if min_len <= len(s) <= max_len and len(_WORD.findall(s)) >= 5:
                out.append(s)
    return out


def tokens(text: str):
    return [t.lower().strip("-'") for t in _WORD.findall(text)]


def content_tokens(text: str):
    return [t for t in tokens(text) if t not in STOP and len(t) > 2]


def keyphrases(text: str, n: int = 12):
    """Most characteristic terms (single words and two-word phrases), keeping
    the capitalisation they most often appear with."""
    uni, bi, surface = Counter(), Counter(), {}
    for sent in re.split(r"[.!?\n]+", text):
        words = _WORD.findall(sent)
        prev = None
        for w in words:
            lw = w.lower().strip("-'")
            if lw in STOP or len(lw) < 3:
                prev = None
                continue
            uni[lw] += 1
            surface.setdefault(lw, Counter())[w] += 1
            if prev:
                bi[f"{prev} {lw}"] += 1
            prev = lw
    scored = {}
    for t, c in uni.items():
        scored[t] = c
    for t, c in bi.items():
        if c >= 2:
            scored[t] = c * 1.6
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    picked, taken = [], set()
    for term, _ in ranked:
        parts = term.split()
        if any(p in taken for p in parts) and len(parts) == 1:
            continue
        picked.append(term)
        taken.update(parts)
        if len(picked) >= n:
            break

    def show(t):
        return " ".join(surface[p].most_common(1)[0][0] if p in surface else p for p in t.split())
    return [show(t) for t in picked]


def extractive_summary(text: str, n: int = 5):
    """TextRank-style: rank sentences by how similar they are to the rest."""
    sents = sentences(text)
    if len(sents) <= n:
        return sents
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    try:
        m = TfidfVectorizer(stop_words=list(STOP)).fit_transform(sents)
    except ValueError:
        return sents[:n]
    sim = (m @ m.T).toarray()
    np.fill_diagonal(sim, 0)
    rowsum = sim.sum(axis=1)
    rowsum[rowsum == 0] = 1
    trans = sim / rowsum[:, None]
    score = np.ones(len(sents)) / len(sents)
    for _ in range(40):
        score = 0.15 / len(sents) + 0.85 * trans.T @ score
    top = sorted(np.argsort(-score)[:n])
    return [sents[i] for i in top]


def definitions(text: str, limit: int = 60):
    """[(term, full defining sentence)] for sentences shaped like 'X is ...'."""
    out, seen = [], set()
    for s in sentences(text, min_len=30, max_len=330):
        m = DEF_RE.match(s)
        if not m:
            continue
        term = re.sub(r"^(?:A|An|The)\s+", "", m.group("term").strip())
        low = term.lower()
        if low.startswith(_BAD_TERM_START) or len(term.split()) > 6 or low in seen:
            continue
        seen.add(low)
        out.append((term, s))
        if len(out) >= limit:
            break
    return out


_FORMULA = re.compile(r"(?:[A-Za-z][A-Za-z0-9_()\[\] ]{0,25}\s=\s[^=]{2,60}|O\([^)]{1,20}\))")


def formulas(text: str, limit: int = 15):
    out = []
    for line in clean(text).splitlines():
        line = line.strip()
        if 4 < len(line) < 90 and _FORMULA.search(line) and not line.endswith("?"):
            out.append(line)
            if len(out) >= limit:
                break
    return out


_HEADING_NUM = re.compile(r"^(\d+(\.\d+){0,3}|[IVX]+\.|[A-Z]\.)\s+[A-Z][\w ,&/()\-:']{2,70}$")


def is_heading(line: str) -> bool:
    line = line.strip()
    if not 3 <= len(line) <= 80 or line.endswith((".", ",", ";")) or sum(c.isdigit() for c in line) > len(line) / 3:
        return False
    if _HEADING_NUM.match(line):
        return True
    words = line.split()
    if len(words) > 9:
        return False
    if line.isupper() and len(line) >= 4 and len(words) <= 6:
        return True
    capital = sum(1 for w in words if w[0].isupper())
    return len(words) >= 2 and capital >= max(2, len(words) - 1) and not line.endswith("?")
