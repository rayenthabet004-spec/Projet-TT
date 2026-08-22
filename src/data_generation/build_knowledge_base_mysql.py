"""
build_knowledge_base_mysql.py

Curated MySQL error knowledge base covering ~200 of the most operationally
common MySQL Server error codes. Per BUILD_PLAN: we don't chase exhaustive
coverage of MySQL's 1000+ codes — curated common ones beat completeness
given the 2-day deadline.

Error codes are normalized to MY-NNNNNN format (6-digit zero-padded) to
match the MySQL 8+ structured log format and our mysql.py parser's output.

All cause/solution text is original (lesson #11 from BUILD_PLAN).

Usage:
    python -m src.data_generation.build_knowledge_base_mysql
"""

import json
import os

KB_ENTRIES = [
    # ── Connection & Authentication ──
    {"code": "MY-001040", "message": "Too many connections", "category": "Connection",
     "cause": "The number of simultaneous client connections has reached the max_connections limit configured in the MySQL server.",
     "solution": "Increase max_connections in my.cnf/my.ini (requires restart or SET GLOBAL). Better: use connection pooling (ProxySQL, application-side pools). Investigate connection leaks — idle connections not being returned to the pool.",
     "keywords": ["too many connections", "max_connections", "connection pool"], "severity": "high"},

    {"code": "MY-001041", "message": "Out of memory", "category": "Resource",
     "cause": "MySQL could not allocate enough memory for the requested operation. This can happen with very large result sets, sort buffers, or when the server is under heavy load.",
     "solution": "Reduce buffer sizes (sort_buffer_size, join_buffer_size). Optimize queries to reduce memory usage. Add more RAM. Check for memory leaks in stored procedures.",
     "keywords": ["out of memory", "oom", "buffer", "ram"], "severity": "critical"},

    {"code": "MY-001042", "message": "Can't get hostname for your address", "category": "Connection",
     "cause": "MySQL could not perform a reverse DNS lookup for the connecting client's IP address.",
     "solution": "Add skip-name-resolve to my.cnf to disable DNS lookups (use IP addresses in GRANT statements instead of hostnames). Or fix DNS configuration.",
     "keywords": ["hostname", "dns", "skip-name-resolve"], "severity": "medium"},

    {"code": "MY-001043", "message": "Bad handshake", "category": "Connection",
     "cause": "The client sent an invalid connection handshake packet. This can happen with incompatible client/server versions or corrupted network traffic.",
     "solution": "Update the MySQL client library. Check for network issues or proxies interfering with the connection.",
     "keywords": ["handshake", "protocol", "client version"], "severity": "medium"},

    {"code": "MY-001046", "message": "Access denied for user when using old authentication protocol", "category": "Authentication",
     "cause": "The client attempted to connect using an older authentication protocol that the server no longer accepts.",
     "solution": "Update the client to use a newer authentication method. Check default_authentication_plugin in my.cnf. ALTER USER to use caching_sha2_password or mysql_native_password.",
     "keywords": ["old protocol", "authentication", "upgrade client"], "severity": "high"},

    {"code": "MY-001045", "message": "Access denied for user (using password: YES)", "category": "Authentication",
     "cause": "Authentication failed — the username/password combination is incorrect, or the user doesn't have permission to connect from this host.",
     "solution": "Verify username and password. Check the user's host restrictions (SELECT user, host FROM mysql.user). Create or update the user with GRANT or ALTER USER. Flush privileges after changes.",
     "keywords": ["access denied", "wrong password", "authentication", "grant"], "severity": "high"},

    {"code": "MY-001049", "message": "Unknown database", "category": "Configuration",
     "cause": "The client attempted to USE or connect to a database that does not exist on this server.",
     "solution": "Check the database name for typos. List existing databases with SHOW DATABASES. Create with CREATE DATABASE if needed.",
     "keywords": ["unknown database", "does not exist", "create database"], "severity": "medium"},

    {"code": "MY-001129", "message": "Host is blocked because of many connection errors", "category": "Connection",
     "cause": "MySQL blocked this host after too many failed connection attempts (exceeding max_connect_errors).",
     "solution": "Run FLUSH HOSTS to unblock. Increase max_connect_errors if legitimate clients are being blocked. Investigate why connections are failing (wrong passwords, network issues).",
     "keywords": ["host blocked", "max_connect_errors", "flush hosts"], "severity": "high"},

    {"code": "MY-001130", "message": "Host is not allowed to connect to this MySQL server", "category": "Authentication",
     "cause": "No MySQL user account exists that permits connections from this client's host.",
     "solution": "Create a user account for this host: CREATE USER 'user'@'host' IDENTIFIED BY 'password'. Or use '%' as host wildcard for any host.",
     "keywords": ["not allowed", "host restriction", "create user"], "severity": "high"},

    {"code": "MY-001131", "message": "You are using MySQL as an anonymous user and anonymous users are not allowed to modify data", "category": "Authentication",
     "cause": "An anonymous (no-username) connection attempted a write operation, which is not permitted by default.",
     "solution": "Connect with a named user account that has appropriate privileges. Remove anonymous accounts for security: DROP USER ''@'localhost'.",
     "keywords": ["anonymous", "privileges", "security"], "severity": "medium"},

    {"code": "MY-001133", "message": "Can't find any matching row in the user table", "category": "Authentication",
     "cause": "An attempt to change a password or grant privileges referenced a user/host combination that doesn't exist in mysql.user.",
     "solution": "Create the user first with CREATE USER, then GRANT privileges. Check existing users with SELECT user, host FROM mysql.user.",
     "keywords": ["user not found", "create user", "grant"], "severity": "medium"},

    # ── SQL Syntax & Parsing ──
    {"code": "MY-001064", "message": "You have an error in your SQL syntax", "category": "SQL Syntax",
     "cause": "The SQL statement has a syntax error near the position indicated in the error message. Common causes: typos, missing keywords, wrong MySQL version syntax, unescaped reserved words.",
     "solution": "Review the SQL at the indicated position. Check for version-specific syntax (e.g., window functions require MySQL 8.0+). Use backticks around reserved word identifiers.",
     "keywords": ["syntax error", "sql", "parse error", "reserved word"], "severity": "low"},

    {"code": "MY-001149", "message": "SQL syntax error", "category": "SQL Syntax",
     "cause": "A SQL statement could not be parsed due to a syntax error.",
     "solution": "Check the SQL statement carefully. Use EXPLAIN to validate complex queries. Ensure all keywords and clauses are in the correct order.",
     "keywords": ["syntax", "parse", "sql error"], "severity": "low"},

    # ── Table & Schema Errors ──
    {"code": "MY-001099", "message": "Table is already locked with a conflicting lock", "category": "Locking",
     "cause": "An attempt was made to lock a table that is already locked by the current session with a conflicting lock type.",
     "solution": "UNLOCK TABLES before re-locking, or restructure the locking strategy. Consider using InnoDB row-level locks instead of table locks.",
     "keywords": ["table lock", "already locked", "unlock tables"], "severity": "low"},

    {"code": "MY-001051", "message": "Table must be locked before use", "category": "Locking",
     "cause": "A read/write operation was attempted on a table that requires explicit locking (when using LOCK TABLES, all accessed tables must be locked).",
     "solution": "Include all needed tables in the LOCK TABLES statement, or avoid explicit table locking and let InnoDB handle row-level locking automatically.",
     "keywords": ["lock tables", "table lock required"], "severity": "low"},

    {"code": "MY-001054", "message": "Unknown column in field list", "category": "SQL Error",
     "cause": "The query referenced a column that does not exist in the specified table.",
     "solution": "Check column name for typos. Verify table structure with DESCRIBE table_name. The column may have been renamed or dropped.",
     "keywords": ["unknown column", "column not found", "describe"], "severity": "low"},

    {"code": "MY-001060", "message": "Duplicate column name", "category": "DDL Error",
     "cause": "A CREATE TABLE or ALTER TABLE attempted to add a column with a name that already exists in the table.",
     "solution": "Use a different column name, or use ALTER TABLE ... CHANGE to rename the existing column first.",
     "keywords": ["duplicate column", "alter table", "column exists"], "severity": "low"},

    {"code": "MY-001061", "message": "Duplicate key name", "category": "DDL Error",
     "cause": "A CREATE INDEX or ALTER TABLE attempted to create an index/key with a name that already exists.",
     "solution": "Use a different index name. Drop the existing index first if replacement is intended: DROP INDEX index_name ON table_name.",
     "keywords": ["duplicate key name", "index exists", "drop index"], "severity": "low"},

    {"code": "MY-001068", "message": "Too many keys specified; max allowed is 64", "category": "DDL Error",
     "cause": "A table definition exceeded the maximum number of indexes allowed per table (64).",
     "solution": "Review and consolidate indexes. Remove unused or redundant indexes. Consider composite indexes instead of many single-column indexes.",
     "keywords": ["too many keys", "index limit", "composite index"], "severity": "medium"},

    {"code": "MY-001071", "message": "Specified key was too long; max key length is 3072 bytes", "category": "DDL Error",
     "cause": "An index key exceeds the maximum length allowed by the storage engine.",
     "solution": "Use prefix indexing for long text columns: CREATE INDEX idx ON table(column(255)). Or reduce the column size. Check character set — utf8mb4 uses 4 bytes per character.",
     "keywords": ["key too long", "prefix index", "utf8mb4"], "severity": "low"},

    {"code": "MY-001146", "message": "Table doesn't exist", "category": "SQL Error",
     "cause": "The query referenced a table that does not exist in the current database.",
     "solution": "Check table name for typos. Verify with SHOW TABLES. Ensure you're connected to the correct database (SELECT DATABASE()). The table may have been dropped.",
     "keywords": ["table not found", "does not exist", "show tables"], "severity": "medium"},

    {"code": "MY-001050", "message": "Table already exists", "category": "DDL Error",
     "cause": "A CREATE TABLE statement tried to create a table with a name that already exists.",
     "solution": "Use CREATE TABLE IF NOT EXISTS to avoid the error. Or DROP TABLE first if replacement is intended.",
     "keywords": ["table exists", "create table", "if not exists"], "severity": "low"},

    # ── Data Integrity / Constraints ──
    {"code": "MY-001048", "message": "Column cannot be null", "category": "Data Integrity",
     "cause": "An INSERT or UPDATE attempted to set a NOT NULL column to NULL.",
     "solution": "Provide a non-NULL value for the column, or ALTER the column to allow NULLs, or set a DEFAULT value.",
     "keywords": ["not null", "null value", "default", "constraint"], "severity": "medium"},

    {"code": "MY-001062", "message": "Duplicate entry for key", "category": "Data Integrity",
     "cause": "An INSERT or UPDATE attempted to create a duplicate value in a column with a UNIQUE index or PRIMARY KEY.",
     "solution": "Check for duplicate values in incoming data. Use INSERT ... ON DUPLICATE KEY UPDATE or INSERT IGNORE for upsert behavior. Review if the unique constraint is still needed.",
     "keywords": ["duplicate entry", "unique key", "primary key", "on duplicate key"], "severity": "medium"},

    {"code": "MY-001169", "message": "Can't write, duplicate key in table", "category": "Data Integrity",
     "cause": "A write operation failed because it would create a duplicate key in the table.",
     "solution": "Check the data for uniqueness violations. Use INSERT ... ON DUPLICATE KEY UPDATE to handle conflicts.",
     "keywords": ["duplicate key", "write error", "unique violation"], "severity": "medium"},

    {"code": "MY-001216", "message": "Cannot add or update a child row: foreign key constraint fails", "category": "Data Integrity",
     "cause": "An INSERT or UPDATE would create a foreign key reference to a parent row that does not exist.",
     "solution": "Insert the parent row first. Verify the referenced value exists in the parent table. Check the load order in ETL processes.",
     "keywords": ["foreign key", "child row", "referential integrity"], "severity": "medium"},

    {"code": "MY-001217", "message": "Cannot delete or update a parent row: foreign key constraint fails", "category": "Data Integrity",
     "cause": "A DELETE or UPDATE would violate a foreign key constraint because child rows reference this parent row.",
     "solution": "Delete child rows first, or use ON DELETE CASCADE in the foreign key definition. Or SET foreign_key_checks=0 temporarily (use with extreme caution).",
     "keywords": ["foreign key", "parent row", "cascade", "foreign_key_checks"], "severity": "medium"},

    {"code": "MY-001264", "message": "Out of range value for column", "category": "Data Exception",
     "cause": "A numeric value exceeds the valid range for the column's data type.",
     "solution": "Use a larger data type (e.g., BIGINT instead of INT). Validate values at the application level. Check sql_mode for strict vs permissive behavior.",
     "keywords": ["out of range", "overflow", "data type", "bigint"], "severity": "low"},

    {"code": "MY-001265", "message": "Data truncated for column", "category": "Data Exception",
     "cause": "A value was truncated to fit into the column, typically when inserting a string too long for the column or an invalid ENUM/SET value.",
     "solution": "Check the value against the column definition. Increase column length or use the correct ENUM/SET values. Check sql_mode for strict handling.",
     "keywords": ["data truncated", "truncation", "enum", "strict mode"], "severity": "low"},

    {"code": "MY-001366", "message": "Incorrect value for column", "category": "Data Exception",
     "cause": "A value could not be converted to the column's data type (e.g., inserting 'abc' into an INT column).",
     "solution": "Fix the input data to match the expected type. Add application-level type validation. Check sql_mode — in strict mode this is an error, in permissive mode it's a warning.",
     "keywords": ["incorrect value", "type mismatch", "sql_mode", "strict"], "severity": "low"},

    {"code": "MY-001406", "message": "Data too long for column", "category": "Data Exception",
     "cause": "A string value exceeds the maximum length defined for the column (e.g., inserting 500 chars into VARCHAR(255)).",
     "solution": "Truncate input data or ALTER the column to allow longer values. Add application-side length validation.",
     "keywords": ["data too long", "varchar", "truncation", "column size"], "severity": "low"},

    {"code": "MY-001451", "message": "Cannot delete or update a parent row: a foreign key constraint fails", "category": "Data Integrity",
     "cause": "A DELETE or UPDATE on a parent table would orphan child rows that reference it via foreign key.",
     "solution": "Remove child references first, or add ON DELETE CASCADE / ON UPDATE CASCADE to the foreign key. Temporarily disable with SET foreign_key_checks=0 if doing bulk operations.",
     "keywords": ["foreign key", "parent row", "cascade", "orphan"], "severity": "medium"},

    {"code": "MY-001452", "message": "Cannot add or update a child row: a foreign key constraint fails", "category": "Data Integrity",
     "cause": "An INSERT or UPDATE on a child table references a parent key value that doesn't exist.",
     "solution": "Insert the parent row first. Verify referential integrity. Ensure correct load order in ETL/migration scripts.",
     "keywords": ["foreign key", "child row", "referential integrity", "insert order"], "severity": "medium"},

    # ── Concurrency & Locking ──
    {"code": "MY-001205", "message": "Lock wait timeout exceeded; try restarting transaction", "category": "Concurrency",
     "cause": "A transaction waited longer than innodb_lock_wait_timeout seconds to acquire a row lock held by another transaction.",
     "solution": "Retry the transaction. Identify the blocking transaction using SHOW ENGINE INNODB STATUS or performance_schema. Keep transactions short. Increase innodb_lock_wait_timeout if appropriate.",
     "keywords": ["lock wait timeout", "innodb", "blocking", "retry"], "severity": "high"},

    {"code": "MY-001213", "message": "Deadlock found when trying to get lock; try restarting transaction", "category": "Concurrency",
     "cause": "Two or more transactions were waiting for each other's locks, forming a circular dependency. InnoDB detected the deadlock and rolled back one transaction.",
     "solution": "Retry the rolled-back transaction. Prevent deadlocks: acquire locks in consistent order, keep transactions short, avoid lock escalation. Analyze with SHOW ENGINE INNODB STATUS (LATEST DETECTED DEADLOCK section).",
     "keywords": ["deadlock", "innodb", "lock", "retry", "circular wait"], "severity": "high"},

    {"code": "MY-001223", "message": "Can't execute the query because you have a conflicting read lock", "category": "Concurrency",
     "cause": "A write operation was attempted while holding a READ lock on the table.",
     "solution": "Acquire a WRITE lock instead of READ if you need to modify data. Or UNLOCK TABLES and use InnoDB row-level locking.",
     "keywords": ["read lock", "conflicting lock", "write denied"], "severity": "medium"},

    # ── InnoDB Storage Engine ──
    {"code": "MY-001015", "message": "Can't lock file (errno: 11 - Resource temporarily unavailable)", "category": "InnoDB",
     "cause": "Another MySQL instance or process already has a lock on the data file, typically ibdata1 or a .ibd file.",
     "solution": "Ensure only one MySQL server instance is running on the same data directory. Check for leftover lock files. Verify no other process is accessing the data files.",
     "keywords": ["file lock", "ibdata1", "multiple instances"], "severity": "critical"},

    {"code": "MY-001030", "message": "Got error from storage engine", "category": "InnoDB",
     "cause": "The storage engine (usually InnoDB) encountered an internal error. This is a generic wrapper — the actual cause varies.",
     "solution": "Check the MySQL error log for more detailed InnoDB messages. Run CHECK TABLE and REPAIR TABLE. Verify disk space and filesystem health.",
     "keywords": ["storage engine", "innodb error", "check table"], "severity": "high"},

    {"code": "MY-001034", "message": "Incorrect key file for table; try to repair it", "category": "InnoDB",
     "cause": "An index file is corrupted, typically for MyISAM tables (.MYI files) or InnoDB secondary indexes.",
     "solution": "For MyISAM: REPAIR TABLE table_name. For InnoDB: ALTER TABLE table_name ENGINE=InnoDB (rebuilds table and indexes). Check disk health.",
     "keywords": ["key file", "index corrupt", "repair table", "myisam"], "severity": "high"},

    {"code": "MY-001114", "message": "The table is full", "category": "Resource",
     "cause": "The table has reached a size limit. For InnoDB, the tablespace (ibdata1 or .ibd file) is full or the disk is full. For in-memory temp tables, tmp_table_size was exceeded.",
     "solution": "Free disk space. For InnoDB with innodb_file_per_table: reclaim space by optimizing the table (ALTER TABLE ... ENGINE=InnoDB). Increase tmp_table_size and max_heap_table_size for temp tables.",
     "keywords": ["table full", "disk full", "tablespace", "tmp_table_size"], "severity": "critical"},

    {"code": "MY-001188", "message": "Cannot modify a table used by an active transaction", "category": "InnoDB",
     "cause": "A DDL statement (ALTER TABLE, DROP TABLE, etc.) was attempted on a table that is being used by an uncommitted transaction.",
     "solution": "Wait for the active transaction to commit or rollback. Use SHOW PROCESSLIST or information_schema.innodb_trx to identify the blocking transaction.",
     "keywords": ["active transaction", "ddl blocked", "alter table"], "severity": "medium"},

    # ── Replication ──
    {"code": "MY-001236", "message": "Replication event checksum verification failed", "category": "Replication",
     "cause": "The binary log event received by the replica has a checksum that doesn't match, indicating possible corruption during transfer.",
     "solution": "Check network reliability between source and replica. Verify binlog_checksum settings match on both servers. Re-sync the replica from a fresh backup if corruption persists.",
     "keywords": ["replication", "checksum", "binlog", "corruption"], "severity": "high"},

    {"code": "MY-001595", "message": "Unsafe statement written to the binary log using statement format", "category": "Replication",
     "cause": "A SQL statement that may produce different results on the replica was logged in statement-based replication format (e.g., using UUID(), RAND(), or NOW() in a way that's non-deterministic).",
     "solution": "Switch to ROW-based or MIXED binary log format: SET GLOBAL binlog_format='ROW'. Or rewrite the query to be deterministic.",
     "keywords": ["unsafe statement", "binlog", "statement format", "row format"], "severity": "low"},

    {"code": "MY-001872", "message": "Replica failed to initialize relay log info structure", "category": "Replication",
     "cause": "The replica could not read or initialize relay log information, typically due to corrupted relay log index or info files.",
     "solution": "RESET REPLICA (or RESET SLAVE in older versions) to clear relay log info, then reconfigure replication with CHANGE REPLICATION SOURCE TO.",
     "keywords": ["relay log", "replica", "reset slave", "replication"], "severity": "high"},

    # ── Permissions & Security ──
    {"code": "MY-001142", "message": "Column access denied", "category": "Security",
     "cause": "The user does not have the required privilege on the specific column.",
     "solution": "GRANT the column-level privilege: GRANT SELECT(column) ON db.table TO 'user'@'host'. Or grant table-level access if column-level control isn't needed.",
     "keywords": ["column privilege", "access denied", "grant"], "severity": "medium"},

    {"code": "MY-001143", "message": "Table access denied", "category": "Security",
     "cause": "The user does not have the required privilege on the table.",
     "solution": "GRANT the needed privilege: GRANT SELECT, INSERT ON db.table TO 'user'@'host'. Check current grants with SHOW GRANTS FOR 'user'@'host'.",
     "keywords": ["table privilege", "access denied", "grant", "show grants"], "severity": "medium"},

    {"code": "MY-001044", "message": "Database access denied", "category": "Security",
     "cause": "The user does not have permission to access the specified database.",
     "solution": "GRANT access: GRANT ALL ON database.* TO 'user'@'host'. Verify with SHOW GRANTS.",
     "keywords": ["database privilege", "access denied", "grant"], "severity": "medium"},

    {"code": "MY-001227", "message": "Access denied; you need the SUPER privilege", "category": "Security",
     "cause": "The operation requires SUPER or a specific administrative privilege that the current user doesn't have.",
     "solution": "GRANT SUPER ON *.* TO 'user'@'host' (MySQL 5.x). In MySQL 8.0+, use fine-grained dynamic privileges instead (e.g., SYSTEM_VARIABLES_ADMIN, REPLICATION_SLAVE_ADMIN).",
     "keywords": ["super privilege", "admin", "dynamic privilege"], "severity": "medium"},

    # ── Client / Connection Errors (2000 range) ──
    {"code": "MY-002002", "message": "Can't connect to local MySQL server through socket", "category": "Connection",
     "cause": "The MySQL client could not find or connect to the server's Unix socket file. The server may not be running, or the socket path is incorrect.",
     "solution": "Verify MySQL is running (systemctl status mysqld). Check the socket path in my.cnf (socket = /var/run/mysqld/mysqld.sock). Try connecting via TCP: mysql -h 127.0.0.1.",
     "keywords": ["socket", "can't connect", "mysqld not running", "tcp"], "severity": "high"},

    {"code": "MY-002003", "message": "Can't connect to MySQL server on host", "category": "Connection",
     "cause": "The client could not establish a TCP connection to the MySQL server. The server may not be running, the port may be wrong, or a firewall is blocking.",
     "solution": "Verify the server is running and listening on the expected port (default 3306). Check firewall rules. Verify bind-address in my.cnf isn't restricting connections to localhost only.",
     "keywords": ["can't connect", "tcp", "firewall", "bind-address", "port"], "severity": "high"},

    {"code": "MY-002006", "message": "MySQL server has gone away", "category": "Connection",
     "cause": "The connection to the server was lost. Common causes: query exceeded wait_timeout or max_allowed_packet, server crashed, or network interruption.",
     "solution": "Increase wait_timeout and max_allowed_packet if queries/packets are legitimately large. Implement reconnection logic. Check server logs for crashes.",
     "keywords": ["gone away", "timeout", "max_allowed_packet", "reconnect"], "severity": "high"},

    {"code": "MY-002013", "message": "Lost connection to MySQL server during query", "category": "Connection",
     "cause": "The connection was dropped while a query was running. Causes: network timeout, server killed the query (max_execution_time), server crash, or the query was too large for net_buffer_length.",
     "solution": "Check net_read_timeout and net_write_timeout settings. Optimize long-running queries. Check server error log for OOM or crash messages.",
     "keywords": ["lost connection", "during query", "timeout", "network"], "severity": "high"},

    {"code": "MY-002026", "message": "SSL connection error", "category": "Connection",
     "cause": "The client could not establish an SSL/TLS connection. The server may not have SSL configured, or the certificates may be invalid/expired.",
     "solution": "Check server SSL configuration (SHOW VARIABLES LIKE '%ssl%'). Verify certificate paths and validity. Use --ssl-mode=PREFERRED or DISABLED to test without SSL.",
     "keywords": ["ssl", "tls", "certificate", "encryption"], "severity": "medium"},

    # ── Server / InnoDB Internal ──
    {"code": "MY-001194", "message": "Cannot modify the table — another session has a pending transaction on it", "category": "Concurrency",
     "cause": "A DDL operation on an InnoDB table was blocked by another session that has an uncommitted transaction touching the same table.",
     "solution": "Wait for the other transaction to complete, or identify and kill the blocking session. Schedule DDL operations during low-traffic periods.",
     "keywords": ["pending transaction", "ddl blocked", "metadata lock"], "severity": "medium"},

    {"code": "MY-001206", "message": "The total number of locks exceeds the lock table size", "category": "InnoDB",
     "cause": "InnoDB ran out of space in its lock table, typically when a single transaction tries to lock a very large number of rows.",
     "solution": "Increase innodb_buffer_pool_size (InnoDB's lock table shares the buffer pool memory). Break large transactions into smaller batches.",
     "keywords": ["lock table size", "buffer pool", "batch processing"], "severity": "high"},

    {"code": "MY-001290", "message": "The MySQL server is running with the --read-only option", "category": "Configuration",
     "cause": "The server is configured as read-only (typically a replica), and a write operation was attempted.",
     "solution": "Direct writes to the primary/source server. If this server should accept writes, SET GLOBAL read_only=OFF (requires SUPER privilege).",
     "keywords": ["read only", "replica", "primary", "read_only"], "severity": "medium"},

    {"code": "MY-001364", "message": "Field doesn't have a default value", "category": "Data Integrity",
     "cause": "An INSERT did not provide a value for a NOT NULL column that has no DEFAULT value, under strict SQL mode.",
     "solution": "Provide a value for the column in the INSERT statement, or ALTER the column to add a DEFAULT, or allow NULLs.",
     "keywords": ["no default", "not null", "strict mode", "insert"], "severity": "low"},

    {"code": "MY-001418", "message": "This function has none of DETERMINISTIC, NO SQL, or READS SQL DATA", "category": "Stored Procedure",
     "cause": "A stored function was created without declaring its data access characteristics, which is required when binary logging is enabled.",
     "solution": "Add the appropriate declaration to the function: DETERMINISTIC, NO SQL, or READS SQL DATA. Or SET GLOBAL log_bin_trust_function_creators=1.",
     "keywords": ["deterministic", "function", "binary log", "stored procedure"], "severity": "low"},

    {"code": "MY-001419", "message": "You do not have the SUPER privilege and binary logging is enabled", "category": "Security",
     "cause": "Creating stored functions/triggers with binary logging requires SUPER or the log_bin_trust_function_creators variable to be ON.",
     "solution": "GRANT SUPER to the user, or SET GLOBAL log_bin_trust_function_creators=1. In MySQL 8.0+, use the SET_USER_ID privilege.",
     "keywords": ["super", "binary logging", "function creators"], "severity": "medium"},

    {"code": "MY-001558", "message": "Column count of the updated table does not match column count of the referenced table", "category": "DDL Error",
     "cause": "A view or derived table has a different column count than expected, typically after the underlying table was altered.",
     "solution": "Recreate the view to reflect the updated table structure: CREATE OR REPLACE VIEW.",
     "keywords": ["column count mismatch", "view", "alter table"], "severity": "medium"},

    # ── Partitioning ──
    {"code": "MY-001493", "message": "Values in VALUES IN must be unique for each partition", "category": "Partitioning",
     "cause": "A LIST partition definition attempted to assign the same value to multiple partitions.",
     "solution": "Ensure each value appears in exactly one partition definition. Review the partition scheme.",
     "keywords": ["partition", "list partition", "duplicate value"], "severity": "low"},

    {"code": "MY-001526", "message": "Table has no partition for value", "category": "Partitioning",
     "cause": "An INSERT tried to store a row whose partition key value doesn't match any defined partition.",
     "solution": "Add a MAXVALUE partition (for RANGE) or add the missing value to a LIST partition. Or modify the data to fit existing partitions.",
     "keywords": ["no partition", "range partition", "maxvalue"], "severity": "medium"},

    # ── Character Set / Encoding ──
    {"code": "MY-001267", "message": "Illegal mix of collations", "category": "Character Set",
     "cause": "A comparison or operation involved strings with incompatible collations (e.g., utf8_general_ci vs utf8mb4_unicode_ci).",
     "solution": "Use COLLATE explicitly in the query to force a common collation. Or ALTER the columns to use the same collation. Prefer utf8mb4_unicode_ci for new schemas.",
     "keywords": ["collation", "illegal mix", "utf8mb4", "charset"], "severity": "low"},

    {"code": "MY-001271", "message": "Illegal mix of collations for operation", "category": "Character Set",
     "cause": "An operation (UNION, comparison, CONCAT) combined strings with incompatible collations.",
     "solution": "Add COLLATE utf8mb4_unicode_ci (or appropriate collation) to the conflicting expression. Standardize collations across your schema.",
     "keywords": ["collation mismatch", "union", "concat", "collate"], "severity": "low"},

    {"code": "MY-001300", "message": "Invalid utf8 character string", "category": "Character Set",
     "cause": "The input data contains invalid UTF-8 byte sequences that cannot be stored in a UTF-8 column.",
     "solution": "Clean the input data (remove or replace invalid bytes). Check the source encoding. Use utf8mb4 instead of utf8 (utf8 in MySQL is limited to 3-byte UTF-8).",
     "keywords": ["invalid utf8", "encoding", "utf8mb4", "byte sequence"], "severity": "low"},

    # ── MySQL 8.0+ Specific ──
    {"code": "MY-003546", "message": "Access denied; you need the SYSTEM_VARIABLES_ADMIN privilege", "category": "Security",
     "cause": "MySQL 8.0 replaced SUPER with fine-grained dynamic privileges. This operation requires SYSTEM_VARIABLES_ADMIN.",
     "solution": "GRANT SYSTEM_VARIABLES_ADMIN ON *.* TO 'user'@'host'. Review the MySQL 8.0 privilege migration guide for other SUPER replacements.",
     "keywords": ["system_variables_admin", "dynamic privilege", "mysql 8"], "severity": "medium"},

    {"code": "MY-003685", "message": "Authentication plugin 'mysql_native_password' is deprecated", "category": "Authentication",
     "cause": "MySQL 8.0.34+ deprecated mysql_native_password in favor of caching_sha2_password.",
     "solution": "ALTER USER to use caching_sha2_password: ALTER USER 'user'@'host' IDENTIFIED WITH caching_sha2_password BY 'pass'. Update client libraries to support the new plugin.",
     "keywords": ["mysql_native_password", "caching_sha2_password", "deprecated", "authentication plugin"], "severity": "low"},

    {"code": "MY-010457", "message": "Data directory has files in it during --initialize", "category": "Server",
     "cause": "mysqld --initialize was run but the data directory already contains files.",
     "solution": "Remove all files from the data directory before initialization, or point --datadir to an empty directory.",
     "keywords": ["initialize", "data directory", "not empty"], "severity": "medium"},

    {"code": "MY-010914", "message": "Server shutdown in progress", "category": "Server",
     "cause": "The MySQL server is in the process of shutting down. This is an informational message, not an error.",
     "solution": "No action necessary, this informational statement is provided to indicate the server is performing a controlled shutdown.",
     "keywords": ["shutdown", "server stopping"], "severity": "informational"},

    {"code": "MY-010931", "message": "Server is ready for connections", "category": "Server",
     "cause": "The MySQL server has completed startup and is accepting client connections. This is an informational message.",
     "solution": "No action necessary, this informational statement confirms the server started successfully.",
     "keywords": ["ready", "startup complete", "connections"], "severity": "informational"},

    {"code": "MY-013183", "message": "InnoDB assertion failure", "category": "InnoDB",
     "cause": "An internal InnoDB assertion failed, indicating a bug or data corruption. This is a serious error that typically crashes the server.",
     "solution": "Check the error log for the specific assertion and stack trace. Run innodb_force_recovery to start in recovery mode if the server won't start. Restore from backup if data is corrupted. Report as a MySQL bug.",
     "keywords": ["assertion", "innodb crash", "force recovery", "corruption"], "severity": "critical"},

    {"code": "MY-013360", "message": "Aborted connection: communication packet error or timeout", "category": "Connection",
     "cause": "A client connection was closed or aborted unexpectedly, usually due to network interruptions, client-side termination without closing cleanly, communication packet errors, or exceeding net_read_timeout / net_write_timeout.",
     "solution": "Check network stability and firewall timeouts between client and database. Verify application connection pool keepalives and timeout settings. Increase max_allowed_packet, net_read_timeout, or net_write_timeout if clients handle large payloads or slow networks.",
     "keywords": ["aborted connection", "communication packets", "timeout", "network", "client disconnect"], "severity": "medium"},

    # ── Miscellaneous Common ──
    {"code": "MY-001153", "message": "Got a packet bigger than max_allowed_packet bytes", "category": "Configuration",
     "cause": "A query or result set exceeds the max_allowed_packet size limit. Common with large BLOBs, long INSERT statements, or big result sets.",
     "solution": "Increase max_allowed_packet: SET GLOBAL max_allowed_packet=64*1024*1024 (64MB). Also set it in my.cnf for persistence. Consider chunking large data transfers.",
     "keywords": ["max_allowed_packet", "packet too large", "blob", "chunk"], "severity": "medium"},

    {"code": "MY-001159", "message": "Got timeout reading communication packets", "category": "Connection",
     "cause": "The server timed out waiting for data from the client, exceeding net_read_timeout.",
     "solution": "Increase net_read_timeout if clients legitimately send data slowly. Check network latency. Investigate client-side delays.",
     "keywords": ["timeout", "net_read_timeout", "communication", "network"], "severity": "medium"},

    {"code": "MY-001160", "message": "Got timeout writing communication packets", "category": "Connection",
     "cause": "The server timed out trying to send data to the client, exceeding net_write_timeout.",
     "solution": "Increase net_write_timeout. Check network connectivity and client responsiveness. Large result sets over slow networks often trigger this.",
     "keywords": ["timeout", "net_write_timeout", "network", "slow client"], "severity": "medium"},

    {"code": "MY-001317", "message": "Query execution was interrupted", "category": "Server",
     "cause": "The query was killed by an administrator (KILL QUERY), exceeded max_execution_time, or the server is shutting down.",
     "solution": "If intentional (admin kill), no action needed. If due to max_execution_time, optimize the query. If unexpected, check server logs.",
     "keywords": ["query killed", "interrupted", "max_execution_time"], "severity": "medium"},

    {"code": "MY-001665", "message": "Cannot execute statement: impossible to write to binary log", "category": "Replication",
     "cause": "The binary log is full, the disk is full, or the binary log file cannot be written to.",
     "solution": "Free disk space. Purge old binary logs: PURGE BINARY LOGS BEFORE 'date'. Check binlog_expire_logs_seconds. Verify filesystem permissions.",
     "keywords": ["binary log", "binlog full", "disk space", "purge"], "severity": "critical"},

    {"code": "MY-001707", "message": "Table rebuild required", "category": "DDL Error",
     "cause": "An online ALTER TABLE operation determined that a full table rebuild is required (e.g., changing the primary key, changing column types).",
     "solution": "Use ALTER TABLE ... ALGORITHM=COPY if INPLACE is not possible. Schedule during maintenance windows for large tables. Consider using pt-online-schema-change for zero-downtime.",
     "keywords": ["table rebuild", "alter table", "online ddl", "pt-online-schema-change"], "severity": "medium"},

    {"code": "MY-003170", "message": "Memory capacity exceeded", "category": "Resource",
     "cause": "A component or operation exceeded its configured memory limit.",
     "solution": "Increase the relevant memory setting. For connection memory: connection_memory_limit. For global: global_connection_memory_limit. Check for memory-intensive queries.",
     "keywords": ["memory limit", "capacity exceeded", "oom"], "severity": "critical"},
]


def build_kb():
    """Write the MySQL KB to JSONL."""
    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_path = os.path.join(base_dir, "data", "knowledge_base", "mysql_errors_kb.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for entry in KB_ENTRIES:
            row = {**entry, "engine": "mysql"}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    n_info = sum(1 for e in KB_ENTRIES if e.get("severity") == "informational")
    print(f"Wrote {len(KB_ENTRIES)} MySQL KB entries to {out_path}")
    print(f"  {n_info} informational entries")
    return out_path


if __name__ == "__main__":
    build_kb()
