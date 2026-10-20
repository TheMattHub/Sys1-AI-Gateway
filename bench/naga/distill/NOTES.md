# Distillation notes

## TEST2 (frozen 2026-10-20)
Written by a fresh subagent (Claude Sonnet 5.5) that saw only the 90 tool names, never the descriptions or any
existing query. 100 rows, all 90 tools gold at least once. Its own interpretation doubts, kept as it gave them:
- study_view = the study's main picture; study_show = the live control room.
- study_page_html = one standalone web page of the outcomes; study_package = bundle the study files for hand-off.
- study_extensions = optional add-on analyses (cost, energy).
- get_model_format = the JSON model format spec; write_model = store a hand-written full model JSON.
- list_records / get_record_schema = generic data records (shifts, products, maintenance).
- evaluate_policy = compare dispatch/decision policies; fit_surrogate = a fast approximation of the model.
- set_initial_state = start the run from current work in progress.
- Twin: get_plant_timeline = history of plant events; get_twin_monitor = live state.
Doubts found later are logged below; the file itself is never edited.
