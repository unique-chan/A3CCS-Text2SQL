import hashlib
from uuid import uuid4
from datetime import datetime

import orjson
from tqdm import tqdm
from sqlalchemy import select

from .db_util import make_engine, make_session_factory
from .db_schema import Base, Snapshot, Group, Unit, Vehicle, UnitAmmo, VehicleAmmo


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def time_list_to_iso(t):
    y, mo, d, hh, mm, ss, ms = t
    return datetime(y, mo, d, hh, mm, ss, ms * 1000).isoformat(timespec="milliseconds")


def safe_pos3(pos):
    try:
        return float(pos[0]), float(pos[1]), float(pos[2])
    except Exception:
        return None, None, None


def dumps(obj) -> str:
    """
    Robust JSON dump to UTF-8 string.
    - If orjson can't serialize (rare), fallback to string representation.
    """
    try:
        return orjson.dumps(obj).decode()
    except Exception:
        return orjson.dumps(str(obj)).decode()


def _to_int_or_none(x):
    if x is None:
        return None
    try:
        # allow strings like "12"
        return int(float(x))
    except Exception:
        return None


def normalize_ammo_items(ammo_obj):
    """
    Normalize heterogeneous ammo structures into rows:
      (ammo_key: str, count: int|None, raw_json: str)

    Supported patterns (best-effort):
    - dict: prefer keys in order: class, magazine, ammo, weapon, type, name, id
            count from: count, qty, amount, num, n
    - list/tuple: [key, count, ...]
    - scalar: ammo_key = str(value), count=None
    - unknown: ammo_key = '__unknown__:<hash>', count=None
    """
    if ammo_obj is None:
        return []

    # Common case: list of ammo items
    items = ammo_obj if isinstance(ammo_obj, list) else [ammo_obj]
    out = []

    key_candidates = ("class", "magazine", "ammo", "weapon", "type", "name", "id")
    count_candidates = ("count", "qty", "amount", "num", "n")

    for it in items:
        raw = dumps(it)
        ammo_key = None
        count = None

        if isinstance(it, dict):
            for k in key_candidates:
                v = it.get(k)
                if v is not None and str(v) != "":
                    ammo_key = str(v)
                    break

            for ck in count_candidates:
                if ck in it:
                    count = _to_int_or_none(it.get(ck))
                    break

            # Edge: single-entry dict like {"30Rnd_556x45": 6}
            if ammo_key is None and len(it) == 1:
                k0, v0 = next(iter(it.items()))
                if k0 is not None and str(k0) != "":
                    ammo_key = str(k0)
                if count is None:
                    count = _to_int_or_none(v0)

        elif isinstance(it, (list, tuple)) and len(it) >= 2:
            ammo_key = str(it[0]) if it[0] is not None else None
            count = _to_int_or_none(it[1])

        else:
            # scalar / unknown structure
            ammo_key = str(it) if it is not None else None

        if ammo_key is None or ammo_key == "":
            ammo_key = "__unknown__:" + sha256_bytes(raw.encode("utf-8"))

        out.append((ammo_key, count, raw))

    return out


def aggregate_ammo_rows(rows):
    """
    rows: iterable of (ammo_key, count, raw_item_json_str)
    return: dict ammo_key -> (count_sum_or_none, raw_json_list_str)

    Purpose:
    - Fix duplicates per (snapshot_id, side, unitname/vehiclename, ammo_key) PK.
    - Keep one row per ammo_key by aggregating counts and preserving raw items.
    """
    agg = {}  # ammo_key -> {"sum": int, "has_any": bool, "raws": [raw_item_json_str]}
    for ammo_key, count, raw_item in rows:
        rec = agg.get(ammo_key)
        if rec is None:
            rec = {"sum": 0, "has_any": False, "raws": []}
            agg[ammo_key] = rec

        rec["raws"].append(raw_item)

        if count is not None:
            rec["sum"] += int(count)
            rec["has_any"] = True

    out = {}
    for k, rec in agg.items():
        count_out = rec["sum"] if rec["has_any"] else None
        out[k] = (count_out, dumps(rec["raws"]))  # raw_json = list of raw items
    return out


