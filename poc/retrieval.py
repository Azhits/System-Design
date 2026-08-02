"""
TF-IDF cosine-similarity retrieval over the knowledge base.

PoC simplification: TF-IDF bag-of-words.
Target architecture: replace with sentence-embeddings + vector DB
(pgvector / FAISS) — see docs/ml.md.
"""
from pathlib import Path
import json
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_PATH = Path(__file__).parent / "data" / "knowledge_base.json"


class KnowledgeBase:
    def __init__(self):
        with open(KB_PATH, encoding="utf-8") as f:
            self._items = json.load(f)
        self._texts = [item["question"] for item in self._items]
        self._vectorizer = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), max_features=3000, sublinear_tf=True
        )
        self._matrix = self._vectorizer.fit_transform(self._texts)

    def search(self, query: str, top_k: int = 1) -> list[dict]:
        """Return top_k most similar KB items with similarity scores."""
        qvec = self._vectorizer.transform([query])
        sims = cosine_similarity(qvec, self._matrix)[0]
        top_indices = sims.argsort()[::-1][:top_k]
        results = []
        for i in top_indices:
            item = dict(self._items[i])
            item["similarity"] = round(float(sims[i]), 3)
            results.append(item)
        return results


# Module-level singleton
_kb = KnowledgeBase()


def find_similar(query: str, top_k: int = 1) -> list[dict]:
    return _kb.search(query, top_k=top_k)
