from pathlib import Path

from text2sql_langgraph import build_config_from_env, run_and_save_sqlite


def _run(sql: str) -> str:
    """Execute the given SQL against the configured SQLite database and return the formatted result string.
    한국어: 설정된 SQLite 데이터베이스에 SQL을 실행하고 포맷된 결과 문자열을 반환합니다."""
    cfg = build_config_from_env()
    return run_and_save_sqlite(
        db_path=cfg.db_path,
        sql=sql,
        csv_path=Path("_ignore.csv"),
        max_rows=50,
        save_csv=False,
    )


# =========================
# shared normalized event CTEs
# =========================

def _normalized_events_cte() -> str:
    """Build the shared SQL CTE that normalizes and unions damaged, fired, and killed event logs.
    한국어: damaged, fired, killed 이벤트 로그를 정규화하고 하나로 합치는 공통 SQL CTE를 생성합니다."""
    return """
    WITH
    normalized_dammaged AS (
        SELECT
            snapshotid,
            datetime,
            replace(substr(datetime, 1, 19), 'T', ' ') AS dt_norm,
            side,
            targetunit,
            shooter,
            weapon,
            MAX(damage) AS damage,
            GROUP_CONCAT(DISTINCT hitpoint) AS hitpoint,
            MAX(seq) AS seq
        FROM event_dammaged
        GROUP BY
            snapshotid,
            side,
            datetime,
            targetunit,
            shooter,
            weapon
    ),
    normalized_fired AS (
        SELECT
            snapshotid,
            datetime,
            replace(substr(datetime, 1, 19), 'T', ' ') AS dt_norm,
            side,
            unit,
            gunner,
            weapon,
            ammotype,
            muzzle,
            MAX(seq) AS seq
        FROM event_fired
        GROUP BY
            snapshotid,
            side,
            datetime,
            unit,
            gunner,
            weapon,
            ammotype,
            muzzle
    ),
    normalized_killed AS (
        SELECT
            snapshotid,
            datetime,
            replace(substr(datetime, 1, 19), 'T', ' ') AS dt_norm,
            side,
            targetunit,
            killer,
            MAX(seq) AS seq
        FROM event_killed
        GROUP BY
            snapshotid,
            side,
            datetime,
            targetunit,
            killer
    ),
    events AS (
        SELECT
            datetime,
            dt_norm,
            side,
            seq,
            'event_dammaged' AS event_type,
            targetunit,
            shooter,
            damage,
            weapon,
            hitpoint,
            NULL AS unit,
            NULL AS gunner,
            NULL AS ammotype,
            NULL AS muzzle,
            NULL AS killer
        FROM normalized_dammaged

        UNION ALL

        SELECT
            datetime,
            dt_norm,
            side,
            seq,
            'event_fired' AS event_type,
            NULL AS targetunit,
            NULL AS shooter,
            NULL AS damage,
            weapon,
            NULL AS hitpoint,
            unit,
            gunner,
            ammotype,
            muzzle,
            NULL AS killer
        FROM normalized_fired

        UNION ALL

        SELECT
            datetime,
            dt_norm,
            side,
            seq,
            'event_killed' AS event_type,
            targetunit,
            NULL AS shooter,
            NULL AS damage,
            NULL AS weapon,
            NULL AS hitpoint,
            NULL AS unit,
            NULL AS gunner,
            NULL AS ammotype,
            NULL AS muzzle,
            killer
        FROM normalized_killed
    )
    """


