# State Field Map

## AgentState fields

- `messages`
- `question`
- `schema`
- `schema_instruction`
- `sql`
- `result`
- `error`
- `semantic_error`
- `attempts`
- `steps`
- `seen_sql`
- `csv_path`
- `llm_generate_time`
- `llm_repair_time`
- `sql_execute_time`
- `semantic_check_time`
- `llm_semantic_repair_time`
- `rewrite_mode`
- `rewrite_request`
- `rewrite_guidance`
- `previous_question`
- `previous_sql`
- `previous_result`
- `reflection`
- `rewrite_attempts`
- `rewrite_reflection_time`
- `llm_rewrite_time`
- `rewrite_intent_time`
- `cheat_sheet_general`

## Node read/write map

| node | function | reads | writes |
|---|---|---|---|
| `classify_rewrite_intent` | `node_classify_rewrite_intent` |  | `error`, `messages`, `rewrite_guidance`, `rewrite_intent_time`, `rewrite_mode`, `semantic_error` |
| `execute_sql` | `node_execute_sql` | `csv_path`, `sql` | `error`, `result`, `semantic_error`, `sql_execute_time` |
| `generate_sql` | `node_generate_sql` | `seen_sql` | `error`, `llm_generate_time`, `messages`, `seen_sql`, `semantic_error`, `sql` |
| `prepare_context` | `node_prepare_context` | `schema` | `cheat_sheet_general`, `schema`, `schema_instruction` |
| `repair_sql` | `node_repair_sql` | `attempts`, `llm_repair_time`, `seen_sql` | `attempts`, `error`, `llm_repair_time`, `messages`, `seen_sql`, `semantic_error`, `sql` |
| `rewrite_reflect` | `node_rewrite_reflect` | `rewrite_attempts`, `rewrite_reflection_time` | `error`, `messages`, `reflection`, `rewrite_attempts`, `rewrite_reflection_time`, `semantic_error` |
| `rewrite_sql` | `node_rewrite_sql` | `llm_rewrite_time`, `seen_sql` | `error`, `llm_rewrite_time`, `messages`, `seen_sql`, `semantic_error`, `sql` |
| `safety_check` | `node_safety_check` | `error`, `sql` | `error`, `semantic_error` |
| `semantic_check` | `node_semantic_check` | `previous_question`, `question`, `result`, `semantic_check_time`, `sql` | `messages`, `semantic_check_time`, `semantic_error` |
| `semantic_repair_sql` | `node_semantic_repair_sql` | `attempts`, `llm_semantic_repair_time`, `seen_sql` | `attempts`, `error`, `llm_semantic_repair_time`, `messages`, `seen_sql`, `semantic_error`, `sql` |
| `tick` | `node_tick` | `steps` | `error`, `steps` |