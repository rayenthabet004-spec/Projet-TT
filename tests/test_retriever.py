import pytest

from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever


@pytest.fixture(scope="module")
def kb():
    return load_default_kb()


@pytest.fixture(scope="module")
def retriever(kb):
    return Retriever(kb)


def test_kb_loads_entries(kb):
    assert len(kb) > 40  # sanity check we have a real KB, not an empty/broken one


def test_kb_has_no_duplicate_codes(kb):
    codes = [e.code for e in kb.entries]
    assert len(codes) == len(set(codes))


def test_exact_match_wins_and_scores_highest(retriever):
    results = retriever.retrieve_for_error(
        "ORA-01555",
        "ORA-01555: snapshot too old: rollback segment number 3 too small",
        k=3,
    )
    assert results[0][0].code == "ORA-01555"
    assert results[0][1] >= 999.0


def test_normalization_still_hits_exact_match(retriever):
    # "ORA-1555" (no leading zero) should still resolve to the same KB entry
    results = retriever.retrieve_for_error("ORA-1555", "snapshot too old", k=3)
    assert results[0][0].code == "ORA-01555"


def test_unknown_code_falls_back_to_lexical_match(retriever):
    results = retriever.retrieve_for_error(
        "ORA-99999",
        "listener does not know service name tnsnames connect identifier",
        k=3,
    )
    assert len(results) > 0
    # none of these should be treated as an exact match (score should not hit the sentinel)
    assert all(score < 999.0 for _, score in results)


def test_free_text_retrieve_ranks_relevant_entries_first(retriever):
    results = retriever.retrieve("deadlock waiting for resource", k=3)
    top_codes = {r[0].code for r in results[:3]}
    assert "ORA-00060" in top_codes or "ORA-37013" in top_codes
