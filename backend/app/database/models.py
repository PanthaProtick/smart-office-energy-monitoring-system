import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class DeviceType(str, enum.Enum):
    FAN = "Fan"
    LIGHT = "Light"


class Room(Base):
    __tablename__ = "Room"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    device_count = Column(Integer, nullable=False)

    # Timestamp of when every device in this room most recently became
    # active at the same time. Reset to None as soon as any device in the
    # room turns off. Used by AlertEngine.check_room_active_duration to
    # detect a room that has been fully active for 2+ hours.
    all_active_since = Column(DateTime, nullable=True)

    devices = relationship(
        "Device",
        back_populates="room",
        cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "Device"

    id = Column(Integer, primary_key=True, index=True)

    room_id = Column(
        Integer,
        ForeignKey("Room.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(String, nullable=False)

    type = Column(Enum(DeviceType), nullable=False)

    power_rating = Column(Float, nullable=False)

    is_active = Column(Boolean, default=False, nullable=False)

    last_updated = Column(DateTime, nullable=False)

    room = relationship(
        "Room",
        back_populates="devices"
    )

    logs = relationship(
        "DeviceLog",
        back_populates="device",
        cascade="all, delete-orphan"
    )


class DeviceLog(Base):
    __tablename__ = "DeviceLog"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(
        Integer,
        ForeignKey("Device.id", ondelete="CASCADE"),
        nullable=False
    )
    is_active = Column(Boolean, nullable=False)
    timestamp = Column(DateTime, nullable=False)

    device = relationship(
        "Device",
        back_populates="logs"
    )


class PowerLog(Base):
    __tablename__ = "PowerLog"

    id = Column(Integer, primary_key=True, index=True)
    total_power = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class AlertRule(str, enum.Enum):
    POWER_EXCEEDED = "power_exceeded"
    ROOM_COMPLETELY_ACTIVE = "room_completely_active"
    DEVICES_AFTER_HOURS = "devices_after_hours"
    HIGH_POWER_SUSTAINED = "high_power_sustained"


class Alert(Base):
    __tablename__ = "Alert"

    id = Column(Integer, primary_key=True, index=True)
    rule = Column(Enum(AlertRule), nullable=False)
    status = Column(Enum(AlertStatus), default=AlertStatus.ACTIVE, nullable=False)
    message = Column(String, nullable=False)
    triggered_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    context = Column(String, nullable=True)
