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