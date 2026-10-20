Study open = the gold tool starts with study_. Cells are TEST / TRAIN counts (25 / 54 rows). End-to-end top-3 = a gold tool in the first three of the stage-2 ranking inside the stage-1 top-1 family. Baseline = single-stage over all 90 (round-2 Tall run).

| engine | single-stage 90: top-1 / top-3 | 4a subset: top-1 / top-3 (gold offered) | 4b stage 1 family top-1 | 4b stage 2 given true family top-1 | 4b end-to-end top-1 / top-3 | 4c group-right top-1 (gain) |
|---|---|---|---|---|---|---|
| tuned | 11/16 / 54/54 | 13/17 / 52/54 (25/25 / 54/54) | 12 / 48 | 16 / 54 | 9/11 / 46/48 | 10 / 46 (+1 / +0) |
| gte | 14/19 / 39/44 | 14/20 / 42/45 (25/25 / 54/54) | 15 / 40 | 19 / 45 | 12/14 / 39/39 | 13 / 39 (+1 / +0) |
| laya | 16/18 / 34/45 | 15/18 / 39/48 (25/25 / 54/54) | 11 / 29 | 20 / 45 | 8/10 / 25/28 | 8 / 25 (+0 / +0) |

Groups that gave 4c gains (engine:row):
- TEST: twin_read (tuned:TEST-12, gte:TEST-12)
