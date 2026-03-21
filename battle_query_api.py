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
# 1) current / initial counts
# =========================

def get_b_unit_count() -> str:
    return _run("""
    SELECT
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = 'b'
              AND unitname NOT IN (
                  SELECT DISTINCT targetunit
                  FROM event_killed
                  WHERE side = 'b'
              )
        ) AS alive_unit_count,
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = 'b'
        ) AS initial_unit_count
    """)


def get_op_unit_count() -> str:
    return _run("""
    SELECT
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = 'op'
              AND unitname NOT IN (
                  SELECT DISTINCT targetunit
                  FROM event_killed
                  WHERE side = 'op'
              )
        ) AS alive_unit_count,
        (
            SELECT COUNT(DISTINCT unitname)
            FROM units
            WHERE side = 'op'
        ) AS initial_unit_count
    """)


def get_b_equipment_count() -> str:
    return _run("""
    SELECT
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = 'b'
              AND damage < 1
        ) AS available_equipment_count,
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = 'b'
        ) AS initial_equipment_count
    """)


def get_op_equipment_count() -> str:
    return _run("""
    SELECT
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = 'op'
              AND damage < 1
        ) AS available_equipment_count,
        (
            SELECT COUNT(DISTINCT vehiclename)
            FROM vehicles
            WHERE side = 'op'
        ) AS initial_equipment_count
    """)


# =========================
# 2) interval stats
# =========================

def get_b_unit_alive_by_interval(interval_minutes: int) -> str:
    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT unitname) AS alive_unit_count
    FROM units
    WHERE side = 'b'
      AND unitname NOT IN (
          SELECT DISTINCT targetunit
          FROM event_killed
          WHERE side = 'b'
      )
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


def get_op_unit_alive_by_interval(interval_minutes: int) -> str:
    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT unitname) AS alive_unit_count
    FROM units
    WHERE side = 'op'
      AND unitname NOT IN (
          SELECT DISTINCT targetunit
          FROM event_killed
          WHERE side = 'op'
      )
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


def get_b_equipment_available_by_interval(interval_minutes: int) -> str:
    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT vehiclename) AS available_equipment_count
    FROM vehicles
    WHERE side = 'b'
      AND damage < 1
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


def get_op_equipment_available_by_interval(interval_minutes: int) -> str:
    return _run(f"""
    SELECT
        datetime(
            (CAST(strftime('%s', datetime) AS INTEGER) / ({interval_minutes} * 60)) * ({interval_minutes} * 60),
            'unixepoch'
        ) AS bucket_time,
        COUNT(DISTINCT vehiclename) AS available_equipment_count
    FROM vehicles
    WHERE side = 'op'
      AND damage < 1
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


def get_b_ammo_total_by_interval(interval_minutes: int) -> str:
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
        WHERE side = 'b'

        UNION ALL

        SELECT datetime, count
        FROM vehicles_ammo
        WHERE side = 'b'
    )
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


def get_op_ammo_total_by_interval(interval_minutes: int) -> str:
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
        WHERE side = 'op'

        UNION ALL

        SELECT datetime, count
        FROM vehicles_ammo
        WHERE side = 'op'
    )
    GROUP BY bucket_time
    ORDER BY bucket_time
    """)


# =========================
# 3) events
# =========================

def get_events_between(start_time: str, end_time: str) -> str:
    return _run(f"""
    SELECT *
    FROM (
        SELECT
            datetime,
            side,
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
        FROM event_dammaged
        WHERE datetime >= '{start_time}'
          AND datetime <= '{end_time}'

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_fired
        WHERE datetime >= '{start_time}'
          AND datetime <= '{end_time}'

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_killed
        WHERE datetime >= '{start_time}'
          AND datetime <= '{end_time}'
    )
    ORDER BY datetime
    """)


def get_events_recent_minutes(minutes: int) -> str:
    return _run(f"""
    WITH last_time AS (
        SELECT MAX(datetime) AS max_dt
        FROM (
            SELECT datetime FROM event_dammaged
            UNION ALL
            SELECT datetime FROM event_fired
            UNION ALL
            SELECT datetime FROM event_killed
        )
    )
    SELECT *
    FROM (
        SELECT
            datetime,
            side,
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
        FROM event_dammaged
        WHERE datetime >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_fired
        WHERE datetime >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_killed
        WHERE datetime >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')
    )
    ORDER BY datetime
    """)


def get_events_recent_rows(limit: int) -> str:
    return _run(f"""
    SELECT *
    FROM (
        SELECT
            datetime,
            side,
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
        FROM event_dammaged

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_fired

        UNION ALL

        SELECT
            datetime,
            side,
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
        FROM event_killed
    )
    ORDER BY datetime DESC
    LIMIT {limit}
    """)


# =========================
# 4) observations
# =========================

def get_observation_between(start_time: str, end_time: str) -> str:
    return _run(f"""
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout
    FROM event_knowsaboutchanged
    WHERE datetime >= '{start_time}'
      AND datetime <= '{end_time}'
    ORDER BY datetime, groupname, targetunit
    """)


def get_observation_recent_minutes(minutes: int) -> str:
    return _run(f"""
    WITH last_time AS (
        SELECT MAX(datetime) AS max_dt
        FROM event_knowsaboutchanged
    )
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout
    FROM event_knowsaboutchanged
    WHERE datetime >= datetime((SELECT max_dt FROM last_time), '-{minutes} minutes')
    ORDER BY datetime, groupname, targetunit
    """)


def get_observation_recent_rows(limit: int) -> str:
    return _run(f"""
    SELECT
        datetime,
        side,
        groupname,
        targetunit,
        oldknowsabout,
        newknowsabout
    FROM event_knowsaboutchanged
    ORDER BY datetime DESC, groupname, targetunit
    LIMIT {limit}
    """)