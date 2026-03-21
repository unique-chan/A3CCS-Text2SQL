# View Catalog

## v_current_friendly_units
- Purpose: 현재 시점 아군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 현재 아군 유닛 목록, 현재 아군 위치, 현재 아군 상태

## v_initial_friendly_units
- Purpose: 최초 시점 아군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 원래 아군 유닛 목록, 최초 아군 배치

## v_current_enemy_units
- Purpose: 현재 시점 적군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 현재 적군 유닛 목록, 현재 적군 위치, 현재 적군 상태

## v_initial_enemy_units
- Purpose: 최초 시점 적군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 원래 적군 유닛 목록, 최초 적군 배치

## v_current_friendly_unit_count
- Purpose: 현재 아군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 현재 아군 유닛 개수, 현재 남은 아군 병력 수

## v_initial_friendly_unit_count
- Purpose: 최초 아군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 원래 아군 유닛 개수, 시작 시점 아군 병력 수

## v_current_enemy_unit_count
- Purpose: 현재 적군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 현재 적군 유닛 개수, 현재 남은 적군 병력 수

## v_initial_enemy_unit_count
- Purpose: 최초 적군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 원래 적군 유닛 개수, 시작 시점 적군 병력 수

## v_current_friendly_vehicles
- Purpose: 현재 시점 아군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 현재 아군 장비 목록, 현재 아군 차량 상태, 현재 아군 장비 위치

## v_initial_friendly_vehicles
- Purpose: 최초 시점 아군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 원래 아군 장비 목록, 시작 시점 아군 차량 배치

## v_current_enemy_vehicles
- Purpose: 현재 시점 적군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 현재 적군 장비 목록, 현재 적군 차량 상태, 현재 적군 장비 위치

## v_initial_enemy_vehicles
- Purpose: 최초 시점 적군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 원래 적군 장비 목록, 시작 시점 적군 차량 배치

## v_current_friendly_vehicle_count
- Purpose: 현재 아군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 현재 아군 장비 개수, 현재 아군 차량 수

## v_initial_friendly_vehicle_count
- Purpose: 최초 아군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 원래 아군 장비 개수, 시작 시점 아군 차량 수

## v_current_enemy_vehicle_count
- Purpose: 현재 적군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 현재 적군 장비 개수, 현재 적군 차량 수

## v_initial_enemy_vehicle_count
- Purpose: 최초 적군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 원래 적군 장비 개수, 시작 시점 적군 차량 수

## v_current_friendly_enemy_group_distance
- Purpose: 현재 시점 기준 아군 그룹 centroid와 적군 그룹 centroid 간의 쌍별 거리
- Key columns: ref_datetime, friendly_groupname, friendly_datetime, friendly_posx, friendly_posy, friendly_posz, enemy_groupname, enemy_datetime, enemy_posx, enemy_posy, enemy_posz, distance_3d
- Use when: 현재 아군 그룹과 적군 그룹의 상대 거리, 가장 가까운 적군 그룹 탐색, 그룹 간 근접도 비교
- Notes: groups 테이블에는 적군 정보가 없으므로, units 테이블의 그룹별 평균 위치(centroid)로 아군/적군 그룹 위치를 구성

## v_current_friendly_enemy_unit_distance
- Purpose: 현재 시점 기준 아군 유닛과 적군 유닛 간의 쌍별 거리
- Key columns: ref_datetime, friendly_unitname, friendly_groupname, friendly_unittype, friendly_datetime, enemy_unitname, enemy_groupname, enemy_unittype, enemy_datetime, distance_3d
- Use when: 현재 아군 병사와 적군 병사 간 거리, 가장 가까운 적군 유닛 탐색, 유닛 단위 접촉 분석
- Notes: 전체 데이터의 MAX(datetime)을 기준 시각으로 두고, 각 유닛별로 그 시각에 가장 가까운 레코드 1건을 사용

