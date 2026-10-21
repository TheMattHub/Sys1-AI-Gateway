# Which System-1 model for naga decisions?

An assistant that drives the [naga](https://github.com/TheMattHub/naga) simulation engine must pick one of 90 agent tools for each step, and this study measures which small or cheap model picks best, and how fast. The answer: Claude Haiku 5.5 first, with a 150M cross-encoder trained on Claude Opus 5.5's labels as the offline backup. On 274 search queries written by the agent, Haiku puts the right tool first for 190 (69%) in about 1 s, the trained cross-encoder for 183 (67%) in 1.1 s on a 4 GB laptop GPU, and naga's keyword search alone for 136 (50%). On 150 requests written by four other models the trained cross-encoder leads instead, 104 against 86. Every number comes from the result files under [bench/naga](../../bench/naga/RESULTS.md), and the sections below say how far to trust them.

<div class="pareto-chart" data-src="../assets/engines.json"><noscript><img src="../screenshots/hero.png" alt="Right first time against median latency, per engine, on TEST3 and AGENT3"></noscript></div>

The grey step line is the Pareto frontier: the engines that no other engine beats on both speed and accuracy. Point at an engine, or at a kind in the legend, to see that kind's own frontier. The main chart shows the twelve engines the story turns on, failures included, and the retries chart five; the table below lists every engine we tried.

## How we test

Every result is on a frozen blind set: written before any engine saw it, committed, and never used to tune anything. Two sets carry the story:

- **TEST3:** 150 requests by four writers (Claude Opus 5.5, Gemma 4 E4B, Qwen3-1.7B and Liquid AI's d1-3B), each given only the 90 tool names and the tool to ask for.
- **AGENT3:** 274 `find_tool` queries as the agent writes them. Opus 5.5 got each request of TEST3, TEST2 and HELD_OUT_2 with naga's real server instructions and `find_tool` as its only tool, and the query of its first call became the row. In Claude desktop this is the main role: the agent sends `find_tool` a short phrase of its own, not the user's words.

Two earlier sets are supporting evidence only. TEST2 (100 requests) was written by Claude Sonnet 5.5, the same writer as the students' training data, and HELD_OUT_2 (25) is the first blind set. Every engine chooses from all 90 tools; the four that take at most 20 or 26 options (Laya, Gemma 4 E4B, AnyJev and the OpenThai Ollama build) get the 20 tools a bi-encoder ranks highest, which hold the right tool for 125 of 150 TEST3 rows and 234 of 274 AGENT3 rows. All local runs used one laptop with an RTX A500 (4 GB) and seed 0, and latency is the wall-clock time per decision; the hosted models' time is the API round trip from that laptop.

## Every engine on the two sets

The trained cross-encoders and the hosted Claude models lead, and most System-1 decision models trail the untuned reranker. Top-1 is the right tool first, top-3 the right tool among the first three, out of 150 (TEST3) and 274 (AGENT3); the time is the median on AGENT3, or on TEST3 where AGENT3 was not run.

| engine | kind | TEST3 top-1 | TEST3 top-3 | AGENT3 top-1 | AGENT3 top-3 | median ms |
|---|---|---|---|---|---|---|
| `find_tool` alone | keyword search | 36/150 | 63/150 | 136/274 | 190/274 | 0 |
| harrier (bi-encoder) | encoder | 36/150 | 62/150 | 134/274 | 178/274 | 79 |
| gte-reranker, untuned | encoder | 75/150 | 99/150 | 161/274 | 201/274 | 1,127 |
| Qwen3-Reranker-0.6B | encoder | 86/150 | 115/150 | 172/274 | 212/274 | 5,514 |
| gte, tuned on 54 questions | encoder | 78/150 | 114/150 | 175/274 | 204/274 | 1,142 |
| gte <- Gemma labels | encoder | 48/150 | 111/150 | 152/274 | 202/274 | 1,149 |
| gte <- Haiku labels | encoder | 96/150 | 123/150 | 178/274 | 211/274 | 1,128 |
| gte <- Opus labels | encoder | 104/150 | 128/150 | 183/274 | 215/274 | 1,129 |
| gte <- agreed labels | encoder | 99/150 | 130/150 | 183/274 | 219/274 | 1,127 |
| Laya | System-1 decision model | 71/150 | 105/150 | 147/274 | 191/274 | 67 |
| d1-omni-600M | System-1 decision model | 69/150 | 96/150 | 137/274 | 180/274 | 375 |
| d1-3B (Q8_0) | System-1 decision model | 98/150 | 118/150 | not run | not run | 13,667 |
| AnyJev on Qwen3-1.7B | System-1 decision model | 30/150 | 59/150 | 92/274 | 136/274 | 1,891 |
| OpenThai (Ollama build) | System-1 decision model | 31/150 | 61/150 | 75/274 | 168/274 | 371 |
| Gemma 4 E4B | LLM | 84/150 | 103/150 | 179/274 | 206/274 | 3,006 |
| Claude Haiku 5.5 (API) | LLM | 86/150 | 117/150 | 190/274 | 216/274 | 966 |
| Claude Opus 5.5 (API) | LLM | 98/150 | 128/150 | 190/274 | 225/274 | 1,741 |

The agent's phrasing is easier for every engine, because the agent already turns a loose request into the catalogue's words: `find_tool` alone climbs from 24% on TEST3 to 50% on AGENT3, and the gaps between engines shrink. Liquid AI's d1-3B is the one System-1 model level with the hosted ones on TEST3 (98, like Opus), but it takes 13.7 s a decision on this GPU, its licence allows commercial use only below USD 10 M revenue, and its AGENT3 run (about an hour) was not made. Six engines have no TEST3 or AGENT3 rows, because a run would take well over half an hour here, the engine had already failed, or it does not fit the GPU:

- ModernBERT-NLI and GLiNER2.5: 14 of 25 on HELD_OUT_2 over all 90 tools, at 5 to 7 s a decision.
- Von 1.3: 2 of 25 on HELD_OUT_2 over all 90 tools, 17 s a decision.
- OpenThai-SystemOne through its own client: 7 of 100 on TEST2 over all 90 tools, 16.6 s a decision.
- JEV-9B and Jeva-4B: their weights do not fit 4 GB.

The table settles the shortlist of serious candidates: the trained cross-encoders, the hosted Claude models and, where time does not matter, d1-3B and Qwen3-Reranker.

## Retries: a fast engine catches up

A fast engine that may try its next pick after a wrong one catches the best engines' first try at a tenth of their time. Within three tries Laya is right on 105 of 150 TEST3 requests (70%) in about 130 ms of decisions, where the best first try is the Opus-trained cross-encoder's 104 at 1.2 s; on AGENT3 it reaches 191 of 274 in about 120 ms, against Haiku's and Opus's 190 first time at 1.0 and 1.7 s. The slower engines climb too: within three tries the Opus-trained and agreed cross-encoders reach 85-87% on TEST3 and 78-80% on AGENT3, Opus 85% and 82%.

[![Right within 1, 2 and 3 tries against the time those tries take, per engine](../screenshots/retries.png)](../screenshots/retries.png)

Try k counts as right when the right tool is in the first k of the engine's ranking, and the time is the median decision time times the mean tries used (a request stops when it is right). That is how naga uses the ranking: the assistant tries the next tool in the same list after a call fails, so in practice the extra cost is the failed tool call rather than a new decision. Round 2 checked that re-asking with the wrong pick removed gives counts close to the first ranking's ([RESULTS.md](../../bench/naga/RESULTS.md#round-2-retries), oracle table), and that telling the model what the wrong pick did makes it worse. Retries pay when a wrong pick is cheap to notice; when it is not, the first try is what counts.

## A small student beats its teacher

A 150M cross-encoder trained on a strong teacher's labels beats that teacher on requests from writers it never saw. The student is `Alibaba-NLP/gte-reranker-modernbert-base`, trained on about 1,000 requests written by Claude Sonnet 5.5 from the tool descriptions, each labelled with a teacher's first choice over all 90 tools; one student per teacher, same recipe and seed, 23 to 27 minutes of training each on the laptop GPU.

| teacher | teacher's top-1 = the request's tool (of 1,067) | cost of the labels | student on TEST3 (teacher) | student on AGENT3 (teacher) |
|---|---|---|---|---|
| Gemma 4 E4B (local) | 838 | 57 min of GPU | 48 (84) | 152 (179) |
| Claude Haiku 5.5 | 943 | 13.3 M input tokens, mostly cached, and 56 k output; 20 min | 96 (86) | 178 (190) |
| Claude Opus 5.5 | 1,030 | about USD 4.70 with the cached tool documents | 104 (98) | 183 (190) |
| Haiku and Opus agreed (936 rows) | 936 | no new labels | 99 | 183 |

The better the labels, the better the student: Opus labels beat the agreed ones, which beat Haiku's, and Gemma's noisy labels made a student below the untuned reranker. On TEST3 the students beat their teachers, probably because they learned the tool a request was written for, while a language model picks what the tool documents fit best when a request is loosely worded. On the agent's own phrasing Haiku and Opus keep a lead of 7 to 12 queries over their students. The trained models are kept for our own use and not published; [distill/](../../bench/naga/distill/NOTES.md) has the scripts to train one.

## Precision: half on a GPU, full on CPU

The trained cross-encoder should run in half precision (float16) on a GPU and in full precision (float32) on a CPU, and the answer it gives does not change. We re-ran it in float32 over all 90 tools on TEST3, AGENT3, TEST2 and HELD_OUT_2 (549 requests): the top-1 pick is the same on every request, and the top-3 order differs on 3.

| run | TEST3 top-1 | AGENT3 top-1 | median per request |
|---|---|---|---|
| GPU, float16 | 104 of 150 | 183 of 274 | 1.2 s |
| GPU, float32 | 104 | 183 | 3.9 s |
| GPU, bfloat16 | 105 | not run | 1.1 s |
| CPU, float16 | same picks as float32 (10 rows) | not run | 117 s |
| CPU, float32 | 10 rows, same picks as float16 | not run | 16.5 s |

The speed flips with the hardware because a GPU has half-precision units and most CPUs do not, so the CPU converts every number back and forth and runs 7 times slower in float16 than in float32 (10 TEST3 rows, 90 tools each; a small sample, but the gap is large). bfloat16 gains nothing over float16 on the GPU. Since 0.14.0, naga loads any cross-encoder picker in float16 on a CUDA GPU and in float32 on a CPU, whatever the folder stores (decision D674), and the [published model](https://huggingface.co/TheMattFace/gte-reranker-naga-toolpicker) keeps float16 weights (290 MB) because that is the smaller download and loads as float32 on a CPU without losing anything.

## Do models favour their own writing?

We expected that a model would score higher on requests written by itself or by its teacher, and the data does not show it. The checks, all over the 90 tools:

- Students trained on Sonnet-written requests did not gain on the Sonnet-written TEST2: the Haiku student got 80 of 100 against Haiku's 82. On TEST3, from four other writers, the same student beat its teacher, 96 against 86 of 150.
- Engines on their own TEST3 rows show no consistent pattern. Opus gets 71% of its own rows against 56-68% of the others, but d1-3B scores even higher on Opus's rows (74%) than on its own (68%), so Opus's rows are simply the cleanest; Gemma gets 45% of its own rows against 53-66% of the others.
- AGENT3 was written by Opus, and Opus as the picker ties Haiku there (190 each).

The one hint the other way is small: the Opus-trained student leads the Haiku-trained one most on Opus's rows (31 against 26 of 38, against 0 to 2 on the other writers). The clear overfitting came from training on too few questions: round 2's fine-tune on 54 questions got all 54 right and 11 of 25 new ones.

## Model building

Naga's assistant also picks a block type (24) and a distribution (31) when it builds a model, and there a hosted model leads by a wide margin. These sets are 40 and 30 sentences, written blind from the names, with naga's fuller label descriptions (round 2); top-1 out of 40 and 30.

| engine | blocks | distributions | median ms |
|---|---|---|---|
| Claude Haiku 5.5 (API) | 37 | 30 | 876-906 |
| Gemma 4 E4B | 34 | 27 | 2,316-2,455 |
| d1-3B (Q8_0) | 33 | 28 | 1,095-1,096 |
| gte-reranker, untuned | 25 | 19 | 75-91 |
| Qwen3-Reranker-0.6B | 24 | 21 | 591-754 |
| Laya | 18 | 13 | 65-75 |
| keyword search (BM25) | 15 | 17 | 0 |

These sets are small, so a difference of one or two rows means nothing, but the order matches tool choice: Haiku, then the large local models, then the fast encoders.

## What to pick

Pick by where the queries come from, and by whether a hosted call is acceptable. The times are medians per decision on the laptop above.

| You need | Pick | What you get | Trade-off |
|---|---|---|---|
| Tool choice in an agent (our setup) | Claude Haiku 5.5 first, the Opus-trained gte as offline backup | AGENT3 190 (Haiku) and 183 (backup) of 274, about 1 s each | Haiku needs a key and a network and costs under USD 0.0013 a decision; the backup is free but must be trained |
| Tool choice from people's own words | The Opus-trained gte | TEST3 104 of 150, against Haiku's 86 (28 rows it wins, 10 it loses; sign test p = 0.005) | 1.1 s on a 4 GB GPU; train it yourself |
| A published local model, no training | Gemma 4 E4B (Q4_K_M via Ollama) or `Qwen/Qwen3-Reranker-0.6B` | TEST3 84 and 86, AGENT3 179 and 172 | 3.0 and 5.5 s over 90 tools; d1-3B gets 98 on TEST3 at 13.7 s |
| Fast | Laya `typed-decisions`, with up to three tries | 70% within three tries on both sets, about 120-130 ms | 47-54% first time; at most 20 options |
| Model building | Claude Haiku 5.5, or Gemma 4 E4B locally | blocks 37 and 34 of 40, distributions 30 and 27 of 30 | Gemma takes 2.3-2.5 s |

Opus as the picker adds nothing over Haiku on agent queries (190 each) at twice the time and about 40 times the price per token. Our own naga setup runs `--tool-picker haiku --tool-picker-backup` with the Opus-trained gte: on AGENT3 Haiku wins 15 queries the backup loses and loses 8 it wins (sign test p = 0.21), so the two are within noise, and the backup costs nothing and works offline.

## Caveats

The sets are small for close calls: on AGENT3 one query is 0.4 points, and Haiku's 7-query lead over the student is within noise. AGENT3's queries come from one agent model (Opus 5.5) prompted from requests, not from logs of real sessions, and TEST3's small writers add label noise (12 of its requests do not fit their target, listed in [NOTES.md](../../bench/naga/distill/NOTES.md)). Everything ran on one laptop, so the times move with your GPU. Models ran out of the box with the prompts in RESULTS.md, and a better prompt may change the order.

## Rerun it

The bench is in [bench/naga](../../bench/naga/README.md) and runs against a clone of the public [naga](https://github.com/TheMattHub/naga) repository. `run.ps1` runs each engine in its venv; `BENCH_ROUND=test3` or `agent3` with `BENCH_TASKS=Tall` writes the TEST3 and AGENT3 rows to `distill/results3` and `distill/results4`, and `python bench/naga/plot.py` redraws both charts and prints the engine table above. [RESULTS.md](../../bench/naga/RESULTS.md) is the full lab notebook, round by round.
