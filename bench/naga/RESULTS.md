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