def _normalized_knowsaboutchanged_cte() -> str:
    """Build the SQL CTE that deduplicates knowsabout change events by keeping the latest sequence.
    한국어: knowsaboutchanged 이벤트를 최신 seq 기준으로 중복 제거하는 SQL CTE를 생성합니다."""
    return """
    WITH ranked AS (
        SELECT
            snapshotid,
            datetime,
            replace(substr(datetime, 1, 19), 'T', ' ') AS dt_norm,
            side,
            groupname,
            targetunit,
            oldknowsabout,
            newknowsabout,
            seq,
            ROW_NUMBER() OVER (
                PARTITION BY snapshotid, side, datetime, groupname, targetunit
                ORDER BY seq DESC
            ) AS rn
        FROM event_knowsaboutchanged
    ),
    normalized_knowsaboutchanged AS (
        SELECT
            snapshotid,
            datetime,
            dt_norm,
            side,
            groupname,
            targetunit,
            oldknowsabout,
            newknowsabout,
            seq
        FROM ranked
        WHERE rn = 1
    )
    """


# =========================
# 1) current / initial counts
# =========================

def get_unit_count(side: str, damage_threshold: float = 0.5) -> str:
    """Return the current alive unit count and the initial total unit count for the specified side.
    한국어: 지정된 진영의 현재 생존 유닛 수와 초기 전체 유닛 수를 반환합니다."""
    return _run(f"""
    SELECT
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = '{side}'
              AND unitname NOT IN (
                  SELECT DISTINCT targetunit
                  FROM event_killed
                  WHERE side = '{side}'

                  UNION

                  SELECT DISTINCT unitname
                  FROM units
                  WHERE side = '{side}'
                    AND damage >= {damage_threshold}
              )
        ) AS alive_unit_count,
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = '{side}'
        ) AS initial_unit_count
    """)


def get_vehicle_count(side: str, damage_threshold: float = 0.5) -> str:
    """Return the current available vehicle count and the initial total vehicle count for the specified side.
    한국어: 지정된 진영의 현재 사용 가능한 차량 수와 초기 전체 차량 수를 반환합니다."""
    return _run(f"""
    SELECT
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = '{side}'
              AND vehiclename NOT IN (
                  SELECT DISTINCT vehiclename
                  FROM vehicles
                  WHERE side = '{side}'
                    AND damage >= {damage_threshold}
              )
        ) AS available_vehicle_count,
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = '{side}'
        ) AS initial_vehicle_count
    """)


# =========================
# 2) interval stats
# =========================

def get_unit_alive_by_interval(
    side: str,
    interval_minutes: int,
    damage_threshold: float = 0.5,
    limit: int | None = None,
) -> str:
    """Return alive unit counts for the specified side aggregated into fixed time buckets.
    한국어: 지정된 진영의 생존 유닛 수를 고정된 시간 버킷 단위로 집계하여 반환합니다."""
    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""

    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT unitname) AS alive_unit_count
    FROM units
    WHERE side = '{side}'
      AND unitname NOT IN (
          SELECT DISTINCT targetunit
          FROM event_killed
          WHERE side = '{side}'

          UNION

          SELECT DISTINCT unitname
          FROM units
          WHERE side = '{side}'
            AND damage >= {damage_threshold}
      )
    GROUP BY bucket_time
    ORDER BY bucket_time DESC{limit_clause}
    """)


def get_vehicle_available_by_interval(
    side: str,
    interval_minutes: int,
    damage_threshold: float = 1.0,
    limit: int | None = None,
) -> str:
    """Return available vehicle counts for the specified side aggregated into fixed time buckets.
    한국어: 지정된 진영의 사용 가능한 차량 수를 고정된 시간 버킷 단위로 집계하여 반환합니다."""
    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""

    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT vehiclename) AS available_vehicle_count
    FROM vehicles
    WHERE side = '{side}'
      AND vehiclename NOT IN (
          SELECT DISTINCT vehiclename
          FROM vehicles
          WHERE side = '{side}'
            AND damage >= {damage_threshold}
      )
    GROUP BY bucket_time
    ORDER BY bucket_time DESC{limit_clause}
    """)


