"""
Функції адміністрування серверної частини системи
Включає управління даними, резервне копіювання, експорт/імпорт, логування
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import csv
import io

from app import models


# ============================================
# УПРАВЛІННЯ КОРИСТУВАЧАМИ
# ============================================

class UserManagement:
    """Адміністративні функції для управління користувачами"""
    
    @staticmethod
    def get_all_users(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[models.User]:
        """Отримати список всіх користувачів системи"""
        query = db.query(models.User)
        
        if is_active is not None:
            query = query.filter(models.User.is_active == is_active)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_user_statistics(db: Session) -> Dict:
        """Отримати статистику по користувачам"""
        total_users = db.query(func.count(models.User.id)).scalar()
        active_users = db.query(func.count(models.User.id)).filter(
            models.User.is_active == True
        ).scalar()
        
        # Користувачі зареєстровані за останні 30 днів
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        new_users = db.query(func.count(models.User.id)).filter(
            models.User.created_at >= cutoff_date
        ).scalar()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "new_users_last_30_days": new_users
        }
    
    @staticmethod
    def deactivate_user(db: Session, user_id: int) -> Dict:
        """Деактивувати користувача"""
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        user.is_active = False
        db.commit()
        
        return {
            "success": True,
            "message": f"User {user.username} deactivated"
        }
    
    @staticmethod
    def activate_user(db: Session, user_id: int) -> Dict:
        """Активувати користувача"""
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        user.is_active = True
        db.commit()
        
        return {
            "success": True,
            "message": f"User {user.username} activated"
        }
    
    @staticmethod
    def delete_user_data(db: Session, user_id: int) -> Dict:
        """
        Видалити всі дані користувача (GDPR compliance)
        CASCADE видалить всі повʼязані записи
        """
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        username = user.username
        
        db.delete(user)
        db.commit()
        
        return {
            "success": True,
            "message": f"User {username} and all associated data deleted"
        }


# ============================================
# УПРАВЛІННЯ СИСТЕМНИМИ ДАНИМИ
# ============================================

class DataManagement:
    """Адміністративні функції для управління даними системи"""
    
    @staticmethod
    def get_system_statistics(db: Session) -> Dict:
        """Отримати загальну статистику системи"""
        return {
            "users": {
                "total": db.query(func.count(models.User.id)).scalar(),
                "active": db.query(func.count(models.User.id)).filter(
                    models.User.is_active == True
                ).scalar()
            },
            "rooms": db.query(func.count(models.Room.id)).scalar(),
            "sensors": {
                "total": db.query(func.count(models.Sensor.id)).scalar(),
                "active": db.query(func.count(models.Sensor.id)).filter(
                    models.Sensor.status == "active"
                ).scalar()
            },
            "climate_devices": {
                "total": db.query(func.count(models.ClimateDevice.id)).scalar(),
                "on": db.query(func.count(models.ClimateDevice.id)).filter(
                    models.ClimateDevice.status == "on"
                ).scalar()
            },
            "sensor_readings": db.query(func.count(models.SensorReading.id)).scalar(),
            "alerts": {
                "total": db.query(func.count(models.Alert.id)).scalar(),
                "unread": db.query(func.count(models.Alert.id)).filter(
                    models.Alert.is_read == False
                ).scalar()
            }
        }
    
    @staticmethod
    def cleanup_old_data(
        db: Session,
        days_to_keep: int = 90
    ) -> Dict:
        """
        Очистити старі дані для оптимізації БД
        Видаляє показники сенсорів та логи старші за вказану кількість днів
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Видалити старі показники сенсорів
        deleted_readings = db.query(models.SensorReading).filter(
            models.SensorReading.timestamp < cutoff_date
        ).delete()
        
        # Видалити старі логи пристроїв
        deleted_logs = db.query(models.DeviceLog).filter(
            models.DeviceLog.timestamp < cutoff_date
        ).delete()
        
        # Видалити прочитані alerts старші 30 днів
        alert_cutoff = datetime.utcnow() - timedelta(days=30)
        deleted_alerts = db.query(models.Alert).filter(
            and_(
                models.Alert.created_at < alert_cutoff,
                models.Alert.is_read == True
            )
        ).delete()
        
        db.commit()
        
        return {
            "success": True,
            "deleted_sensor_readings": deleted_readings,
            "deleted_device_logs": deleted_logs,
            "deleted_alerts": deleted_alerts,
            "cutoff_date": cutoff_date.isoformat()
        }
    
    @staticmethod
    def get_database_size_info(db: Session) -> Dict:
        """Отримати інформацію про розмір даних у БД"""
        return {
            "sensor_readings_count": db.query(func.count(models.SensorReading.id)).scalar(),
            "device_logs_count": db.query(func.count(models.DeviceLog.id)).scalar(),
            "alerts_count": db.query(func.count(models.Alert.id)).scalar(),
            "device_commands_count": db.query(func.count(models.DeviceCommand.id)).scalar()
        }


