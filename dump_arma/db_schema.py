from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, Text, Index


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    __tablename__ = "snapshots"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)              # Surrogate key
    source_file: Mapped[str] = mapped_column(String, nullable=False)                # original json file name
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)        # content hash (to avoid duplicates)
    datetime: Mapped[str | None] = mapped_column(String)                            # ISO8601: [YYYY-MM-DD]T[HH:MM:SS.mmm]
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)                     # original raw json content


class Group(Base):
    __tablename__ = "groups"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)              # foreign key to Snapshot.snapshot_id
    side: Mapped[str] = mapped_column(String, primary_key=True)                     # side identifier ("friend" | "enemy")

    company: Mapped[str] = mapped_column(String, primary_key=True)                  # Company (중대) identifier (1, 2, 3, ...)
    platoon: Mapped[str] = mapped_column(String, primary_key=True)                  # Platoon (소대) identifier (i[n]: IFV, t[n]: Tank, hq[n]: headquarter, ...)
    squad: Mapped[str] = mapped_column(String, primary_key=True)                    # Squad (분대) identifier
    groupname: Mapped[str] = mapped_column(String, primary_key=True)                # [Side]_[Company]_[Platoon]_[Squad]

    leaderpos_x: Mapped[float | None] = mapped_column(Float)                        # Leader X position of the squad
    leaderpos_y: Mapped[float | None] = mapped_column(Float)                        # Leader Y position of the squad
    leaderpos_z: Mapped[float | None] = mapped_column(Float)                        # Leader Z position of the squad
    unitlist_json: Mapped[str | None] = mapped_column(Text)                         # Members belonging to each squad (json list)
    waypointpos_json: Mapped[str | None] = mapped_column(Text)                      # ??? Waypoint positions (json list)

Index("ix_groups_snapshot_side_group", Group.snapshot_id, Group.side, Group.groupname)

class Unit(Base):
    __tablename__ = "units"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)              # foreign key to Snapshot.snapshot_id
    side: Mapped[str] = mapped_column(String, primary_key=True)                     # side identifier ("friend" | "enemy")
    unitname: Mapped[str] = mapped_column(String, primary_key=True)
    groupname: Mapped[str] = mapped_column(String)                                  # foreign key to Group.groupname
    unittype: Mapped[str | None] = mapped_column(String)
    pos_x: Mapped[float | None] = mapped_column(Float)                              # X position of the unit
    pos_y: Mapped[float | None] = mapped_column(Float)                              # Y position of the unit
    pos_z: Mapped[float | None] = mapped_column(Float)                              # Z position of the unit
    damage: Mapped[float | None] = mapped_column(Float)                             # damage value between 0.0 and 1.0
    objectparent: Mapped[str | None] = mapped_column(String)                        # vehiclename if the unit is in a vehicle
    # discovered: Mapped[float | None] = mapped_column(Float)                       # only available for enemy units
    # behaviour: Mapped[str | None] = mapped_column(String)

Index("ix_units_snapshot_side_group", Unit.snapshot_id, Unit.side, Unit.groupname)

class Vehicle(Base):
    __tablename__ = "vehicles"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)              # foreign key to Snapshot.snapshot_id
    side: Mapped[str] = mapped_column(String, primary_key=True)                     # side identifier ("friend" | "enemy")
    vehiclename: Mapped[str] = mapped_column(String, primary_key=True)
    groupname: Mapped[str] = mapped_column(String)                                  # foreign key to Group.groupname
    vehicletype: Mapped[str | None] = mapped_column(String)
    pos_x: Mapped[float | None] = mapped_column(Float)                              # X position of the vehicle
    pos_y: Mapped[float | None] = mapped_column(Float)                              # Y position of the vehicle
    pos_z: Mapped[float | None] = mapped_column(Float)                              # Z position of the vehicle
    damage: Mapped[float | None] = mapped_column(Float)                             # damage value between 0.0 and 1.0
    hitpoint_json: Mapped[str | None] = mapped_column(Text)                         # available hitpoints and their damage values
    # discovered: Mapped[float | None] = mapped_column(Float)                       # only available for enemy vehicles
    # group_display_name: Mapped[str | None] = mapped_column(String)                # display_name ???

Index("ix_vehicles_snapshot_side_group", Vehicle.snapshot_id, Vehicle.side, Vehicle.groupname)

class UnitAmmo(Base):
    __tablename__ = "units_ammo"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    unitname: Mapped[str] = mapped_column(String, primary_key=True)

    ammo_key: Mapped[str] = mapped_column(String, primary_key=True)                 # normalized identifier (class/magazine/weapon/...)
    count: Mapped[int | None] = mapped_column(Integer)                              # ammo count (nullable if unknown)
    raw_json: Mapped[str | None] = mapped_column(Text)                              # original ammo item json (for audit/debug)


Index("ix_units_ammo_snapshot_side_key", UnitAmmo.snapshot_id, UnitAmmo.side, UnitAmmo.ammo_key)
Index("ix_units_ammo_snapshot_side_unit", UnitAmmo.snapshot_id, UnitAmmo.side, UnitAmmo.unitname)


class VehicleAmmo(Base):
    __tablename__ = "vehicles_ammo"
    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    vehiclename: Mapped[str] = mapped_column(String, primary_key=True)

    ammo_key: Mapped[str] = mapped_column(String, primary_key=True)                 # normalized identifier (class/magazine/weapon/...)
    count: Mapped[int | None] = mapped_column(Integer)                              # ammo count (nullable if unknown)
    raw_json: Mapped[str | None] = mapped_column(Text)                              # original ammo item json (for audit/debug)


Index("ix_vehicles_ammo_snapshot_side_key", VehicleAmmo.snapshot_id, VehicleAmmo.side, VehicleAmmo.ammo_key)
Index("ix_vehicles_ammo_snapshot_side_vehicle", VehicleAmmo.snapshot_id, VehicleAmmo.side, VehicleAmmo.vehiclename)