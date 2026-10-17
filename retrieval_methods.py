"""
Three interchangeable retrieval methods over the same UTG knowledge base,
all sharing one interface:

    search(query) -> (answer, matched_question, confidence, source)

This is what lets evaluate.py benchmark all three against the same test
set under identical conditions, and lets the live assistant (via
config.RETRIEVAL_METHOD) use whichever one performs best once you've seen
the results.

Methods, roughly in order of sophistication:

    KeywordBaseline     Generalises the ORIGINAL prototype's approach
                         (`"x" in voice_data` substring checks) into a
                         comparable scorer: token overlap between the query
                         and each KB question. Deliberately simple -- this
                         is the baseline your dissertation's RQ1 measures
                         improvement against, not a method meant to win.

    TfidfRetrieval      TF-IDF + cosine similarity. What the assistant used
                         immediately before this upgrade. Matches on word
                         overlap weighted by how distinctive each word is,
                         but still has no notion of *meaning* -- "lecturer"
                         and "professor" are unrelated to it.

    EmbeddingRetrieval  Pretrained sentence-embedding similarity (the
                         all-MiniLM-L6-v2 model via sentence-transformers).
                         Matches on meaning, not just shared words, so it
                         should generalise better to paraphrased or
                         differently-worded questions. This is the one
                         worth reporting as your main contribution if it
                         outperforms the other two -- but let the
                         evaluation decide that, don't assume it.
"""

import json
import re

from config import KB_PATH, RETRIEVAL_THRESHOLDS, TFIDF_EXTRA_STOPWORDS


def _load_entries(path=KB_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "what", "which", "who", "whom", "where", "when", "why", "how",
    "i", "you", "it", "at", "in", "on", "for", "of", "to", "and", "or",
    "can", "could", "would", "should", "me", "my", "your", "about",
}


def _tokenize(text):
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


class KeywordBaseline:
    """Baseline: score = fraction of the query's non-stopword tokens that
    also appear in a KB question. This is a fair generalisation of what
    the original script's `"x" in voice_data` checks were doing -- matching
    on shared words, nothing more."""

    name = "keyword_baseline"

    def __init__(self, path=KB_PATH, similarity_threshold=None):
        self.entries = _load_entries(path)
        self._question_tokens = [set(_tokenize(e["question"])) for e in self.entries]
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else RETRIEVAL_THRESHOLDS["keyword"]
        )

    def search(self, query):
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return None, None, 0.0, None

        best_idx, best_score = None, 0.0
        for i, q_tokens in enumerate(self._question_tokens):
            if not q_tokens:
                continue
            overlap = len(query_tokens & q_tokens)
            score = overlap / len(query_tokens)
            if score > best_score:
                best_idx, best_score = i, score

        if best_idx is not None and best_score >= self.similarity_threshold:
            e = self.entries[best_idx]
            return e["answer"], e["question"], best_score, e.get("source")
        return None, None, best_score, None


class TfidfRetrieval:
    """TF-IDF + cosine similarity. See knowledge_base.py's git history (or
    the dissertation) for the empirical threshold-tuning that produced the
    default 0.45 -- short version: in-scope queries scored 0.55-0.97,
    clearly out-of-scope ones scored 0.00-0.37 on a small manual test."""

    name = "tfidf"

    def __init__(self, path=KB_PATH, similarity_threshold=None):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.entries = _load_entries(path)
        self.questions = [e["question"] for e in self.entries]
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else RETRIEVAL_THRESHOLDS["tfidf"]
        )
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

        stop_words = list(ENGLISH_STOP_WORDS | set(TFIDF_EXTRA_STOPWORDS))
        self._vectorizer = TfidfVectorizer(stop_words=stop_words).fit(self.questions)
        self._matrix = self._vectorizer.transform(self.questions)

    def search(self, query):
        from sklearn.metrics.pairwise import cosine_similarity

        if not query:
            return None, None, 0.0, None
        query_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._matrix)[0]
        best_idx = int(sims.argmax())
        best_score = float(sims[best_idx])
        if best_score >= self.similarity_threshold:
            e = self.entries[best_idx]
            return e["answer"], e["question"], best_score, e.get("source")
        return None, None, best_score, None


class EmbeddingRetrieval:
    """Pretrained sentence-embedding similarity. Downloads the model
    (~90MB) from Hugging Face the first time it's used, then caches it
    locally -- the first run needs internet, later runs don't."""

    name = "embeddings"
    _MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self, path=KB_PATH, similarity_threshold=None):
        from sentence_transformers import SentenceTransformer
        import numpy as np

        self._np = np
        self.entries = _load_entries(path)
        self.questions = [e["question"] for e in self.entries]
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else RETRIEVAL_THRESHOLDS["embeddings"]
        )
        self._model = SentenceTransformer(self._MODEL_NAME)
        self._matrix = self._model.encode(self.questions, normalize_embeddings=True)

    def search(self, query):
        if not query:
            return None, None, 0.0, None
        query_vec = self._model.encode([query], normalize_embeddings=True)[0]
        sims = self._matrix @ query_vec
        best_idx = int(self._np.argmax(sims))
        best_score = float(sims[best_idx])
        if best_score >= self.similarity_threshold:
            e = self.entries[best_idx]
            return e["answer"], e["question"], best_score, e.get("source")
        return None, None, best_score, None


METHODS = {
    "keyword": KeywordBaseline,
    "tfidf": TfidfRetrieval,
    "embeddings": EmbeddingRetrieval,
}
