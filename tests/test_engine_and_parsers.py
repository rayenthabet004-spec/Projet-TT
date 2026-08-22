"""Tests for engine detection and per-engine parsers."""

import pytest
from src.engine_detection import detect_engine, detect_engine_line
from src.parsers import parse_log_text, ErrorOccurrence
from src.parsers.postgres import parse_postgres_log_text
from src.parsers.mysql import parse_mysql_log_text, normalize_mysql_code


# ============================================================
# Engine detection
# ============================================================

class TestEngineDetection:
    def test_detect_oracle(self):
        text = """Sun Jul 05 14:23:11 2026
ORA-01555: snapshot too old: rollback segment number 7 with name "_SYSSMU7$" too small
Errors in file /u01/app/oracle/diag/rdbms/ttprod/ttprod1/trace/ttprod1_ora_12345.trc
ORA-00060: deadlock detected while waiting for resource"""
        assert detect_engine(text) == "oracle"

    def test_detect_postgres(self):
        text = """2026-08-20 14:23:11.456 UTC [12345] ERROR:  duplicate key value violates unique constraint "pk_users"
2026-08-20 14:23:11.456 UTC [12345] DETAIL:  Key (id)=(42) already exists.
2026-08-20 14:23:11.457 UTC [12345] STATEMENT:  INSERT INTO users (id, name) VALUES (42, 'test')
2026-08-20 14:23:12.100 UTC [12346] ERROR:  relation "nonexistent_table" does not exist (SQLSTATE 42P01)"""
        assert detect_engine(text) == "postgres"

    def test_detect_mysql_structured(self):
        text = """2026-08-20T14:23:11.456789Z 0 [ERROR] [MY-010457] [Server] --initialize specified but the data directory has files in it. Aborting.
2026-08-20T14:23:11.456790Z 0 [ERROR] [MY-013183] [InnoDB] Assertion failure: fil0fil.cc:2456:err == DB_SUCCESS"""
        assert detect_engine(text) == "mysql"

    def test_detect_mysql_classic(self):
        text = """ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: YES)
ERROR 2002 (HY000): Can't connect to local MySQL server through socket '/var/run/mysqld/mysqld.sock'"""
        assert detect_engine(text) == "mysql"

    def test_detect_postgres_keywords(self):
        text = """LOG:  database system is ready to accept connections
LOG:  autovacuum launcher started
WARNING:  pg_hba.conf entry should specify a valid authentication method"""
        assert detect_engine(text) == "postgres"

    def test_detect_fallback_oracle(self):
        """Empty or ambiguous text should fall back to oracle with confidence=0.0."""
        assert detect_engine("") == "oracle"
        assert detect_engine("some random text\nwith no db indicators\n") == "oracle"
        engine, conf = detect_engine("", return_confidence=True)
        assert engine == "oracle"
        assert conf == 0.0

    def test_detect_confidence_positive(self):
        text = "ORA-01555: snapshot too old\nORA-00060: deadlock detected"
        engine, conf = detect_engine(text, return_confidence=True)
        assert engine == "oracle"
        assert conf > 0.0

    def test_detect_engine_line_oracle(self):
        assert detect_engine_line("ORA-01555: snapshot too old") == "oracle"

    def test_detect_engine_line_postgres(self):
        assert detect_engine_line("ERROR:  duplicate key (SQLSTATE 23505)") == "postgres"

    def test_detect_engine_line_mysql(self):
        assert detect_engine_line("[ERROR] [MY-010457] [Server] data dir issue") == "mysql"

    def test_detect_engine_line_none(self):
        assert detect_engine_line("just a normal line") is None


# ============================================================
# PostgreSQL parser
# ============================================================

