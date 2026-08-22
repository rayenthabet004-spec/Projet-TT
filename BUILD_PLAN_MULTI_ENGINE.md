# Build Plan: Multi-Engine Oracle/Postgres/MySQL Log RAG — Handoff for Antigravity

This is a complete, standalone build spec. You (the AI reading this in
Antigravity) should be able to execute this without needing the original
conversation that produced it. Read the whole thing before writing any code
-- the "Lessons learned" section documents real bugs already found and fixed
in the existing Oracle-only version of this project; repeating them here
would waste time the user doesn't have.

**Hard constraint: the user has 2 days total.** Prioritize accordingly.
Where this doc says "cut" or "optional," actually cut it unless there's time
left over at the very end. Do not silently expand scope.

## 1. What already exists (don't rebuild this)

This project (`3rd attempt (fixed rag)/`) already has a complete, tested
Oracle-only pipeline:
- `data/knowledge_base/oracle_errors_kb.jsonl` -- 27,282 Oracle error
  entries (code, message, category, cause, solution, keywords, severity).
- `src/log_parser.py` -- regex extraction of Oracle error codes (81
  prefixes: ORA, TNS, RMAN, CRS, DRG, etc.) + context window + code
  normalization.
- `src/rag/{knowledge_base.py, retriever.py, generator.py, pipeline.py}` --
  BM25 retrieval (exact-match + lexical fallback) + generation (mock /
  local T5 / Llama via Ollama / auto dispatch).
- `src/classifier/` -- a TF-IDF + Logistic Regression classifier
  distinguishing real errors from informational-only log lines (trained on
  auto-labeled data, F1 0.882 on the informational class after tuning).
- `src/data_generation/{generate_finetune_logs.py, build_finetune_dataset.py}`
  -- generates a large synthetic Oracle log corpus and turns it into
  code-level-split fine-tuning JSONL (train/val/test_unseen_codes).
- `notebook/oracle_log_t5_finetune_kaggle.ipynb` -- fine-tunes
  `google/flan-t5-base` on the Oracle data, runs on a free Kaggle T4 GPU.
- A trained checkpoint likely exists at `models/oracle_log_t5_model/` --
  **check for this first**; if present, Day 2's fine-tuning step should
  CONTINUE fine-tuning from it, not restart from the raw `flan-t5-base`
  pretrained weights (faster convergence -- the model already learned the
  output format/structure, it just needs new vocabulary).
- `PROGRESS.md` and `CONVERSATION_SUMMARY.md` in the project root have the
  full history of what was built and why, including several bugs found and
  fixed. Read `CONVERSATION_SUMMARY.md` first for the narrative, then skim
  `PROGRESS.md` for detail on any specific file you're about to touch.

## 2. Scope decision (already made, don't relitigate)

**Build:** Oracle (done) + PostgreSQL + MySQL, unified into ONE knowledge
base, ONE fine-tuned model, ONE classifier, ONE retriever -- not 4 separate
pipelines. See section 4 for why and how.

**SQLite: bonus only, if time remains after everything else works.** SQLite
is embedded, not client-server -- there is no server log file. It returns
numeric result codes (SQLITE_BUSY, SQLITE_CONSTRAINT, etc.) directly to the
calling application via its API. There's nothing to "parse" as a log file
unless some specific application happens to print those codes into its own
log in some app-specific format. If you do add it: it's just a small KB
(~30 primary + ~80 extended result codes, all officially documented, cheap
to hand-write) with NO dedicated log parser -- treat it as a lookup-only
addition, not a fourth parallel pipeline. Do not present it in the final
report as the same category of thing as Oracle/Postgres/MySQL.

