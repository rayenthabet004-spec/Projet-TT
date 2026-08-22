"""
test_multi_engine_e2e.py

End-to-end smoke tests for the multi-engine pipeline — verifies that Oracle,
PostgreSQL, and MySQL logs can each flow through: engine detection -> parser
-> retriever -> generator -> report, producing valid output.
"""

import pytest
from src.rag.pipeline import analyze_log
from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever
from src.engine_detection import detect_engine


# Sample logs per engine

ORACLE_LOG = """Sun Jul 05 14:23:11 2026
Starting background process VKTM
Thread 1 advanced to log sequence 42
ORA-01555: snapshot too old: rollback segment number 7 with name "_SYSSMU7$" too small
Errors in file /u01/app/oracle/diag/rdbms/ttprod/ttprod1/trace/ttprod1_ora_12345.trc
ORA-00060: deadlock detected while waiting for resource
Beginning log switch checkpoint up to RBA
ORA-01555: snapshot too old: rollback segment number 7 with name "_SYSSMU7$" too small
"""

PG_LOG = """2026-08-20 14:23:11.456 UTC [12345] LOG:  database system is ready to accept connections
2026-08-20 14:23:12.100 UTC [12346] ERROR:  duplicate key value violates unique constraint "pk_users" (SQLSTATE 23505)
2026-08-20 14:23:12.101 UTC [12346] DETAIL:  Key (id)=(42) already exists.
2026-08-20 14:23:13.200 UTC [12347] ERROR:  relation "nonexistent_table" does not exist (SQLSTATE 42P01)
2026-08-20 14:23:14.300 UTC [12348] FATAL:  password authentication failed for user "baduser"
"""

MYSQL_LOG = """2026-08-20T14:23:11.456789Z 0 [System] [MY-010116] [Server] mysqld starting
2026-08-20T14:23:12.100000Z 0 [ERROR] [MY-010457] [Server] --initialize specified but the data directory has files in it.
2026-08-20T14:23:13.200000Z 0 [ERROR] [MY-013183] [InnoDB] Assertion failure: fil0fil.cc:2456:err == DB_SUCCESS
ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: YES)
"""


@pytest.fixture(scope="module")
def kb_and_retriever():
    """Load the combined KB once for all tests in this module."""
    kb = load_default_kb()
    retriever = Retriever(kb)
    return kb, retriever


class TestMultiEngineE2E:
    def test_oracle_detection_and_analysis(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        assert detect_engine(ORACLE_LOG) == "oracle"

        report = analyze_log(
            ORACLE_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False, engine="oracle"
        )
        assert report["engine"] == "oracle"
        assert report["total_error_occurrences"] >= 2
        assert report["unique_error_codes"] >= 2
        assert len(report["findings"]) >= 2

        codes = {f["code"] for f in report["findings"]}
        assert "ORA-01555" in codes
        assert "ORA-00060" in codes

        # Every finding should have explanation fields
        for f in report["findings"]:
            assert "explanation" in f
            assert f["explanation"]["meaning"]
            assert f["explanation"]["source"]

    def test_postgres_detection_and_analysis(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        assert detect_engine(PG_LOG) == "postgres"

        report = analyze_log(
            PG_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False, engine="postgres"
        )
        assert report["engine"] == "postgres"
        assert report["total_error_occurrences"] >= 2
        assert len(report["findings"]) >= 2

        codes = {f["code"] for f in report["findings"]}
        assert "23505" in codes or "42P01" in codes

        for f in report["findings"]:
            assert "explanation" in f
            assert f["explanation"]["meaning"]

    def test_mysql_detection_and_analysis(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        assert detect_engine(MYSQL_LOG) == "mysql"

        report = analyze_log(
            MYSQL_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False, engine="mysql"
        )
        assert report["engine"] == "mysql"
        assert report["total_error_occurrences"] >= 2
        assert len(report["findings"]) >= 2

        for f in report["findings"]:
            assert "explanation" in f
            assert f["explanation"]["meaning"]

    def test_auto_detection_oracle(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        report = analyze_log(
            ORACLE_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False
        )
        assert report["engine"] == "oracle"

    def test_auto_detection_postgres(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        report = analyze_log(
            PG_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False
        )
        assert report["engine"] == "postgres"

    def test_auto_detection_mysql(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        report = analyze_log(
            MYSQL_LOG, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False
        )
        assert report["engine"] == "mysql"

    def test_report_has_engine_field(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        for log, expected_engine in [(ORACLE_LOG, "oracle"), (PG_LOG, "postgres"), (MYSQL_LOG, "mysql")]:
            report = analyze_log(
                log, kb=kb, retriever=retriever, mode="mock",
                use_classifier=False
            )
            assert "engine" in report
            assert report["engine"] == expected_engine
            assert "engine_detection_confidence" in report
            assert report["engine_detection_confidence"] > 0.0

    def test_report_engine_warning_on_unrecognized_log(self, kb_and_retriever):
        kb, retriever = kb_and_retriever
        unrecognized_log = "This is a generic server log with no db patterns."
        report = analyze_log(
            unrecognized_log, kb=kb, retriever=retriever, mode="mock",
            use_classifier=False
        )
        assert "engine_detection_warning" in report
        assert "could not be reliably identified" in report["engine_detection_warning"]
        assert report["engine_detection_confidence"] == 0.0
