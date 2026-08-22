"""
build_knowledge_base.py

Builds the Oracle error knowledge base used by the RAG retriever.

HOW TO EXTEND THIS DATASET
---------------------------
1. Manually: add more dicts to KB_ENTRIES below, following the same schema.
2. Semi-automatically: use scrape_oracle_docs.py (in this same folder) to pull
   additional official "Cause / Action" text directly from Oracle's own
   documentation pages on YOUR machine (needs real internet access, which the
   sandbox this was originally built in does not have). Read the docstring in
   that file first -- it has notes on responsible/internal use.
3. From real logs: once you get access to real Tunisie Telecom logs, mine the
   unique error codes that appear and add any codes missing from this KB.

Run this file directly to (re)generate the JSONL knowledge base file:
    python src/data_generation/build_knowledge_base.py
"""

import json
import os

KB_ENTRIES = [
    # ---------------- Data integrity / constraints ----------------
    {
        "code": "ORA-00001",
        "message": "Unique constraint violated",
        "category": "Data Integrity",
        "cause": "An INSERT or UPDATE tried to write a value into a column (or set of columns) that is protected by a unique index or primary key, and that value already exists in another row.",
        "solution": "Check the incoming data for duplicates before writing it, add application-level de-duplication, or catch the exception and decide whether to update the existing row instead of inserting a new one. If duplicates should legitimately be allowed, the unique constraint itself may need to be reviewed.",
        "keywords": ["duplicate key", "unique index", "insert", "update", "primary key"],
        "severity": "medium",
    },
    {
        "code": "ORA-02290",
        "message": "Check constraint violated",
        "category": "Data Integrity",
        "cause": "A row failed to satisfy a CHECK constraint defined on the table, e.g. a value fell outside an allowed range or failed a validation rule.",
        "solution": "Inspect the failing row's values against the constraint definition (query USER_CONSTRAINTS / USER_CONS_COLUMNS), fix the offending data at the source, or adjust the constraint if the business rule has changed.",
        "keywords": ["check constraint", "validation", "invalid value"],
        "severity": "low",
    },
    {
        "code": "ORA-02291",
        "message": "Integrity constraint violated - parent key not found",
        "category": "Data Integrity",
        "cause": "An INSERT or UPDATE referenced a foreign key value that does not exist in the parent table.",
        "solution": "Insert the parent row first, correct the foreign key value being used, or verify the ETL/load order so parent tables are always populated before child tables.",
        "keywords": ["foreign key", "parent key", "referential integrity"],
        "severity": "medium",
    },
    {
        "code": "ORA-02292",
        "message": "Integrity constraint violated - child record found",
        "category": "Data Integrity",
        "cause": "An attempt to DELETE a parent row failed because dependent (child) rows still reference it through a foreign key.",
        "solution": "Delete or reassign the child rows first, use ON DELETE CASCADE on the foreign key if that behavior is desired, or confirm the delete should really happen given the dependent data.",
        "keywords": ["foreign key", "delete", "child record", "cascade"],
        "severity": "medium",
    },
    {
        "code": "ORA-00955",
        "message": "Name is already used by an existing object",
        "category": "Data Integrity",
        "cause": "A CREATE statement used a name (table, index, view, etc.) that is already taken in that schema.",
        "solution": "Choose a different object name, drop the existing object first if it's no longer needed, or use CREATE OR REPLACE for views/procedures where supported.",
        "keywords": ["create table", "name conflict", "ddl"],
        "severity": "low",
    },

    # ---------------- Space management ----------------
    {
        "code": "ORA-01652",
        "message": "Unable to extend temp segment",
        "category": "Space Management",
        "cause": "A sort, hash join, or temporary table operation ran out of space in the assigned temporary tablespace because it either has no room left or autoextend is disabled/capped.",
        "solution": "Add a datafile to the temporary tablespace, enable/raise AUTOEXTEND and MAXSIZE, or tune the query (better indexing, smaller sort area) so it needs less temp space.",
        "keywords": ["temp tablespace", "sort", "hash join", "extend"],
        "severity": "high",
    },
    {
        "code": "ORA-01654",
        "message": "Unable to extend index",
        "category": "Space Management",
        "cause": "An index could not grow because its tablespace ran out of free space or hit a MAXEXTENTS limit.",
        "solution": "Add space to the tablespace (new datafile or enable autoextend), rebuild the index in a tablespace with more room, or check for unnecessary large indexes that could be dropped.",
        "keywords": ["index", "tablespace full", "extend", "maxextents"],
        "severity": "high",
    },
    {
        "code": "ORA-01658",
        "message": "Unable to create INITIAL extent for segment in tablespace",
        "category": "Space Management",
        "cause": "There isn't enough contiguous free space in the tablespace to allocate even the first extent for a new segment (table, index, LOB, etc.).",
        "solution": "Add a datafile, enable autoextend on existing datafiles, or free up space by dropping/purging unused objects and emptying the recycle bin.",
        "keywords": ["initial extent", "tablespace full", "create table"],
        "severity": "high",
    },
    {
        "code": "ORA-01631",
        "message": "Max # extents reached in table/index",
        "category": "Space Management",
        "cause": "A segment hit the MAXEXTENTS limit set in its storage clause and cannot allocate any further extents, even if the tablespace itself has free space.",
        "solution": "Increase MAXEXTENTS (or set it to UNLIMITED) for the segment, or move the segment to a tablespace using modern extent management (locally managed) where this limit rarely applies.",
        "keywords": ["maxextents", "storage clause", "extents"],
        "severity": "medium",
    },
    {
        "code": "ORA-01555",
        "message": "Snapshot too old",
        "category": "Space Management",
        "cause": "A long-running query needed a read-consistent view of data, but the undo (rollback) information it depended on was already overwritten by other transactions -- usually because UNDO_RETENTION is too low or the undo tablespace is too small for the workload.",
        "solution": "Increase UNDO_RETENTION and/or the size of the undo tablespace, shorten long-running queries (batch them, add indexes), and avoid designs that fetch a cursor across long gaps or commits.",
        "keywords": ["undo", "rollback segment", "read consistency", "long running query"],
        "severity": "high",
    },
    {
        "code": "ORA-30036",
        "message": "Unable to extend segment by in undo tablespace",
        "category": "Space Management",
        "cause": "The undo tablespace ran out of space, typically caused by a mix of long transactions and a high volume of changes with insufficient undo capacity.",
        "solution": "Increase the undo tablespace size or enable autoextend, commit large batch jobs more frequently, and review UNDO_RETENTION settings.",
        "keywords": ["undo tablespace", "extend", "space"],
        "severity": "high",
    },
    {
        "code": "ORA-00257",
        "message": "Archiver error, connect internal only until freed",
        "category": "Space Management",
        "cause": "The archive log destination is full (or unreachable), so the database can no longer archive redo logs and has stopped normal connections to protect data.",
        "solution": "Free up space in the archive destination (back up and delete old archived logs with RMAN), add space to the destination, or add/enable an alternate archive destination.",
        "keywords": ["archive log", "archiver", "disk full"],
        "severity": "critical",
    },

    # ---------------- Performance / concurrency ----------------
    {
        "code": "ORA-00060",
        "message": "Deadlock detected while waiting for resource",
        "category": "Concurrency",
        "cause": "Two or more sessions each hold a lock the other needs, creating a circular wait. Oracle detects this and automatically kills one of the sessions' statements to break the cycle.",
        "solution": "Review the application's transaction and locking order so all sessions acquire resources in a consistent sequence, keep transactions short, and add retry logic for the rolled-back session.",
        "keywords": ["deadlock", "lock", "concurrency", "transaction"],
        "severity": "high",
    },
    {
        "code": "ORA-04031",
        "message": "Unable to allocate shared memory (shared pool)",
        "category": "Memory",
        "cause": "The shared pool ran out of contiguous free memory, usually from fragmentation caused by many hard-parsed (non-reusable) SQL statements, or the shared pool is simply undersized.",
        "solution": "Use bind variables to reduce hard parsing, increase SHARED_POOL_SIZE (or let it grow via MEMORY_TARGET / SGA_TARGET), and as a short-term relief flush the shared pool (ALTER SYSTEM FLUSH SHARED_POOL).",
        "keywords": ["shared pool", "memory", "hard parse", "fragmentation"],
        "severity": "critical",
    },
    {
        "code": "ORA-04036",
        "message": "PGA memory used by the instance exceeds PGA_AGGREGATE_LIMIT",
        "category": "Memory",
        "cause": "One or more sessions (often those doing large sorts, hash joins, or PL/SQL collections) consumed enough private memory that the instance-wide PGA limit was hit.",
        "solution": "Identify the memory-hungry sessions/SQL and tune them, raise PGA_AGGREGATE_LIMIT if the hardware allows it, or add controls (resource manager, better indexing) to reduce per-session memory use.",
        "keywords": ["pga", "memory", "aggregate limit"],
        "severity": "high",
    },
    {
        "code": "ORA-01000",
        "message": "Maximum open cursors exceeded",
        "category": "Concurrency",
        "cause": "A session opened more cursors than the OPEN_CURSORS parameter allows, almost always because application code isn't closing cursors/result sets properly.",
        "solution": "Fix the code to close cursors/statements after use (or use cursor sharing/connection pooling correctly), and consider raising OPEN_CURSORS as a safety margin, not a substitute for the fix.",
        "keywords": ["open cursors", "cursor leak", "resource limit"],
        "severity": "medium",
    },
    {
        "code": "ORA-00018",
        "message": "Maximum number of sessions exceeded",
        "category": "Resource Limits",
        "cause": "More concurrent sessions were requested than the SESSIONS initialization parameter allows.",
        "solution": "Increase the SESSIONS parameter (and PROCESSES, which it derives from), investigate whether connections are being leaked/not returned to the pool, and tune connection pool sizing in the application tier.",
        "keywords": ["sessions", "resource limit", "connections"],
        "severity": "high",
    },
    {
        "code": "ORA-00020",
        "message": "Maximum number of processes exceeded",
        "category": "Resource Limits",
        "cause": "The number of OS processes/threads serving the database exceeded the PROCESSES initialization parameter.",
        "solution": "Increase PROCESSES (and SESSIONS accordingly), check for connection leaks in applications, and consider a connection pooler if many short-lived connections are being opened.",
        "keywords": ["processes", "resource limit", "connections"],
        "severity": "high",
    },
    {
        "code": "ORA-02391",
        "message": "Exceeded simultaneous SESSIONS_PER_USER limit",
        "category": "Resource Limits",
        "cause": "A specific user account tried to open more concurrent sessions than allowed by their profile's SESSIONS_PER_USER limit.",
        "solution": "Raise the SESSIONS_PER_USER limit in the user's profile if legitimate, or investigate why that account is opening so many sessions (runaway job, leaked connections, shared credential misuse).",
        "keywords": ["sessions per user", "profile", "resource limit"],
        "severity": "medium",
    },
    {
        "code": "ORA-02049",
        "message": "Timeout: distributed transaction waiting for lock",
        "category": "Concurrency",
        "cause": "A distributed transaction (across database links) has been waiting too long to acquire a lock held by another transaction, and the DISTRIBUTED_LOCK_TIMEOUT was reached.",
        "solution": "Investigate the blocking session (often on the remote database), shorten transactions that span database links, and consider whether the distributed design can be simplified.",
        "keywords": ["distributed transaction", "database link", "lock timeout"],
        "severity": "medium",
    },

    # ---------------- Connectivity / network (TNS) ----------------
    {
        "code": "TNS-12154",
        "message": "TNS: could not resolve the connect identifier specified",
        "category": "Connectivity",
        "cause": "The client could not find the service name/alias it was given in any naming method it's configured to use -- most often a missing or misspelled entry in tnsnames.ora, or TNS_ADMIN pointing to the wrong directory.",
        "solution": "Check that tnsnames.ora contains the exact alias being used, confirm TNS_ADMIN / ORACLE_HOME environment variables point to the right file, and verify NAMES.DIRECTORY_PATH in sqlnet.ora includes TNSNAMES.",
        "keywords": ["tnsnames", "connect identifier", "service name"],
        "severity": "medium",
    },
    {
        "code": "TNS-12514",
        "message": "TNS: listener does not currently know of service requested in connect descriptor",
        "category": "Connectivity",
        "cause": "The listener is running, but the specific service name in the connection string hasn't registered with it yet (or never will, due to misconfiguration).",
        "solution": "Run 'lsnrctl services' to see what the listener currently knows about, confirm the SERVICE_NAMES parameter on the database matches what the client is requesting, and check whether the instance has registered with the listener (or wait, if it just started).",
        "keywords": ["listener", "service name", "connect descriptor"],
        "severity": "medium",
    },
    {
        "code": "TNS-12505",
        "message": "TNS: listener does not currently know of SID given in connect descriptor",
        "category": "Connectivity",
        "cause": "The client connected using a SID (not a service name) that the listener doesn't recognize -- often a stale SID after an instance rename, or a typo.",
        "solution": "Verify the correct SID with the DBA (or switch the connection string to use SERVICE_NAME instead of SID), and check the listener's static/dynamic registration.",
        "keywords": ["listener", "sid", "connect descriptor"],
        "severity": "medium",
    },
    {
        "code": "TNS-12541",
        "message": "TNS: no listener",
        "category": "Connectivity",
        "cause": "There is no listener process running at all on the target host/port, or the client is pointed at the wrong host/port.",
        "solution": "Start the listener (lsnrctl start), confirm the host and port in the connection string are correct, and check for firewall rules blocking the port.",
        "keywords": ["listener down", "connection refused", "port"],
        "severity": "critical",
    },
    {
        "code": "TNS-12560",
        "message": "TNS: protocol adapter error",
        "category": "Connectivity",
        "cause": "A generic, often Windows-specific error meaning the Oracle client/service couldn't be initialized -- commonly the Oracle service isn't started, or ORACLE_HOME/ORACLE_SID environment variables are wrong.",
        "solution": "Confirm the OracleService<SID> Windows service is running, verify ORACLE_HOME and ORACLE_SID are set correctly for the session, and check the listener log for more specific detail.",
        "keywords": ["protocol adapter", "oracle service", "windows"],
        "severity": "medium",
    },
    {
        "code": "TNS-12170",
        "message": "TNS: connect timeout occurred",
        "category": "Connectivity",
        "cause": "The client attempted a connection but did not get a response within SQLNET.OUTBOUND_CONNECT_TIMEOUT -- typically a network issue, an overloaded listener, or a firewall silently dropping packets.",
        "solution": "Check network connectivity and latency between client and server, review firewall/security group rules, and inspect listener load (a very busy listener queue can cause this too).",
        "keywords": ["connect timeout", "network", "firewall"],
        "severity": "medium",
    },
    {
        "code": "ORA-03113",
        "message": "End-of-file on communication channel",
        "category": "Connectivity",
        "cause": "The client's connection to the server process was severed unexpectedly -- possible causes include a server-side crash, an OS/network-level connection drop, a killed session, or exceeding a resource limit that terminated the process.",
        "solution": "Check the database alert log and OS logs around the time of the error for a crash or session kill, check network stability, and look for resource exhaustion (memory, file descriptors) on the server.",
        "keywords": ["connection lost", "communication channel", "eof"],
        "severity": "high",
    },
    {
        "code": "ORA-03114",
        "message": "Not connected to ORACLE",
        "category": "Connectivity",
        "cause": "A client tried to execute a command after its session was already disconnected (often right after an ORA-03113 or a manual/administrative disconnect).",
        "solution": "Reconnect and retry the operation; if this happens repeatedly, investigate the root disconnect cause (often paired with ORA-03113 in the same incident).",
        "keywords": ["not connected", "session dropped"],
        "severity": "medium",
    },

    # ---------------- Authentication / security ----------------
    {
        "code": "ORA-01017",
        "message": "Invalid username/password; logon denied",
        "category": "Security",
        "cause": "The credentials supplied don't match any valid account, or the password has changed since the client last cached it.",
        "solution": "Verify the username/password (case sensitivity can matter depending on configuration), check for a recent password rotation, and confirm the account isn't locked (see ORA-28000).",
        "keywords": ["login failed", "authentication", "password"],
        "severity": "low",
    },
    {
        "code": "ORA-28000",
        "message": "The account is locked",
        "category": "Security",
        "cause": "The account exceeded the FAILED_LOGIN_ATTEMPTS limit defined in its profile, usually from repeated bad password attempts (sometimes an application with a stale cached credential retrying in a loop).",
        "solution": "Unlock the account (ALTER USER ... ACCOUNT UNLOCK), find and fix whatever is retrying with a bad password, and consider whether the lockout threshold/duration in the profile needs adjusting.",
        "keywords": ["account locked", "failed login attempts"],
        "severity": "medium",
    },
    {
        "code": "ORA-28001",
        "message": "The password has expired",
        "category": "Security",
        "cause": "The account's password exceeded the PASSWORD_LIFE_TIME set in its profile.",
        "solution": "Reset the password, and if this is a service/application account that shouldn't expire, adjust the profile's PASSWORD_LIFE_TIME or move it to a profile designed for non-interactive accounts.",
        "keywords": ["password expired", "profile"],
        "severity": "low",
    },
    {
        "code": "ORA-01031",
        "message": "Insufficient privileges",
        "category": "Security",
        "cause": "The current user tried to perform an operation (DDL, a privileged view, SYSDBA-only action, etc.) without the required system or object privilege.",
        "solution": "Grant the specific privilege needed (avoid blanket DBA grants where possible), or connect with an account that already has it, and double-check whether the privilege needs to be granted directly vs. through a role for the given operation.",
        "keywords": ["privileges", "grant", "permission denied"],
        "severity": "low",
    },
    {
        "code": "ORA-01045",
        "message": "User lacks CREATE SESSION privilege; logon denied",
        "category": "Security",
        "cause": "The account exists and the password is correct, but it was never granted CREATE SESSION (or the privilege/role granting it was revoked).",
        "solution": "Grant CREATE SESSION to the user (directly or via a role), and check whether a role that carried this privilege was accidentally revoked or disabled.",
        "keywords": ["create session", "logon denied", "privilege"],
        "severity": "low",
    },
    {
        "code": "ORA-01950",
        "message": "No privileges on tablespace",
        "category": "Security",
        "cause": "A user tried to create objects in a tablespace they don't have a quota on.",
        "solution": "Grant a quota on the tablespace to the user (ALTER USER ... QUOTA ...) or point them at a tablespace they already have quota on.",
        "keywords": ["tablespace quota", "privileges"],
        "severity": "low",
    },

    # ---------------- PL/SQL ----------------
    {
        "code": "ORA-06502",
        "message": "PL/SQL: numeric or value error",
        "category": "PL/SQL",
        "cause": "A PL/SQL block tried to assign a value that doesn't fit its target -- classic cases are a VARCHAR2 too small for the string being assigned, or a numeric conversion that overflows/truncates.",
        "solution": "Check the specific variable sizes/types involved against the data being assigned, widen the variable if the data is legitimately that large, and validate/trim input before assignment.",
        "keywords": ["plsql", "value error", "buffer too small"],
        "severity": "low",
    },
    {
        "code": "ORA-06508",
        "message": "PL/SQL: could not find program unit being called",
        "category": "PL/SQL",
        "cause": "The stored procedure/package being called is invalid or was recompiled with an incompatible signature since the calling code was compiled.",
        "solution": "Recompile the calling and called units (UTL_RECOMP or manual ALTER ... COMPILE), and check dependency chains for stale/invalid objects (query DBA_OBJECTS for STATUS = 'INVALID').",
        "keywords": ["plsql", "program unit", "invalid object"],
        "severity": "medium",
    },
    {
        "code": "ORA-04098",
        "message": "Trigger is invalid and failed re-validation",
        "category": "PL/SQL",
        "cause": "A trigger became invalid (often because an object it depends on changed) and Oracle couldn't automatically recompile it successfully.",
        "solution": "Manually recompile the trigger (ALTER TRIGGER ... COMPILE), review the compile error for the real root cause, and fix the underlying dependency issue.",
        "keywords": ["trigger", "invalid", "recompile"],
        "severity": "medium",
    },
    {
        "code": "ORA-06512",
        "message": "at line -- PL/SQL error position indicator",
        "category": "PL/SQL",
        "cause": "This isn't a standalone error -- it's a trailer that appears after another error to show the call stack/line number where it was raised.",
        "solution": "Look at the error code(s) that appear alongside this line and address those; ORA-06512 itself only tells you where, not what.",
        "keywords": ["plsql", "stack trace", "line number"],
        "severity": "low",
    },

    # ---------------- SQL syntax / semantics ----------------
    {
        "code": "ORA-00904",
        "message": "Invalid identifier",
        "category": "SQL Syntax",
        "cause": "The SQL references a column or object name that doesn't exist, is misspelled, or isn't visible in the current schema/alias context.",
        "solution": "Double-check spelling and case, confirm the column exists in the table/view being queried, and verify table aliases are used consistently.",
        "keywords": ["invalid identifier", "column name", "typo"],
        "severity": "low",
    },
    {
        "code": "ORA-00933",
        "message": "SQL command not properly ended",
        "category": "SQL Syntax",
        "cause": "Extra or misplaced characters (often a stray semicolon, clause, or bind variable) follow what should have been the end of a valid SQL statement.",
        "solution": "Review the statement for trailing tokens or clauses in the wrong order, and check the client isn't appending anything after the query is built dynamically.",
        "keywords": ["syntax error", "sql not ended"],
        "severity": "low",
    },
    {
        "code": "ORA-00936",
        "message": "Missing expression",
        "category": "SQL Syntax",
        "cause": "The parser expected a value/expression at a point in the SQL and didn't find one -- common with an incomplete WHERE clause or a trailing comma in a SELECT list.",
        "solution": "Review the statement around where the parser stopped, check for a dangling operator (=, AND, ,) with nothing after it, especially in dynamically built SQL.",
        "keywords": ["syntax error", "missing expression"],
        "severity": "low",
    },
    {
        "code": "ORA-00942",
        "message": "Table or view does not exist",
        "category": "SQL Syntax",
        "cause": "The referenced object genuinely doesn't exist, exists in a different schema than expected, or the current user lacks the SELECT/object privilege needed to even see it (Oracle intentionally reports both cases the same way for security).",
        "solution": "Verify the table/view name and owning schema, check whether a synonym is needed, and confirm the appropriate GRANT exists for the querying user.",
        "keywords": ["table not found", "view not found", "privileges"],
        "severity": "low",
    },
    {
        "code": "ORA-00979",
        "message": "Not a GROUP BY expression",
        "category": "SQL Syntax",
        "cause": "A SELECT list includes a column that isn't aggregated and isn't part of the GROUP BY clause.",
        "solution": "Add the column to the GROUP BY clause, or wrap it in an aggregate function (MAX, MIN, etc.) if that better reflects the intent.",
        "keywords": ["group by", "aggregate", "syntax"],
        "severity": "low",
    },
    {
        "code": "ORA-01422",
        "message": "Exact fetch returns more than requested number of rows",
        "category": "SQL Syntax",
        "cause": "A PL/SQL SELECT INTO expected exactly one row back but the query actually matched more than one.",
        "solution": "Add WHERE conditions to make the query uniquely match one row, or switch to a BULK COLLECT / cursor loop if multiple rows are legitimately expected.",
        "keywords": ["select into", "too many rows", "plsql"],
        "severity": "low",
    },
    {
        "code": "ORA-01427",
        "message": "Single-row subquery returns more than one row",
        "category": "SQL Syntax",
        "cause": "A subquery used in a context expecting a single value (e.g. after '=' ) actually returned multiple rows.",
        "solution": "Use IN instead of '=' if multiple matches are valid, or add conditions/aggregation to the subquery to guarantee a single row.",
        "keywords": ["subquery", "too many rows"],
        "severity": "low",
    },
    {
        "code": "ORA-01722",
        "message": "Invalid number",
        "category": "SQL Syntax",
        "cause": "An implicit or explicit conversion tried to turn a non-numeric string into a NUMBER and failed -- often bad/dirty source data, or a WHERE clause comparing a VARCHAR2 column to a numeric literal.",
        "solution": "Validate/clean the source data, use TO_NUMBER with error handling for untrusted input, and check for accidental type mismatches in comparisons.",
        "keywords": ["invalid number", "conversion error", "data type"],
        "severity": "low",
    },
    {
        "code": "ORA-01858",
        "message": "Not a valid month",
        "category": "SQL Syntax",
        "cause": "A date conversion (implicit or via TO_DATE) received a string whose format doesn't match the expected date format model, often due to a locale/NLS_DATE_FORMAT mismatch.",
        "solution": "Always specify an explicit format mask in TO_DATE rather than relying on implicit conversion, and confirm the session's NLS_DATE_FORMAT matches what the application expects.",
        "keywords": ["date format", "to_date", "nls"],
        "severity": "low",
    },
    {
        "code": "ORA-01476",
        "message": "Divisor is equal to zero",
        "category": "SQL Syntax",
        "cause": "A division operation in SQL or PL/SQL had a zero denominator.",
        "solution": "Add a check (CASE WHEN denom = 0 THEN NULL ELSE ... END) or use NULLIF(denom, 0) to avoid the division entirely when the denominator is zero.",
        "keywords": ["division by zero", "arithmetic"],
        "severity": "low",
    },
    {
        "code": "ORA-12899",
        "message": "Value too large for column",
        "category": "SQL Syntax",
        "cause": "An INSERT/UPDATE tried to store a string longer than the column's declared size (bytes or characters, depending on NLS settings).",
        "solution": "Truncate/validate the input at the application layer, or widen the column if the longer values are legitimately expected going forward.",
        "keywords": ["column size", "value too large", "varchar2"],
        "severity": "low",
    },

    # ---------------- Backup / recovery / redo ----------------
    {
        "code": "ORA-16038",
        "message": "Log member cannot be archived, no available destinations",
        "category": "Backup & Recovery",
        "cause": "The database needs to archive a redo log but every configured archive destination is unavailable or full, so redo generation is effectively blocked.",
        "solution": "Free space on or fix connectivity to at least one archive destination, and if this happens often, add more archive destinations or increase existing ones' capacity.",
        "keywords": ["archive log", "redo log", "backup"],
        "severity": "critical",
    },
    {
        "code": "ORA-19502",
        "message": "Write error on backup piece / file",
        "category": "Backup & Recovery",
        "cause": "RMAN encountered an I/O error while writing a backup piece, commonly due to the backup destination running out of disk space or a storage/network hiccup.",
        "solution": "Check free space at the backup destination, review OS-level I/O errors around the same timestamp, and verify RMAN's configured backup location is healthy.",
        "keywords": ["rman", "backup failed", "write error"],
        "severity": "high",
    },
    {
        "code": "ORA-38701",
        "message": "Redo log corruption detected",
        "category": "Backup & Recovery",
        "cause": "A redo log block failed a checksum/consistency check, most often from underlying storage corruption or a hardware issue.",
        "solution": "Restore/recover from backup as needed, run storage-level diagnostics (disk, SAN, filesystem) to find the root hardware cause, and verify RAID/redundancy is functioning for redo log members.",
        "keywords": ["redo log", "corruption", "recovery"],
        "severity": "critical",
    },

    # ---------------- Generic / internal ----------------
    {
        "code": "ORA-00600",
        "message": "Internal error code",
        "category": "Internal",
        "cause": "A generic bucket for internal Oracle code-level errors that aren't meant to happen in normal operation -- the specific arguments after the code point to the exact internal fault, but the root cause can range from a known bug to storage corruption.",
        "solution": "Capture a full diagnostic trace (Oracle's Autonomous Health Framework / incident package), search My Oracle Support for the exact argument signature, and open an SR with Oracle Support if no known bug/patch matches.",
        "keywords": ["internal error", "generic", "diagnostic"],
        "severity": "critical",
    },
    {
        "code": "ORA-07445",
        "message": "Exception encountered: core dump",
        "category": "Internal",
        "cause": "An Oracle background or server process crashed at the OS level (segmentation fault or similar), similar in spirit to ORA-00600 but originating from an OS-level exception rather than an internal Oracle check.",
        "solution": "Collect the generated trace/core files, check the specific function name in the trace against Oracle Support's knowledge base, and apply any relevant patch or open an SR if none is found.",
        "keywords": ["core dump", "crash", "internal error"],
        "severity": "critical",
    },
    {
        "code": "ORA-27101",
        "message": "Shared memory realm does not exist",
        "category": "Internal",
        "cause": "A client tried to attach to an instance's SGA but the shared memory segment isn't there -- typically because the instance isn't actually running, or ORACLE_SID doesn't match a running instance.",
        "solution": "Confirm the instance is started, verify ORACLE_SID matches an actual running instance, and check for a recent crash in the alert log.",
        "keywords": ["shared memory", "sga", "instance down"],
        "severity": "high",
    },

    # ---------------- External / misc ----------------
    {
        "code": "ORA-29283",
        "message": "Invalid file operation",
        "category": "External I/O",
        "cause": "A PL/SQL UTL_FILE call tried to read/write a file in a way the OS or Oracle directory object permissions don't allow -- file doesn't exist, wrong mode, or the directory object isn't granted.",
        "solution": "Verify the file path and existence, check OS-level permissions for the Oracle process user, and confirm READ/WRITE has been granted on the DIRECTORY object to the calling user.",
        "keywords": ["utl_file", "directory object", "file permissions"],
        "severity": "low",
    },
    {
        "code": "ORA-29913",
        "message": "Error in executing ODCIEXTTABLEOPEN callout",
        "category": "External I/O",
        "cause": "An external table couldn't be opened, almost always because the underlying flat file is missing, the DIRECTORY object path is wrong, or the file's format doesn't match the external table definition.",
        "solution": "Confirm the source file exists at the DIRECTORY object's OS path with the expected name, and check the external table's access parameters against the file's actual format.",
        "keywords": ["external table", "odciexttableopen", "flat file"],
        "severity": "medium",
    },
    {
        "code": "ORA-20001",
        "message": "User-defined application error",
        "category": "Application",
        "cause": "This is not a built-in Oracle error -- it's the default range (ORA-20000 to ORA-20999) developers use with RAISE_APPLICATION_ERROR to signal custom business-logic errors from PL/SQL.",
        "solution": "Check the actual message text attached to the error (it's set by the application developer) and the calling PL/SQL unit's source, since the fix is entirely application-specific rather than a database-level issue.",
        "keywords": ["raise_application_error", "custom error", "business logic"],
        "severity": "low",
    },
]


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "oracle_errors_kb.jsonl")

    with open(out_path, "w", encoding="utf-8") as f:
        for entry in KB_ENTRIES:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote {len(KB_ENTRIES)} knowledge base entries to {out_path}")


if __name__ == "__main__":
    main()