**Explicitly NOT in scope for these 2 days:**
- Website/deployment (user already said "for later" -- correct instinct, don't touch it now).
- Wiring the classifier into the live generation pipeline (it's a standalone module currently; leave it that way).
- Fixing the one pre-existing stale test in `tests/test_retriever.py` (unrelated to this work, low value, don't spend time on it).
- Chasing exhaustive error-code coverage for MySQL. Curated ~150-300 common codes beats attempting completeness.
- A 4th "real" engine (SQL Server, MongoDB, etc.) -- three is already a strong, defensible scope.

## 3. Lessons learned from the Oracle build -- READ THIS BEFORE CODING

These are real bugs that were found, diagnosed, and fixed during the
original Oracle-only build. Apply the fixes proactively this time instead
of rediscovering them.

1. **Verify placeholder/format conventions against real data, don't guess.**
   For Oracle, the scraped KB messages use the literal word `"string"` as a
   placeholder (confirmed by checking the actual file: every one of 9,028
   occurrences was a genuine placeholder). The word `"number"` looked like
   it might also be a placeholder but wasn't (1,463 occurrences, almost all
   genuine English -- "Maximum number of sessions exceeded"). **Before
   writing placeholder-substitution logic for Postgres/MySQL error message
   templates, actually inspect a sample of real error message text from
   whatever source you pull them from**, and check what placeholder
   convention (if any) that source actually uses. Don't assume it matches
   Oracle's convention.

2. **Audit error-code-prefix/pattern coverage against your actual KB, not a
   guess.** The Oracle parser originally only recognized 13 of the 81
   prefixes that actually existed in the scraped KB -- a real gap that
   silently dropped most codes until caught. When you build the Postgres
   and MySQL parsers, after building each KB, run a quick script that
   extracts every distinct code-prefix/pattern actually present in that KB
   and cross-check it against what the parser's regex actually matches.
   Postgres SQLSTATE codes are 5 alphanumeric characters (e.g. `23505`,
   `42601`, `08006`) with no letter prefix, so the matching pattern is
   different in kind from Oracle's `PREFIX-NNNNN`, not just a different
   prefix list -- design the regex for what SQLSTATE actually looks like,
   don't reuse Oracle's pattern shape.

3. **Use BOTH `cause` and `solution` fields when checking for
   "informational-only" entries, not just one.** The Oracle KB had 648
   entries with "informational" in the `cause` field, but 230 MORE entries
   (including a specific real one, ORA-16111) only had that marker in the
   `solution` field. Checking one field alone silently mislabeled 230
   entries. When building the classifier's informational-detection
   heuristic for the new Postgres/MySQL data, check every text field you
   have (cause, solution, description, whatever the schema ends up being),
   not just the first one that seems obviously relevant.

4. **When a target/label text is built from a template, make sure it's
   actually consistent with what appears in the corresponding input, not
   just internally correct.** A real bug: the fine-tuning target's MEANING
   field originally used the KB's raw templated message (still containing
   unfilled placeholders) while the input log line showed the actual
   filled-in value -- teaching the model to output literal placeholder
   text. Fix pattern: always derive the target's "meaning" text from the
   ACTUAL rendered log line (the thing the parser matched), not from the KB
   template directly, whenever your corpus-generation pipeline fills in
   placeholders.

5. **Split fine-tuning data by CODE, not by row, and not with a
   per-code-stratified split either.** A per-code stratified split still
   leaks near-identical phrasings of the same code across train/val. Use a
   deterministic hash-based split so every occurrence of a given code lands
   in exactly one bucket (train/val/test), and hold out an entirely unseen
   set of codes as a true generalization test set (`test_unseen_codes.jsonl`
   in the existing Oracle pipeline is exactly this pattern -- replicate it
   for the combined multi-engine dataset). Verify zero code overlap between
   splits after building.

6. **T5-family tokenizers commonly collapse/normalize whitespace, including
   literal newlines, during encoding.** This means generated output at
   inference time often comes back as ONE continuous line even if your
   training targets have each field on a separate line with `\n`. A parser
   that only matches field labels at the START of a line (via
   `text.splitlines()`) will silently fail to extract every field after the
   first one -- this happened in `generator.py::_parse_structured_response`
   and the notebook's `extract_fields`/`compute_metrics`, producing a flat
   0.000000 "format adherence" metric despite the model actually learning
   fine (loss and ROUGE-L were both improving normally). **Both were fixed
   to use a regex with lookahead** (find each label anywhere in the text,
   capture up to the next label or end of string) instead of line-start
   matching. If you're touching either of these files, keep that fix --
   don't revert to line-based parsing.

7. **Don't eagerly pad every tokenized example to the max length ceiling.**
   Original notebook code used `padding="max_length"` in the tokenize
   function with `MAX_SOURCE_LENGTH=384`/`MAX_TARGET_LENGTH=256`, even
   though actual median example length was ~52 words (~70 tokens) for
   source and ~37 words (~50 tokens) for target -- wasting ~3-5x compute
   per batch on padding tokens. This alone caused a training run to be
   projected at 7+ hours instead of a fraction of that. Fix: tokenize
   WITHOUT eager padding, and let `DataCollatorForSeq2Seq` (already
   instantiated for the Trainer) pad dynamically per-batch to the longest
   example in that batch. Check actual token/word length distribution of
   whatever new combined dataset you build (a simple word-count check on a
   few thousand rows is enough) before picking length ceilings -- don't
   default to 384/256 without checking.

8. **`Seq2SeqTrainer`'s `tokenizer=` argument was renamed to
   `processing_class=`** in recent `transformers` versions (a hard
   `TypeError` otherwise, not a deprecation warning, as of whatever version
   Kaggle installs when the notebook's `!pip install` cell doesn't pin a
   version). Use `processing_class=tokenizer` in any new/modified
   `Seq2SeqTrainer(...)` call. Consider pinning a specific `transformers`
   version in the install cell once things work, to avoid this recurring
   with a future Kaggle image update.

9. **When checking whether a Kaggle training run is actually using the GPU
   (vs. silently falling back to CPU), do the step-count math** rather than
   just trusting the accelerator setting: `total_steps = ceil(num_examples
   / (per_device_batch_size * num_gpus)) * num_epochs`. If Kaggle gave 2x
   T4s and the Trainer used data-parallel, the observed step count will be
   roughly half of what you'd expect from a single-GPU calculation -- this
   confirmed multi-GPU use in a case where the training speed alone looked
   suspicious. Useful sanity check any time training speed seems off.

10. **Pickling custom scikit-learn-adjacent classes (e.g. a custom feature
    combiner) defined inside a script that gets run as `__main__` will
    break loading from a DIFFERENT entry point.** `python -m
    src.classifier.train_classifier` makes any class defined in that file
    get recorded by pickle under module `"__main__"`, so loading the same
    pickle later from `classify.py` (a different `__main__`) fails with
    `AttributeError: Can't get attribute '<ClassName>'`. Fix: define any
    such custom class in its own always-imported-by-name module (see
    `src/classifier/features.py::CombinedVectorizer` for the existing
    pattern), imported explicitly by both the training script and the
    inference script.

11. **Copyright care when building KBs from official documentation.** The
    original Oracle KB avoided bulk-reproducing Oracle's copyrighted docs
    verbatim at scale -- entries were either hand-written in original
    wording (the first 58) or extracted via a scraper the USER runs
    themselves for internal/personal tool use (not redistributed
    publicly), with cause/solution text summarized rather than quoted at
    length. Apply the same standard to Postgres/MySQL KB construction:
    Postgres's official SQLSTATE error-code list (condition name + class)
    is short, factual, and enumeration-like (fine to include directly, akin
    to a reference table); write your own original cause/solution
    explanations rather than copying long-form prose from any single
    source, and don't bulk-scrape+republish extensive verbatim
    documentation text at thousands-of-entries scale.

## 4. Architecture: one unified pipeline, not four parallel ones

Do NOT build 4 separate knowledge bases, 4 separate fine-tuned models, or 4
separate classifiers. This wastes the 2-day budget for no real benefit.
Instead:

### 4a. Engine detection (new, small)
A lightweight function/module (`src/engine_detection.py` or similar) that
sniffs a raw log file/text and tags it with which DB engine it's from,
before routing to the right parser. Keep this simple -- regex/heuristic
based, not a trained classifier (no time budget for that):
- Oracle: presence of `ORA-`, `TNS-`, or other known Oracle prefixes.
- Postgres: `FATAL:`/`ERROR:`/`WARNING:` log level markers combined with a
  5-character alphanumeric SQLSTATE pattern, or Postgres-specific phrasing.
- MySQL: `[ERROR] [MY-` (MySQL 8+ structured log format) or the classic
  `ERROR NNNN (SQLSTATE):` pattern from older versions/general query log.
Should be resolvable per-file (assume one engine per file/upload) or even
per-line if you want to be more robust, but per-file is enough for the
2-day scope.

### 4b. Per-engine log parsers, common interface
Each engine gets its own parser module (e.g. `src/parsers/oracle.py`,
`src/parsers/postgres.py`, `src/parsers/mysql.py`) because the actual log
line SHAPES differ meaningfully between engines (this is not just "swap
the regex prefix list" -- Postgres's SQLSTATE has no letter prefix at all,
and MySQL's format differs again). All three should still return the same
`ErrorOccurrence`-shaped object (code, line_number, raw_line, context,
timestamp) so everything downstream (retriever, generator, pipeline)
doesn't need to know which engine it came from.

### 4c. One combined knowledge base
Same JSONL schema as the existing Oracle KB, with one added field:
`"engine": "oracle" | "postgres" | "mysql" | "sqlite"`. Store as one file
(`data/knowledge_base/combined_errors_kb.jsonl`) or three files loaded
together into one `KnowledgeBase` object -- either is fine, just make sure
the retriever indexes across all of them together (a Postgres log's error
should never accidentally retrieve an Oracle KB entry, so consider whether
the retriever needs an engine filter passed in from the detected engine, to
avoid cross-engine false-positive lexical matches muddying results).

### 4d. One fine-tuned model, engine named in the instruction text
Do NOT fine-tune 3 separate T5 models. Build ONE combined fine-tuning
dataset spanning all engines, with the per-example instruction text naming
the engine, e.g.:
- `"Analyze this Oracle database log entry and explain the error. ..."`
- `"Analyze this PostgreSQL log entry and explain the error. ..."`
- `"Analyze this MySQL log entry and explain the error. ..."`
This is standard multi-domain instruction fine-tuning practice -- FLAN-T5
generalizes the task STRUCTURE (explain -> cause -> solution, same 4-field
output format) across engines fine, since that structure doesn't depend on
which engine the vocabulary comes from. Keep everything else about the
training pipeline (code-level split, dynamic padding, the regex-based
output parser) exactly as already built for Oracle.

**If `models/oracle_log_t5_model/` already exists (a previously trained
checkpoint), continue fine-tuning FROM it** on the new combined dataset,
rather than restarting from raw `google/flan-t5-base` pretrained weights.
Point `MODEL_NAME` in the notebook at that local checkpoint path instead of
the HuggingFace hub name. This should converge faster since the model
already learned the output format/structure from the Oracle-only run.

### 4e. One classifier
Same TF-IDF + Logistic Regression (or the calibrated Linear SVM comparison
already built into `train_classifier.py`) approach, trained on combined
labeled data across all engines' informational-vs-real-error examples.
Reuse `src/classifier/features.py::CombinedVectorizer` and the existing
threshold-tuning logic as-is -- just feed it the combined dataset.

## 5. Concrete file-by-file build list

Mirror the existing project's conventions closely (naming, docstring style,
CLI argparse patterns, JSONL schemas) -- consistency matters more than
novelty here given the time constraint.

```
data/
├── knowledge_base/
│   ├── oracle_errors_kb.jsonl          # existing, unchanged
│   ├── postgres_errors_kb.jsonl        # NEW
│   ├── mysql_errors_kb.jsonl           # NEW
│   └── combined_errors_kb.jsonl        # NEW -- all three (+ sqlite if built) merged, "engine" field added
├── synthetic_logs/
│   └── finetune_corpus_v2/             # NEW -- multi-engine corpus (keep old finetune_corpus/ as-is for reference)
├── finetune/
│   ├── train_v2.jsonl                  # NEW -- combined, code-level split, engine-tagged instructions
│   ├── val_v2.jsonl
│   └── test_unseen_codes_v2.jsonl
└── classifier/
    ├── train_v2.jsonl
    └── val_v2.jsonl

src/
├── engine_detection.py                 # NEW
├── parsers/
│   ├── __init__.py
│   ├── oracle.py                       # NEW -- can mostly wrap/reuse existing src/log_parser.py logic
│   ├── postgres.py                     # NEW
│   └── mysql.py                        # NEW
├── data_generation/
│   ├── build_knowledge_base_postgres.py   # NEW -- hand-written/curated, same style as build_knowledge_base.py
│   ├── build_knowledge_base_mysql.py      # NEW
│   ├── merge_knowledge_bases.py           # NEW -- combines the 3(4) KB files into combined_errors_kb.jsonl
│   ├── generate_finetune_logs_v2.py       # NEW -- multi-engine version of generate_finetune_logs.py
│   └── build_finetune_dataset_v2.py       # NEW -- multi-engine version, engine-tagged instructions, code-level split
├── classifier/
│   └── (reuse existing files, just point at the v2 combined dataset when retraining)
└── rag/
    └── (retriever.py/generator.py/pipeline.py -- extend to accept/pass through an "engine" hint if you add engine-filtered retrieval; otherwise minimal changes needed)

notebook/
└── multi_engine_t5_finetune_kaggle.ipynb   # NEW -- clone of oracle_log_t5_finetune_kaggle.ipynb, pointed at v2 data + (if it exists) continuing from models/oracle_log_t5_model/ as the starting checkpoint instead of google/flan-t5-base
```

## 6. Where to get real Postgres/MySQL error code data

- **PostgreSQL**: the official documentation has a complete, structured
  "Appendix: PostgreSQL Error Codes" listing SQLSTATE code, condition name,
  and error class -- this is exactly analogous to Oracle's error code
  reference and is the right primary source. It's short enough (a few
  hundred entries) to fully hand-curate cause/solution text for within the
  time budget, rather than needing a scraper.
