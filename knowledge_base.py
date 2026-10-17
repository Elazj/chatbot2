"""
Thin wrapper around retrieval_methods.py so main.py / gui.py / app.py don't
need to change: they still do `kb = KnowledgeBase()` and `kb.search(query)`
exactly as before. Which actual method runs underneath (keyword baseline,
TF-IDF, or embeddings) is controlled by config.RETRIEVAL_METHOD.

For comparing all three methods against each other on a labelled test set,
see evaluate.py -- that's the piece that actually produces evaluation
results, this file just wires one method into the live assistant.
"""

from config import RETRIEVAL_METHOD
from retrieval_methods import METHODS


class KnowledgeBase:
    def __init__(self, method: str = None):
        method_name = method or RETRIEVAL_METHOD
        method_cls = METHODS.get(method_name)
        if method_cls is None:
            raise ValueError(
                f"Unknown retrieval method {method_name!r}. "
                f"Choose from: {list(METHODS)}"
            )
        self.method_name = method_name
        self._impl = method_cls()

    def search(self, query: str):
        return self._impl.search(query)
