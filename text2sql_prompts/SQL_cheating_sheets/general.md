# SQL Cheat Sheet (General Rewrite Patterns for SQLite)

이 문서는 재작성 요청이 들어왔을 때 SQL을 더 실용적으로 다시 쓰기 위한 패턴 모음이다.

## 1) 최신 시점 한 건만 보기
```sql
SELECT *
FROM some_table
ORDER BY timestamp_col DESC
LIMIT 1;
```

## 2) 그룹별 최신 row 선택
```sql
WITH ranked AS (
  SELECT
    t.*,
    ROW_NUMBER() OVER (
      PARTITION BY group_id
      ORDER BY timestamp_col DESC
    ) AS rn
  FROM some_table t
)
SELECT *
FROM ranked
WHERE rn = 1;
```

## 3) 집계 대신 raw row 보기
```sql
SELECT
  id,
  unit_name,
  status,
  timestamp_col
FROM some_table
WHERE some_condition = 1
ORDER BY timestamp_col DESC, id;
```

## 4) raw row 대신 집계 보기
```sql
SELECT
  category,
  COUNT(*) AS cnt,
  AVG(score) AS avg_score
FROM some_table
GROUP BY category
ORDER BY cnt DESC;
```

## 5) duplicate join 완화
```sql
WITH dedup_b AS (
  SELECT key_col, MAX(timestamp_col) AS latest_ts
  FROM table_b
  GROUP BY key_col
)
SELECT a.*, b.*
FROM table_a a
JOIN dedup_b d
  ON a.key_col = d.key_col
JOIN table_b b
  ON b.key_col = d.key_col
 AND b.timestamp_col = d.latest_ts;
```

## 6) Top-K / ranking 명시
```sql
SELECT
  name,
  metric
FROM some_table
ORDER BY metric DESC, name ASC
LIMIT 10;
```

## 7) null-safe division
```sql
SELECT
  numerator,
  denominator,
  CASE
    WHEN denominator IS NULL OR denominator = 0 THEN NULL
    ELSE 1.0 * numerator / denominator
  END AS ratio
FROM some_table;
```

## 8) 기간 제한
```sql
SELECT *
FROM some_table
WHERE timestamp_col >= '2025-01-01 00:00:00'
  AND timestamp_col < '2025-01-02 00:00:00';
```

## 9) 질문 의도 재해석 원칙
- 결과가 너무 요약적이면 row-level 결과를 고려한다.
- 결과가 너무 많으면 latest/top-k/stronger filtering을 고려한다.
- 현재 상태를 묻는 질문이면 latest snapshot을 우선 검토한다.
- join 후 row 수가 이상하게 늘면 dedup 후 join 패턴을 고려한다.
- 사용자가 재작성을 요청했지만 추가 지시가 없으면 아래 순서로 개선을 검토한다:
  1. granularity mismatch
  2. time anchoring mismatch
  3. missing ordering/top-k
  4. duplicate join
  5. weak filtering
