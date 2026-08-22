"""
retriever.py

Retrieval layer for the RAG pipeline.

Why BM25 instead of dense embeddings?
- Zero external model downloads: BM25 is a pure lexical/statistical ranking
  algorithm (rank_bm25 package), so it works completely offline the moment
  you `pip install rank_bm25` -- no HuggingFace/OpenAI model weights needed.
  This makes the whole project runnable in restricted/offline dev sandboxes.
- Oracle error codes and messages are short, structured, keyword-heavy text
  (e.g. "ORA-01555 snapshot too old rollback segment") -- exactly the kind of
  text where lexical matching (BM25) already performs very well, arguably
  better than embeddings for exact code/keyword matches.
- It's a legitimate documented approach in this space too (upgrade path
  noted below), not just a shortcut.

Upgrade path (documented for whoever continues this in Antigravity):
  Once you have real internet access (this was built in a sandboxed
  environment that could not reach huggingface.co), swap this out for a
  dense retriever using sentence-transformers (e.g. all-MiniLM-L6-v2) or an
  API-based embedding model, and/or combine both (hybrid BM25 + dense) for
  better recall on paraphrased/unusual log wording. The KnowledgeBase and
  Retriever interfaces below are written so that swap only touches this file.
"""

from typing import List, Optional, Tuple

from rank_bm25 import BM25Okapi

from src.rag.knowledge_base import KBEntry, KnowledgeBase
from src.log_parser import normalize_code, ERROR_CODE_RE


def _tokenize(text: str) -> List[str]:
    return text.lower().replace("-", " ").replace("_", " ").replace(".", " ").split()


class Retriever:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.corpus_tokens = [_tokenize(e.searchable_text()) for e in kb.entries]
        self.bm25 = BM25Okapi(self.corpus_tokens)

    def retrieve(self, query: str, k: int = 3, engine: Optional[str] = None) -> List[Tuple[KBEntry, float]]:
        """Return up to k (KBEntry, score) pairs ranked by BM25 relevance.
        If engine is specified, only considers KB entries matching that engine,
        falling back to cross-engine search only if zero same-engine candidates exist.
        """
        import heapq
        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)
        all_pairs = list(zip(self.kb.entries, scores))

        if engine:
            engine_lower = engine.lower()
            same_engine_pairs = [
                p for p in all_pairs
                if getattr(p[0], "engine", "oracle").lower() == engine_lower and p[1] > 0
            ]
            if same_engine_pairs:
                top_k = heapq.nlargest(k, same_engine_pairs, key=lambda x: x[1])
                return top_k

        # Fallback to cross-engine search if no engine specified or zero same-engine candidates
        top_k = heapq.nlargest(k, all_pairs, key=lambda x: x[1])
        return [pair for pair in top_k if pair[1] > 0]

    def retrieve_for_error(
        self,
        code: str,
        context_text: str,
        k: int = 3,
        is_pseudo_code: bool = False,
        engine: Optional[str] = None,
    ) -> List[Tuple[KBEntry, float]]:
        """The main entry point used by the pipeline: prioritize an exact
        error-code match (deterministic, always correct if the code is in
        our KB), then fall back to / supplement with BM25 over the
        surrounding log context so we still return *something* useful for
        codes not yet in the knowledge base.

        When is_pseudo_code is True (e.g. PG-ERROR, MY-WARNING), exact match
        lookup is bypassed so confidence is never artificially inflated to 'high'.
        When engine is provided, candidate retrieval is filtered to that engine.
        """
        code = normalize_code(code)
        results: List[Tuple[KBEntry, float]] = []

        is_pseudo = is_pseudo_code
        exact = None if is_pseudo else self.kb.get_exact(code)
        if exact is not None:
            if not engine or getattr(exact, "engine", "oracle").lower() == engine.lower():
                results.append((exact, 999.0))  # sentinel score: exact match always wins
            else:
                exact = None

        # supplement with lexical matches over code + context, skipping the
        # exact entry if we already added it
        query = context_text if is_pseudo else f"{code} {context_text}"
        for entry, score in self.retrieve(query, k=k + 1, engine=engine):
            if exact is not None and entry.code == exact.code:
                continue
            results.append((entry, score))
            if len(results) >= k:
                break

        return results[:k]