## v_current_friendly_enemy_vehicle_distance
- Purpose: 현재 시점 기준 아군 장비와 적군 장비 간의 쌍별 거리
- Key columns: ref_datetime, friendly_vehiclename, friendly_groupname, friendly_vehicletype, friendly_datetime, enemy_vehiclename, enemy_groupname, enemy_vehicletype, enemy_datetime, distance_3d
- Use when: 현재 아군 장비와 적군 장비 간 거리, 가장 가까운 적군 장비 탐색, 차량/장비 간 근접도 비교
- Notes: 전체 데이터의 MAX(datetime)을 기준 시각으로 두고, 각 장비별로 그 시각에 가장 가까운 레코드 1건을 사용

## v_friendly_unit_speed_trend
- Purpose: 아군 유닛별 속도 시계열 추이
- Key columns: unitname, groupname, unittype, datetime, prev_datetime, dt_seconds, distance_delta, speed_per_sec, prev_speed_per_sec, speed_change_per_sec
- Use when: 아군 병사 이동 속도 변화, 특정 유닛의 가속/감속 추적, 최근 이동 추세 확인
- Notes: 연속 시점 간 3차원 위치 변화량 / 시간차(초)로 속도를 계산하며, datetime DESC 기준으로 최신 시점부터 정렬

## v_friendly_vehicle_speed_trend
- Purpose: 아군 장비별 속도 시계열 추이
- Key columns: vehiclename, groupname, vehicletype, datetime, prev_datetime, dt_seconds, distance_delta, speed_per_sec, prev_speed_per_sec, speed_change_per_sec
- Use when: 아군 장비 이동 속도 변화, 차량 가속/감속 추적, 최근 기동 추세 확인
- Notes: 연속 시점 간 3차원 위치 변화량 / 시간차(초)로 속도를 계산하며, datetime DESC 기준으로 최신 시점부터 정렬

## v_enemy_unit_speed_trend
- Purpose: 적군 유닛별 속도 시계열 추이
- Key columns: unitname, groupname, unittype, datetime, prev_datetime, dt_seconds, distance_delta, speed_per_sec, prev_speed_per_sec, speed_change_per_sec
- Use when: 적군 병사 이동 속도 변화, 특정 적 유닛의 가속/감속 추적, 최근 이동 추세 확인
- Notes: 연속 시점 간 3차원 위치 변화량 / 시간차(초)로 속도를 계산하며, datetime DESC 기준으로 최신 시점부터 정렬

## v_enemy_vehicle_speed_trend
- Purpose: 적군 장비별 속도 시계열 추이
- Key columns: vehiclename, groupname, vehicletype, datetime, prev_datetime, dt_seconds, distance_delta, speed_per_sec, prev_speed_per_sec, speed_change_per_sec
- Use when: 적군 장비 이동 속도 변화, 특정 적 장비의 가속/감속 추적, 최근 기동 추세 확인
- Notes: 연속 시점 간 3차원 위치 변화량 / 시간차(초)로 속도를 계산하며, datetime DESC 기준으로 최신 시점부터 정렬

## v_friendly_unit_ammo_trend
- Purpose: 아군 유닛별 총 탄약량 시계열 추이
- Key columns: unitname, datetime, prev_datetime, total_ammo_count, prev_total_ammo_count, ammo_change
- Use when: 아군 유닛 탄약 소모 추적, 최근 탄약 감소량 확인, 병사별 잔여 탄약 추세 분석
- Notes: units_ammo에서 동일 유닛의 모든 탄종 count를 합산한 total_ammo_count 기준

## v_friendly_vehicle_ammo_trend
- Purpose: 아군 장비별 총 탄약량 시계열 추이
- Key columns: vehiclename, datetime, prev_datetime, total_ammo_count, prev_total_ammo_count, ammo_change
- Use when: 아군 장비 탄약 소모 추적, 최근 탄약 감소량 확인, 차량별 잔여 탄약 추세 분석
- Notes: vehicles_ammo에서 동일 장비의 모든 탄종 count를 합산한 total_ammo_count 기준