def dump_arma_into_sql(db_url: str = None, json_dir: str = None):
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)  # create tables from db_schema.py
    Session = make_session_factory(engine)

    files = sorted(json_dir.glob("*.json"))
    if not files:
        print("💽 No JSON files")
        return

    ok, skip, fail = 0, 0, 0

    for f in tqdm(files):
        with Session() as session:
            try:
                raw = f.read_bytes()
                sha = sha256_bytes(raw)

                # skip if already ingested (same content hash)
                if session.execute(
                    select(Snapshot.snapshot_id).where(Snapshot.sha256 == sha)
                ).first():
                    skip += 1
                    continue

                raw_json_file = orjson.loads(raw)
                sid = str(uuid4())  # snapshot id

                start_iso = None
                if isinstance(raw_json_file.get("friend_info"), dict):
                    fi0 = raw_json_file["friend_info"]
                    start_iso = time_list_to_iso(fi0["start_time"]) if "start_time" in fi0 else None
                elif isinstance(raw_json_file.get("enemy_info"), dict):
                    ei0 = raw_json_file["enemy_info"]
                    start_iso = time_list_to_iso(ei0["start_time"]) if "start_time" in ei0 else None

                session.add(
                    Snapshot(
                        snapshot_id=sid,
                        source_file=f.name,
                        sha256=sha,
                        datetime=start_iso,
                        raw_json=dumps(raw_json_file),
                    )
                )

                for side, key in (("b", "friend_info"), ("op", "enemy_info")):
                    info = raw_json_file.get(key)
                    if not isinstance(info, dict):
                        continue

                    # groups
                    for g in info.get("groups", []):
                        x, y, z = safe_pos3(g.get("leaderpos", []))
                        gc = g.get("groupname")
                        if not gc:
                            continue

                        parts = gc.split("_")
                        company = parts[1] if len(parts) > 1 else None
                        platoon = parts[2] if len(parts) > 2 else None
                        squad = parts[3] if len(parts) > 3 else None

                        session.add(
                            Group(
                                snapshot_id=sid,
                                side=side,
                                company=company,
                                platoon=platoon,
                                squad=squad,
                                groupname=gc,
                                leaderpos_x=x,
                                leaderpos_y=y,
                                leaderpos_z=z,
                                unitlist_json=dumps(g.get("unitlist", [])),
                                waypointpos_json=dumps(g.get("waypointpos", [])),
                            )
                        )

                    # units + units_ammo
                    for u in info.get("units", []):
                        uname = u.get("unitname")
                        if not uname:
                            continue

                        x, y, z = safe_pos3(u.get("pos", []))
                        session.add(
                            Unit(
                                snapshot_id=sid,
                                side=side,
                                unitname=uname,
                                unittype=u.get("unittype"),
                                pos_x=x,
                                pos_y=y,
                                pos_z=z,
                                groupname="_".join(uname.split("_")[:4]),
                                damage=u.get("damage", 0.0),
                                objectparent=u.get("objectparent"),
                            )
                        )

                        rows = normalize_ammo_items(u.get("ammo", []))
                        agg = aggregate_ammo_rows(rows)
                        for ammo_key, (count_sum, raw_list_json) in agg.items():
                            session.add(
                                UnitAmmo(
                                    snapshot_id=sid,
                                    side=side,
                                    unitname=uname,
                                    ammo_key=ammo_key,
                                    count=count_sum,
                                    raw_json=raw_list_json,
                                )
                            )

                    # vehicles + vehicles_ammo
                    for v in info.get("vehicles", []):
                        vname = v.get("vehiclename")
                        if not vname:
                            continue

                        x, y, z = safe_pos3(v.get("pos", []))
                        session.add(
                            Vehicle(
                                snapshot_id=sid,
                                side=side,
                                vehiclename=vname,
                                vehicletype=v.get("vehicletype"),
                                groupname="_".join(vname.split("_")[:4]),
                                pos_x=x,
                                pos_y=y,
                                pos_z=z,
                                damage=v.get("damage", 0.0),
                                hitpoint_json=dumps(v.get("hitpoint", [])),
                            )
                        )

                        rows = normalize_ammo_items(v.get("ammo", []))
                        agg = aggregate_ammo_rows(rows)
                        for ammo_key, (count_sum, raw_list_json) in agg.items():
                            session.add(
                                VehicleAmmo(
                                    snapshot_id=sid,
                                    side=side,
                                    vehiclename=vname,
                                    ammo_key=ammo_key,
                                    count=count_sum,
                                    raw_json=raw_list_json,
                                )
                            )

                session.commit()
                ok += 1

            except Exception as e:
                session.rollback()
                print(f"💽 [FAIL] {f.name}: {e}")
                fail += 1

    print(
        f"💽 Migrating Arma 3 metadata into SQLite3 database: Done ⭕ - ok={ok}, skipped={skip}, failed={fail}"
    )