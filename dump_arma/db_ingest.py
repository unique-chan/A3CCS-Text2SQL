import hashlib
from uuid import uuid4
from datetime import datetime

import orjson
from tqdm import tqdm
from sqlalchemy import select

from .db_util import make_engine, make_session_factory
from .db_schema import (
    Base,
    Snapshot,
    Group,
    Unit,
    Vehicle,
    UnitAmmo,
    VehicleAmmo,
    VehicleHitpoint,
    # EventED,
    EventEDC,
    EventF,
    EventD,
    EventK,
)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def time_list_to_iso(t):
    # [YYYY,MM,DD,hh,mm,ss,ms] -> ISO8601 with milliseconds
    y, mo, d, hh, mm, ss, ms = t
    return datetime(y, mo, d, hh, mm, ss, ms * 1000).isoformat(timespec="milliseconds")


def dumps(obj) -> str:
    """Robust JSON dump to UTF-8 string."""
    try:
        return orjson.dumps(obj).decode()
    except Exception:
        return orjson.dumps(str(obj)).decode()


def safe_pos2(pos):
    try:
        return float(pos[0]), float(pos[1])
    except Exception:
        return None, None


def safe_pos3(pos):
    try:
        return float(pos[0]), float(pos[1]), float(pos[2])
    except Exception:
        return None, None, None


def safe_waypoint_xy(waypoints):
    """
    waypoints examples:
      [[x, y, z], ...] or [[x, y], ...]
    We take the first waypoint only.
    """
    try:
        if not waypoints:
            return None, None
        wp0 = waypoints[0]
        return float(wp0[0]), float(wp0[1])
    except Exception:
        return None, None


def _to_int_or_none(x):
    if x is None:
        return None
    try:
        return int(float(x))
    except Exception:
        return None


def _to_float_or_none(x):
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def normalize_ammo_items(ammo_obj):
    """
    Normalize heterogeneous ammo structures into rows:
      (ammotype: str, count: int|None)

    Best-effort patterns:
    - list/tuple: [ammotype, count, ...]  (common case)
    - dict: pick first among class/magazine/ammo/weapon/type/name/id
            count from count/qty/amount/num/n
    - scalar: ammotype = str(value), count=None
    - unknown: ammotype = '__unknown__:<hash>'
    """
    if ammo_obj is None:
        return []

    items = ammo_obj if isinstance(ammo_obj, list) else [ammo_obj]
    out = []

    key_candidates = ("class", "magazine", "ammo", "weapon", "type", "name", "id")
    count_candidates = ("count", "qty", "amount", "num", "n")

    for it in items:
        ammotype = None
        count = None

        if isinstance(it, (list, tuple)) and len(it) >= 1:
            ammotype = str(it[0]) if it[0] is not None else None
            if len(it) >= 2:
                count = _to_int_or_none(it[1])

        elif isinstance(it, dict):
            for k in key_candidates:
                v = it.get(k)
                if v is not None and str(v) != "":
                    ammotype = str(v)
                    break

            for ck in count_candidates:
                if ck in it:
                    count = _to_int_or_none(it.get(ck))
                    break

            # Edge: {"30Rnd_556x45": 6}
            if ammotype is None and len(it) == 1:
                k0, v0 = next(iter(it.items()))
                if k0 is not None and str(k0) != "":
                    ammotype = str(k0)
                if count is None:
                    count = _to_int_or_none(v0)

        else:
            ammotype = str(it) if it is not None else None

        if ammotype is None or ammotype == "":
            raw = dumps(it).encode("utf-8")
            ammotype = "__unknown__:" + sha256_bytes(raw)

        out.append((ammotype, count))

    return out


def aggregate_ammo(rows):
    """
    rows: iterable of (ammotype, count)
    Returns: dict ammotype -> count_sum_or_none

    Ensures uniqueness for PK (snapshotid, side, name, ammotype) by aggregating
    duplicates within a single entity (unit/vehicle).
    """
    agg = {}  # ammotype -> {"sum": int, "has_any": bool}
    for ammotype, count in rows:
        rec = agg.get(ammotype)
        if rec is None:
            rec = {"sum": 0, "has_any": False}
            agg[ammotype] = rec
        if count is not None:
            rec["sum"] += int(count)
            rec["has_any"] = True

    out = {}
    for k, rec in agg.items():
        out[k] = rec["sum"] if rec["has_any"] else None
    return out