## v_enemy_unit_ammo_trend
- Purpose: 적군 유닛별 총 탄약량 시계열 추이
- Key columns: unitname, datetime, prev_datetime, total_ammo_count, prev_total_ammo_count, ammo_change
- Use when: 적군 유닛 탄약 소모 추적, 최근 탄약 감소량 확인, 병사별 잔여 탄약 추세 분석
- Notes: units_ammo에서 동일 유닛의 모든 탄종 count를 합산한 total_ammo_count 기준

## v_enemy_vehicle_ammo_trend
- Purpose: 적군 장비별 총 탄약량 시계열 추이
- Key columns: vehiclename, datetime, prev_datetime, total_ammo_count, prev_total_ammo_count, ammo_change
- Use when: 적군 장비 탄약 소모 추적, 최근 탄약 감소량 확인, 차량별 잔여 탄약 추세 분석
- Notes: vehicles_ammo에서 동일 장비의 모든 탄종 count를 합산한 total_ammo_count 기준


## 뷰 우선 활용 가이드

- `view_catalog.csv` / `view_catalog.md`에 정의된 뷰가 있으면, **원본 테이블 직접 조인보다 뷰를 우선 사용**한다.
- 특히 현재 시점 아군/적군 간 거리, 속도 변화 추이, 탄약량 변화 추이는 아래 뷰를 우선 검토한다.
- 사용자가 "현재"를 물으면, 별도 시점 조건이 없는 한 **가장 최신 시점** 기준으로 해석한다.
- 사용자가 "추이"를 물으면, 특별한 요구가 없는 한 **최신 시간대부터 (`datetime DESC`)** 보여주는 질의를 선호한다.

### 거리 관련 추천 뷰
- `v_current_friendly_enemy_group_distance`
  - 아군 그룹과 적군 그룹 간 현재 거리.
  - 주의: `groups` 테이블에는 적군 정보가 없으므로, 이 뷰는 `units` 테이블의 **그룹별 평균 위치(centroid)** 를 그룹 위치로 사용한다.
  - `ref_datetime`은 전체 데이터의 `MAX(datetime)`이며, 각 그룹은 그 시각에 가장 가까운 관측 1건을 사용한다.

- `v_current_friendly_enemy_unit_distance`
  - 아군 유닛과 적군 유닛 간 현재 거리.
  - 각 유닛별로 `ref_datetime`에 가장 가까운 1개 레코드를 사용한다.

- `v_current_friendly_enemy_vehicle_distance`
  - 아군 장비와 적군 장비 간 현재 거리.
  - 각 장비별로 `ref_datetime`에 가장 가까운 1개 레코드를 사용한다.

### 속도 변화 추이 관련 추천 뷰
- `v_friendly_unit_speed_trend`
- `v_friendly_vehicle_speed_trend`
- `v_enemy_unit_speed_trend`
- `v_enemy_vehicle_speed_trend`

공통 규칙:
- 속도는 별도 컬럼이 없으므로, 연속 두 시점 간 위치 변화량을 이용해 계산한다.
- `dt_seconds = (julianday(datetime) - julianday(prev_datetime)) * 86400.0`
- `distance_delta = sqrt(dx*dx + dy*dy + dz*dz)`
- `speed_per_sec = distance_delta / dt_seconds`
- `speed_change_per_sec = speed_per_sec - prev_speed_per_sec`

### 탄약량 변화 추이 관련 추천 뷰
- `v_friendly_unit_ammo_trend`
- `v_friendly_vehicle_ammo_trend`
- `v_enemy_unit_ammo_trend`
- `v_enemy_vehicle_ammo_trend`

공통 규칙:
- 탄약량 변화 추이는 **개체별 총 탄약량(total ammo)** 기준이다.
- 즉, `units_ammo` 또는 `vehicles_ammo`에서 동일 개체의 여러 `ammotype` 행을 `SUM(count)`로 합산한다.
- `ammo_change = total_ammo_count - prev_total_ammo_count`
  - 음수면 탄약 소모, 양수면 탄약 보충/적재 가능성을 의미한다.