# ============================================
# ЕКСПОРТ ДАНИХ
# ============================================

class DataExport:
    """Функції для експорту даних системи"""
    
    @staticmethod
    def export_sensor_data_to_csv(
        db: Session,
        room_id: Optional[int] = None,
        sensor_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """
        Експортувати дані сенсорів у CSV формат
        
        Returns:
            CSV string
        """
        query = db.query(models.SensorReading).join(models.Sensor)
        
        if room_id:
            query = query.filter(models.Sensor.room_id == room_id)
        
        if sensor_id:
            query = query.filter(models.SensorReading.sensor_id == sensor_id)
        
        if start_date:
            query = query.filter(models.SensorReading.timestamp >= start_date)
        
        if end_date:
            query = query.filter(models.SensorReading.timestamp <= end_date)
        
        readings = query.all()
        
        # Створити CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'reading_id', 'sensor_id', 'sensor_name', 'room_id',
            'temperature', 'humidity', 'timestamp', 'is_anomaly'
        ])
        
        # Data
        for reading in readings:
            writer.writerow([
                reading.id,
                reading.sensor_id,
                reading.sensor.name,
                reading.sensor.room_id,
                reading.temperature,
                reading.humidity,
                reading.timestamp.isoformat(),
                reading.is_anomaly
            ])
        
        # Додати BOM для правильного відображення UTF-8 в Excel
        csv_content = '\ufeff' + output.getvalue()
        return csv_content
        
    @staticmethod
    def export_system_configuration(db: Session) -> Dict:
        """
        Експортувати конфігурацію системи у JSON
        Включає налаштування приміщень, порогових значень, пристроїв
        """
        rooms = db.query(models.Room).all()
        
        config = {
            "export_date": datetime.utcnow().isoformat(),
            "rooms": []
        }
        
        for room in rooms:
            room_data = {
                "id": room.id,
                "name": room.name,
                "description": room.description,
                "floor": room.floor,
                "area": room.area,
                "sensors": [],
                "climate_devices": [],
                "threshold": None
            }
            
            # Сенсори
            for sensor in room.sensors:
                room_data["sensors"].append({
                    "id": sensor.id,
                    "name": sensor.name,
                    "device_id": sensor.device_id,
                    "sensor_type": sensor.sensor_type
                })
            
            # Кліматичні пристрої
            for device in room.climate_devices:
                room_data["climate_devices"].append({
                    "id": device.id,
                    "name": device.name,
                    "device_id": device.device_id,
                    "device_type": device.device_type,
                    "power_consumption": device.power_consumption
                })
            
            # Порогові значення
            if room.climate_threshold:
                t = room.climate_threshold
                room_data["threshold"] = {
                    "min_temperature": t.min_temperature,
                    "max_temperature": t.max_temperature,
                    "min_humidity": t.min_humidity,
                    "max_humidity": t.max_humidity,
                    "auto_control_enabled": t.auto_control_enabled
                }
            
            config["rooms"].append(room_data)
        
        return config
    
    @staticmethod
    def export_alerts(
        db: Session,
        room_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        severity: Optional[str] = None
    ) -> List[Dict]:
        """Експортувати історію alerts"""
        query = db.query(models.Alert)
        
        if room_id:
            query = query.filter(models.Alert.room_id == room_id)
        
        if start_date:
            query = query.filter(models.Alert.created_at >= start_date)
        
        if end_date:
            query = query.filter(models.Alert.created_at <= end_date)
        
        if severity:
            query = query.filter(models.Alert.severity == severity)
        
        alerts = query.order_by(models.Alert.created_at.desc()).all()
        
        return [
            {
                "id": alert.id,
                "room_id": alert.room_id,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "severity": alert.severity,
                "is_read": alert.is_read,
                "created_at": alert.created_at.isoformat()
            }
            for alert in alerts
        ]


# ============================================
# ІМПОРТ ДАНИХ
# ============================================

