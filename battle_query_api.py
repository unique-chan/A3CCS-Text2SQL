from pathlib import Path

from text2sql_langgraph import build_config_from_env, run_and_save_sqlite


def _run(sql: str) -> str:
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