### 예시 질의 패턴

#### 예시 1) 현재 아군 그룹별 가장 가까운 적군 그룹은?
```sql
WITH ranked AS (
    SELECT
        friendly_groupname,
        enemy_groupname,
        friendly_datetime,
        enemy_datetime,
        distance_3d,
        ROW_NUMBER() OVER (
            PARTITION BY friendly_groupname
            ORDER BY distance_3d ASC, enemy_groupname
        ) AS rn
    FROM v_current_friendly_enemy_group_distance
)
SELECT
    friendly_groupname,
    enemy_groupname AS nearest_enemy_groupname,
    friendly_datetime,
    enemy_datetime,
    distance_3d
FROM ranked
WHERE rn = 1
ORDER BY distance_3d ASC, friendly_groupname;
```

#### 예시 2) 현재 아군 유닛별 가장 가까운 적군 유닛은?
```sql
WITH ranked AS (
    SELECT
        friendly_unitname,
        enemy_unitname,
        distance_3d,
        ROW_NUMBER() OVER (
            PARTITION BY friendly_unitname
            ORDER BY distance_3d ASC, enemy_unitname
        ) AS rn
    FROM v_current_friendly_enemy_unit_distance
)
SELECT
    friendly_unitname,
    enemy_unitname AS nearest_enemy_unitname,
    distance_3d
FROM ranked
WHERE rn = 1
ORDER BY distance_3d ASC, friendly_unitname;
```

#### 예시 3) 현재 아군 장비별 가장 가까운 적군 장비는?
```sql
WITH ranked AS (
    SELECT
        friendly_vehiclename,
        enemy_vehiclename,
        distance_3d,
        ROW_NUMBER() OVER (
            PARTITION BY friendly_vehiclename
            ORDER BY distance_3d ASC, enemy_vehiclename
        ) AS rn
    FROM v_current_friendly_enemy_vehicle_distance
)
SELECT
    friendly_vehiclename,
    enemy_vehiclename AS nearest_enemy_vehiclename,
    distance_3d
FROM ranked
WHERE rn = 1
ORDER BY distance_3d ASC, friendly_vehiclename;
```

#### 예시 4) 특정 아군 유닛의 최근 속도 변화 추이
```sql
SELECT
    unitname,
    groupname,
    datetime,
    prev_datetime,
    dt_seconds,
    distance_delta,
    speed_per_sec,
    prev_speed_per_sec,
    speed_change_per_sec
FROM v_friendly_unit_speed_trend
WHERE unitname = 'b_1_m2_1_u1'
ORDER BY datetime DESC;
```

#### 예시 5) 특정 적군 장비의 최근 속도 변화 추이
```sql
SELECT
    vehiclename,
    groupname,
    datetime,
    prev_datetime,
    dt_seconds,
    distance_delta,
    speed_per_sec,
    prev_speed_per_sec,
    speed_change_per_sec
FROM v_enemy_vehicle_speed_trend
WHERE vehiclename = 'op_1_i3_1_v1'
ORDER BY datetime DESC;
```

#### 예시 6) 특정 아군 유닛의 탄약량 변화 추이
```sql
SELECT
    unitname,
    datetime,
    prev_datetime,
    total_ammo_count,
    prev_total_ammo_count,
    ammo_change
FROM v_friendly_unit_ammo_trend
WHERE unitname = 'b_1_m2_1_u1'
ORDER BY datetime DESC;
```

#### 예시 7) 특정 적군 장비의 탄약량 변화 추이
```sql
SELECT
    vehiclename,
    datetime,
    prev_datetime,
    total_ammo_count,
    prev_total_ammo_count,
    ammo_change
FROM v_enemy_vehicle_ammo_trend
WHERE vehiclename = 'op_1_i3_1_v1'
ORDER BY datetime DESC;
```
