from src.rag.pipeline import analyze_log, report_to_markdown

SAMPLE_LOG = """\
Wed Jul 01 00:03:01 2026
Starting background process VKTM
ORA-01555: snapshot too old: rollback segment number 3 with name "_SYSSMU3$" too small
Wed Jul 01 00:05:11 2026
ORA-12154: TNS:could not resolve the connect identifier specified
ORA-01555: snapshot too old: rollback segment number 7 with name "_SYSSMU7$" too small
"""


def test_analyze_log_end_to_end_mock_mode():
    report = analyze_log(SAMPLE_LOG, mode="mock")
    assert report["total_error_occurrences"] == 3
    assert report["unique_error_codes"] == 2

    codes_found = {f["code"] for f in report["findings"]}
    assert "ORA-01555" in codes_found
    assert "ORA-12154" in codes_found

    # ORA-01555 appeared twice -> should be the top finding after sort-by-count
    assert report["findings"][0]["code"] == "ORA-01555"
    assert report["findings"][0]["occurrence_count"] == 2

    # exact KB match should produce a high-confidence, grounded explanation
    exp = report["findings"][0]["explanation"]
    assert exp["confidence"] == "high"
    assert exp["source"] == "kb_exact_match"
    assert "undo" in exp["likely_cause"].lower() or "rollback" in exp["likely_cause"].lower()


def test_analyze_log_handles_no_errors_gracefully():
    report = analyze_log("just a normal log line\nanother normal line\n", mode="mock")
    assert report["total_error_occurrences"] == 0
    assert report["unique_error_codes"] == 0
    assert report["findings"] == []


def test_report_to_markdown_renders_without_error():
    report = analyze_log(SAMPLE_LOG, mode="mock")
    md = report_to_markdown(report)
    assert "ORA-01555" in md
    assert "Suggested solution" in md


def test_analyze_log_with_classifier():
    # ORA-16111 is an informational LOGSTDBY message
    log = "LOGSTDBY status: ORA-16111: log mining and apply setting up\n"
    report = analyze_log(log, mode="mock", use_classifier=True)
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert "classification" in finding
    assert finding["classification"]["label"] == "INFORMATIONAL"
    assert finding["classification"]["is_real_error"] is False


def test_analyze_log_filter_informational():
    log = "LOGSTDBY status: ORA-16111: log mining and apply setting up\nORA-01555: snapshot too old\n"
    report = analyze_log(log, mode="mock", use_classifier=True, filter_informational=True)
    codes_found = [f["code"] for f in report["findings"]]
    assert "ORA-01555" in codes_found
    assert "ORA-16111" not in codes_found

