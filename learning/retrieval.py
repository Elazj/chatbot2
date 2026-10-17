"""
Searching a student's own documents.

Every query starts with WHERE user_id = ? so another student's text can never
be returned, however the question is worded. Optional document_id /
course_id filters narrow the search further ("chat with this document").
The ranking itself is TF-IDF cosine similarity computed over just the chunks
that passed the filter.
"""

import db
from learning import textproc


def scoped_chunks(user_id: int, document_id=None, course_id=None, kinds=("material",)):
    sql = (
        "SELECT c.id, c.document_id, c.page, c.section, c.text, d.filename, d.kind "
        "FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.user_id = ? AND d.user_id = ? AND d.status = 'ready'"
    )
    params = [user_id, user_id]
    if document_id is not None:
        sql += " AND c.document_id = ?"
        params.append(document_id)
    if course_id is not None:
        sql += " AND d.course_id = ?"
        params.append(course_id)
    if kinds:
        sql += " AND d.kind IN (%s)" % ",".join("?" * len(kinds))
        params.extend(kinds)
    sql += " ORDER BY c.document_id, c.ord"
    return db.fetchall(sql, params)


def search_chunks(user_id: int, query: str, document_id=None, course_id=None, k=4, min_score=0.12, kinds=("material",)):
    chunks = scoped_chunks(user_id, document_id, course_id, kinds)
    if not chunks or not query.strip():
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    texts = [(c["section"] or "") + " " + c["text"] for c in chunks]
    try:
        vec = TfidfVectorizer(stop_words=list(textproc.STOP), sublinear_tf=True).fit(texts)
        scores = cosine_similarity(vec.transform([query]), vec.transform(texts))[0]
    except ValueError:  # query or documents contain no usable words
        return []
    order = scores.argsort()[::-1][:k]
    out = []
    for i in order:
        if scores[i] >= min_score:
            c = dict(chunks[i])
            c["score"] = float(scores[i])
            out.append(c)
    return out


def citation(chunk) -> dict:
    snippet = " ".join(chunk["text"].split())
    return {
        "document_id": chunk["document_id"],
        "filename": chunk["filename"],
        "page": chunk["page"],
        "section": chunk["section"],
        "snippet": snippet[:220] + ("..." if len(snippet) > 220 else ""),
    }
