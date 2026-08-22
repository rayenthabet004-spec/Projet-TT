# Fresh Log Acceptance Test — What To Check

These 4 logs were never seen by Antigravity during the fix work — use them
as a genuine held-out test of the "all 8 bugs fixed" claim, not the 6 logs
it already iterated against.

Run each through the CLI (t5 mode, the only mode that should exist now):
```bash
python analyze.py oracle_fresh_incident.log
python analyze.py postgres_fresh_incident.log
python analyze.py mysql_fresh_incident.log
python analyze.py ambiguous_lowsignal_postgres.log
```

## oracle_fresh_incident.log

| Code | What to check | Ties to |
|---|---|---|
| ORA-01555, ORA-00060, ORA-04031, ORA-01652, ORA-01017 | Should return instantly with `Source: kb_exact_match`, no model call needed, text matching the KB verbatim | **Fix 1** — exact-match short-circuit must fire in t5 mode |
| ORA-01013 | **Deliberately NOT in your KB** (confirmed absent in an earlier review). Watch what happens here specifically — does it honestly hedge (medium/low confidence, "unconfirmed") or confidently invent a wrong explanation? | Tests the hallucination/abstention behavior — no specific fix targets this, it's a genuine open question about current model behavior |
| RMAN-00569 / RMAN-03002 / RMAN-06059 | Expected to still be reported as 3 separate findings, not one grouped incident — this is **known, accepted, out of scope** for this fix pass. Don't flag it as a new bug. | Explicitly deferred (event-chain grouping) |
| TNS-12541, ORA-12154 | Should not bleed Postgres/MySQL KB entries into `KB refs` | **Fix 6** — engine-filtered retrieval |

## postgres_fresh_incident.log

| Line | What to check | Ties to |
|---|---|---|
| `23505`-class duplicate key, `42P01`-class relation-does-not-exist, `40001` serialization | Should get real SQLSTATE codes, not garbage | Baseline Postgres parsing (should already work) |
| `WARNING: there is already a transaction in progress` / `LOG: incomplete startup packet` | No SQLSTATE present — should tag `is_pseudo_code=True`, NOT do a normal exact-match lookup on a meaningless string | **Fix 2's pseudo-code principle**, applied consistently across engines |
| All findings in this report | `KB refs:` should contain **zero** `ORA-` or `MY-` codes | **Fix 6** — engine-filtered retrieval |
| `DETAIL`/`STATEMENT`/`HINT`/`CONTEXT` lines | Should appear as context, not get mistakenly parsed as their own separate error occurrences | Baseline parser correctness |

## mysql_fresh_incident.log — the most important file, tests Fix 2 directly

This file deliberately mixes **4 different timestamp formats** on purpose:
`Z` suffix, `+01:00`, `-05:00`, and no timezone suffix at all. Before the
fix, only `Z` matched — everything else silently fell through to the
weaker fallback path.

| Line | Expected code | Tests |
|---|---|---|
| FK violation (`+01:00` timestamp) | `MY-001452` via **message-pattern inference**, `is_pseudo_code=False` | Fix 2, tier 1, offset timestamp |
| `Unknown database` (`-05:00` timestamp) | `MY-001049` via message inference | Fix 2, tier 1, negative offset |
| Duplicate entry (`Z` timestamp) | `MY-001062` via message inference | Fix 2, tier 1, baseline |
| Deadlock (`+01:00`) | `MY-001213` via message inference | Fix 2, tier 1 |
| IP resolution warning (**no timezone suffix at all**) | Should still parse — this is the format most likely to still be broken if the regex fix wasn't fully generalized | Fix 2, the timestamp-optional case |
| Access denied, `[ERROR]` level (not Warning) | `MY-001045`, AND classifier should say `REAL ERROR` (not informational) | Fix 2 + **Fix 8** classifier override |
| Table doesn't exist (`-05:00`) | `MY-001146` via message inference | Fix 2, tier 1 |
| Plugin deprecation warning | No message-pattern match, but a **valid bracket code** `MY-013457` — should fall through to tier 2 (raw bracket code), NOT tier 3 pseudo-code | Fix 2, tier 2 — the case most likely to be implemented wrong |
| 3x repeated `MY-011825` "Buffer pool(s) load completed" | Occurrence count should show `x3`; if T5 is called for this code (unlikely if it's an exact KB match), generated text should not loop/repeat itself | **Fix 5** — repetition guard |
| Replica I/O thread error, `[MY-014502]` | Valid bracket code, no message pattern match → tier 2, real code `MY-014502` | Fix 2, tier 2, second case |
| Final line — **no bracket structure at all** | Should fall to tier 3: `MY-ERROR` pseudo-code, `is_pseudo_code=True`, and should NOT trigger a misleading confident BM25 match | Fix 2, tier 3 |

## ambiguous_lowsignal_postgres.log — tests Fix 3 specifically

20 lines total, only **2 lines** carry any engine-specific fingerprint at
all (one `ERROR:` SQLSTATE-adjacent line, one `FATAL:` line) — both
unambiguously PostgreSQL, zero competing votes from other engines.

**Before the fix**, the old formula (`total_votes / non_empty_lines`) would
score this around 2/20 × margin ≈ 0.1 — misleadingly low despite zero
disagreement. **After the fix**, per Antigravity's stated scaling
(`total_votes==2 -> 0.67 * margin`), this should report confidence around
**0.67**, not near-zero. Run:
```python
from src.engine_detection import detect_engine
print(detect_engine(open("ambiguous_lowsignal_postgres.log").read(), return_confidence=True))
```
If it still reports something close to 0.1, the fix didn't actually change
the formula's behavior on realistic low-density logs — push back.

## Red flags to watch for across all 4 reports, regardless of the table above

- Any `KB refs:` list mixing codes from a different engine than the one detected
- Any field (`Meaning`/`Likely cause`/`Suggested solution`) left blank
- Any generated text that repeats a phrase verbatim 2+ times
- `Generation mode:` showing anything other than `t5` (llama/local should no longer be selectable)
- The `--mode` CLI help text still listing `auto`/`llama`/`local` as options