class DataImport:
    """Функції для імпорту даних у систему"""
    
    @staticmethod
    def import_system_configuration(
        db: Session,
        user_id: int,
        config_data: Dict
    ) -> Dict:
        """
        Імпортувати конфігурацію системи з JSON
        
        УВАГА: Створює нові записи, не оновлює існуючі
        """
        created_rooms = 0
        created_sensors = 0
        created_devices = 0
        created_thresholds = 0
        
        try:
            for room_data in config_data.get("rooms", []):
                # Створити приміщення
                room = models.Room(
                    name=room_data["name"],
                    description=room_data.get("description"),
                    floor=room_data.get("floor"),
                    area=room_data.get("area"),
                    user_id=user_id
                )
                db.add(room)
                db.flush()  # Отримати ID нового приміщення
                created_rooms += 1
                
                # Створити сенсори
                for sensor_data in room_data.get("sensors", []):
                    sensor = models.Sensor(
                        name=sensor_data["name"],
                        device_id=f"{sensor_data['device_id']}_imported_{datetime.utcnow().timestamp()}",
                        room_id=room.id,
                        sensor_type=sensor_data["sensor_type"]
                    )
                    db.add(sensor)
                    created_sensors += 1
                
                # Створити кліматичні пристрої
                for device_data in room_data.get("climate_devices", []):
                    device = models.ClimateDevice(
                        name=device_data["name"],
                        device_id=f"{device_data['device_id']}_imported_{datetime.utcnow().timestamp()}",
                        room_id=room.id,
                        device_type=device_data["device_type"],
                        power_consumption=device_data.get("power_consumption")
                    )
                    db.add(device)
                    created_devices += 1
                
                # Створити порогові значення
                threshold_data = room_data.get("threshold")
                if threshold_data:
                    threshold = models.ClimateThreshold(
                        room_id=room.id,
                        min_temperature=threshold_data.get("min_temperature"),
                        max_temperature=threshold_data.get("max_temperature"),
                        min_humidity=threshold_data.get("min_humidity"),
                        max_humidity=threshold_data.get("max_humidity"),
                        auto_control_enabled=threshold_data.get("auto_control_enabled", False)
                    )
                    db.add(threshold)
                    created_thresholds += 1
            
            db.commit()
            
            return {
                "success": True,
                "created_rooms": created_rooms,
                "created_sensors": created_sensors,
                "created_devices": created_devices,
                "created_thresholds": created_thresholds
            }
        
        except Exception as e:
            db.rollback()
            return {
                "success": False,
                "error": str(e)
            }


# ============================================
# ЛОГУВАННЯ ТА МОНІТОРИНГ
# ============================================

class SystemLogging:
    """Функції для логування подій системи"""
    
    @staticmethod
    def log_device_event(
        db: Session,
        device_id: int,
        device_type: str,
        log_level: str,
        message: str,
        metadata: Optional[Dict] = None
    ) -> models.DeviceLog:
        """Записати подію пристрою в лог"""
        log = models.DeviceLog(
            device_id=device_id,
            device_type=device_type,
            log_level=log_level,
            message=message,
            log_metadata=metadata
        )
        
        db.add(log)
        db.commit()
        db.refresh(log)
        
        return log
    
    @staticmethod
    def get_system_logs(
        db: Session,
        log_level: Optional[str] = None,
        device_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[models.DeviceLog]:
        """Отримати системні логи"""
        query = db.query(models.DeviceLog)
        
        if log_level:
            query = query.filter(models.DeviceLog.log_level == log_level)
        
        if device_type:
            query = query.filter(models.DeviceLog.device_type == device_type)
        
        if start_date:
            query = query.filter(models.DeviceLog.timestamp >= start_date)
        
        return query.order_by(models.DeviceLog.timestamp.desc()).limit(limit).all()
    
    @staticmethod
    def get_error_summary(
        db: Session,
        hours: int = 24
    ) -> Dict:
        """Отримати статистику помилок за вказаний період"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        errors = db.query(models.DeviceLog).filter(
            and_(
                models.DeviceLog.log_level == "error",
                models.DeviceLog.timestamp >= cutoff_time
            )
        ).all()
        
        # Групувати за типом пристрою
        by_device_type = {}
        for error in errors:
            dtype = error.device_type
            if dtype not in by_device_type:
                by_device_type[dtype] = 0
            by_device_type[dtype] += 1
        
        return {
            "period_hours": hours,
            "total_errors": len(errors),
            "errors_by_device_type": by_device_type,
            "recent_errors": [
                {
                    "device_id": e.device_id,
                    "device_type": e.device_type,
                    "message": e.message,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in errors[:10]  # Останні 10 помилок
            ]
        }