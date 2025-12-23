"""
Pydantic schemas для валідації request/response
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal, Dict
from datetime import datetime


# ============================================
# USER SCHEMAS
# ============================================

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    is_active: bool
    is_admin: bool
    
    class Config:
        from_attributes = True


# ============================================
# ROOM SCHEMAS
# ============================================

class RoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    floor: Optional[int] = None
    area: Optional[float] = Field(None, gt=0)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    floor: Optional[int] = None
    area: Optional[float] = Field(None, gt=0)


class RoomResponse(RoomBase):
    id: int
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# SENSOR SCHEMAS
# ============================================

class SensorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    device_id: str
    sensor_type: Literal["temperature", "humidity", "combined"]


class SensorCreate(SensorBase):
    room_id: int


class SensorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[Literal["active", "inactive", "error"]] = None


class SensorResponse(SensorBase):
    id: int
    room_id: int
    status: str
    last_online: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# SENSOR READING SCHEMAS
# ============================================

class SensorReadingBase(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = Field(None, ge=0, le=100)


class SensorReadingCreate(SensorReadingBase):
    sensor_id: int
    timestamp: Optional[datetime] = None


class SensorReadingResponse(SensorReadingBase):
    id: int
    sensor_id: int
    timestamp: datetime
    is_anomaly: bool
    
    class Config:
        from_attributes = True


# ============================================
# CLIMATE DEVICE SCHEMAS
# ============================================

class ClimateDeviceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    device_id: str
    device_type: Literal["air_conditioner", "heater", "humidifier", "dehumidifier"]
    power_consumption: Optional[float] = Field(None, ge=0)


class ClimateDeviceCreate(ClimateDeviceBase):
    room_id: int


class ClimateDeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[Literal["on", "off", "error"]] = None
    power_consumption: Optional[float] = Field(None, ge=0)


class ClimateDeviceResponse(ClimateDeviceBase):
    id: int
    room_id: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# DEVICE COMMAND SCHEMAS
# ============================================

class DeviceCommandCreate(BaseModel):
    command: Literal["turn_on", "turn_off", "set_temperature", "set_humidity"]
    parameters: Optional[dict] = None


class DeviceCommandResponse(BaseModel):
    id: int
    device_id: int
    command: str
    parameters: Optional[dict]
    issued_by: int
    issued_at: datetime
    executed: bool
    executed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============================================
# CLIMATE THRESHOLD SCHEMAS
# ============================================

class ClimateThresholdBase(BaseModel):
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    min_humidity: Optional[float] = Field(None, ge=0, le=100)
    max_humidity: Optional[float] = Field(None, ge=0, le=100)
    auto_control_enabled: bool = False


class ClimateThresholdCreate(ClimateThresholdBase):
    room_id: int


class ClimateThresholdUpdate(ClimateThresholdBase):
    pass


class ClimateThresholdResponse(ClimateThresholdBase):
    id: int
    room_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============================================
# ALERT SCHEMAS
# ============================================

class AlertResponse(BaseModel):
    id: int
    room_id: int
    alert_type: str
    message: str
    severity: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class AlertCreate(BaseModel):
    """Схема для створення Alert"""
    room_id: int
    alert_type: Literal[
        "temperature_high",
        "temperature_low", 
        "humidity_high",
        "humidity_low",
        "device_error"
    ]
    message: str = Field(..., min_length=1, max_length=500)
    severity: Literal["info", "warning", "critical"] = "warning"
    
# ============================================
# DEVICE LOG SCHEMAS
# ============================================

class DeviceLogCreate(BaseModel):
    device_id: int
    device_type: str = Field(..., pattern="^(sensor|climate_device)$")
    log_level: str = "info"
    message: str
    log_metadata: Optional[dict] = None


class DeviceLogResponse(BaseModel):
    id: int
    device_id: int
    device_type: str
    log_level: str
    message: str
    log_metadata: Optional[dict]
    timestamp: datetime
    
    class Config:
        from_attributes = True


# ============================================
# AUTH SCHEMAS
# ============================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    """Схема для зміни паролю"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="Новий пароль (мінімум 8 символів)")


class SensorReadingInput(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "temperature": 28.5,
                "humidity": 65.0,
                "timestamp": "2024-12-23T12:00:00"
            }
        }


class SensorProcessingResponse(BaseModel):
    success: bool
    reading_id: int
    is_anomaly: bool
    commands_executed: int
    alerts_created: int
    threshold_check: bool
    details: Optional[Dict] = None