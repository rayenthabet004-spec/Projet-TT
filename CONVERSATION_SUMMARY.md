# Conversation Summary — Oracle Log RAG Project (Tunisie Telecom Internship)

Written for a future AI session (or human) picking this up with no memory of
the conversation that produced it. Read this first, then `PROGRESS.md` for
granular phase-by-phase build notes. This file is the narrative; PROGRESS.md
is the changelog.

## The project, in one paragraph

Internship at Tunisie Telecom (Tunisia). Problem: staff spend hours manually
reading Oracle DB log files to find and diagnose errors. Goal: an AI system
that analyzes log files, identifies errors, explains what they mean and why
they happened, and suggests a fix. Constraints set by the employer/reality:
no real log dataset was provided (had to be built from scratch), scope
limited to Oracle DB errors initially, and the person explicitly wants to
**build the model themselves rather than relying on a paid LLM API** ("I can
use some help from LLMs but the base model should be built by hand" — API
costs money, they want something they trained). The scope later expanded to
add PostgreSQL and MySQL support alongside Oracle (see the end of this file).

## How the conversation unfolded (chronological)

1. **Initial planning (no code yet)**: surveyed approaches for both the
   *data problem* (no dataset available) and the *architecture problem*
   (RAG vs Agentic RAG vs fine-tuning vs classical anomaly detection vs
   rule-based lookup). Landed on: Simple RAG as MVP, built on a hand-written
   knowledge base + synthetic logs (since Oracle's real docs are
   copyrighted and can't be bulk-reproduced), with Agentic RAG and
   fine-tuning noted as future work.

2. **First build (an earlier project attempt, `oracle_log_rag/`)**: built a
   complete Simple RAG pipeline from scratch:
   - Knowledge base: 58 hand-written Oracle error entries (original wording,
     not scraped, to avoid reproducing Oracle's copyrighted docs verbatim).
   - Synthetic Oracle alert-log generator.
   - `log_parser.py`: regex extraction of ORA-/TNS-/etc. codes + context
     window + code normalization (handles inconsistent zero-padding like
     `ORA-1652` vs `ORA-01652`).
   - `retriever.py`: BM25 (rank_bm25) — deliberately NOT dense embeddings,
     because the build sandbox had no internet access to huggingface.co, so
     embedding models couldn't even be downloaded/tested. BM25 needs zero
     model downloads and works well on short keyword-heavy Oracle error text.
   - `generator.py`: KB-exact-match (free, deterministic) + Claude API call
     as a fallback for non-exact matches.
   - `pipeline.py` + `cli.py`: end to end, dedup errors by code, produce
     JSON + Markdown reports.
   - Found and fixed a real bug during testing: the mock generator was
     presenting an unrelated BM25-matched KB entry as if it confidently
     explained an out-of-KB code (`ORA-16111`, matched to `ORA-00257`
     "archiver error" purely on shared "archiv-"/"log" vocabulary). Fixed to
     say "not confirmed, low confidence" instead of guessing confidently —
     this exact bug (ORA-16111 mislabeling) resurfaces and gets fixed again
     more thoroughly in step 5 below.
   - Full test suite (16 tests), all offline, all passing.

3. **Pivot away from paid API generation**: explicit ask — suggest
   approaches for building the generation model by hand (not calling an
   LLM API), given API costs money. Covered: fact-checked that no
   ready-made "pretrained transformer for logs" checkpoint exists for
   generation (LogBERT/NeuralLog/etc. are anomaly-DETECTION encoders, not
   explanation generators); proposed three sub-problems (rephrase retrieved
   KB text / handle non-exact-match codes / classify real-error-vs-
   informational) each better served by a different small model; recommended
   FLAN-T5/BART fine-tuning as primary (encoder-decoder fits the structured
   mapping task, far cheaper to train than a decoder-only causal LM), a
   tiny classifier as a quick win, and continuing an already-started
   Qwen2.5-1.5B QLoRA decoder-only path as a secondary/heavier option.

4. **User's own independent work (between sessions, not built by this AI)**:
   the user (with some other AI help, per their own account) expanded the
   project into what's now called `3rd attempt (fixed rag)/`. Notably:
   - Grew the knowledge base from 58 to **27,282 entries** by scraping
     Oracle's real documentation (`data/knowledge_base/oracle_errors_kb.jsonl`).
   - Added Ollama-based local LLM serving (`generate_llama()` — generic
     Llama via Ollama; `generate_local()` — a separately fine-tuned
     decoder-only model, likely the Qwen2.5 path, served through Ollama
     with an Alpaca-style `### Instruction:` prompt).
   - Had a `build_finetune_dataset.py` (v1) that only worked off the
     original 58-entry KB with hardcoded message templates, and a
     per-code *stratified* split (which leaks near-identical phrasings of
     the same code across train/val — flagged as a design issue, not fixed
     until step 5).
   - A Qwen2.5-1.5B Kaggle notebook (`oracle_log_finetune_kaggle.ipynb`),
     written but never actually run/tested.

5. **This AI's second build session ("Phase 5" in PROGRESS.md)**: asked to
   (a) generate logs for fine-tuning, (b) build the tiny classifier, (c)
   build a notebook to train T5/BART. Inspected the user's actual uploaded
   27,282-entry KB file directly (not guessed) to get real facts:
   - 81 distinct error-code prefixes exist in the KB, but `log_parser.py`
     only recognized 13 — **real gap, fixed** (most of any new corpus, and
     likely real logs, would have been silently unparsed otherwise).
   - Oracle's scraped messages use the literal word `"string"` as a
     placeholder (verified: every one of 9,028 occurrences is a genuine
     placeholder). The word `"number"` is NOT a placeholder marker (1,463
     occurrences, almost all genuine English) — deliberately left alone.
   - 648 KB entries are informational-only per their `cause` field
     containing "informational"; **230 more** (including the actual
     `ORA-16111` from the very first bug found in step 2) only have that
     marker in `solution`, not `cause` — checking cause alone would have
     silently mislabeled all 230. Fixed to check both fields (878 total).

   Built:
   - **`generate_finetune_logs.py`**: generates a large synthetic log
     corpus covering the FULL 27,282-code KB (not just ~20 hand-templated
     codes), with genuine placeholder-filling diversity, noise, and
     occasional multi-error bundling. Ran with defaults: 81,846 occurrences
     across 50 files (~16MB) at `data/synthetic_logs/finetune_corpus/`.
   - **`build_finetune_dataset.py` (v2, replaces v1)**: parses the
     generated corpus through the project's OWN `log_parser.py` + KB
     lookup (dogfooding the real pipeline as the labeling function).
     Splits by error CODE (not row, and not per-code-stratified like v1) —
     produces `train.jsonl` (69,657 examples / 23,218 codes),
     `val.jsonl` (8,220 / 2,740 codes), and a genuinely held-out
     `test_unseen_codes.jsonl` (3,972 / 1,324 codes never touched during
     training, for a true generalization check). Zero code overlap
     verified across all three splits.
     - **Real bug found+fixed here**: the target MEANING text initially
       used the KB's raw (placeholder-containing) message field while the
       input showed the filled-in value — inconsistent, would have taught
       the model to output literal unfilled `"string"` tokens. Fixed to
       extract the actual rendered text from the matched log line instead.
       Verified 0/69,657 targets affected after the fix.
   - **`src/classifier/`** (new package): `build_classifier_dataset.py`
     (auto-labels real-error vs informational using the KB's own text, no
     manual labeling), `train_classifier.py` (TF-IDF + Logistic Regression,
     `class_weight="balanced"` since informational is ~3.9% of examples;
     achieved informational-class recall 0.865 / precision 0.570 / F1 0.687
     on held-out validation), `classify.py` (inference wrapper). Verified
     against the real `ORA-16111` case: correctly predicts informational at
     83.8% confidence, after the cause+solution field fix above.
   - **`oracle_log_t5_finetune_kaggle.ipynb`** (new, alongside the existing
     Qwen notebook): fine-tunes `google/flan-t5-base`, full fine-tune (no
     LoRA needed at 250M params), evaluates with ROUGE-L + a custom
     structured-format-adherence check, and specifically evaluates on
     `test_unseen_codes.jsonl` separately as the real generalization
     signal. Exports a plain `transformers`-loadable folder (no
     GGUF/Ollama needed at this size).

6. **User hit two real errors running the notebook on Kaggle, both diagnosed
   and fixed**:
   - `TypeError: Seq2SeqTrainer.__init__() got an unexpected keyword
     argument 'tokenizer'` — a `transformers` library version change (the
     `tokenizer=` kwarg was renamed to `processing_class=`). Fixed in the
     notebook; flagged that the install cell doesn't pin a version, so this
     class of breakage can recur.
   - Training was projected to take ~7+ hours at 0.60 it/s. Diagnosed using
     the ACTUAL data (not guessed): median source ~52 words, median target
     ~37 words, both far under the `MAX_SOURCE_LENGTH=384` /
     `MAX_TARGET_LENGTH=256` ceilings — but `tokenize_fn` used
     `padding="max_length"`, so every batch was computed at the full
     384/256 tokens regardless, wasting ~3-5x compute on padding. Fix:
     remove eager padding, let the already-instantiated
     `DataCollatorForSeq2Seq` pad dynamically per batch; also suggested
     lowering the length ceilings to ~160/160 and increasing batch size
     now that padding waste is gone. (Math on step counts — 17,416 total
     steps vs. the ~34,832 expected from 69,657 examples / batch 8 / 4
     epochs — confirmed the run really was using 2 GPUs (data-parallel
     halves step count), ruling out the worse "silently running on CPU"
     explanation.)

7. **This AI's third build session ("Phase 6" in PROGRESS.md)**: user
   trained the T5 model on Kaggle, downloaded it, extracted to
   `models/oracle_log_t5_model/`, asked "then what?" Wired it into
   `generator.py`:
   - New `generate_t5()`: loads via native `transformers`
     (`AutoModelForSeq2SeqLM`/`AutoTokenizer`), **not** through Ollama
     (Ollama/GGUF doesn't support T5's encoder-decoder architecture well,
     unlike the existing decoder-only `generate_local()`). Critically uses
     the EXACT training-time prompt format (`INSTRUCTION + "\n\n" +
     context`, imported directly from `build_finetune_dataset.py` as one
     source of truth) — deliberately NOT the Alpaca `### Instruction:`
     format `generate_local()` uses for the separate Ollama model, since
     mixing those up would silently produce garbage with no error.
   - `generate()` dispatcher: added `mode="t5"`; changed `"auto"` mode's
     fallback order to prefer the local T5 model (if
     `models/oracle_log_t5_model` exists) over Ollama/Llama, matching the
     project's actual goal of avoiding external-service dependency/cost.
   - Model+tokenizer cached at module level after first load.
   - Tested mechanically (not for quality — no access to the user's real
     trained weights or to huggingface.co in this sandbox) by building a
     genuinely tiny, fully-offline, randomly-initialized T5 model + a
     from-scratch-trained BPE tokenizer, and running the real
     `generate_t5()` code path against it: load → tokenize → generate →
     decode → cache → parse. Ran with no exceptions; caching confirmed
     correct.

8. **This AI's fourth build session ("Phase 7" in PROGRESS.md)**: user
   shared screenshots of classifier metrics (F1 0.687 on the informational
   class) and T5 training curves (loss/ROUGE-L improving normally, but
   "format_adherence" flat at exactly 0.000000 across all 4 epochs) and
   asked how to improve accuracy.
   - **Diagnosed the format_adherence number as a measurement bug, not a
     real model failure**: an exact, unmoving zero across thousands of
     examples over 4 epochs while everything else improved was too clean
     to be genuine model failure. Root cause: T5-family tokenizers commonly
     collapse/normalize whitespace (including literal newlines) during
     encoding, so generated output likely came back as one continuous line
     even though training targets had each field on its own line. The old
     parser (`_parse_structured_response` in `generator.py`, and the
     notebook's `extract_fields`) only matched field labels at the START of
     a line via `text.splitlines()` — so only the first field could ever
     match, and the other three were permanently empty. Fixed both to use
     a regex with lookahead that finds each label anywhere in the text.
     Verified the fix against both a newline-separated and a single-line
     simulated example. Added a new "Phase 5B" section to the notebook that
     reloads an already-trained checkpoint and re-evaluates with the fixed
     metric WITHOUT needing to retrain from scratch.
   - **Classifier improvements**: oversampled informational-flagged KB
     codes 8x when regenerating the synthetic corpus (negative class went
     from 2.9% to 17.5% of the classifier dataset, far more diversity);
     added combined word + character n-gram TF-IDF features
     (`src/classifier/features.py::CombinedVectorizer`); compared Logistic
     Regression against a calibrated Linear SVM (Logistic Regression won);
     tuned the decision threshold on the informational-class probability
     instead of using the default 0.5 cutoff, targeting recall >= 0.90
     since the classifier is meant to be a flag for human review, not a
     silent auto-filter. Result: informational-class F1 went from 0.687 to
     **0.882** (precision 0.570→0.863, recall 0.865→0.901). Verified again
     against the real ORA-16111 case: confidence improved from 83.8% to
     90.2%.
   - **Real bug found+fixed while wiring this up**: `CombinedVectorizer`
     was originally defined inline in `train_classifier.py`. Since that
     script runs as `__main__`, pickle recorded its module as `"__main__"`
     rather than a real importable path — so loading the saved vectorizer
     from `classify.py` (a DIFFERENT `__main__`) failed with
     `AttributeError: Can't get attribute 'CombinedVectorizer'`. Fixed by
     moving the class to its own always-imported module,
     `src/classifier/features.py`.

9. **Scope expansion discussion**: user described a broader vision — RAG
   across Oracle, PostgreSQL, MySQL, and SQLite logs, with a fine-tuned
   FLAN-T5 model built entirely by hand, eventually deployed as a website
   (explicitly "for later"). Given, and constrained to, a hard 2-day
   deadline:
   - **SQLite flagged as fundamentally different, not a drop-in**: it's
     embedded, not client-server, so there's no server log file at all —
     it returns numeric result codes directly via its API. Recommended
     treating it as an optional bonus (KB-only, no dedicated parser), not
     presenting it as the same category of thing as the other three.
   - **PostgreSQL and MySQL confirmed as good real additions**: Postgres
     has a small, official, well-documented SQLSTATE code list (cheap to
     hand-curate); MySQL has a much larger official list but only a
     curated ~150-300 common codes is recommended given the time budget.
   - **Recommended NOT fine-tuning 4 separate models or building 4
     separate knowledge bases/classifiers** — one combined KB (with an
     `"engine"` field), one combined fine-tuning dataset (engine named in
     each example's instruction text, e.g. "Analyze this PostgreSQL log
     entry..."), one classifier, one retriever. Also recommended
     continuing fine-tuning FROM the existing trained Oracle T5 checkpoint
     rather than restarting from raw `flan-t5-base` pretrained weights, to
     converge faster.
   - Produced a full day-by-day 2-day execution plan (Postgres first,
     MySQL second, combined fine-tuning last) with explicit cut scope
     (no website, no classifier-pipeline wiring, no stale-test fix, no
     MySQL completeness chase, no 4th real engine).

10. **Handoff request**: user asked for (a) a summary of the whole
    conversation for a future AI (this file), and (b) a complete, detailed,
    all-at-once build plan to hand to Claude in Antigravity, incorporating
    every lesson learned so far without gatekeeping any detail. That build
    plan was written to `BUILD_PLAN_MULTI_ENGINE.md` in the project root —
    it contains the full multi-engine architecture decision, all 11 "lessons
    learned" bugs from this file in detail (so Antigravity doesn't repeat
    them), the file-by-file build list, and the day-by-day execution order.

## Current state of the project (as of the end of this conversation)

### Confirmed working (tested, either by this AI or via the user's own runs)
- Full Simple RAG pipeline: parse → retrieve (BM25, exact+lexical) →
  generate (mock/KB-exact/T5/Llama) → report. 16 original tests pass (1
  pre-existing unrelated failure, see below).
- Knowledge base: 27,282 Oracle entries, 81 prefixes, 878 correctly-flagged
  informational entries.
- Fine-tuning data generation pipeline (logs → dataset) end to end, with
  code-level train/val/test split and zero leakage.
- Tiny classifier: trained, evaluated, tuned (F1 0.882 on informational
  class), verified against the real ORA-16111 case (90.2% confidence).
- T5 Kaggle notebook: fixed three real bugs across sessions (trainer kwarg
  rename, wasteful padding, the newline-collapse parsing bug). A "Phase 5B"
  re-evaluation section was added so the user can re-check their existing
  trained checkpoint's real quality without retraining.
- `generate_t5()` integration in `generator.py`: mechanically verified with
  a fake tiny model; never run against the user's real trained weights
  within this conversation (no internet access to huggingface.co in this
  sandbox, and no copy of the user's actual downloaded model).

### Known outstanding issues (all previously flagged, none silently dropped)
1. `tests/test_retriever.py::test_free_text_retrieve_ranks_relevant_entries_first`
   fails — a stale assumption from when the KB had 58 entries (now
   27,282; BM25 now ranks a different, also-valid deadlock-related entry
   first for that query). Not fixed, out of scope of any specific ask so far.
2. `classify.py` is a standalone module — **not wired into
   `generator.py`/`pipeline.py`**. An error currently gets sent straight to
   `generate()` regardless of whether the classifier would flag it as
   informational.
3. No real quality comparison yet between: KB-exact-match (free/instant),
   the fine-tuned T5 model, and the still-untested Qwen/Ollama path, on the
   same real (or even synthetic) log file.
4. Nothing in this project has ever been run against real Tunisie Telecom
   logs — only synthetic data throughout. Still the single highest-value
   next step whenever real log access becomes possible.
5. The T5 model's TRUE quality (post-parsing-bug-fix) has not actually been
   re-measured yet — that's the user's next step (run the new Phase 5B).
6. `scrape_oracle_docs.py` (the optional KB-expansion script from the first
   build) was apparently run successfully by the user at some point between
   sessions (the KB went from 58 to 27,282 entries) but this AI never
   observed or verified that scraping process directly.
7. The PostgreSQL/MySQL expansion described in point 9 above is a PLAN
   only — `BUILD_PLAN_MULTI_ENGINE.md` describes what to build, but as of
   the end of this conversation, none of it has been built yet.

## Where things live (current repo: `3rd attempt (fixed rag)/`)

```
3rd attempt (fixed rag)/
├── data/
│   ├── knowledge_base/oracle_errors_kb.jsonl      # 27,282 entries
│   ├── synthetic_logs/
│   │   ├── (original demo logs)
│   │   └── finetune_corpus/*.log                  # 55 files, full-KB coverage, informational-oversampled
│   ├── finetune/{train,val,test_unseen_codes}.jsonl
│   └── classifier/{train,val}.jsonl
├── models/
│   ├── error_classifier.joblib
│   ├── error_classifier_vectorizer.joblib
│   ├── error_classifier_threshold.json
│   └── oracle_log_t5_model/                       # user's trained T5, extracted here
├── src/
│   ├── log_parser.py                              # 81 prefixes, code normalization
│   ├── cli.py                                      # --mode auto|mock|t5|llama|local
│   ├── data_generation/
│   │   ├── build_knowledge_base.py                 # original 58 hand-written entries
│   │   ├── scrape_oracle_docs.py                    # user ran this to reach 27,282
│   │   ├── generate_synthetic_logs.py               # original ~20-code demo generator
│   │   ├── generate_finetune_logs.py                # full-KB corpus generator, informational oversampling
│   │   ├── build_finetune_dataset.py                # v2, code-level split
│   │   └── build_finetune_dataset_v1_backup.py
│   ├── classifier/
│   │   ├── features.py                              # CombinedVectorizer (word+char TF-IDF)
│   │   ├── build_classifier_dataset.py
│   │   ├── train_classifier.py                       # LogReg vs LinearSVC comparison, threshold tuning
│   │   └── classify.py                               # uses tuned threshold
│   └── rag/
│       ├── knowledge_base.py
│       ├── retriever.py                            # BM25, exact+lexical fallback
│       ├── generator.py                            # mock / t5 / llama / local / auto, regex-based output parser
│       └── pipeline.py
├── notebook/
│   ├── oracle_log_finetune_kaggle.ipynb            # Qwen2.5-1.5B QLoRA, never run
│   └── oracle_log_t5_finetune_kaggle.ipynb          # FLAN-T5-base, fixed bugs, Phase 5B re-eval section
├── tests/                                          # 16 tests, 1 pre-existing failure (see above)
├── PROGRESS.md                                     # phase-by-phase build log (Phases 1-7)
├── CONVERSATION_SUMMARY.md                         # this file
└── BUILD_PLAN_MULTI_ENGINE.md                      # the Postgres/MySQL/SQLite expansion plan, not yet executed
```

## Multi-Engine Expansion (Phase 8 — Completed)

`BUILD_PLAN_MULTI_ENGINE.md` has been fully implemented and tested (**53/53 pytest tests passing**):
- PostgreSQL and MySQL parsers + engine detection module created.
- PostgreSQL and MySQL knowledge bases built and merged (`combined_errors_kb.jsonl` — 27,622 entries, 0 duplicate codes).
- Synthetic log generators and fine-tuning datasets built for all 3 engines with zero code leakage (101k examples).
- Classifier retrained on multi-engine data (`train_v2.jsonl`) with 96% accuracy and 0.893 informational F1.
- Complete self-contained Kaggle notebook created at `notebooks/kaggle_finetune_t5_from_scratch.ipynb`.

👉 **For the complete architecture, inventory of changes, and instructions for the next session, see [`HANDOFF_NEXT_SESSION.md`](file:///c:/Users/Rayen/Desktop/proj/PROJET-STAGE-TT/Projet%20Rayen%20Thabet/HANDOFF_NEXT_SESSION.md).**

