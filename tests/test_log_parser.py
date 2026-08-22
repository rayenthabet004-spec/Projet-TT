from src.log_parser import normalize_code, parse_log_text, summarize_occurrences


def test_normalize_code_pads_ora_codes():
    assert normalize_code("ORA-1652") == "ORA-01652"
    assert normalize_code("ORA-600") == "ORA-00600"
    assert normalize_code("ORA-01555") == "ORA-01555"


def test_normalize_code_leaves_other_prefixes_alone():
    # Non-ORA prefixes are left as-is; we haven't seen padding inconsistency
    # for these in practice, so we don't guess a width for them.
    assert normalize_code("TNS-12154") == "TNS-12154"


def test_parse_log_text_finds_basic_error():
    text = "some line\nORA-01555: snapshot too old: rollback segment number 3\nnext line"
    occs = parse_log_text(text)
    assert len(occs) == 1
    assert occs[0].code == "ORA-01555"
    assert occs[0].line_number == 2


def test_parse_log_text_dedupes_via_normalization():
    text = "ORA-01652: unable to extend temp segment\nORA-1652 signalled during: INSERT"
    occs = parse_log_text(text)
    codes = [o.code for o in occs]
    assert codes == ["ORA-01652", "ORA-01652"]


def test_parse_log_text_captures_context_window():
    text = "\n".join([f"line{i}" for i in range(5)] + ["ORA-00600: internal error"] + [f"line{i}" for i in range(5, 10)])
    occs = parse_log_text(text, context_window=2)
    assert len(occs) == 1
    # context should include 2 lines before and after the match
    assert "line3" in occs[0].context
    assert "line4" in occs[0].context
    assert "line5" in occs[0].context
    assert "line6" in occs[0].context


def test_summarize_occurrences_counts_and_sorts():
    text = "ORA-00001: dup\nORA-00001: dup\nORA-00600: internal"
    occs = parse_log_text(text)
    summary = summarize_occurrences(occs)
    assert summary[0]["code"] == "ORA-00001"
    assert summary[0]["count"] == 2
    assert summary[1]["code"] == "ORA-00600"
    assert summary[1]["count"] == 1


def test_no_false_positives_on_plain_text():
    text = "This is a completely normal line with no error codes in it at all."
    occs = parse_log_text(text)
    assert occs == []