class TestPostgresParser:
    def test_parse_basic_error(self):
        text = """2026-08-20 14:23:11.456 UTC [12345] ERROR:  duplicate key value violates unique constraint "pk_users"
2026-08-20 14:23:11.456 UTC [12345] DETAIL:  Key (id)=(42) already exists."""
        occs = parse_postgres_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "23505"
        assert occs[0].line_number == 1
        assert occs[0].is_pseudo_code is False

    def test_parse_sqlstate_inline(self):
        text = '2026-08-20 14:23:12.100 UTC [12346] ERROR:  relation "foo" does not exist (SQLSTATE 42P01)'
        occs = parse_postgres_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "42P01"
        assert occs[0].is_pseudo_code is False

    def test_parse_fatal(self):
        text = '2026-08-20 10:00:00 UTC [1] FATAL:  password authentication failed for user "baduser"'
        occs = parse_postgres_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "28P01"
        assert occs[0].is_pseudo_code is False

    def test_parse_simple_format(self):
        text = "ERROR:  syntax error at or near \"SELCT\""
        occs = parse_postgres_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "42601"
        assert occs[0].is_pseudo_code is False

    def test_parse_multiple(self):
        text = """2026-08-20 14:00:00 UTC [1] ERROR:  deadlock detected
2026-08-20 14:00:01 UTC [2] ERROR:  too many connections for role "app_user"
2026-08-20 14:00:02 UTC [3] WARNING:  out of memory"""
        occs = parse_postgres_log_text(text)
        assert len(occs) == 3
        codes = {o.code for o in occs}
        assert "40P01" in codes  # deadlock
        assert "53300" in codes  # too many connections
        assert "53200" in codes  # out of memory
        for o in occs:
            assert o.is_pseudo_code is False

    def test_unknown_message_gets_level_code(self):
        text = "2026-08-20 14:00:00 UTC [1] ERROR:  something entirely unknown happened"
        occs = parse_postgres_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "PG-ERROR"
        assert occs[0].is_pseudo_code is True

    def test_context_window(self):
        text = """line before
2026-08-20 14:00:00 UTC [1] ERROR:  syntax error at or near "FOO"
line after"""
        occs = parse_postgres_log_text(text, context_window=1)
        assert len(occs) == 1
        assert "line before" in occs[0].context
        assert "line after" in occs[0].context

    def test_dispatch_via_parsers_init(self):
        text = "ERROR:  deadlock detected"
        occs = parse_log_text(text, engine="postgres")
        assert len(occs) == 1
        assert occs[0].code == "40P01"


# ============================================================
# MySQL parser
# ============================================================

class TestMySQLParser:
    def test_parse_structured_format(self):
        text = "2026-08-20T14:23:11.456789Z 0 [ERROR] [MY-010457] [Server] --initialize specified but data directory has files"
        occs = parse_mysql_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "MY-010457"
        assert occs[0].line_number == 1

    def test_parse_client_error(self):
        text = "ERROR 1045 (28000): Access denied for user 'root'@'localhost'"
        occs = parse_mysql_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "MY-001045"

    def test_parse_classic_format(self):
        text = "2026-08-20 14:23:11 12345 [ERROR] Deadlock found when trying to get lock"
        occs = parse_mysql_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "MY-001213"  # deadlock

    def test_parse_multiple(self):
        text = """2026-08-20T14:00:00.000000Z 0 [ERROR] [MY-010457] [Server] Data dir issue
2026-08-20T14:00:01.000000Z 0 [ERROR] [MY-013183] [InnoDB] Assertion failure
ERROR 1062 (23000): Duplicate entry '42' for key 'PRIMARY'"""
        occs = parse_mysql_log_text(text)
        assert len(occs) == 3

    def test_normalize_code(self):
        assert normalize_mysql_code("1045") == "MY-001045"
        assert normalize_mysql_code("010457") == "MY-010457"

    def test_skip_informational(self):
        """Shutdown/startup messages (code 0) should be skipped."""
        text = "2026-08-20 14:23:11 0 [ERROR] Shutdown complete"
        occs = parse_mysql_log_text(text)
        # Should be skipped (MY-000000)
        assert len(occs) == 0

    def test_warning_captured(self):
        text = "2026-08-20T14:00:00.000000Z 0 [Warning] [MY-013360] [Server] Plugin mysql_native_password reported"
        occs = parse_mysql_log_text(text)
        assert len(occs) == 1
        assert occs[0].code == "MY-013360"

    def test_context_window(self):
        text = """line before
2026-08-20T14:00:00.000000Z 0 [ERROR] [MY-010457] [Server] Some error
line after"""
        occs = parse_mysql_log_text(text, context_window=1)
        assert len(occs) == 1
        assert "line before" in occs[0].context
        assert "line after" in occs[0].context

    def test_dispatch_via_parsers_init(self):
        text = "ERROR 1045 (28000): Access denied for user 'root'@'localhost'"
        occs = parse_log_text(text, engine="mysql")
        assert len(occs) == 1
        assert occs[0].code == "MY-001045"


# ============================================================
# Oracle parser (basic sanity via dispatch)
# ============================================================

class TestOracleParserDispatch:
    def test_dispatch_oracle(self):
        text = "ORA-01555: snapshot too old: rollback segment number 7"
        occs = parse_log_text(text, engine="oracle")
        assert len(occs) == 1
        assert occs[0].code == "ORA-01555"
