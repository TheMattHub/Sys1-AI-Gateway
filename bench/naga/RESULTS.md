# Naga System-1 bench: results

Rerun everything (from the repo root, Windows; see bench/naga/README.md): `powershell -ExecutionPolicy Bypass -File bench/naga/run.ps1` (exports the engine data, runs every
engine in its venv, starting and stopping its server, then `report.py` rebuilds the tables below). One engine:
the same with `-Only <engine>`. Seeds fixed (0); GPU RTX A500 4 GB; latency = wall clock per decision.

Data: T = naga tests/test_toolsearch.py (TRAIN = EVAL + HELD_OUT, 54; TEST = HELD_OUT_2, 25, frozen);
B = data/*.jsonl (frozen, blind), fields with data/CORRECTIONS.md applied (16 of 30 rows kept).
Top-1/top-3 count a hit when any accepted label is there. Threshold rule in report.py.

<!-- tables:start -->
### T: tool choice (re-rank of find_tool's top 10)

Candidate recall@10 (the ceiling): TRAIN 54/54, TEST 19/25.

| engine | TRAIN top-1 | TRAIN top-3 | TEST top-1 | TEST top-3 | median ms | threshold (TRAIN) | TEST above threshold | errors |
|---|---|---|---|---|---|---|---|---|
| baseline | 44/54 | 54/54 | 8/25 | 14/25 | 0 | 0.613 | 5/25 at 20% |  |
| harrier-bi | 37/54 | 46/54 | 8/25 | 16/25 | 155 | 0.082 | 2/25 at 100% |  |
| gte-rerank | 42/54 | 47/54 | 14/25 | 17/25 | 96 | 0.342 | 5/25 at 40% |  |
| qwen3-rerank | 44/54 | 51/54 | 14/25 | 19/25 | 513 | 0.982 | 0/25 |  |

### B: blocks (40 rows, all TEST)

| engine | accuracy | top-3 | median ms | above T threshold | errors |
|---|---|---|---|---|---|
| baseline | 15/40 | 30/40 | 0 | 16/40 at 31% |  |
| harrier-bi | 15/40 | 22/40 | 27 | 0/40 |  |
| gte-rerank | 25/40 | 31/40 | 75 | 0/40 |  |
| qwen3-rerank | 24/40 | 35/40 | 591 | 0/40 |  |

### B: distributions (30 rows, all TEST)

| engine | accuracy | top-3 | median ms | above T threshold | errors |
|---|---|---|---|---|---|
| baseline | 17/30 | 27/30 | 0 | 13/30 at 85% |  |
| harrier-bi | 13/30 | 24/30 | 26 | 0/30 |  |
| gte-rerank | 19/30 | 23/30 | 91 | 0/30 |  |
| qwen3-rerank | 21/30 | 28/30 | 754 | 0/30 |  |

<!-- tables:end -->

## Notes (per engine, in run order)
- baseline: T = find_tool's own order (matches the test file: TEST top-1 8, top-3 14). B = the engine's BM25
  tool search (nagasim.toolsearch) over the label one-liners: plain token overlap.
- harrier-bi (microsoft/harrier-oss-v1-270m, MIT): the B bi-encoder baseline; its top 20 is the shortlist
  for Laya and Gemma on blocks (24 labels) and distributions (31); shortlist recall@20: blocks 40/40,
  distributions 29/30.
- Label documents are the engine's one-liners, some very thin ("CREATE: Entity source.", "DECIDE: N-way
  branch."): every encoder that reads only the document is capped by that; Gemma brings its own knowledge.
- gte-rerank, qwen3-rerank (model card yes/no prompt with one instruction per task), nli (zero-shot pipeline,
  default template), gliner2 (classification with {label: description}, softmax over all labels): one pass each.
- laya (typed-decisions, via system1_gateway LayaProvider), von (von-1.3, criteria {label: document}): one
  pass each in their native choice form, no prompt variations (2026-10-19).
- gemma4 (hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M via the gateway's OllamaProvider: options as letters, one
  letter back, probabilities from logprobs; one call per decision). 1 error: on TEST-7 ("is it worth buying
  another machine") it answered "I" instead of a letter (format not followed), counted as a miss.
- von: no TRAIN threshold reaches 90% top-1, so no coverage figure.
- Dropped by the maintainer (time box): Qwen3-4B / a second LLM, jina-reranker (non-commercial), other embeddings.
- Run environment: the Store build of pwsh cannot load its modules from this agent's shell, so run.ps1 is
  written for Windows PowerShell 5.1 as well.
- tuned (tune.py): gte-reranker-modernbert-base, the smallest tunable cross-encoder (149M), fine-tuned with a
  listwise loss on T TRAIN (find_tool's top 10 as hard negatives) plus 211 synthetic queries made from later
  sentences of the tool descriptions and 20 block-docstring pairs; never a TEST row. 2 epochs, lr 2e-5, seed 0.
  Honest check first, 2-fold CV on TRAIN grouped by gold tool: zero-shot 42/54 -> tuned 45/54 (+3).
  TEST measured once, at the end: T top-1 14 -> 15/25, top-3 17 -> 18/25 (ceiling 19). B got no better
  (blocks 17 -> 13, distributions 9 -> 11, fields 10 -> 11): B's synthetic pairs are too few and thin.
  The tuned row's TRAIN columns and threshold are on its own training data: read only its TEST columns.

## Summary (2026-10-19)
- T, tool choice: the re-rank ceiling is 19/25 (find_tool's top 10 misses 6 TEST queries). Best: Gemma 4
  E4B, TEST top-1 18/25, top-3 19/25 (find_tool alone 8 and 14), but 2.1 s median per decision. Best fast:
  the TRAIN-tuned gte cross-encoder, 15/25 and 18/25 at 105 ms; zero-shot nli 15/25, gte and qwen3 14/25,
  Laya 13/25 at 65 ms. Von, harrier and GLiNER2 are near or below the others.
- B, model building: only Gemma is reliable: blocks 33/40, distributions 28/30, fields 15/16, 0.7-2.1 s.
  The encoders read the engine's one-line label docs, which are too thin ("Entity source."): best of them
  Von 23/40 on blocks, qwen3/GLiNER2 17/30 on distributions, Laya and harrier 13/16 on fields.
- Tuning helped T a little (CV on TRAIN +3/54; TEST +1 top-1) and not B.
- Confidence: at the TRAIN threshold Gemma covers 20/25 T TEST decisions at 85% right; no fast engine gives a
  threshold that holds on TEST (Laya 21/25 at 62%, tuned 23/25 at 61%).

<!-- r2:start -->
## Round 2 (2026-10-20)

Fuller block and distribution descriptions (naga after the fuller-descriptions change), T also over all 90 tools. Fields not rerun (their texts did not change).

#### T, mode top10 (find_tool's 10 candidates)

| engine | TRAIN top-1 | TRAIN top-3 | TEST top-1 | TEST top-3 | median ms | note |
|---|---|---|---|---|---|---|
| baseline | 44/54 | 54/54 | 8/25 | 14/25 | 0 |  |
| harrier-bi | 37/54 | 46/54 | 8/25 | 16/25 | 155 |  |
| gte-rerank | 42/54 | 47/54 | 14/25 | 17/25 | 96 |  |
| qwen3-rerank | 44/54 | 51/54 | 14/25 | 19/25 | 513 |  |
| nli | 44/54 | 49/54 | 15/25 | 17/25 | 624 |  |
| gliner2 | 36/54 | 50/54 | 12/25 | 16/25 | 1015 |  |
| laya | 48/54 | 52/54 | 13/25 | 17/25 | 66 |  |
| von | 24/54 | 42/54 | 9/25 | 16/25 | 488 |  |
| gemma4 | 48/54 | 52/54 | 18/25 | 19/25 | 2604 | 1 errors |
| tuned | 54/54 | 54/54 | 11/25 | 17/25 | 104 |  |
| haiku | 50/54 | 52/54 | 19/25 | 19/25 | 923 | hosted (Anthropic API), all options |

#### T, mode all (all 90 tools)

| engine | TRAIN top-1 | TRAIN top-3 | TEST top-1 | TEST top-3 | median ms | note |
|---|---|---|---|---|---|---|
| baseline | 44/54 | 54/54 | 8/25 | 14/25 | 0 |  |
| harrier-bi | 27/54 | 38/54 | 8/25 | 12/25 | 27 |  |
| gte-rerank | 39/54 | 44/54 | 14/25 | 19/25 | 1130 |  |
| qwen3-rerank | 40/54 | 51/54 | 15/25 | 22/25 | 5392 |  |
| nli | 38/54 | 48/54 | 14/25 | 18/25 | 5160 |  |
| gliner2 | 27/54 | 37/54 | 14/25 | 18/25 | 6458 |  |
| laya | 34/54 | 45/54 | 16/25 | 18/25 | 66 | harrier top 20 as options |
| von | 4/54 | 16/54 | 2/25 | 8/25 | 17361 |  |
| gemma4 | 44/54 | 47/54 | 19/25 | 19/25 | 3042 | harrier top 20 as options |
| tuned | 54/54 | 54/54 | 11/25 | 16/25 | 1067 |  |
| haiku | 44/54 | 47/54 | 22/25 | 23/25 | 964 | hosted (Anthropic API), all options |

#### B: blocks

| engine | R1 acc | R1 top-3 | R2 acc | R2 top-3 | R2 median ms | note |
|---|---|---|---|---|---|---|
| baseline | 11/40 | 15/40 | 15/40 | 30/40 | 0 |  |
| harrier-bi | 5/40 | 11/40 | 15/40 | 22/40 | 27 |  |
| gte-rerank | 17/40 | 23/40 | 25/40 | 31/40 | 75 |  |
| qwen3-rerank | 19/40 | 27/40 | 24/40 | 35/40 | 591 |  |
| nli | 21/40 | 29/40 | 21/40 | 31/40 | 1134 |  |
| gliner2 | 13/40 | 27/40 | 25/40 | 32/40 | 693 |  |
| laya | 9/40 | 19/40 | 18/40 | 29/40 | 65 | shortlist: harrier top 20 |
| von | 23/40 | 29/40 | 22/40 | 30/40 | 356 | all labels |
| gemma4 | 33/40 | 36/40 | 34/40 | 36/40 | 2455 | shortlist: harrier top 20 |
| tuned | 13/40 | 24/40 | 21/40 | 32/40 | 83 |  |
| haiku | - | - | 37/40 | 37/40 | 906 | all labels |

#### B: distributions

| engine | R1 acc | R1 top-3 | R2 acc | R2 top-3 | R2 median ms | note |
|---|---|---|---|---|---|---|
| baseline | 11/30 | 14/30 | 17/30 | 27/30 | 0 |  |
| harrier-bi | 12/30 | 21/30 | 13/30 | 24/30 | 26 |  |
| gte-rerank | 9/30 | 21/30 | 19/30 | 23/30 | 91 |  |
| qwen3-rerank | 17/30 | 25/30 | 21/30 | 28/30 | 754 |  |
| nli | 12/30 | 20/30 | 19/30 | 24/30 | 1430 |  |
| gliner2 | 17/30 | 23/30 | 20/30 | 28/30 | 834 |  |
| laya | 15/30 | 22/30 | 13/30 | 22/30 | 75 | shortlist: harrier top 20 |
| von | 8/30 | 19/30 | 13/30 | 21/30 | 359 | all labels |
| gemma4 | 28/30 | 29/30 | 27/30 | 29/30 | 2316 | shortlist: harrier top 20 |
| tuned | 11/30 | 18/30 | 16/30 | 23/30 | 113 |  |
| haiku | - | - | 30/30 | 30/30 | 876 | all labels |

## Round 2, retries

| engine | task | variant | TEST 1 / 2 / 3 | TRAIN 1 / 2 / 3 | mean ms per request (TEST) |
|---|---|---|---|---|---|
| tuned | T | plain | 11 / 17 / 17 of 25 | 54 / 54 / 54 of 54 | 197 |
| tuned | T | nudged | 11 / 16 / 17 of 25 | 54 / 54 / 54 of 54 | 209 |
| tuned | Tall | plain | 11 / 16 / 16 of 25 | 54 / 54 / 54 of 54 | 2037 |
| tuned | Tall | nudged | 11 / 15 / 16 of 25 | 54 / 54 / 54 of 54 | 2169 |
| tuned | blocks | plain | 21 / 32 / 32 of 40 | - | 139 |
| tuned | blocks | nudged | 21 / 25 / 26 of 40 | - | 198 |
| tuned | distributions | plain | 16 / 20 / 23 of 30 | - | 197 |
| tuned | distributions | nudged | 16 / 19 / 22 of 30 | - | 240 |
| laya | T | plain | 13 / 17 / 17 of 25 | 48 / 49 / 51 of 54 | 125 |
| laya | T | nudged | 13 / 14 / 16 of 25 | 48 / 48 / 50 of 54 | 138 |
| laya | Tall | plain | 16 / 17 / 19 of 25 | 34 / 43 / 46 of 54 | 145 |
| laya | Tall | nudged | 16 / 17 / 18 of 25 | 34 / 42 / 44 of 54 | 149 |
| laya | blocks | plain | 18 / 24 / 28 of 40 | - | 167 |
| laya | blocks | nudged | 18 / 20 / 21 of 40 | - | 181 |
| laya | distributions | plain | 13 / 16 / 22 of 30 | - | 177 |
| laya | distributions | nudged | 13 / 16 / 19 of 30 | - | 178 |

Oracle (the ranking of the round-2 run, no retry):

| engine | task | oracle TEST top-1 / 2 / 3 | oracle TRAIN top-1 / 2 / 3 |
|---|---|---|---|
| tuned | T | 11 / 17 / 17 of 25 | 54 / 54 / 54 of 54 |
| tuned | Tall | 11 / 16 / 16 of 25 | 54 / 54 / 54 of 54 |
| tuned | blocks | 21 / 32 / 32 of 40 | - |
| tuned | distributions | 16 / 20 / 23 of 30 | - |
| laya | T | 13 / 17 / 17 of 25 | 48 / 49 / 52 of 54 |
| laya | Tall | 16 / 16 / 18 of 25 | 34 / 41 / 45 of 54 |
| laya | blocks | 18 / 24 / 29 of 40 | - |
| laya | distributions | 13 / 17 / 22 of 30 | - |

## Phase 4

Study open = the gold tool starts with study_. Cells are TEST / TRAIN counts (25 / 54 rows). End-to-end top-3 = a gold tool in the first three of the stage-2 ranking inside the stage-1 top-1 family. Baseline = single-stage over all 90 (round-2 Tall run).

| engine | single-stage 90: top-1 / top-3 | 4a subset: top-1 / top-3 (gold offered) | 4b stage 1 family top-1 | 4b stage 2 given true family top-1 | 4b end-to-end top-1 / top-3 | 4c group-right top-1 (gain) |
|---|---|---|---|---|---|---|
| tuned | 11/16 / 54/54 | 13/17 / 52/54 (25/25 / 54/54) | 12 / 48 | 16 / 54 | 9/11 / 46/48 | 10 / 46 (+1 / +0) |
| gte | 14/19 / 39/44 | 14/20 / 42/45 (25/25 / 54/54) | 15 / 40 | 19 / 45 | 12/14 / 39/39 | 13 / 39 (+1 / +0) |
| laya | 16/18 / 34/45 | 15/18 / 39/48 (25/25 / 54/54) | 11 / 29 | 20 / 45 | 8/10 / 25/28 | 8 / 25 (+0 / +0) |

Groups that gave 4c gains (engine:row):
- TEST: twin_read (tuned:TEST-12, gte:TEST-12)
<!-- r2:end -->

## Round 2 notes and summary (2026-10-20)
Rerun: `BENCH_ROUND=2` via `run.ps1 -Round 2 -Naga <path to a naga clone> [-Only <engine|retry-tuned|retry-laya|phase4-tuned|phase4-gte|phase4-laya>]`;
data in derived2/, results in results2/, tables by `report2.py`, phase 4 by `phase4.py report`. Round 1 files are untouched.
- Conditions: label texts = the engine's list_block_types / list_distributions summaries from post-desc 4664d7e9; T "all" = the
  90 tool documents. Fields not rerun. Test sets frozen, no corrections.
- Shortlists: Laya and Gemma on T "all" and on B get the harrier bi-encoder's top 20 (Laya's cap 20, Gemma's 26 letters).
  GLiNER2 on T "all" ran out of GPU memory with 90 long documents (4 GB): it got the harrier top 20 too. Von got all labels in
  round 2 (round 1 shortlisted its B sets); with 90 criteria it fell apart (2/25 TEST, 17 s per decision).
- gemma4 (added back by the maintainer, run last): 1 format error on T top10 as in round 1.
- tuned: retrained with hard negatives from the full 90 as well (5 from find_tool's top 10 plus 4 from ranks 11-90). Grouped 2-fold
  CV on TRAIN: top10 zero-shot 42 -> tuned 45 of 54, all-90 39 -> 41. TEST was measured once: T top-1 11/25 (round 1: 15/25), so
  the retune did not hold on TEST (25 rows; the TRAIN columns are its own training data and read 54/54).
- Phase 3 rules: a pick is wrong when not in gold; plain retry removes rejected labels, nudged adds "(not: <label>: <one-line
  summary>; ...)" (cross-encoder query) or the same text in Laya's context. Laya's shortlist is refilled from the harrier order;
  harrier's latency is added once per request. Time = mean per TEST request, retries included (a request stops when right).
- Summary: (1) The fuller descriptions help B a lot for the encoders: blocks gte 17 -> 25 of 40, GLiNER2 13 -> 25, Laya 9 -> 18,
  tuned 13 -> 21, qwen3 19 -> 24; distributions gte 9 -> 19, nli 12 -> 19, qwen3 17 -> 21; Gemma stays top (34/40, 27/30, about 2.4 s);
  Von and NLI-blocks flat. T top10 is unchanged (tool texts barely changed). (2) "All 90" vs "top 10" for the fast rerankers: top-3
  rises (gte 17 -> 19, qwen3 19 -> 22 of 25, since the 6 misses of find_tool's top 10 are reachable), top-1 stays (gte 14, tuned 11),
  TRAIN top-1 falls (gte 42 -> 39, qwen3 44 -> 40), latency x10 or more (gte 96 -> 1130 ms). (3) Best fast: T Laya 16/25 top-1 at 66 ms
  (with the harrier shortlist; gte 14/25 at 96 ms on top 10); blocks gte 25/40 at 75 ms; distributions gte 19/30 at 91 ms
  (qwen3 21/30 at 0.75 s). (4) Retries: a plain retry reaches the oracle ranking (3 attempts: tuned blocks 21 -> 32 of 40, Laya blocks 18 -> 28);
  the nudge never beat a plain retry and often lost (tuned blocks 26 vs 32, Laya blocks 21 vs 28), so the rejected labels' summaries
  mislead the encoders. (5) Phase 4: see the table; a subset by context (4a) is flat on TEST and helps TRAIN a little, two-stage (4b)
  is worse than single-stage (family errors compound), merging near-duplicates (4c) adds at most +1 (twin_read).

## Distillation (2026-10-20/21)

Can a fast local picker learn tool choice from a stronger model? The fine-tune on 54 TRAIN questions did not hold
(above), so this time gte-reranker-modernbert-base was trained on about 1,000 requests labelled by a teacher, one
student per teacher: Gemma 4 E4B (local, Apache-2.0) and Claude Haiku 5.5 (Anthropic API). Matteo chose to train on
Haiku's labels; each table row names the teacher whose labels it learned from. Scripts and data: `distill/`
(`prep.py`, `label.py`, `train.py`, `report.py`; notes and doubts in `distill/NOTES.md`). Run with `BENCH_ROUND=distill`.

- TEST2 (new, blind, frozen first): 100 requests written by a fresh Claude Sonnet 5.5 subagent that saw only the 90
  tool names, every tool gold at least once; committed before any teacher or student saw it. HELD_OUT_2 = round 2's
  25 TEST questions. find_tool's top 10 holds the gold for 80/100 TEST2 and 19/25 HELD_OUT_2 rows (top10 ceiling).
- TRAIN2: 1,080 requests generated by three Claude Sonnet 5.5 subagents (12 per tool) from the full tool descriptions
  and the 54 TRAIN questions; 6 near-duplicates and 7 near-copies of TEST2/HELD_OUT_2 rows dropped (word-set Jaccard
  >= 0.6): 1,067 kept, 961 to fit, 106 held out (seed 0).
- Labels: each teacher's top 3 for every TRAIN2 request, with the bench's prompt (common.question, the 90 tool
  documents). Haiku saw all 90; Gemma saw the harrier top-20 shortlist (its letter limit), as in round 2.
- Students: tune.py's recipe unchanged (listwise loss, hard negatives from find_tool's top 10 and ranks 11-90,
  2 epochs, lr 2e-5, seed 0, one run each); positive = the teacher's top-1, its 2nd and 3rd picks left out of the
  negatives (the loss takes one positive). No tuning against TEST2.

| engine | mode | TEST2 top-1 | TEST2 top-3 | HELD_OUT_2 top-1 | HELD_OUT_2 top-3 | median ms | errors |
|---|---|---|---|---|---|---|---|
| find_tool alone | all 90 | 36/100 | 51/100 | 8/25 | 14/25 | 1 |  |
| gte, untuned | all 90 | 58/100 | 80/100 | 14/25 | 19/25 | 1191 |  |
| gte <- Gemma labels | all 90 | 50/100 | 86/100 | 10/25 | 17/25 | 1191 |  |
| gte <- Haiku labels | all 90 | 80/100 | 92/100 | 15/25 | 18/25 | 1189 |  |
| Gemma 4 E4B | all 90 | 69/100 | 82/100 | 19/25 | 19/25 | 3223 | 1 |
| Claude Haiku 5.5 (API) | all 90 | 82/100 | 95/100 | 22/25 | 23/25 | 1002 |  |
| find_tool alone | top10 | 36/100 | 51/100 | 8/25 | 14/25 | 1 |  |
| gte, untuned | top10 | 53/100 | 75/100 | 14/25 | 17/25 | 109 |  |
| gte <- Gemma labels | top10 | 63/100 | 79/100 | 13/25 | 17/25 | 109 |  |
| gte <- Haiku labels | top10 | 70/100 | 78/100 | 14/25 | 18/25 | 110 |  |
| Gemma 4 E4B | top10 | 67/100 | 77/100 | 19/25 | 19/25 | 2390 | 3 |
| Claude Haiku 5.5 (API) | top10 | 76/100 | 80/100 | 19/25 | 19/25 | 950 |  |

Plain retry, students (right within 1 / 2 / 3 tries; mean ms per request, retries included):

| student | mode | TEST2 1 / 2 / 3 | HELD_OUT_2 1 / 2 / 3 | mean ms (TEST2) |
|---|---|---|---|---|
| gte-gemma4 | all 90 | 50 / 78 / 86 of 100 | 10 / 15 / 17 of 25 | 2042 |
| gte-haiku | all 90 | 80 / 89 / 92 of 100 | 15 / 15 / 18 of 25 | 1549 |
| gte-gemma4 | top10 | 63 / 77 / 79 of 100 | 13 / 16 / 17 of 25 | 240 |
| gte-haiku | top10 | 70 / 77 / 78 of 100 | 14 / 17 / 18 of 25 | 227 |

| teacher | labelled | top-1 = generated gold | generated gold in top 3 | labelling time | API tokens in / out |
|---|---|---|---|---|---|
| gemma4 | 1067/1067 | 838 | 912 | 57 min | - |
| haiku | 1067/1067 | 943 | 1012 | 20 min | 13,281,633 / 55,594 |

The two teachers give the same top-1 on 824 of 1067 requests.
- student gte <- gemma4: trained on 961 requests in 26.6 min (GPU); held-out 106: agrees with its teacher on 58, matches the generated gold on 52 (the teacher itself: 81).
- student gte <- haiku: trained on 961 requests in 26.6 min (GPU); held-out 106: agrees with its teacher on 80, matches the generated gold on 84 (the teacher itself: 91).

Plain retry: a cross-encoder scores each option on its own, so removing a rejected pick leaves the others in the
same order: try k is right exactly when the gold is in the first k. The time is the measured decision time times
the tries used (an estimate). Gemma had 3 format errors on top10 and 1 on all 90 (it answered a word, not a
letter), counted as misses; its labelling run had none. Haiku's tokens are mostly cache reads (the 90 tool documents,
about 12,300 tokens, are the cached system block); the benchmark itself used 1,825,017 in / 13,090 out more.
GPU time: Gemma labelling 57 min, each student 26.6 min of training, every bench run under 10 min.

Read:
- Haiku's labels made a student that nearly matches its teacher on TEST2: all 90 tools, top-1 80/100 against
  Haiku's 82 and untuned gte's 58, top-3 92 against 95, at 1.2 s per decision on the laptop GPU (Haiku about 1 s
  over the network). Over find_tool's top 10 it gets 70/100 at 110 ms (Haiku 76, ceiling 80).
- Gemma's labels did not: its student is below untuned gte over all 90 (50/100 top-1) and in between on top10
  (63/100). Gemma's top-1 matched the generated gold on 838 of 1,067 TRAIN2 requests, Haiku's on 943; on the 106
  held-out requests the Gemma student agreed with its teacher on 58, the Haiku student with its teacher on 80.
- On HELD_OUT_2 (25 questions written before this study, by a different hand) the gain mostly vanishes: Haiku
  student 15/25 all 90 and 14/25 top10, untuned gte 14 and 14, Haiku 22 and 19. TRAIN2 and TEST2 were both written
  by Claude Sonnet 5.5, so part of the TEST2 gain is likely the shared style of requests, not tool knowledge.
- Cost of the Haiku student: about 13.3 M input tokens (mostly cached) and 56 k output tokens for 1,067 labels,
  20 min of API time, then 27 min of GPU training.

## Round 3 (2026-10-21)

New System-1 decision models, and every earlier engine whose run is cheap, on TEST2 (100, frozen; distill/) in
modes top10 and all 90, plus round 2's blocks (40) and distributions (30). Table: `python report3.py`; engines:
`eng_d1.py`, `eng_openthai.py`, `eng_anyjev.py` (and the earlier `eng_*.py` with `BENCH_ROUND=distill`).
`BENCH_TASKS=T,Tall` picks tasks in any round; rows go to a `.part` file, so a time-boxed run resumes.

Models (ids, licences and sizes from the model cards, 2026-10-20):
- `LiquidAI/d1-omni-600M` (587M) and `LiquidAI/d1-3B` (3.12B), LFM Open License v1.0: free, but commercial use is
  licensed only to organisations below USD 10 M annual revenue. Run as the GGUF builds (`LiquidAI/d1-omni-600M-GGUF`
  F16, `LiquidAI/d1-3B-GGUF` Q8_0; d1-3B's 6.2 GB of weights do not fit 4 GB) through llama.cpp b11757's
  `llama-server` (`-np 1 -c 16384 -b 16384 -ub 16384`; a decision model needs the whole input in one batch),
  `POST /v1/systemone`, one `choice` question, criteria {label: document}, up to 255 options, so all 90 tools.
- `iapp/OpenThai-SystemOne` (0.8B, Apache-2.0): the HF weights through its own client (`openthai-systemone==0.1.0`,
  float16, all options, order averaging above 10); and its Ollama build `iapp/openthai-systemone:0.8b` (Q8_0)
  through the gateway's ollama provider (letters, harrier top 20 above 20 options). Ollama 0.40.6's own
  `/v1/systemone` refuses the build ("not a llama.cpp decision model").
- AnyJev 0.3.0 (Nokia, Apache-2.0, github.com/nokia-applied-research/AnyJev): the training-free `Decider` at L0 with
  two rotations (its Decision Index settings) over `Qwen/Qwen3-1.7B` (Apache-2.0; 4.1 GB in bfloat16, so 4-bit NF4
  via bitsandbytes). Letter readout, at most 26 options: harrier top 20 for all 90 tools and the distributions.
- Skipped: JEV-9B (does not fit 4 GB); Jeva: weights exist (`LIQIIIII/Jeva-4B`, Apache-2.0, 4B, about 8 GB in
  16-bit), but they do not fit 4 GB unquantised; quantising it was not tried tonight.

| engine | kind | TEST2 top10: top-1 / top-3 | ms | TEST2 all 90: top-1 / top-3 | ms | HELD_OUT_2 all 90 | blocks (40) | distributions (30) | B ms |
|---|---|---|---|---|---|---|---|---|---|
| find_tool alone | - | 36 / 51 | 1 | 36 / 51 | 1 | 8 / 14 | 15 / 30 | 17 / 27 | 0 |
| harrier (bi-encoder) | encoder | 44 / 72 | 159 | 35 / 64 | 30 | 8 / 12 | 15 / 22 | 13 / 24 | 27 |
| gte-reranker, zero-shot | encoder | 53 / 75 | 109 | 58 / 80 | 1191 | 14 / 19 | 25 / 31 | 19 / 23 | 75 |
| gte-reranker, round-1 fine-tune | encoder | 65 / 79 | 112 | 73 / 90 | 1190 | 15 / 20 | - | - | - |
| gte <- Haiku labels | encoder | 70 / 78 | 110 | 80 / 92 | 1189 | 15 / 18 | - | - | - |
| gte <- Gemma labels | encoder | 63 / 79 | 109 | 50 / 86 | 1191 | 10 / 17 | - | - | - |
| Qwen3-Reranker-0.6B | encoder | 61 / 78 | 520 | 64 / 86 | 5849 | 15 / 22 | 24 / 35 | 21 / 28 | 591 |
| ModernBERT-NLI | encoder | 56 / 72 | 649 | - | - | - | 21 / 31 | 19 / 24 | 1134 |
| GLiNER2.5 | System-1 | 49 / 68 | 1179 | - | - | - | 25 / 32 | 20 / 28 | 693 |
| Laya | System-1 | 52 / 74 | 65 | 52 / 74 | 66 | 16 / 18 | 18 / 29 | 13 / 22 | 65 |
| Von 1.3 | System-1 | 41 / 65 | 491 | - | - | - | 22 / 30 | 13 / 21 | 356 |
| d1-omni-600M (new) | System-1 | 52 / 75 | 47 | 43 / 58 | 364 | 7 / 10 | 16 / 26 | 8 / 18 | 110 |
| d1-3B (new) | System-1 | 69 / 78 | 1377 | 73 / 91 | 13676 | 19 / 20 | 33 / 38 | 28 / 29 | 1096 |
| OpenThai-SystemOne (new) | System-1 | 55 / 63 | 556 | 7 / 10 | 16621 | 2 / 3 | 23 / 35 | 23 / 26 | 339 |
| OpenThai, Ollama build (new) | System-1 | 31 / 53 | 289 | - | - | - | 5 / 15 | 16 / 19 | 244 |
| AnyJev L0 on Qwen3-1.7B (new) | System-1 | 25 / 44 | 1454 | 21 / 39 | 2461 | 8 / 11 | 12 / 21 | 16 / 24 | 1115 |
| Gemma 4 E4B | LLM | 67 / 77 | 2390 | 69 / 82 | 3223 | 19 / 19 | 34 / 36 | 27 / 29 | 2455 |
| Claude Haiku 5.5 (API) | LLM | 76 / 80 | 950 | 82 / 95 | 1002 | 22 / 23 | 37 / 37 | 30 / 30 | 906 |

Not rerun on TEST2 (not cheap): NLI and GLiNER2.5 over all 90 (5-6 s a decision), Von over all 90 (17 s and 2/25
in round 2). The round-1 fine-tune is `models/tuned` (54 TRAIN questions, round-1 texts; round 2's retune is gone
from disk), so its model-building cells stay empty here. HELD_OUT_2 = round 2's 25 TEST questions.

Read:
- d1-3B is the first local model to match Gemma 4 E4B everywhere: TEST2 top-1 73/100 over all 90 tools (Gemma 69)
  and 69/100 over the top 10 (Gemma 67), HELD_OUT_2 19/25 (Gemma 19), blocks 33/40 (34), distributions 28/30 (27),
  with no format errors. It is slow on this GPU: 1.1-1.4 s over short option lists, 13.7 s over all 90 (Q8_0 fills
  the 4 GB, and 90 tool documents are about 9k tokens). Licence: commercial use only below USD 10 M revenue.
- d1-omni-600M is fast (47 ms over the top 10) but on par with untuned gte at best (52/100 vs 53) and weak over
  all 90 and on model building.
- OpenThai-SystemOne through its own client is a fair Apache-2.0 option for short lists (top10 55/100, blocks 23/40,
  distributions 23/30 at 0.3-0.6 s) and collapses over 90 long options (7/100). Its Ollama build through the
  gateway's letter prompt is much worse (blocks 5/40): it was tuned for Ollama's own System One prompt.
- AnyJev L0 on a 1.7B base in 4 bits is below `find_tool` alone on tool choice (25/100 top10): the training-free
  layer cannot add knowledge the small base lacks. Its leaderboard result is on Gemma-4-31B.
- Among earlier engines the order on TEST2 holds: Haiku 82 > gte <- Haiku 80 > d1-3B 73 = round-1 fine-tune 73 >
  Gemma 69 > Qwen3-Reranker 64 > gte 58 (all 90, top-1).

Routing study (round 3): the Claude Code routing question was rerun on the public seed sets with every engine
that answers a choice or a yes/no, through its gateway provider; script `bench/routing/routing.py`, results
`bench/routing/results/`, report `docs/studies/claude-code-routing.md`. Direct choice, out of 45 (always-sonnet 15):
Haiku 43, Gemma 41, d1-3B 40, OpenThai 37, Von 35, Laya 31, gte 30, d1-omni 29, Qwen3-Reranker 24, AnyJev 23,
OpenThai via Ollama 21. Features + rule: d1-3B 32, Haiku 30, Von 24, d1-omni 20, OpenThai 19, Gemma 18, Laya 18,
gte 16, AnyJev 16, Qwen3-Reranker 15, OpenThai via Ollama 9. The seeds are small and synthetic, so this does not
overturn the 284-task result that made routing ask features.

## Round 4: a multi-writer test (2026-10-21)

Does the students' gain hold on requests not written by Claude Sonnet? TEST2 and TRAIN2 were both Sonnet's, so
round 4 adds TEST3: 150 requests by four writers, each seeing only the 90 tool names and the target tool (the gold),
frozen and committed before any picker saw it (`distill/write3.py`; drops, coverage and doubts in
`distill/NOTES.md`). Writers: Claude Opus 5.5 (38 rows), Gemma 4 E4B (40), Qwen3-1.7B (34; the AnyJev base on
disk, 4-bit) and LiquidAI d1-3B (38; it writes plain text through llama-server's chat endpoint, so it stayed).
89 of 90 tools are gold (study_revert's one row was a near-copy of a TRAIN2 row). find_tool's top 10 holds the gold
for 94 of 150 rows (the top10 ceiling). Run with `BENCH_ROUND=test3` (`distill/derived3`, `distill/results3`; the
TEST2 and HELD_OUT_2 rows of engines run last night are copied in, so only new rows ran); tables: `distill/report4.py`.
Median ms is over the TEST3 rows.

Claude Opus 5.5 as a picker: same prompt as Haiku, but Opus 5.5 refuses a forced `tool_choice` (HTTP 400), so it
gets `tool_choice: auto` plus one line "Answer only by calling the choose tool." and max_tokens 4,000 (its
thinking cannot be turned off; effort left at its default, medium). No row missed the tool call.

Students (same recipe, seed and split as last night; training now resumes from a checkpoint across calls):
- gte <- Opus labels: the gate (Opus beats Haiku on TEST3 all-90 top-1 by at least 3 points) passed, 98 against
  86 of 150 (65 % against 57 %), so Opus labelled all 1,067 TRAIN2 requests (top 3 over all 90).
- gte <- agreed labels: the TRAIN2 rows where Haiku's and Opus's top-1 both equal the generated tool (936 of 1,067),
  positive = that tool, both teachers' other top-3 picks left out of the negatives.

| engine | mode | TEST3 top-1 | TEST3 top-3 | median ms | TEST2 top-1 | TEST2 top-3 | HELD_OUT_2 top-1 | errors |
|---|---|---|---|---|---|---|---|---|
| find_tool alone | all 90 | 36/150 | 63/150 | 0 | 36/100 | 51/100 | 8/25 |  |
| gte, untuned | all 90 | 75/150 | 99/150 | 1228 | 58/100 | 80/100 | 14/25 |  |
| gte <- Gemma labels | all 90 | 48/150 | 111/150 | 1371 | 50/100 | 86/100 | 10/25 |  |
| gte <- Haiku labels | all 90 | 96/150 | 123/150 | 1221 | 80/100 | 92/100 | 15/25 |  |
| gte <- Opus labels (new) | all 90 | 104/150 | 128/150 | 1197 | 79/100 | 91/100 | 16/25 |  |
| gte <- agreed labels (new) | all 90 | 99/150 | 130/150 | 1200 | 81/100 | 93/100 | 17/25 |  |
| Gemma 4 E4B | all 90 | 84/150 | 103/150 | 3273 | 69/100 | 82/100 | 19/25 |  |
| d1-3B | all 90 | 98/150 | 118/150 | 13667 | 73/100 | 91/100 | 19/25 |  |
| Claude Haiku 5.5 (API) | all 90 | 86/150 | 117/150 | 935 | 82/100 | 95/100 | 22/25 |  |
| Claude Opus 5.5 (API, new) | all 90 | 98/150 | 128/150 | 2038 | 86/100 | 98/100 | 23/25 |  |
| find_tool alone | top10 | 36/150 | 63/150 | 0 | 36/100 | 51/100 | 8/25 |  |
| gte, untuned | top10 | 64/150 | 87/150 | 130 | 53/100 | 75/100 | 14/25 |  |
| gte <- Gemma labels | top10 | 66/150 | 90/150 | 210 | 63/100 | 79/100 | 13/25 |  |
| gte <- Haiku labels | top10 | 74/150 | 90/150 | 126 | 70/100 | 78/100 | 14/25 |  |
| gte <- Opus labels (new) | top10 | 72/150 | 91/150 | 126 | 70/100 | 79/100 | 16/25 |  |
| gte <- agreed labels (new) | top10 | 74/150 | 91/150 | 125 | 68/100 | 78/100 | 15/25 |  |
| Gemma 4 E4B | top10 | 76/150 | 86/150 | 2302 | 67/100 | 77/100 | 19/25 | 4 |
| d1-3B | top10 | 72/150 | 88/150 | 1320 | 69/100 | 78/100 | 18/25 |  |
| Claude Haiku 5.5 (API) | top10 | 74/150 | 84/150 | 907 | 76/100 | 80/100 | 19/25 |  |
| Claude Opus 5.5 (API, new) | top10 | 72/150 | 87/150 | 2350 | 72/100 | 80/100 | 19/25 |  |

TEST3 top-1 per writer, all 90:

| engine | Claude Opus 5.5 (38) | Gemma 4 E4B (40) | Qwen3-1.7B (34) | LiquidAI d1-3B (38) | all (150) |
|---|---|---|---|---|---|
| find_tool alone | 6 | 4 | 11 | 15 | 36 |
| gte, untuned | 17 | 19 | 17 | 22 | 75 |
| gte <- Gemma labels | 12 | 11 | 10 | 15 | 48 |
| gte <- Haiku labels | 26 | 25 | 19 | 26 | 96 |
| gte <- Opus labels (new) | 31 | 26 | 21 | 26 | 104 |
| gte <- agreed labels (new) | 27 | 23 | 20 | 29 | 99 |
| Gemma 4 E4B | 23 | 18 | 18 | 25 | 84 |
| d1-3B | 28 | 26 | 18 | 26 | 98 |
| Claude Haiku 5.5 (API) | 23 | 22 | 18 | 23 | 86 |
| Claude Opus 5.5 (API, new) | 27 | 27 | 19 | 25 | 98 |

TEST3 top-1 per writer, top10:

| engine | Claude Opus 5.5 (38) | Gemma 4 E4B (40) | Qwen3-1.7B (34) | LiquidAI d1-3B (38) | all (150) |
|---|---|---|---|---|---|
| find_tool alone | 6 | 4 | 11 | 15 | 36 |
| gte, untuned | 12 | 18 | 13 | 21 | 64 |
| gte <- Gemma labels | 13 | 18 | 14 | 21 | 66 |
| gte <- Haiku labels | 15 | 17 | 17 | 25 | 74 |
| gte <- Opus labels (new) | 17 | 16 | 16 | 23 | 72 |
| gte <- agreed labels (new) | 17 | 16 | 16 | 25 | 74 |
| Gemma 4 E4B | 17 | 17 | 17 | 25 | 76 |
| d1-3B | 18 | 18 | 15 | 21 | 72 |
| Claude Haiku 5.5 (API) | 18 | 18 | 15 | 23 | 74 |
| Claude Opus 5.5 (API, new) | 17 | 16 | 15 | 24 | 72 |

| Opus 5.5 use | calls | tokens in (of which cache reads) | tokens out | cost USD |
|---|---|---|---|---|
| writing TEST3 rows | 40 | 29,268 (0) | 2,525 | 0.17 |
| benchmark, all 90 (TEST3+TEST2+HELD_OUT_2) | 275 | 3,395,977 (3,368,475) | 28,311 | 1.35 |
| benchmark, top10 | 275 | 561,138 (2,295) | 30,921 | 3.39 |
| labels, TRAIN2 (cache share assumed as in the all-90 benchmark) | 1067 | 13,164,263 (13,057,653) | 82,302 | 4.68 |
| total | | | | 9.59 |

| teacher | top-1 = generated gold (of 1,067) | generated gold in top 3 |
|---|---|---|
| gemma4 | 838 | 912 |
| haiku | 943 | 1012 |
| opus | 1030 | 1058 |

Haiku and Opus give the same top-1 on 961 of 1067 TRAIN2 requests.
- student gte <- opus: trained on 961 requests in 26.2 min (GPU); held-out 106: agrees with its label on 90, matches the generated gold on 90 (the label itself: 104).
- student gte <- agreed: trained on 845 requests in 22.9 min (GPU); held-out 91: agrees with its label on 82, matches the generated gold on 82 (the label itself: 91).

Opus's labels were logged without their cache fields (label.py kept tokens in and out only; fixed for later runs),
so their cost assumes the cache share measured on the all-90 benchmark (same cached block of 90 tool documents);
uncached it would be USD 54. Over the top 10 the options change per request and stay under the cache minimum.
Gemma's 4 errors on top10 (and none on all 90 here) are its letter-format misses, counted as wrong.
GPU time: gte <- Opus 26 min, gte <- agreed 23 min of training; d1-3B over all 90 took 34 min for TEST3's 150 rows.

Read:
- The students' gain holds on writers other than Sonnet. Over all 90 tools, TEST3 top-1: gte <- Haiku 96/150 and
  gte <- Opus 104/150 against untuned gte's 75, and each student beats untuned gte on every writer. On TEST3 both
  students also beat their own teachers (Haiku 86, Opus 98): the students learned the generated tool for a request,
  TEST3's gold is the writer's target, and on loosely written requests the LLMs pick what the documents fit best.
- The best local picker is gte <- Opus labels: TEST3 104/150 (top-3 128) at 1.2 s, ahead of Opus itself (98),
  d1-3B (98, 13.7 s), Gemma 4 E4B (84) and Haiku (86). On TEST2 it gives 79/100 (Haiku student 80), on HELD_OUT_2
  16/25 (Haiku student 15). The agreed student is close (99/150, top-3 130, HELD_OUT_2 17/25) and needs no new
  labels beyond the two teachers'.
- Over find_tool's top 10 everything bunches at 72-76 of 150 against a ceiling of 94: the shortlist, not the
  picker, is the limit there; the gain from training shows over all 90 tools.
- Writer matters more than picker for the hardest rows: on Qwen3-1.7B's 34 rows every engine scores 18-21 and
  find_tool alone 11; NOTES.md lists 12 rows (11 from Qwen3 and d1-3B) whose request does not fit its target. No
  picker gains much on its own writer's rows (Opus 27/38, Gemma 18/40, d1-3B 26/38).
- Opus as a picker: best on TEST2 (86/100, top-3 98) and HELD_OUT_2 (23/25), level with d1-3B on TEST3, about
  2 s a decision; it costs about USD 0.005 a decision over all 90 with the cache, 40 times Haiku's price per token.

## Round 5: queries as the agent writes them (2026-10-21)

In Claude desktop the agent (Opus 5.5) sends find_tool its own short search phrase, not the user's request, and no
earlier set had that style. Real queries are not on disk (the desktop log records tools/call without arguments), so
AGENT3 generates them: for each TEST3, TEST2 and HELD_OUT_2 request (never TRAIN2), Opus 5.5 got naga's real MCP
server instructions as system prompt, find_tool as its only tool (real description and schema from nagasim 0.13.0),
the request as the user message and tool_choice auto; the `query` of its first find_tool call is the row, with the
seed's gold (`distill/agent3.py`, frozen at 6f58d35 before any picker ran; notes in `distill/NOTES.md`). 274 of 275
seeds gave a call (TEST2-69: Opus asked for the model JSON instead). Median query 4 words; 41 queries contain a
guessed tool name. find_tool's top 10 holds the gold for 218 of 274. Run with `BENCH_ROUND=agent3` (`distill/derived4`,
`distill/results4`); tables: `distill/report5.py`. In our setup the naga backup now ranks every tool (ArenaPy d2773b07),
so all 90 is the mode that decides; top10 is kept for reference.

| engine | mode | top-1 | top-3 | median ms |
|---|---|---|---|---|
| find_tool alone | all 90 | 136/274 | 190/274 | 0 |
| gte, untuned | all 90 | 161/274 | 201/274 | 1127 |
| gte <- Haiku labels | all 90 | 178/274 | 211/274 | 1128 |
| gte <- Opus labels | all 90 | 183/274 | 215/274 | 1129 |
| gte <- agreed labels | all 90 | 183/274 | 219/274 | 1127 |
| Claude Haiku 5.5 (API) | all 90 | 190/274 | 216/274 | 966 |
| Claude Opus 5.5 (API) | all 90 | 190/274 | 225/274 | 1741 |
| find_tool alone | top10 | 136/274 | 190/274 | 0 |
| gte, untuned | top10 | 163/274 | 202/274 | 90 |
| gte <- Haiku labels | top10 | 180/274 | 207/274 | 93 |
| gte <- Opus labels | top10 | 180/274 | 207/274 | 92 |
| gte <- agreed labels | top10 | 181/274 | 206/274 | 93 |
| Claude Haiku 5.5 (API) | top10 | 183/274 | 208/274 | 922 |
| Claude Opus 5.5 (API) | top10 | 180/274 | 208/274 | 1998 |

Top-1 by seed source, all 90:

| engine | TEST3 (150) | TEST2 (99) | HELD_OUT_2 (25) |
|---|---|---|---|
| find_tool alone | 69 | 53 | 14 |
| gte, untuned | 84 | 61 | 16 |
| gte <- Haiku labels | 87 | 74 | 17 |
| gte <- Opus labels | 88 | 78 | 17 |
| gte <- agreed labels | 89 | 77 | 17 |
| Claude Haiku 5.5 (API) | 93 | 77 | 20 |
| Claude Opus 5.5 (API) | 92 | 79 | 19 |

Top-1 by seed source, top10:

| engine | TEST3 (150) | TEST2 (99) | HELD_OUT_2 (25) |
|---|---|---|---|
| find_tool alone | 69 | 53 | 14 |
| gte, untuned | 85 | 62 | 16 |
| gte <- Haiku labels | 90 | 73 | 17 |
| gte <- Opus labels | 88 | 75 | 17 |
| gte <- agreed labels | 90 | 74 | 17 |
| Claude Haiku 5.5 (API) | 90 | 76 | 17 |
| Claude Opus 5.5 (API) | 91 | 72 | 17 |

Top-1 by seed writer, all 90:

| engine | Claude Opus 5.5 (38) | Gemma 4 E4B (40) | Qwen3-1.7B (34) | LiquidAI d1-3B (38) | Claude Sonnet 5.5 (99) | round-2 set (25) |
|---|---|---|---|---|---|---|
| find_tool alone | 17 | 15 | 15 | 22 | 53 | 14 |
| gte, untuned | 23 | 22 | 17 | 22 | 61 | 16 |
| gte <- Haiku labels | 26 | 20 | 16 | 25 | 74 | 17 |
| gte <- Opus labels | 25 | 20 | 18 | 25 | 78 | 17 |
| gte <- agreed labels | 26 | 22 | 16 | 25 | 77 | 17 |
| Claude Haiku 5.5 (API) | 28 | 21 | 19 | 25 | 77 | 20 |
| Claude Opus 5.5 (API) | 27 | 22 | 17 | 26 | 79 | 19 |

Top-1 by seed writer, top10:

| engine | Claude Opus 5.5 (38) | Gemma 4 E4B (40) | Qwen3-1.7B (34) | LiquidAI d1-3B (38) | Claude Sonnet 5.5 (99) | round-2 set (25) |
|---|---|---|---|---|---|---|
| find_tool alone | 17 | 15 | 15 | 22 | 53 | 14 |
| gte, untuned | 24 | 22 | 17 | 22 | 62 | 16 |
| gte <- Haiku labels | 26 | 23 | 17 | 24 | 73 | 17 |
| gte <- Opus labels | 25 | 21 | 18 | 24 | 75 | 17 |
| gte <- agreed labels | 27 | 23 | 17 | 23 | 74 | 17 |
| Claude Haiku 5.5 (API) | 26 | 23 | 17 | 24 | 76 | 17 |
| Claude Opus 5.5 (API) | 27 | 23 | 17 | 24 | 72 | 17 |

Paired, all 90: haiku right and gte-opus wrong on 15 rows, the reverse on 8; sign test p = 0.21.

Paired, top10: haiku right and gte-opus wrong on 7 rows, the reverse on 4; sign test p = 0.55.

| Opus 5.5 use | calls | tokens in | tokens out | cost USD |
|---|---|---|---|---|
| writing AGENT3 queries | 275 | 190,027 | 27,259 | 1.31 |
| picker, all 90 | 274 | 3,379,183 | 23,496 | 1.29 |
| picker, top10 | 274 | 497,433 | 24,028 | 2.63 |
| total | | | | 5.23 |

Haiku's 274 all-90 decisions used 3.41 M input tokens (3.34 M cache reads) and 14 k output: at most USD 0.35, under
USD 0.0013 a decision even at the full input price.

Read:
- The agent's phrasing is easier for everyone: find_tool alone gets 136/274 right first (TEST3 requests: 36/150),
  untuned gte 161, the students 178-183, Haiku and Opus 190. The gaps shrink because the agent already turns a
  loose request into the words of the tool catalogue.
- Haiku first or gte-opus first (all 90): Haiku by 7 of 274 (190 against 183, 2.6 points); Haiku is right where
  gte-opus is wrong on 15 rows and the reverse on 8, sign test p = 0.21, so the difference is within noise. Top-3:
  gte-opus 215, Haiku 216. Both take about 1.0-1.1 s (Haiku over the network, gte-opus on the laptop GPU).
- Recommendation: Haiku first where a hosted call is acceptable, gte-opus as the backup; the backup loses about 3
  points on agent queries, costs nothing per call and runs offline. Opus as the picker adds nothing over Haiku here
  (190 both, top-3 225 against 216) at twice the latency and 40 times the price per token.
- By source, Haiku's lead comes from TEST3 seeds (93 against 88 of 150) and HELD_OUT_2 (20 against 17 of 25);
  on the Sonnet-written TEST2 seeds, the style the students trained on, gte-opus leads by one (78 against 77 of 99).
