from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, Text, Index


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    __tablename__ = "snapshots"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    sourcefile: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    datetime: Mapped[str | None] = mapped_column(String)          # ISO8601
    rawjson: Mapped[str] = mapped_column(Text, nullable=False)


class Group(Base):
    __tablename__ = "groups"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    company: Mapped[str] = mapped_column(String, primary_key=True)
    platoon: Mapped[str] = mapped_column(String, primary_key=True)
    squad: Mapped[str] = mapped_column(String, primary_key=True)
    groupname: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    leaderposx: Mapped[float | None] = mapped_column(Float)
    leaderposy: Mapped[float | None] = mapped_column(Float)
    leaderposz: Mapped[float | None] = mapped_column(Float)
    waypointposx: Mapped[float | None] = mapped_column(Float)
    waypointposy: Mapped[float | None] = mapped_column(Float)


Index("ix_groups_snapshot_side_group", Group.snapshotid, Group.side, Group.groupname)


class Unit(Base):
    __tablename__ = "units"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    unitname: Mapped[str] = mapped_column(String, primary_key=True)
    groupname: Mapped[str] = mapped_column(String)
    unittype: Mapped[str | None] = mapped_column(String)
    posx: Mapped[float | None] = mapped_column(Float)
    posy: Mapped[float | None] = mapped_column(Float)
    posz: Mapped[float | None] = mapped_column(Float)
    damage: Mapped[float | None] = mapped_column(Float)
    objectparent: Mapped[str | None] = mapped_column(String)


Index("ix_units_snapshot_side_group", Unit.snapshotid, Unit.side, Unit.groupname)


class Vehicle(Base):
    __tablename__ = "vehicles"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    vehiclename: Mapped[str] = mapped_column(String, primary_key=True)
    groupname: Mapped[str] = mapped_column(String)
    vehicletype: Mapped[str | None] = mapped_column(String)
    posx: Mapped[float | None] = mapped_column(Float)
    posy: Mapped[float | None] = mapped_column(Float)
    posz: Mapped[float | None] = mapped_column(Float)             
    damage: Mapped[float | None] = mapped_column(Float)
    hitpointjson: Mapped[str | None] = mapped_column(Text)        


Index("ix_vehicles_snapshot_side_group", Vehicle.snapshotid, Vehicle.side, Vehicle.groupname)


class UnitAmmo(Base):
    __tablename__ = "units_ammo"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    unitname: Mapped[str] = mapped_column(String, primary_key=True)       
    ammotype: Mapped[str] = mapped_column(String, primary_key=True)
    count: Mapped[int | None] = mapped_column(Integer)


Index("ix_units_ammo_snapshot_side_key", UnitAmmo.snapshotid, UnitAmmo.side, UnitAmmo.ammotype)
Index("ix_units_ammo_snapshot_side_unit", UnitAmmo.snapshotid, UnitAmmo.side, UnitAmmo.unitname)


class VehicleAmmo(Base):
    __tablename__ = "vehicles_ammo"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    vehiclename: Mapped[str] = mapped_column(String, primary_key=True)       
    ammotype: Mapped[str] = mapped_column(String, primary_key=True)
    count: Mapped[int | None] = mapped_column(Integer)


Index("ix_vehicles_ammo_snapshot_side_key", VehicleAmmo.snapshotid, VehicleAmmo.side, VehicleAmmo.ammotype)
Index("ix_vehicles_ammo_snapshot_side_vehicle", VehicleAmmo.snapshotid, VehicleAmmo.side, VehicleAmmo.vehiclename)


class VehicleHitpoint(Base):
    __tablename__ = "vehicles_hitpoints"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    vehiclename: Mapped[str] = mapped_column(String, primary_key=True)       # vehiclename
    hitpoint: Mapped[str] = mapped_column(String, primary_key=True)
    damage: Mapped[float | None] = mapped_column(Float)


Index("ix_vhp_snapshot_side_vehicle", VehicleHitpoint.snapshotid, VehicleHitpoint.side, VehicleHitpoint.vehiclename)
Index("ix_vhp_snapshot_side_hitpoint", VehicleHitpoint.snapshotid, VehicleHitpoint.side, VehicleHitpoint.hitpoint)


class EventEDC(Base):
    __tablename__ = "event_knowsaboutchanged"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)          
    side: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyname: Mapped[str] = mapped_column(String)
    groupname: Mapped[str | None] = mapped_column(String)
    targetunit: Mapped[str | None] = mapped_column(String)
    newknowsabout: Mapped[float | None] = mapped_column(Float)
    oldknowsabout: Mapped[float | None] = mapped_column(Float)
    paramsjson: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_eventedc_snapshot_side_time", EventEDC.snapshotid, EventEDC.side, EventEDC.datetime)


class EventF(Base):
    __tablename__ = "event_fired"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyname: Mapped[str] = mapped_column(String)
    unit: Mapped[str | None] = mapped_column(String)               
    weapon: Mapped[str | None] = mapped_column(String)
    muzzle: Mapped[str | None] = mapped_column(String)
    # mode: Mapped[str | None] = mapped_column(String)
    # ammo: Mapped[str | None] = mapped_column(String)
    ammotype: Mapped[str | None] = mapped_column(String) # magazine
    # projectile: Mapped[str | None] = mapped_column(String)
    gunner: Mapped[str | None] = mapped_column(String)                
    paramsjson: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_eventf_snapshot_side_time", EventF.snapshotid, EventF.side, EventF.datetime)


class EventD(Base):
    __tablename__ = "event_dammaged"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyname: Mapped[str] = mapped_column(String)
    targetunit: Mapped[str | None] = mapped_column(String)                
    # hitselection: Mapped[str | None] = mapped_column(String)
    damage: Mapped[float | None] = mapped_column(Float)
    # hitpartindex: Mapped[int | None] = mapped_column(Integer)
    hitpoint: Mapped[str | None] = mapped_column(String)       
    shooter: Mapped[str | None] = mapped_column(String)                   
    # projecttile: Mapped[str | None] = mapped_column(String)
    paramsjson: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_eventd_snapshot_side_time", EventD.snapshotid, EventD.side, EventD.datetime)


class EventK(Base):
    __tablename__ = "event_killed"
    snapshotid: Mapped[str] = mapped_column(String, primary_key=True)
    datetime: Mapped[str | None] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyname: Mapped[str] = mapped_column(String)
    targetunit: Mapped[str | None] = mapped_column(String)
    killer: Mapped[str | None] = mapped_column(String)
    instigator: Mapped[str | None] = mapped_column(String)
    # useeffects: Mapped[int | None] = mapped_column(Integer)
    paramsjson: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_eventk_snapshot_side_time", EventK.snapshotid, EventK.side, EventK.datetime)