- **MySQL**: official MySQL Server error message reference (numeric
  `ER_xxx` codes + SQLSTATE + message). Much larger than Postgres's list
  (1000+), so don't aim for completeness -- curate ~150-300 of the most
  operationally common ones (connection failures, constraint violations,
  deadlocks, syntax errors, replication errors, access-denied/privilege
  errors, table/schema errors) instead.
- Whichever source you pull from, apply lesson #1 above: check the actual
  message-text formatting conventions in a real sample before writing any
  placeholder-substitution logic for synthetic log generation.

## 7. Day-by-day execution order

### Day 1
1. Engine detection module + basic tests.
2. Postgres KB (hand-curated from the official SQLSTATE appendix) + Postgres log parser + tests.
3. MySQL KB (curated ~150-300 codes) + MySQL log parser + tests.
4. Merge into `combined_errors_kb.jsonl`.
5. Multi-engine synthetic log corpus generator (`generate_finetune_logs_v2.py`) -- verify it covers all engines' codes with realistic per-engine formatting.
6. Multi-engine fine-tuning dataset builder (`build_finetune_dataset_v2.py`) -- code-level split, verify zero cross-split code overlap, verify placeholder-filled targets match rendered input text (lesson #4).

### Day 2
1. Combined classifier dataset + retrain classifier (fast, reuse existing script pattern, just point at v2 data).
2. Multi-engine T5 fine-tuning notebook -- check actual token-length distribution before setting length ceilings (lesson #7), use dynamic padding not eager max-length padding, use `processing_class=` not `tokenizer=` (lesson #8), continue from the existing Oracle checkpoint if present (section 4d), use the already-fixed regex-based structured-output parser (lesson #6).
3. Run the fine-tuning job (Kaggle T4, same pattern as the existing Oracle notebook).
4. Once trained: download, extract, wire into `generator.py`'s `generate_t5()` (should mostly just work given the existing integration, since the output format/interface is unchanged -- verify the prompt-building instruction text matches whatever engine-tagged format was actually used in training).
5. Smoke-test all three engines end-to-end through the CLI on real or synthetic sample logs per engine.
6. Update `PROGRESS.md` with what was built, what's tested vs. not, and what's left -- keep the project's existing habit of honest handoff notes, especially anything that had to be cut or rushed given the 2-day constraint.
