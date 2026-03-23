# Route Debug

## `route_after_execute`

- `END`
  - error AND attempt limit reached
  - otherwise
- `repair_sql`
  - error
- `semantic_check`
  - semantic check enabled

## `route_after_prepare_context`


## `route_after_safety`

- `END`
  - step limit exceeded

## `route_after_semantic_check`

- `END`
  - error AND attempt limit reached
  - semantic error AND attempt limit reached
  - otherwise
- `repair_sql`
  - error
- `semantic_repair_sql`
  - semantic error

## `route_after_tick`

- `END`
  - step limit exceeded
