"""
Document summaries (extractive).

Each summary is built from sentences that are really in the document, ranked
by how central they are to the text. Nothing is paraphrased or invented, so
nothing can be wrong in a way the document isn't, but the result reads like
highlights, not like a rewritten summary.
"""

from collections import OrderedDict

import db
from learning import retrieval, textproc

MODES = ("quick", "detailed", "chapter", "exam")


def _sections(user_id, document_id):
    rows = db.fetchall(
        "SELECT section, page, text FROM document_chunks WHERE document_id = ? AND user_id = ? ORDER BY ord",
        (document_id, user_id))
    sections = OrderedDict()
    for r in rows:
        key = r["section"] or "Document"
        s = sections.setdefault(key, {"pages": set(), "text": []})
        if r["page"]:
            s["pages"].add(r["page"])
        s["text"].append(r["text"])
    return sections


def _pages(pages):
    pages = sorted(pages)
    if not pages:
        return ""
    return f" (page {pages[0]})" if len(pages) == 1 else f" (pages {pages[0]}-{pages[-1]})"


def summarize(user_id: int, document_id: int, mode: str = "quick"):
    """Returns {"markdown": str, "sources": [..]} or None if the document isn't the student's / has no text."""
    doc = db.fetchone("SELECT id, filename FROM documents WHERE id = ? AND user_id = ? AND status = 'ready'", (document_id, user_id))
    if not doc:
        return None
    sections = _sections(user_id, document_id)
    if not sections:
        return None
    full = "\n\n".join("\n".join(s["text"]) for s in sections.values())
    md = [f"**{mode.capitalize()} summary of {doc['filename']}**", ""]

    if mode == "quick":
        for s in textproc.extractive_summary(full, 4):
            md.append(f"- {s}")
    elif mode == "detailed":
        for name, s in sections.items():
            pts = textproc.extractive_summary("\n".join(s["text"]), 3)
            if pts:
                md += [f"### {name}{_pages(s['pages'])}"] + [f"- {p}" for p in pts] + [""]
    elif mode == "chapter":
        md.append("Pick a section and ask about it, for example: *explain " + next(iter(sections)) + "*.")
        md.append("")
        for name, s in sections.items():
            pts = textproc.extractive_summary("\n".join(s["text"]), 1)
            md.append(f"- **{name}**{_pages(s['pages'])}: {pts[0] if pts else ''}")
    else:  # exam
        defs = textproc.definitions(full, 12)
        if defs:
            md += ["### Definitions to know"] + [f"- **{t}**: {s}" for t, s in defs] + [""]
        forms = textproc.formulas(full, 8)
        if forms:
            md += ["### Formulas and expressions"] + [f"- `{f}`" for f in forms] + [""]
        keys = textproc.keyphrases(full, 10)
        if keys:
            md += ["### Key terms that appear often", ", ".join(keys), ""]
        biggest = sorted(sections.items(), key=lambda kv: -len(" ".join(kv[1]["text"])))[:4]
        md += ["### Sections with the most material"] + [f"- {n}{_pages(s['pages'])}" for n, s in biggest]
        md += ["", "*These are the most repeated terms and the longest sections in your document. They are not a forecast of exam questions.*"]

    if len(md) <= 2:
        md.append("This document doesn't contain enough sentence-style text to summarise.")
    srcs = [{"document_id": doc["id"], "filename": doc["filename"], "page": None, "section": None, "snippet": ""}]
    return {"markdown": "\n".join(md).strip(), "sources": srcs, "title": doc["filename"]}