def parse_hitpoints(hitpoint_obj):
    """
    Expected shape: 3 x n list
      row0: hitpoint names (strings)
      row1: ignore
      row2: damage values (numbers)

    Returns: list of (hitpoint_name, damage_float_or_none)
    """
    if not hitpoint_obj or not isinstance(hitpoint_obj, list) or len(hitpoint_obj) < 3:
        return []

    names = hitpoint_obj[0]
    damages = hitpoint_obj[2]

    if not isinstance(names, list) or not isinstance(damages, list):
        return []

    n = min(len(names), len(damages))
    out = []
    for i in range(n):
        hp = names[i]
        dv = damages[i]
        if hp is None or str(hp) == "":
            continue
        dmg = _to_float_or_none(dv)
        out.append((str(hp), dmg))
    return out


def parse_event_datetime(x):
    # event entry time is usually [YYYY,MM,DD,hh,mm,ss,ms]
    if isinstance(x, list) and len(x) == 7 and all(isinstance(v, int) for v in x):
        return time_list_to_iso(x)
    # fallback: stringify
    return str(x) if x is not None else None


def dump_arma_into_sql(db_url: str = None, json_dir=None):
    """
    Ingest Arma dump JSON files into SQLite.

    Side mapping:
      - friend_info -> 'b'
      - enemy_info  -> 'op'
    """
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
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

                # Skip if already ingested (same content hash)
                if session.execute(
                    select(Snapshot.snapshotid).where(Snapshot.sha256 == sha)
                ).first():
                    skip += 1
                    continue

                raw_json_file = orjson.loads(raw)
                sid = str(uuid4())

                # Snapshot datetime (best-effort)
                start_iso = None
                if isinstance(raw_json_file.get("friend_info"), dict):
                    fi0 = raw_json_file["friend_info"]
                    if "start_time" in fi0:
                        start_iso = time_list_to_iso(fi0["start_time"])
                elif isinstance(raw_json_file.get("enemy_info"), dict):
                    ei0 = raw_json_file["enemy_info"]
                    if "start_time" in ei0:
                        start_iso = time_list_to_iso(ei0["start_time"])

                session.add(
                    Snapshot(
                        snapshotid=sid,
                        sourcefile=f.name,
                        sha256=sha,
                        datetime=start_iso,
                        rawjson=dumps(raw_json_file),
                    )
                )

                # --------------------
                # friend/enemy blocks
                # --------------------
                for side, key in (("b", "friend_info"), ("op", "enemy_info")):
                    info = raw_json_file.get(key)
                    if not isinstance(info, dict):
                        continue

                    # groups
                    for g in info.get("groups", []):
                        gc = g.get("groupname")
                        if not gc:
                            continue

                        parts = gc.split("_")
                        company = parts[1] if len(parts) > 1 else None
                        platoon = parts[2] if len(parts) > 2 else None
                        squad = parts[3] if len(parts) > 3 else None

                        lx, ly, lz = safe_pos3(g.get("leaderpos", []))
                        wx, wy = safe_waypoint_xy(g.get("waypointpos", []))

                        session.add(
                            Group(
                                snapshotid=sid,
                                datetime=start_iso,
                                side=side,
                                company=company,
                                platoon=platoon,
                                squad=squad,
                                groupname=gc,
                                leaderposx=lx,
                                leaderposy=ly,
                                leaderposz=lz,
                                waypointposx=wx,
                                waypointposy=wy,
                            )
                        )

                    # units + units_ammo
                    for u in info.get("units", []):
                        uname = u.get("unitname")
                        if not uname:
                            continue

                        ux, uy, uz = safe_pos3(u.get("pos", []))

                        if '_' in uname:
                            session.add(
                                Unit(
                                    snapshotid=sid,
                                    side=side,
                                    unitname=uname,
                                    datetime=start_iso,
                                    groupname="_".join(uname.split("_")[:4]),
                                    unittype=u.get("unittype"),
                                    posx=ux,
                                    posy=uy,
                                    posz=uz,
                                    damage=u.get("damage", 0.0),
                                    objectparent=u.get("objectparent"),
                                )
                            )

                        ammo_agg = aggregate_ammo(normalize_ammo_items(u.get("ammo", [])))
                        for ammotype, count_sum in ammo_agg.items():
                            session.add(
                                UnitAmmo(
                                    snapshotid=sid,
                                    side=side,
                                    datetime=start_iso,
                                    unitname=uname,
                                    ammotype=ammotype,
                                    count=count_sum,
                                )
                            )

                    # vehicles + vehicles_ammo + vehicle_hitpoints
                    for v in info.get("vehicles", []):
                        vname = v.get("vehiclename")
                        if not vname:
                            continue

                        vx, vy, vz = safe_pos3(v.get("pos", []))
                        hp_obj = v.get("hitpoint", [])

                        session.add(
                            Vehicle(
                                snapshotid=sid,
                                datetime=start_iso,
                                side=side,
                                vehiclename=vname,
                                groupname="_".join(vname.split("_")[:4]),
                                vehicletype=v.get("vehicletype"),
                                posx=vx,
                                posy=vy,
                                posz=vz,
                                damage=v.get("damage", 0.0),
                                hitpointjson=dumps(hp_obj),
                            )
                        )

                        ammo_agg = aggregate_ammo(normalize_ammo_items(v.get("ammo", [])))
                        for ammotype, count_sum in ammo_agg.items():
                            session.add(
                                VehicleAmmo(
                                    snapshotid=sid,
                                    datetime=start_iso,
                                    side=side,
                                    vehiclename=vname,
                                    ammotype=ammotype,
                                    count=count_sum,
                                )
                            )

                        # hitpoints (3 x n -> keep rows 0 and 2), dedup by hitpoint name (last wins)
                        hp_map = {}
                        for hp_name, dmg in parse_hitpoints(hp_obj):
                            hp_map[hp_name] = dmg

                        for hp_name, dmg in hp_map.items():
                            session.add(
                                VehicleHitpoint(
                                    snapshotid=sid,
                                    datetime=start_iso,
                                    side=side,
                                    vehiclename=vname,
                                    hitpoint=hp_name,
                                    damage=dmg,
                                )
                            )

                # --------------------
                # events block (global JSON["event"])
                # --------------------
                ev = raw_json_file.get("event")
                if isinstance(ev, dict):
                    for keyname, entries in ev.items():
                        if keyname in ("start_time", "end_time"):
                            continue
                        if not isinstance(entries, list):
                            continue

                        # team from key prefix: "B_event_EDC" -> "b", "OP_event_D" -> "op"
                        team = keyname.split("_", 1)[0].lower()
                        keyname = keyname.lower() 

                        # event type suffix
                        up = keyname.upper()
                        if up.endswith("_EVENT_EDC"):
                            etype = "edc"
                        # elif up.endswith("_EVENT_ED"):
                        #     etype = "ed"
                        elif up.endswith("_EVENT_F"):
                            etype = "f"
                        elif up.endswith("_EVENT_D"):
                            etype = "d"
                        elif up.endswith("_EVENT_K"):
                            etype = "k"
                        else:
                            continue

                        for seq, e in enumerate(entries):
                            if not isinstance(e, list) or len(e) == 0:
                                continue

                            datetime = parse_event_datetime(e[0])
                            params = e[1:]
                            paramsjson = dumps(params)

                            # event_enemydetected ->
                            # if etype == "ed":
                            #     group = params[0] if len(params) > 0 else None
                            #     newtarget = params[1] if len(params) > 1 else None
                            #     session.add(
                            #         EventED(
                            #             snapshotid=sid,
                            #             team=team,
                            #             seq=seq,
                            #             keyname=keyname,
                            #             datetime=start_iso,
                            #             group=group,
                            #             newtarget=newtarget,
                            #             paramsjson=paramsjson,
                            #         )
                            #     )

                            #event_knowsaboutchanged ->
                            if etype == "edc":
                                group = params[0] if len(params) > 0 else None
                                targetunit = params[1] if len(params) > 1 else None
                                newknowsabout = _to_float_or_none(params[2]) if len(params) > 2 else None
                                oldknowsabout = _to_float_or_none(params[3]) if len(params) > 3 else None

                                if targetunit is not None and '_' in targetunit and ( targetunit.startswith("b_") or targetunit.startswith("op_") ):
                                    session.add(
                                        EventEDC(
                                            snapshotid=sid,
                                            team=team,
                                            seq=seq,
                                            keyname=keyname,
                                            datetime=start_iso,
                                            group=group,
                                            targetunit=targetunit,
                                            newknowsabout=newknowsabout,
                                            oldknowsabout=oldknowsabout,
                                            paramsjson=paramsjson,
                                        )
                                    )

                            # event_fired ->
                            elif etype == "f":
                                unit = params[0] if len(params) > 0 else None
                                weapon = params[1] if len(params) > 1 else None
                                muzzle = params[2] if len(params) > 2 else None
                                mode = params[3] if len(params) > 3 else None
                                ammo = params[4] if len(params) > 4 else None
                                magazine = params[5] if len(params) > 5 else None
                                projectile = params[6] if len(params) > 6 else None
                                gunner = params[7] if len(params) > 7 else None
                                session.add(
                                    EventF(
                                        snapshotid=sid,
                                        datetime=start_iso,
                                        team=team,
                                        seq=seq,
                                        keyname=keyname,
                                        unit=unit,
                                        weapon=weapon,
                                        muzzle=muzzle,
                                        mode=mode,
                                        ammo=ammo,
                                        magazine=magazine,
                                        projectile=projectile,
                                        gunner=gunner,
                                        paramsjson=paramsjson,
                                    )
                                )

                            # event_dammaged ->
                            elif etype == "d":
                                unit = params[0] if len(params) > 0 else None
                                hitselection = params[1] if len(params) > 1 else None
                                damage = _to_float_or_none(params[2]) if len(params) > 2 else None
                                hitpartindex = _to_int_or_none(params[3]) if len(params) > 3 else None
                                hitpoint = params[4] if len(params) > 4 else None
                                shooter = params[5] if len(params) > 5 else None
                                projecttile = params[6] if len(params) > 6 else None
                                session.add(
                                    EventD(
                                        snapshotid=sid,
                                        team=team,
                                        seq=seq,
                                        keyname=keyname,
                                        datetime=start_iso,
                                        unit=unit,
                                        hitselection=hitselection,
                                        damage=damage,
                                        hitpartindex=hitpartindex,
                                        hitpoint=hitpoint,
                                        shooter=shooter,
                                        projecttile=projecttile,
                                        paramsjson=paramsjson,
                                    )
                                )

                            # event_killed ->
                            elif etype == "k":
                                unit = params[0] if len(params) > 0 else None
                                killer = params[1] if len(params) > 1 else None
                                instigator = params[2] if len(params) > 2 else None
                                useeffects = None
                                if len(params) > 3:
                                    useeffects = 1 if bool(params[3]) else 0
                                session.add(
                                    EventK(
                                        snapshotid=sid,
                                        team=team,
                                        seq=seq,
                                        keyname=keyname,
                                        datetime=start_iso,
                                        unit=unit,
                                        killer=killer,
                                        instigator=instigator,
                                        useeffects=useeffects,
                                        paramsjson=paramsjson,
                                    )
                                )

                session.commit()
                ok += 1

            except Exception as e:
                session.rollback()
                print(f"💽 [FAIL] {f.name}: {e}")
                fail += 1

    print(f"💽 Migrating Arma 3 metadata into SQLite3 database: Done ⭕ - ok={ok}, skipped={skip}, failed={fail}")