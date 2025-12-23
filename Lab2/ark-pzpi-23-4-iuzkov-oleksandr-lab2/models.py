"""
SQLAlchemy Models для системи моніторингу клімату
Відповідають структурі PostgreSQL бази даних
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, CheckConstraint, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# Enum типи для обмеження значень
class SensorType(str, enum.Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    COMBINED = "combined"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ClimateDeviceType(str, enum.Enum):
    AIR_CONDITIONER = "air_conditioner"
    HEATER = "heater"
    HUMIDIFIER = "humidifier"
    DEHUMIDIFIER = "dehumidifier"


class DeviceCommandType(str, enum.Enum):
    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    SET_TEMPERATURE = "set_temperature"
    SET_HUMIDITY = "set_humidity"


class AlertType(str, enum.Enum):
    TEMPERATURE_HIGH = "temperature_high"
    TEMPERATURE_LOW = "temperature_low"
    HUMIDITY_HIGH = "humidity_high"
    HUMIDITY_LOW = "humidity_low"
    DEVICE_ERROR = "device_error"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class LogLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ============================================
# MODELS (Моделі SQLAlchemy)
# ============================================

class User(Base):
    __tablename__ = "user"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(50))
    last_name = Column(String(50))
    phone_number = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    rooms = relationship("Room", back_populates="user", cascade="all, delete-orphan")
    device_commands = relationship("DeviceCommand", back_populates="user", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "room"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    floor = Column(Integer)
    area = Column(Float)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="rooms")
    sensors = relationship("Sensor", back_populates="room", cascade="all, delete-orphan")
    climate_devices = relationship("ClimateDevice", back_populates="room", cascade="all, delete-orphan")
    climate_threshold = relationship("ClimateThreshold", back_populates="room", uselist=False, cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="room", cascade="all, delete-orphan")


class Sensor(Base):
    __tablename__ = "sensor"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_id = Column(String(100), unique=True, nullable=False)
    room_id = Column(Integer, ForeignKey("room.id", ondelete="CASCADE"), nullable=False)
    sensor_type = Column(String(20), nullable=False)  # Змінено на String замість Enum
    status = Column(String(20), default="active")  # Змінено на String замість Enum
    last_online = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    room = relationship("Room", back_populates="sensors")
    sensor_readings = relationship("SensorReading", back_populates="sensor", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_reading"
    
    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensor.id", ondelete="CASCADE"), nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_anomaly = Column(Boolean, default=False)
    
    # Relationships
    sensor = relationship("Sensor", back_populates="sensor_readings")


class ClimateDevice(Base):
    __tablename__ = "climate_device"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_id = Column(String(100), unique=True, nullable=False)
    room_id = Column(Integer, ForeignKey("room.id", ondelete="CASCADE"), nullable=False)
    device_type = Column(String(50), nullable=False)  # Змінено на String
    status = Column(String(20), default="off")  # Змінено на String
    power_consumption = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    room = relationship("Room", back_populates="climate_devices")
    device_commands = relationship("DeviceCommand", back_populates="device", cascade="all, delete-orphan")


class DeviceCommand(Base):
    __tablename__ = "device_command"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("climate_device.id", ondelete="CASCADE"), nullable=False)
    command = Column(String(50), nullable=False)  # Змінено на String
    parameters = Column(JSON)
    issued_by = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    executed = Column(Boolean, default=False)
    executed_at = Column(DateTime(timezone=True))
    
    # Relationships
    device = relationship("ClimateDevice", back_populates="device_commands")
    user = relationship("User", back_populates="device_commands")


class ClimateThreshold(Base):
    __tablename__ = "climate_threshold"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("room.id", ondelete="CASCADE"), unique=True, nullable=False)
    min_temperature = Column(Float)
    max_temperature = Column(Float)
    min_humidity = Column(Float)
    max_humidity = Column(Float)
    auto_control_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    room = relationship("Room", back_populates="climate_threshold")


class Alert(Base):
    __tablename__ = "alert"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("room.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)  # Змінено на String
    message = Column(String(500), nullable=False)
    severity = Column(String(20), default="info")  # Змінено на String
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    room = relationship("Room", back_populates="alerts")


class DeviceLog(Base):
    __tablename__ = "device_log"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False)
    device_type = Column(String(20), nullable=False)  # 'sensor' or 'climate_device'
    log_level = Column(Enum(LogLevel), default=LogLevel.INFO)
    message = Column(String(1000), nullable=False)
    log_metadata = Column("metadata", JSON)  # Перейменовано в Python, але в БД залишається "metadata"
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        CheckConstraint("device_type IN ('sensor', 'climate_device')", name="check_device_type"),
    )