def get_ammo_total_by_interval(
    side: str,
    interval_minutes: int,
    limit: int | None = None,
) -> str:
    """Return total ammo counts for the specified side aggregated into fixed time buckets.
    한국어: 지정된 진영의 총 탄약 수를 고정된 시간 버킷 단위로 집계하여 반환합니다."""
    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""

    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        SUM(count) AS ammo_total
    FROM (
        SELECT datetime, count
        FROM units_ammo
        WHERE side = '{side}'

        UNION ALL

        SELECT datetime, count
        FROM vehicles_ammo
        WHERE side = '{side}'
    )
    GROUP BY bucket_time
    ORDER BY bucket_time DESC{limit_clause}
    """)


# =========================
# 3) events (deduped logical events)
# =========================

def get_events_between(start_time: str, end_time: str) -> str:
    """Return normalized logical events whose timestamps fall within the specified time range.
    한국어: 지정된 시간 범위 안에 속하는 정규화된 논리 이벤트를 반환합니다."""
    return _run(f"""
    {_normalized_events_cte()}
    SELECT
        datetime,
        side,
        event_type,
        targetunit,
        shooter,
        damage,
        weapon,
        hitpoint,
        unit,
        gunner,
        ammotype,
        muzzle,
        killer,
        seq
    FROM events
    WHERE dt_norm >= replace(substr('{start_time}', 1, 19), 'T', ' ')
      AND dt_norm <= replace(substr('{end_time}', 1, 19), 'T', ' ')
    ORDER BY dt_norm DESC, event_type, seq DESC
    """)


def get_events_recent_minutes(minutes: int) -> str:
    """Return normalized logical events observed within the latest rolling time window in minutes.
    한국어: 최근 지정된 분 단위 시간 창 내에서 관측된 정규화된 논리 이벤트를 반환합니다."""
    return _run(f"""
    {_normalized_events_cte()},
    last_time AS (
        SELECT MAX(dt_norm) AS max_dt
        FROM events
    )
    SELECT
        datetime,
        side,
        event_type,
        targetunit,
        shooter,
        damage,
        weapon,
        hitpoint,
        unit,
        gunner,
        ammotype,
        muzzle,
        killer,
        seq
    FROM events
    WHERE dt_norm >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')
      AND dt_norm <= (SELECT max_dt FROM last_time)
    ORDER BY dt_norm DESC, event_type, seq DESC
    """)


def get_events_recent_rows(limit: int) -> str:
    """Return the most recent normalized logical events limited by row count.
    한국어: 가장 최근의 정규화된 논리 이벤트를 행 수 제한과 함께 반환합니다."""
    return _run(f"""
    {_normalized_events_cte()}
    SELECT
        datetime,
        side,
        event_type,
        targetunit,
        shooter,
        damage,
        weapon,
        hitpoint,
        unit,
        gunner,
        ammotype,
        muzzle,
        killer,
        seq
    FROM events
    ORDER BY dt_norm DESC, event_type, seq DESC
    LIMIT {limit}
    """)


# =========================
# 4) observations (deduped by last seq)
# =========================

def get_knowsaboutchanged_between(
    start_time: str,
    end_time: str,
    target_side: str | None = None,
    source_side: str | None = None,
) -> str:
    """Return deduplicated knowsabout change events within the specified time range with optional side filters.
    한국어: 지정된 시간 범위 내의 knowsaboutchanged 이벤트를 중복 제거하여 반환하며, 선택적으로 진영 필터를 적용합니다."""
    filters = ""
    if target_side is not None:
        filters += f"\n      AND targetunit LIKE '{target_side}%'"
    if source_side is not None:
        filters += f"\n      AND side = '{source_side}'"

    return _run(f"""
    {_normalized_knowsaboutchanged_cte()}
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout,
        seq
    FROM normalized_knowsaboutchanged
    WHERE dt_norm >= replace(substr('{start_time}', 1, 19), 'T', ' ')
      AND dt_norm <= replace(substr('{end_time}', 1, 19), 'T', ' '){filters}
    ORDER BY dt_norm DESC, groupname, targetunit, seq DESC
    """)


def get_knowsaboutchanged_recent_minutes(
    minutes: int,
    target_side: str | None = None,
    source_side: str | None = None,
) -> str:
    """Return recent deduplicated knowsabout change events within the latest rolling time window with optional side filters.
    한국어: 최근 지정된 시간 창 내의 knowsaboutchanged 이벤트를 중복 제거하여 반환하며, 선택적으로 진영 필터를 적용합니다."""
    filters = ""
    if target_side is not None:
        filters += f"\n      AND targetunit LIKE '{target_side}%'"
    if source_side is not None:
        filters += f"\n      AND side = '{source_side}'"

    return _run(f"""
    {_normalized_knowsaboutchanged_cte()},
    last_time AS (
        SELECT MAX(dt_norm) AS max_dt
        FROM normalized_knowsaboutchanged
    )
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout,
        seq
    FROM normalized_knowsaboutchanged
    WHERE dt_norm >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')
      AND dt_norm <= (SELECT max_dt FROM last_time){filters}
    ORDER BY dt_norm DESC, groupname, targetunit, seq DESC
    """)


def get_knowsaboutchanged_recent_rows(
    limit: int,
    target_side: str | None = None,
    source_side: str | None = None,
) -> str:
    """Return the most recent deduplicated knowsabout change events limited by row count with optional side filters.
    한국어: 가장 최근의 knowsaboutchanged 이벤트를 중복 제거하여 행 수 제한과 함께 반환하며, 선택적으로 진영 필터를 적용합니다."""
    where_clause = ""
    conditions = []

    if target_side is not None:
        conditions.append(f"targetunit LIKE '{target_side}%'")
    if source_side is not None:
        conditions.append(f"side = '{source_side}'")

    if conditions:
        where_clause = "\nWHERE " + "\n  AND ".join(conditions)

    return _run(f"""
    {_normalized_knowsaboutchanged_cte()}
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout,
        seq
    FROM normalized_knowsaboutchanged{where_clause}
    ORDER BY dt_norm DESC, groupname, targetunit, seq DESC
    LIMIT {limit}
    """)


# =========================
# 5) entity frequency (deduped logical events)
# =========================

def get_entity_frequency_recent_minutes(
    minutes: int,
    top_k: int | None = None,
    entity_type: str | None = None,
) -> str:
    """Return recent entity participation frequencies with inferred entity type, dominant event, and dominant role.
    한국어: 최근 엔티티 참여 빈도를 반환하며, 추론된 엔티티 유형, 주요 이벤트, 주요 역할을 함께 제공합니다."""
    where_clause = ""
    if entity_type is not None:
        where_clause = f"\nWHERE entity_type = '{entity_type}'"

    limit_clause = f"\nLIMIT {top_k}" if top_k is not None else ""

    return _run(f"""
    {_normalized_events_cte()},
    last_time AS (
        SELECT MAX(dt_norm) AS max_dt
        FROM events
    ),
    recent AS (
        SELECT *
        FROM events
        WHERE dt_norm >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')
          AND dt_norm <= (SELECT max_dt FROM last_time)
    ),
    entities AS (
        SELECT
            shooter AS name,
            event_type,
            'attacker' AS role
        FROM recent
        WHERE shooter IS NOT NULL

        UNION ALL

        SELECT
            targetunit AS name,
            event_type,
            'victim' AS role
        FROM recent
        WHERE targetunit IS NOT NULL

        UNION ALL

        SELECT
            unit AS name,
            event_type,
            'attacker' AS role
        FROM recent
        WHERE unit IS NOT NULL

        UNION ALL

        SELECT
            gunner AS name,
            event_type,
            'attacker' AS role
        FROM recent
        WHERE gunner IS NOT NULL

        UNION ALL

        SELECT
            killer AS name,
            event_type,
            'attacker' AS role
        FROM recent
        WHERE killer IS NOT NULL
    ),
    aggregated AS (
        SELECT
            CASE
                WHEN name GLOB '*_v[0-9]*' THEN 'vehicle'
                ELSE 'unit'
            END AS entity_type,
            name AS entity_name,
            COUNT(*) AS frequency
        FROM entities
        GROUP BY name
    ),
    event_ranked AS (
        SELECT
            name,
            event_type,
            COUNT(*) AS event_count,
            ROW_NUMBER() OVER (
                PARTITION BY name
                ORDER BY COUNT(*) DESC, event_type DESC
            ) AS rn
        FROM entities
        GROUP BY name, event_type
    ),
    role_ranked AS (
        SELECT
            name,
            role,
            COUNT(*) AS role_count,
            ROW_NUMBER() OVER (
                PARTITION BY name
                ORDER BY COUNT(*) DESC,
                         CASE WHEN role = 'attacker' THEN 1 ELSE 0 END DESC,
                         role DESC
            ) AS rn
        FROM entities
        GROUP BY name, role
    )
    SELECT
        a.entity_type,
        a.entity_name,
        a.frequency,
        er.event_type AS most_frequent_event_type,
        rr.role AS dominant_role
    FROM aggregated a
    LEFT JOIN event_ranked er
        ON a.entity_name = er.name AND er.rn = 1
    LEFT JOIN role_ranked rr
        ON a.entity_name = rr.name AND rr.rn = 1
    {where_clause}
    ORDER BY a.frequency DESC, a.entity_name DESC
    {limit_clause}
    """)


def get_nearest_enemy_groups(
    friendly_groupname: str | None = None,
    enemy_groupname: str | None = None,
    limit: int = 20,
) -> str:
    """Return the nearest friendly-enemy group pairs from the current group distance view.
    한국어: 현재 그룹 거리 뷰에서 가장 가까운 아군-적군 그룹 쌍을 반환합니다."""
    friendly_filter = f"AND friendly_groupname = '{friendly_groupname}'" if friendly_groupname else ""
    enemy_filter = f"AND enemy_groupname = '{enemy_groupname}'" if enemy_groupname else ""

    return _run(f"""
    SELECT
        ref_datetime,
        friendly_groupname,
        enemy_groupname,
        distance_3d
    FROM v_current_friendly_enemy_group_distance
    WHERE 1 = 1
      {friendly_filter}
      {enemy_filter}
    ORDER BY distance_3d ASC, friendly_groupname, enemy_groupname
    LIMIT {limit}
    """)


def get_nearest_enemy_units(
    friendly_unitname: str | None = None,
    enemy_unitname: str | None = None,
    friendly_groupname: str | None = None,
    enemy_groupname: str | None = None,
    limit: int = 20,
) -> str:
    """Return the nearest friendly-enemy unit pairs from the current unit distance view.
    한국어: 현재 유닛 거리 뷰에서 가장 가까운 아군-적군 유닛 쌍을 반환합니다."""
    friendly_unit_filter = f"AND friendly_unitname = '{friendly_unitname}'" if friendly_unitname else ""
    enemy_unit_filter = f"AND enemy_unitname = '{enemy_unitname}'" if enemy_unitname else ""
    friendly_group_filter = f"AND friendly_groupname = '{friendly_groupname}'" if friendly_groupname else ""
    enemy_group_filter = f"AND enemy_groupname = '{enemy_groupname}'" if enemy_groupname else ""

    return _run(f"""
    SELECT
        ref_datetime,
        friendly_unitname,
        friendly_groupname,
        friendly_unittype,
        enemy_unitname,
        enemy_groupname,
        enemy_unittype,
        distance_3d
    FROM v_current_friendly_enemy_unit_distance
    WHERE 1 = 1
      {friendly_unit_filter}
      {enemy_unit_filter}
      {friendly_group_filter}
      {enemy_group_filter}
    ORDER BY distance_3d ASC, friendly_unitname, enemy_unitname
    LIMIT {limit}
    """)


def get_nearest_enemy_vehicles(
    friendly_vehiclename: str | None = None,
    enemy_vehiclename: str | None = None,
    friendly_groupname: str | None = None,
    enemy_groupname: str | None = None,
    limit: int = 20,
) -> str:
    """Return the nearest friendly-enemy vehicle pairs from the current vehicle distance view.
    한국어: 현재 차량 거리 뷰에서 가장 가까운 아군-적군 차량 쌍을 반환합니다."""
    friendly_vehicle_filter = f"AND friendly_vehiclename = '{friendly_vehiclename}'" if friendly_vehiclename else ""
    enemy_vehicle_filter = f"AND enemy_vehiclename = '{enemy_vehiclename}'" if enemy_vehiclename else ""
    friendly_group_filter = f"AND friendly_groupname = '{friendly_groupname}'" if friendly_groupname else ""
    enemy_group_filter = f"AND enemy_groupname = '{enemy_groupname}'" if enemy_groupname else ""

    return _run(f"""
    SELECT
        ref_datetime,
        friendly_vehiclename,
        friendly_groupname,
        friendly_vehicletype,
        enemy_vehiclename,
        enemy_groupname,
        enemy_vehicletype,
        distance_3d
    FROM v_current_friendly_enemy_vehicle_distance
    WHERE 1 = 1
      {friendly_vehicle_filter}
      {enemy_vehicle_filter}
      {friendly_group_filter}
      {enemy_group_filter}
    ORDER BY distance_3d ASC, friendly_vehiclename, enemy_vehiclename
    LIMIT {limit}
    """)


def get_fastest_units(side: str, limit: int = 20) -> str:
    """Return the fastest unit movement rows for the specified side using the speed trend views.
    한국어: 지정된 진영에 대해 속도 추이 뷰를 사용하여 가장 빠른 유닛 이동 행들을 반환합니다."""
    view_name = "v_friendly_unit_speed_trend" if side == "b" else "v_enemy_unit_speed_trend"

    return _run(f"""
    SELECT
        datetime,
        unitname,
        groupname,
        unittype,
        dt_seconds,
        distance_delta,
        speed_per_sec,
        prev_speed_per_sec,
        speed_change_per_sec
    FROM {view_name}
    WHERE speed_per_sec IS NOT NULL
    ORDER BY speed_per_sec DESC, datetime DESC, unitname
    LIMIT {limit}
    """)


def get_fastest_vehicles(side: str, limit: int = 20) -> str:
    """Return the fastest vehicle movement rows for the specified side using the speed trend views.
    한국어: 지정된 진영에 대해 속도 추이 뷰를 사용하여 가장 빠른 차량 이동 행들을 반환합니다."""
    view_name = "v_friendly_vehicle_speed_trend" if side == "b" else "v_enemy_vehicle_speed_trend"

    return _run(f"""
    SELECT
        datetime,
        vehiclename,
        groupname,
        vehicletype,
        dt_seconds,
        distance_delta,
        speed_per_sec,
        prev_speed_per_sec,
        speed_change_per_sec
    FROM {view_name}
    WHERE speed_per_sec IS NOT NULL
    ORDER BY speed_per_sec DESC, datetime DESC, vehiclename
    LIMIT {limit}
    """)


def get_unit_speed_change_leaders(side: str, limit: int = 20) -> str:
    """Return unit rows with the largest absolute speed change for the specified side.
    한국어: 지정된 진영에 대해 절대 속도 변화량이 가장 큰 유닛 행들을 반환합니다."""
    view_name = "v_friendly_unit_speed_trend" if side == "b" else "v_enemy_unit_speed_trend"

    return _run(f"""
    SELECT
        datetime,
        unitname,
        groupname,
        unittype,
        speed_per_sec,
        prev_speed_per_sec,
        speed_change_per_sec
    FROM {view_name}
    WHERE speed_change_per_sec IS NOT NULL
    ORDER BY ABS(speed_change_per_sec) DESC, datetime DESC, unitname
    LIMIT {limit}
    """)


def get_vehicle_speed_change_leaders(side: str, limit: int = 20) -> str:
    """Return vehicle rows with the largest absolute speed change for the specified side.
    한국어: 지정된 진영에 대해 절대 속도 변화량이 가장 큰 차량 행들을 반환합니다."""
    view_name = "v_friendly_vehicle_speed_trend" if side == "b" else "v_enemy_vehicle_speed_trend"

    return _run(f"""
    SELECT
        datetime,
        vehiclename,
        groupname,
        vehicletype,
        speed_per_sec,
        prev_speed_per_sec,
        speed_change_per_sec
    FROM {view_name}
    WHERE speed_change_per_sec IS NOT NULL
    ORDER BY ABS(speed_change_per_sec) DESC, datetime DESC, vehiclename
    LIMIT {limit}
    """)


def get_lowest_ammo_units(side: str, limit: int = 20) -> str:
    """Return unit rows with the lowest remaining ammo totals for the specified side.
    한국어: 지정된 진영에 대해 남은 탄약 총량이 가장 낮은 유닛 행들을 반환합니다."""
    view_name = "v_friendly_unit_ammo_trend" if side == "b" else "v_enemy_unit_ammo_trend"

    return _run(f"""
    SELECT
        datetime,
        unitname,
        total_ammo_count,
        prev_total_ammo_count,
        ammo_change
    FROM {view_name}
    WHERE total_ammo_count IS NOT NULL
    ORDER BY total_ammo_count ASC, datetime DESC, unitname
    LIMIT {limit}
    """)


def get_lowest_ammo_vehicles(side: str, limit: int = 20) -> str:
    """Return vehicle rows with the lowest remaining ammo totals for the specified side.
    한국어: 지정된 진영에 대해 남은 탄약 총량이 가장 낮은 차량 행들을 반환합니다."""
    view_name = "v_friendly_vehicle_ammo_trend" if side == "b" else "v_enemy_vehicle_ammo_trend"

    return _run(f"""
    SELECT
        datetime,
        vehiclename,
        total_ammo_count,
        prev_total_ammo_count,
        ammo_change
    FROM {view_name}
    WHERE total_ammo_count IS NOT NULL
    ORDER BY total_ammo_count ASC, datetime DESC, vehiclename
    LIMIT {limit}
    """)


def get_unit_ammo_drop_leaders(side: str, limit: int = 20) -> str:
    """Return unit rows with the largest ammo decreases for the specified side.
    한국어: 지정된 진영에 대해 탄약 감소량이 가장 큰 유닛 행들을 반환합니다."""
    view_name = "v_friendly_unit_ammo_trend" if side == "b" else "v_enemy_unit_ammo_trend"

    return _run(f"""
    SELECT
        datetime,
        unitname,
        total_ammo_count,
        prev_total_ammo_count,
        ammo_change
    FROM {view_name}
    WHERE ammo_change IS NOT NULL
    ORDER BY ammo_change ASC, datetime DESC, unitname
    LIMIT {limit}
    """)


def get_vehicle_ammo_drop_leaders(side: str, limit: int = 20) -> str:
    """Return vehicle rows with the largest ammo decreases for the specified side.
    한국어: 지정된 진영에 대해 탄약 감소량이 가장 큰 차량 행들을 반환합니다."""
    view_name = "v_friendly_vehicle_ammo_trend" if side == "b" else "v_enemy_vehicle_ammo_trend"

    return _run(f"""
    SELECT
        datetime,
        vehiclename,
        total_ammo_count,
        prev_total_ammo_count,
        ammo_change
    FROM {view_name}
    WHERE ammo_change IS NOT NULL
    ORDER BY ammo_change ASC, datetime DESC, vehiclename
    LIMIT {limit}
    """)