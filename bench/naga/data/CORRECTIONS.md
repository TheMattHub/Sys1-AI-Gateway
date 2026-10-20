# fields.jsonl corrections (2026-10-19, before any engine ran)

fields.jsonl was written without the real study schema. Each label was checked against the canonical
record fields the engine accepts (ArenaPy `nagasim/studyinput.py` `_FIELDS`, the study_update record
checks in `nagasim/agent_tools/study.py`, and the scenario shape `{name, goal, overrides}` in
`nagasim/core/schema/sections_validation.py`). fields.jsonl itself stays as written; `bench_b.py`
applies this table. Rule: a label that is not a field of its context is removed from also_ok; if the
answer itself is not a field, an also_ok that is a field is promoted (or the one field with the same
meaning is used, with the reason below); otherwise the row is dropped.

Label set per context (the choice is among these):
- goal: id, text, kpi, low, high, precision, share_above
- assumption: id, text, value, source, check
- source: id, text, input
- validation: level, passed, text
- scenario: name, goal, overrides
- precision: the record is `{"relative": x}` only, so every precision row is dropped (no choice to make).

| row | text (context) | was | now | reason |
|---|---|---|---|---|
| 3 | target_metric (goal) | kpi, also name | kpi | goals have no name field |
| 5 | description (assumption) | text, also note | text | no note field |
| 7 | assumed_value_low (assumption) | low | dropped | assumptions have no low/high (only inside check) |
| 8 | range (assumption) | low, also high | dropped | as row 7 |
| 9 | upper_bound (assumption) | high | dropped | as row 7 |
| 10 | max (assumption) | high | dropped | as row 7 |
| 11 | minimum (assumption) | low | dropped | as row 7 |
| 12 | assumption_id (assumption) | id, also name | id | no name field |
| 13 | origin (source) | note, also text | text | sources have no note; text is their free text |
| 14 | where it came from (source) | note, also text | text | as row 13 |
| 15 | source_name (source) | name, also text, id | text, also id | sources have no name |
| 16 | dataset (source) | name | dropped | no name field, no also_ok that exists |
| 18 | check (validation) | text, also note | text | no note field |
| 21 | measured_metric (validation) | kpi | dropped | validation has no kpi field |
| 22 | tolerance (validation) | threshold, also half_width | dropped | neither exists in validation |
| 23-28 | precision rows (6) | level, half_width, half_width, confidence, share_over, share_over | dropped | precision holds only relative |
| 29 | parameter_changes (scenario) | changes | overrides | a scenario's changes are its overrides; no changes field |
| 30 | scenario_label (scenario) | name, also id | name | scenarios have no id |

Rows 1, 2, 4, 6, 17, 19, 20 are unchanged. Kept: 30 - 14 dropped = 16 rows.
