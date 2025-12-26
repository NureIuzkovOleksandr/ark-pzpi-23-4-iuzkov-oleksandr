"""
Розширена бізнес-логіка для системи моніторингу температури та вологості
Реалізація всіх процесів з діаграм: 
- Обробка показників сенсорів (Sequence Diagram 1)
- Аналітика з кешуванням (Sequence Diagram 2)
- Автокерування (Flowchart 1)
- Валідація та виявлення аномалій (Flowchart 2)
- Управління користувачами (Flowchart 3)
- Генерація аналітики (Flowchart 4)
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc, or_
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
import statistics
import json
import hashlib

from . import models, schemas


# ============================================
# ОБРОБКА ПОКАЗНИКІВ СЕНСОРІВ (Sequence Diagram 1)
# ============================================

class SensorReadingProcessor:
    """
    Процес обробки показників сенсора згідно Sequence Diagram 1:
    Сенсор -> API -> Бізнес-логіка -> База даних -> Кліматичний пристрій
    """
    
    @staticmethod
    def process_reading(
        db: Session,
        sensor_id: int,
        temperature: Optional[float],
        humidity: Optional[float],
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Головний метод обробки показника сенсора
        
        Кроки:
        1. POST /sensor-readings
        2. обробити_показник(дані)
        3. отримати_пороги(room_id)
        4. перевірити_умови()
        5. Alt: Якщо температура поза межами:
           - створити_команду()
           - надіслати_команду(device_id, дія)
           - створити_сповіщення()
        6. Повернути результат
        """
        
        # Крок 1: Отримати сенсор
        sensor = db.query(models.Sensor).filter(
            models.Sensor.id == sensor_id
        ).first()
        
        if not sensor:
            return {
                "success": False,
                "error": "Sensor not found",
                "status_code": 404
            }
        
        # Крок 2: Створити запис показника
        sensor_reading = models.SensorReading(
            sensor_id=sensor_id,
            temperature=temperature,
            humidity=humidity,
            timestamp=timestamp or datetime.utcnow()
        )
        
        # Крок 3: Отримати порогові значення для приміщення
        threshold = db.query(models.ClimateThreshold).filter(
            models.ClimateThreshold.room_id == sensor.room_id
        ).first()
        
        # Крок 4: Перевірити умови
        commands_created = []
        alerts_created = []
        
        if threshold:
            # Alt: Перевірка температури поза межами
            if temperature is not None:
                temp_result = SensorReadingProcessor._check_temperature_threshold(
                    db=db,
                    room_id=sensor.room_id,
                    temperature=temperature,
                    min_temp=threshold.min_temperature,
                    max_temp=threshold.max_temperature,
                    auto_control=threshold.auto_control_enabled
                )
                
                if temp_result["command"]:
                    commands_created.append(temp_result["command"])
                if temp_result["alert"]:
                    alerts_created.append(temp_result["alert"])
            
            # Alt: Перевірка вологості поза межами
            if humidity is not None:
                humid_result = SensorReadingProcessor._check_humidity_threshold(
                    db=db,
                    room_id=sensor.room_id,
                    humidity=humidity,
                    min_humid=threshold.min_humidity,
                    max_humid=threshold.max_humidity,
                    auto_control=threshold.auto_control_enabled
                )
                
                if humid_result["command"]:
                    commands_created.append(humid_result["command"])
                if humid_result["alert"]:
                    alerts_created.append(humid_result["alert"])
        
        # Виявлення аномалій
        is_anomaly = AnomalyDetector.detect_anomaly(
            db, sensor_id, temperature, humidity
        )
        sensor_reading.is_anomaly = is_anomaly
        
        # Зберегти показник
        db.add(sensor_reading)
        
        # Зберегти alerts
        for alert_data in alerts_created:
            alert = models.Alert(**alert_data)
            db.add(alert)
        
        # Оновити last_online сенсора
        sensor.last_online = datetime.utcnow()
        
        db.commit()
        db.refresh(sensor_reading)
        
        # Повернути результат (200 OK)
        return {
            "success": True,
            "status_code": 200,
            "reading_id": sensor_reading.id,
            "is_anomaly": is_anomaly,
            "commands_executed": len(commands_created),
            "alerts_created": len(alerts_created),
            "threshold_check": threshold is not None
        }
    
    @staticmethod
    def _check_temperature_threshold(
        db: Session,
        room_id: int,
        temperature: float,
        min_temp: Optional[float],
        max_temp: Optional[float],
        auto_control: bool
    ) -> Dict:
        """Перевірити поріг температури та створити команду"""
        result = {"command": None, "alert": None}
        
        # Температура поза межами?
        if max_temp and temperature > max_temp:
            # Створити сповіщення
            result["alert"] = {
                "room_id": room_id,
                "alert_type": "temperature_high",
                "message": f"Температура {temperature}°C перевищує максимум {max_temp}°C",
                "severity": "warning"
            }
            
            # Якщо автокерування увімкнено - створити команду
            if auto_control:
                command = SensorReadingProcessor._send_device_command(
                    db, room_id, "air_conditioner", "turn_on"
                )
                result["command"] = command
        
        elif min_temp and temperature < min_temp:
            result["alert"] = {
                "room_id": room_id,
                "alert_type": "temperature_low",
                "message": f"Температура {temperature}°C нижче мінімуму {min_temp}°C",
                "severity": "warning"
            }
            
            if auto_control:
                command = SensorReadingProcessor._send_device_command(
                    db, room_id, "heater", "turn_on"
                )
                result["command"] = command
        
        return result
    
    @staticmethod
    def _check_humidity_threshold(
        db: Session,
        room_id: int,
        humidity: float,
        min_humid: Optional[float],
        max_humid: Optional[float],
        auto_control: bool
    ) -> Dict:
        """Перевірити поріг вологості та створити команду"""
        result = {"command": None, "alert": None}
        
        if max_humid and humidity > max_humid:
            result["alert"] = {
                "room_id": room_id,
                "alert_type": "humidity_high",
                "message": f"Вологість {humidity}% перевищує максимум {max_humid}%",
                "severity": "info"
            }
            
            if auto_control:
                command = SensorReadingProcessor._send_device_command(
                    db, room_id, "dehumidifier", "turn_on"
                )
                result["command"] = command
        
        elif min_humid and humidity < min_humid:
            result["alert"] = {
                "room_id": room_id,
                "alert_type": "humidity_low",
                "message": f"Вологість {humidity}% нижче мінімуму {min_humid}%",
                "severity": "info"
            }
            
            if auto_control:
                command = SensorReadingProcessor._send_device_command(
                    db, room_id, "humidifier", "turn_on"
                )
                result["command"] = command
        
        return result
    
    @staticmethod
    def _send_device_command(
        db: Session,
        room_id: int,
        device_type: str,
        command: str
    ) -> Optional[Dict]:
        """
        Надіслати команду пристрою (device_id, дія)
        Повертає інформацію про виконану команду
        """
        device = db.query(models.ClimateDevice).filter(
            and_(
                models.ClimateDevice.room_id == room_id,
                models.ClimateDevice.device_type == device_type
            )
        ).first()
        
        if not device:
            return None
        
        # Оновити статус пристрою БЕЗ створення DeviceCommand
        # (бо issued_by є обов'язковим, а для автоматичних команд немає користувача)
        if command == "turn_on":
            device.status = "on"
        elif command == "turn_off":
            device.status = "off"
        
        return {
            "device_id": device.id,
            "device_type": device_type,
            "command": command,
            "status": "executed"
        }
    
@staticmethod
def _send_device_command(
    db: Session,
    room_id: int,
    device_type: str,
    command: str,
    issued_by_user_id: Optional[int] = None
) -> Optional[Dict]:
    """
    Надіслати команду пристрою (device_id, дія)
    Повертає інформацію про виконану команду
    """
    device = db.query(models.ClimateDevice).filter(
        and_(
            models.ClimateDevice.room_id == room_id,
            models.ClimateDevice.device_type == device_type
        )
    ).first()
    
    if not device:
        return None
    
    # Якщо issued_by не вказано, НЕ створюємо команду
    # Просто змінюємо статус пристрою
    if issued_by_user_id:
        try:
            device_command = models.DeviceCommand(
                device_id=device.id,
                command=command,
                issued_by=issued_by_user_id,
                parameters=None
            )
            db.add(device_command)
        except Exception as e:
            print(f"Warning: Could not create DeviceCommand: {e}")
    
    # Оновити статус пристрою
    if command == "turn_on":
        device.status = "on"
    elif command == "turn_off":
        device.status = "off"
    
    return {
        "device_id": device.id,
        "device_type": device_type,
        "command": command,
        "status": "executed"
    }


# ============================================
# АНАЛІТИКА З КЕШУВАННЯМ (Sequence Diagram 2)
# ============================================

class AnalyticsService:
    """
    Сервіс аналітики з кешуванням згідно Sequence Diagram 2:
    Користувач -> API -> Cache -> Бізнес-логіка -> База даних
    """
    
    # Простий in-memory cache (у продакшені використовувати Redis)
    _cache = {}
    _cache_ttl = 3600  # 1 година в секундах
    
    @staticmethod
    def get_analytics(
        db: Session,
        room_id: Optional[int] = None,
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        GET /analytics?period=7d
        
        Процес:
        1. перевірити_кеш(ключ)
        2. Alt: Дані в кеші -> повернути кешовані дані
        3. Alt: Даних немає в кеші:
           - згенерувати_аналітику()
           - запит_показників(період)
           - розрахувати_середнє()
           - знайти_мін_макс()
           - виявити_тренди()
           - зберегти(ключ, дані, ttl=1год)
        4. 200 OK + дані
        """
        
        # Крок 1: Створити ключ кешу
        cache_key = AnalyticsService._generate_cache_key(room_id, period_days)
        
        # Крок 2: Перевірити кеш
        cached_data = AnalyticsService._check_cache(cache_key)
        
        # Alt: Дані в кеші
        if cached_data:
            return {
                "success": True,
                "data": cached_data,
                "from_cache": True,
                "status_code": 200
            }
        
        # Alt: Даних немає в кеші - згенерувати аналітику
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        
        # Запит показників (період)
        query = db.query(models.SensorReading).join(models.Sensor)
        
        if room_id:
            query = query.filter(models.Sensor.room_id == room_id)
        
        readings = query.filter(
            models.SensorReading.timestamp >= cutoff_date
        ).all()
        
        if not readings:
            return {
                "success": False,
                "error": "No data for specified period",
                "status_code": 404
            }
        
        # Розрахувати середнє()
        temperatures = [r.temperature for r in readings if r.temperature is not None]
        humidities = [r.humidity for r in readings if r.humidity is not None]
        
        avg_temperature = statistics.mean(temperatures) if temperatures else None
        avg_humidity = statistics.mean(humidities) if humidities else None
        
        # Знайти мін/макс()
        min_temperature = min(temperatures) if temperatures else None
        max_temperature = max(temperatures) if temperatures else None
        min_humidity = min(humidities) if humidities else None
        max_humidity = max(humidities) if humidities else None
        
        # Виявити тренди()
        trends = AnalyticsService._detect_trends(readings)
        
        # Сформувати результат аналітики
        analytics_result = {
            "period_days": period_days,
            "room_id": room_id,
            "total_readings": len(readings),
            "temperature": {
                "average": round(avg_temperature, 2) if avg_temperature else None,
                "min": round(min_temperature, 2) if min_temperature else None,
                "max": round(max_temperature, 2) if max_temperature else None,
                "median": round(statistics.median(temperatures), 2) if temperatures else None
            },
            "humidity": {
                "average": round(avg_humidity, 2) if avg_humidity else None,
                "min": round(min_humidity, 2) if min_humidity else None,
                "max": round(max_humidity, 2) if max_humidity else None,
                "median": round(statistics.median(humidities), 2) if humidities else None
            },
            "trends": trends,
            "anomalies_count": sum(1 for r in readings if r.is_anomaly),
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Зберегти в кеш (ключ, дані, ttl=1год)
        AnalyticsService._save_to_cache(cache_key, analytics_result)
        
        return {
            "success": True,
            "data": analytics_result,
            "from_cache": False,
            "status_code": 200
        }
    
    @staticmethod
    def _generate_cache_key(room_id: Optional[int], period_days: int) -> str:
        """Згенерувати ключ для кешу"""
        key_parts = [
            "analytics",
            f"room_{room_id}" if room_id else "all_rooms",
            f"period_{period_days}d"
        ]
        return "_".join(key_parts)
    
    @staticmethod
    def _check_cache(cache_key: str) -> Optional[Dict]:
        """Перевірити кеш(ключ)"""
        if cache_key in AnalyticsService._cache:
            cached_item = AnalyticsService._cache[cache_key]
            
            # Перевірити чи не застарів кеш
            if datetime.utcnow().timestamp() - cached_item["timestamp"] < AnalyticsService._cache_ttl:
                return cached_item["data"]
            else:
                # Видалити застарілий запис
                del AnalyticsService._cache[cache_key]
        
        return None
    
    @staticmethod
    def _save_to_cache(cache_key: str, data: Dict):
        """Зберегти(ключ, дані, ttl=1год)"""
        AnalyticsService._cache[cache_key] = {
            "data": data,
            "timestamp": datetime.utcnow().timestamp()
        }
    
    @staticmethod
    def _detect_trends(readings: List[models.SensorReading]) -> Dict:
        """
        Виявити тренди()
        Простий аналіз: порівняння першої та другої половини періоду
        """
        if len(readings) < 10:
            return {"trend": "insufficient_data"}
        
        # Розділити на дві половини
        mid_point = len(readings) // 2
        first_half = readings[:mid_point]
        second_half = readings[mid_point:]
        
        # Температура
        temp_first = [r.temperature for r in first_half if r.temperature is not None]
        temp_second = [r.temperature for r in second_half if r.temperature is not None]
        
        temp_trend = "stable"
        if temp_first and temp_second:
            avg_first = statistics.mean(temp_first)
            avg_second = statistics.mean(temp_second)
            diff = avg_second - avg_first
            
            if diff > 1.0:
                temp_trend = "increasing"
            elif diff < -1.0:
                temp_trend = "decreasing"
        
        # Вологість
        humid_first = [r.humidity for r in first_half if r.humidity is not None]
        humid_second = [r.humidity for r in second_half if r.humidity is not None]
        
        humid_trend = "stable"
        if humid_first and humid_second:
            avg_first = statistics.mean(humid_first)
            avg_second = statistics.mean(humid_second)
            diff = avg_second - avg_first
            
            if diff > 5.0:
                humid_trend = "increasing"
            elif diff < -5.0:
                humid_trend = "decreasing"
        
        return {
            "temperature_trend": temp_trend,
            "humidity_trend": humid_trend
        }


# ============================================
# АВТОКЕРУВАННЯ (Flowchart 1)
# ============================================

class AutoControlFlow:
    """
    Процес автокерування згідно Flowchart 1:
    Початок -> Отримати дані сенсора -> Автокерування? -> 
    Температура OK? -> Вологість OK? -> Регулювати -> Кінець
    """
    
    @staticmethod
    def execute_auto_control(
        db: Session,
        sensor_reading_id: int
    ) -> Dict[str, Any]:
        """
        Виконати процес автокерування
        
        Flowchart:
        1. Початок
        2. Отримати дані сенсора
        3. Автокерування? -> Ні: Кінець
        4. Автокерування? -> Так: Температура OK?
        5. Температура OK? -> Ні: Регулювати температуру
        6. Температура OK? -> Так: Вологість OK?
        7. Вологість OK? -> Ні: Регулювати вологість
        8. Вологість OK? -> Так: Кінець
        9. Кінець
        """
        
        # Крок 2: Отримати дані сенсора
        reading = db.query(models.SensorReading).filter(
            models.SensorReading.id == sensor_reading_id
        ).first()
        
        if not reading:
            return {"success": False, "error": "Reading not found"}
        
        sensor = reading.sensor
        room_id = sensor.room_id
        
        # Крок 3: Автокерування?
        threshold = db.query(models.ClimateThreshold).filter(
            models.ClimateThreshold.room_id == room_id
        ).first()
        
        if not threshold or not threshold.auto_control_enabled:
            # Ні -> Кінець
            return {
                "success": True,
                "message": "Auto control disabled",
                "actions": []
            }
        
        actions = []
        
        # Крок 4: Так -> Температура OK?
        temp_ok = True
        if reading.temperature is not None:
            if threshold.min_temperature and reading.temperature < threshold.min_temperature:
                temp_ok = False
            if threshold.max_temperature and reading.temperature > threshold.max_temperature:
                temp_ok = False
        
        # Крок 5: Ні -> Регулювати температуру
        if not temp_ok:
            temp_action = AutoControlFlow._regulate_temperature(
                db, room_id, reading.temperature, threshold
            )
            actions.append(temp_action)
        
        # Крок 6: Вологість OK?
        humid_ok = True
        if reading.humidity is not None:
            if threshold.min_humidity and reading.humidity < threshold.min_humidity:
                humid_ok = False
            if threshold.max_humidity and reading.humidity > threshold.max_humidity:
                humid_ok = False
        
        # Крок 7: Ні -> Регулювати вологість
        if not humid_ok:
            humid_action = AutoControlFlow._regulate_humidity(
                db, room_id, reading.humidity, threshold
            )
            actions.append(humid_action)
        
        db.commit()
        
        # Крок 8/9: Кінець
        return {
            "success": True,
            "auto_control_enabled": True,
            "temperature_ok": temp_ok,
            "humidity_ok": humid_ok,
            "actions": actions
        }
    
    @staticmethod
    def _regulate_temperature(
        db: Session,
        room_id: int,
        temperature: float,
        threshold: models.ClimateThreshold
    ) -> Dict:
        """Регулювати температуру"""
        if temperature > threshold.max_temperature:
            # Охолодження
            device = db.query(models.ClimateDevice).filter(
                and_(
                    models.ClimateDevice.room_id == room_id,
                    models.ClimateDevice.device_type == "air_conditioner"
                )
            ).first()
            
            if device:
                device.status = "on"
                return {"action": "cooling", "device": device.name, "status": "on"}
        
        elif temperature < threshold.min_temperature:
            # Обігрів
            device = db.query(models.ClimateDevice).filter(
                and_(
                    models.ClimateDevice.room_id == room_id,
                    models.ClimateDevice.device_type == "heater"
                )
            ).first()
            
            if device:
                device.status = "on"
                return {"action": "heating", "device": device.name, "status": "on"}
        
        return {"action": "none", "reason": "device_not_found"}
    
    @staticmethod
    def _regulate_humidity(
        db: Session,
        room_id: int,
        humidity: float,
        threshold: models.ClimateThreshold
    ) -> Dict:
        """Регулювати вологість"""
        if humidity > threshold.max_humidity:
            # Осушення
            device = db.query(models.ClimateDevice).filter(
                and_(
                    models.ClimateDevice.room_id == room_id,
                    models.ClimateDevice.device_type == "dehumidifier"
                )
            ).first()
            
            if device:
                device.status = "on"
                return {"action": "dehumidifying", "device": device.name, "status": "on"}
        
        elif humidity < threshold.min_humidity:
            # Зволоження
            device = db.query(models.ClimateDevice).filter(
                and_(
                    models.ClimateDevice.room_id == room_id,
                    models.ClimateDevice.device_type == "humidifier"
                )
            ).first()
            
            if device:
                device.status = "on"
                return {"action": "humidifying", "device": device.name, "status": "on"}
        
        return {"action": "none", "reason": "device_not_found"}


# ============================================
# ВАЛІДАЦІЯ ТА ВИЯВЛЕННЯ АНОМАЛІЙ (Flowchart 2)
# ============================================

class DataValidationFlow:
    """
    Процес валідації даних згідно Flowchart 2:
    Початок -> Отримати дані -> Валідні? -> Розрахувати статистику ->
    Аномалія? -> Створити сповіщення -> Зберегти дані -> Кінець
    """
    
    @staticmethod
    def validate_and_process(
        db: Session,
        sensor_id: int,
        temperature: Optional[float],
        humidity: Optional[float]
    ) -> Dict[str, Any]:
        """
        Виконати валідацію та обробку даних
        
        Flowchart:
        1. Початок
        2. Отримати дані
        3. Валідні? -> Ні: Помилка пристрою -> Кінець
        4. Валідні? -> Так: Розрахувати статистику
        5. Аномалія? -> Так: Створити сповіщення
        6. Аномалія? -> Ні: Зберегти дані
        7. Зберегти дані -> Кінець
        """
        
        # Крок 3: Валідні?
        validation_result = DataValidationFlow._validate_data(temperature, humidity)
        
        if not validation_result["valid"]:
            # Ні -> Помилка пристрою -> Кінець
            return {
                "success": False,
                "error": "Device error",
                "details": validation_result["errors"],
                "status": "validation_failed"
            }
        
        # Крок 4: Так -> Розрахувати статистику
        stats = DataValidationFlow._calculate_statistics(
            db, sensor_id, temperature, humidity
        )
        
        # Крок 5: Аномалія?
        is_anomaly = AnomalyDetector.detect_anomaly(
            db, sensor_id, temperature, humidity
        )
        
        alert_created = None
        if is_anomaly:
            # Так -> Створити сповіщення
            sensor = db.query(models.Sensor).filter(
                models.Sensor.id == sensor_id
            ).first()
            
            if sensor:
                alert = models.Alert(
                    room_id=sensor.room_id,
                    alert_type="anomaly_detected",
                    message=f"Виявлено аномальні показники: T={temperature}°C, H={humidity}%",
                    severity="warning"
                )
                db.add(alert)
                alert_created = True
        
        # Крок 6: Зберегти дані
        reading = models.SensorReading(
            sensor_id=sensor_id,
            temperature=temperature,
            humidity=humidity,
            is_anomaly=is_anomaly,
            timestamp=datetime.utcnow()
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        
        # Крок 7: Кінець
        return {
            "success": True,
            "reading_id": reading.id,
            "is_anomaly": is_anomaly,
            "alert_created": alert_created,
            "statistics": stats,
            "status": "saved"
        }
    
    @staticmethod
    def _validate_data(
        temperature: Optional[float],
        humidity: Optional[float]
    ) -> Dict[str, Any]:
        """
        Валідувати дані сенсора
        
        Перевірки:
        - Температура: -50°C до +100°C
        - Вологість: 0% до 100%
        """
        errors = []
        
        if temperature is not None:
            if temperature < -50 or temperature > 100:
                errors.append("Temperature out of valid range (-50 to 100)")
        
        if humidity is not None:
            if humidity < 0 or humidity > 100:
                errors.append("Humidity out of valid range (0 to 100)")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    @staticmethod
    def _calculate_statistics(
        db: Session,
        sensor_id: int,
        temperature: Optional[float],
        humidity: Optional[float]
    ) -> Dict[str, Any]:
        """Розрахувати статистику для сенсора"""
        # Отримати останні 24 години даних
        cutoff = datetime.utcnow() - timedelta(hours=24)
        
        recent_readings = db.query(models.SensorReading).filter(
            and_(
                models.SensorReading.sensor_id == sensor_id,
                models.SensorReading.timestamp >= cutoff
            )
        ).all()
        
        if not recent_readings:
            return {"message": "Insufficient data for statistics"}
        
        temps = [r.temperature for r in recent_readings if r.temperature is not None]
        humids = [r.humidity for r in recent_readings if r.humidity is not None]
        
        return {
            "last_24h_readings": len(recent_readings),
            "temperature": {
                "current": temperature,
                "avg_24h": round(statistics.mean(temps), 2) if temps else None,
                "deviation": round(abs(temperature - statistics.mean(temps)), 2) if temps and temperature else None
            },
            "humidity": {
                "current": humidity,
                "avg_24h": round(statistics.mean(humids), 2) if humids else None,
                "deviation": round(abs(humidity - statistics.mean(humids)), 2) if humids and humidity else None
            }
        }


# ============================================
# УПРАВЛІННЯ КОРИСТУВАЧАМИ (Flowchart 3)
# ============================================

class UserManagementFlow:
    """
    Процес управління користувачами згідно Flowchart 3:
    Початок -> Адміністратор? -> Отримати тип операції -> 
    Тип дії? (Створити/Оновити/Видалити) -> Записати зміни -> Успіх -> Кінець
    """
    
    @staticmethod
    def manage_user(
        db: Session,
        admin_user_id: int,
        operation: str,  # "create", "update", "delete"
        user_data: Optional[Dict] = None,
        target_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Управління користувачами (адміністративна функція)
        
        Flowchart:
        1. Початок
        2. Адміністратор? -> Ні: Відмова в доступі -> Кінець
        3. Адміністратор? -> Так: Отримати тип операції
        4. Тип дії?:
           - Створити: Валідувати дані -> Створити користувача
           - Оновити: Існує? -> Оновити дані
           - Видалити: Підтвердити? -> Видалити користувача
        5. Записати зміни
        6. Успіх -> Кінець
        """
        
        # Крок 2: Адміністратор?
        admin = db.query(models.User).filter(
            models.User.id == admin_user_id
        ).first()
        
        if not admin or not admin.is_admin:
            # Ні -> Відмова в доступі -> Кінець
            return {
                "success": False,
                "error": "Access denied",
                "message": "Only administrators can manage users",
                "status": "unauthorized"
            }
        
        # Крок 3: Так -> Отримати тип операції
        # Крок 4: Тип дії?
        
        if operation == "create":
            # Створити -> Валідувати дані
            if not user_data:
                return {
                    "success": False,
                    "error": "User data required for creation"
                }
            
            validation = UserManagementFlow._validate_user_data(db, user_data)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "Validation failed",
                    "details": validation["errors"]
                }
            
            # Створити користувача
            from auth import get_password_hash
            new_user = models.User(
                username=user_data["username"],
                email=user_data["email"],
                password_hash=get_password_hash(user_data["password"]),
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name"),
                is_admin=user_data.get("is_admin", False)
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # Крок 5: Записати зміни (у логи)
            UserManagementFlow._log_change(
                db, admin_user_id, "create", f"Created user {new_user.username}"
            )
            
            # Крок 6: Успіх -> Кінець
            return {
                "success": True,
                "operation": "create",
                "user_id": new_user.id,
                "username": new_user.username,
                "status": "created"
            }
        
        elif operation == "update":
            # Оновити -> Існує?
            if not target_user_id:
                return {
                    "success": False,
                    "error": "Target user ID required for update"
                }
            
            target_user = db.query(models.User).filter(
                models.User.id == target_user_id
            ).first()
            
            if not target_user:
                # Ні -> Користувач не знайдений -> Кінець
                return {
                    "success": False,
                    "error": "User not found",
                    "status": "not_found"
                }
            
            # Так -> Оновити дані
            if user_data:
                for key, value in user_data.items():
                    if hasattr(target_user, key) and key != "password":
                        setattr(target_user, key, value)
                
                db.commit()
                db.refresh(target_user)
                
                # Крок 5: Записати зміни
                UserManagementFlow._log_change(
                    db, admin_user_id, "update", f"Updated user {target_user.username}"
                )
                
                # Крок 6: Успіх -> Кінець
                return {
                    "success": True,
                    "operation": "update",
                    "user_id": target_user.id,
                    "username": target_user.username,
                    "status": "updated"
                }
        
        elif operation == "delete":
            # Видалити -> Підтвердити?
            if not target_user_id:
                return {
                    "success": False,
                    "error": "Target user ID required for deletion"
                }
            
            # Підтвердити? (припускаємо що підтвердження вже отримано)
            confirm = user_data.get("confirm_delete", False) if user_data else False
            
            if not confirm:
                # Ні -> Скасувати -> Кінець
                return {
                    "success": False,
                    "error": "Deletion not confirmed",
                    "message": "Set confirm_delete=true to proceed",
                    "status": "cancelled"
                }
            
            # Так -> Видалити користувача
            target_user = db.query(models.User).filter(
                models.User.id == target_user_id
            ).first()
            
            if not target_user:
                return {
                    "success": False,
                    "error": "User not found",
                    "status": "not_found"
                }
            
            username = target_user.username
            db.delete(target_user)
            db.commit()
            
            # Крок 5: Записати зміни
            UserManagementFlow._log_change(
                db, admin_user_id, "delete", f"Deleted user {username}"
            )
            
            # Крок 6: Успіх -> Кінець
            return {
                "success": True,
                "operation": "delete",
                "username": username,
                "status": "deleted"
            }
        
        else:
            return {
                "success": False,
                "error": "Invalid operation",
                "message": "Operation must be 'create', 'update', or 'delete'"
            }
    
    @staticmethod
    def _validate_user_data(db: Session, user_data: Dict) -> Dict[str, Any]:
        """Валідувати дані користувача"""
        errors = []
        
        # Перевірка обов'язкових полів
        if "username" not in user_data or not user_data["username"]:
            errors.append("Username is required")
        elif len(user_data["username"]) < 3:
            errors.append("Username must be at least 3 characters")
        
        if "email" not in user_data or not user_data["email"]:
            errors.append("Email is required")
        elif "@" not in user_data["email"]:
            errors.append("Invalid email format")
        
        if "password" not in user_data or not user_data["password"]:
            errors.append("Password is required")
        elif len(user_data["password"]) < 8:
            errors.append("Password must be at least 8 characters")
        
        # Перевірка унікальності
        if "username" in user_data:
            existing = db.query(models.User).filter(
                models.User.username == user_data["username"]
            ).first()
            if existing:
                errors.append("Username already exists")
        
        if "email" in user_data:
            existing = db.query(models.User).filter(
                models.User.email == user_data["email"]
            ).first()
            if existing:
                errors.append("Email already exists")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    @staticmethod
    def _log_change(
        db: Session,
        admin_id: int,
        action: str,
        description: str
    ):
        """Записати зміни в лог"""
        log = models.DeviceLog(
            device_id=admin_id,
            device_type="admin_action",
            log_level="info",
            message=f"[{action.upper()}] {description}",
            timestamp=datetime.utcnow()
        )
        db.add(log)


# ============================================
# ГЕНЕРАЦІЯ АНАЛІТИЧНОГО ЗВІТУ (Flowchart 4)
# ============================================

class AnalyticsReportFlow:
    """
    Процес генерації аналітики згідно Flowchart 4:
    Початок -> Отримати параметри запиту -> Вибрати часовий період ->
    Завантажити дані з БД -> Розрахувати середні значення ->
    Знайти мін/макс значення -> Визначити тренди ->
    Сформувати звіт -> Кешувати результат -> Повернути дані -> Кінець
    """
    
    @staticmethod
    def generate_report(
        db: Session,
        room_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Згенерувати аналітичний звіт
        
        Flowchart:
        1. Початок
        2. Отримати параметри запиту
        3. Вибрати часовий період
        4. Завантажити дані з БД
        5. Розрахувати середні значення
        6. Знайти мін/макс значення
        7. Визначити тренди
        8. Сформувати звіт
        9. Кешувати результат
        10. Повернути дані
        11. Кінець
        """
        
        # Крок 2: Отримати параметри запиту
        params = {
            "room_id": room_id,
            "start_date": start_date,
            "end_date": end_date,
            "period_hours": period_hours
        }
        
        # Крок 3: Вибрати часовий період
        if period_hours:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(hours=period_hours)
        elif not start_date:
            start_date = datetime.utcnow() - timedelta(days=7)
        
        if not end_date:
            end_date = datetime.utcnow()
        
        # Крок 4: Завантажити дані з БД
        query = db.query(models.SensorReading).join(models.Sensor)
        
        if room_id:
            query = query.filter(models.Sensor.room_id == room_id)
        
        query = query.filter(
            and_(
                models.SensorReading.timestamp >= start_date,
                models.SensorReading.timestamp <= end_date
            )
        )
        
        readings = query.order_by(models.SensorReading.timestamp).all()
        
        if not readings:
            return {
                "success": False,
                "error": "No data available for specified period",
                "params": params
            }
        
        # Крок 5: Розрахувати середні значення
        temperatures = [r.temperature for r in readings if r.temperature is not None]
        humidities = [r.humidity for r in readings if r.humidity is not None]
        
        avg_temp = statistics.mean(temperatures) if temperatures else None
        avg_humid = statistics.mean(humidities) if humidities else None
        
        # Крок 6: Знайти мін/макс значення
        min_temp = min(temperatures) if temperatures else None
        max_temp = max(temperatures) if temperatures else None
        min_humid = min(humidities) if humidities else None
        max_humid = max(humidities) if humidities else None
        
        # Знайти часові мітки екстремумів
        min_temp_time = None
        max_temp_time = None
        if temperatures:
            min_temp_reading = min(readings, key=lambda r: r.temperature if r.temperature else float('inf'))
            max_temp_reading = max(readings, key=lambda r: r.temperature if r.temperature else float('-inf'))
            min_temp_time = min_temp_reading.timestamp.isoformat()
            max_temp_time = max_temp_reading.timestamp.isoformat()
        
        # Крок 7: Визначити тренди
        trends = AnalyticsReportFlow._determine_trends(readings)
        
        # Додаткова аналітика
        hourly_stats = AnalyticsReportFlow._calculate_hourly_stats(readings)
        anomaly_analysis = AnalyticsReportFlow._analyze_anomalies(readings)
        
        # Крок 8: Сформувати звіт
        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_hours": (end_date - start_date).total_seconds() / 3600
                },
                "room_id": room_id,
                "total_readings": len(readings)
            },
            "summary": {
                "temperature": {
                    "average": round(avg_temp, 2) if avg_temp else None,
                    "min": round(min_temp, 2) if min_temp else None,
                    "max": round(max_temp, 2) if max_temp else None,
                    "min_timestamp": min_temp_time,
                    "max_timestamp": max_temp_time,
                    "median": round(statistics.median(temperatures), 2) if temperatures else None,
                    "stdev": round(statistics.stdev(temperatures), 2) if len(temperatures) > 1 else None
                },
                "humidity": {
                    "average": round(avg_humid, 2) if avg_humid else None,
                    "min": round(min_humid, 2) if min_humid else None,
                    "max": round(max_humid, 2) if max_humid else None,
                    "median": round(statistics.median(humidities), 2) if humidities else None,
                    "stdev": round(statistics.stdev(humidities), 2) if len(humidities) > 1 else None
                }
            },
            "trends": trends,
            "hourly_analysis": hourly_stats,
            "anomaly_analysis": anomaly_analysis
        }
        
        # Крок 9: Кешувати результат
        cache_key = AnalyticsReportFlow._generate_cache_key(params)
        AnalyticsReportFlow._cache_report(cache_key, report)
        
        # Крок 10: Повернути дані
        return {
            "success": True,
            "report": report,
            "status": "generated"
        }
        
        # Крок 11: Кінець
    
    @staticmethod
    def _determine_trends(readings: List[models.SensorReading]) -> Dict[str, Any]:
        """
        Визначити тренди у даних
        
        Аналізує:
        - Загальний тренд (зростання/спадання/стабільність)
        - Волатильність
        - Циклічність
        """
        if len(readings) < 10:
            return {"status": "insufficient_data"}
        
        # Розділити на періоди для порівняння
        third = len(readings) // 3
        first_period = readings[:third]
        second_period = readings[third:2*third]
        third_period = readings[2*third:]
        
        # Температурні тренди
        temp_first = [r.temperature for r in first_period if r.temperature is not None]
        temp_second = [r.temperature for r in second_period if r.temperature is not None]
        temp_third = [r.temperature for r in third_period if r.temperature is not None]
        
        temp_trend = "unknown"
        if temp_first and temp_second and temp_third:
            avg1 = statistics.mean(temp_first)
            avg2 = statistics.mean(temp_second)
            avg3 = statistics.mean(temp_third)
            
            if avg3 > avg2 > avg1:
                temp_trend = "increasing"
            elif avg3 < avg2 < avg1:
                temp_trend = "decreasing"
            elif abs(avg3 - avg1) < 1.0:
                temp_trend = "stable"
            else:
                temp_trend = "fluctuating"
        
        # Тренди вологості
        humid_first = [r.humidity for r in first_period if r.humidity is not None]
        humid_second = [r.humidity for r in second_period if r.humidity is not None]
        humid_third = [r.humidity for r in third_period if r.humidity is not None]
        
        humid_trend = "unknown"
        if humid_first and humid_second and humid_third:
            avg1 = statistics.mean(humid_first)
            avg2 = statistics.mean(humid_second)
            avg3 = statistics.mean(humid_third)
            
            if avg3 > avg2 > avg1:
                humid_trend = "increasing"
            elif avg3 < avg2 < avg1:
                humid_trend = "decreasing"
            elif abs(avg3 - avg1) < 3.0:
                humid_trend = "stable"
            else:
                humid_trend = "fluctuating"
        
        return {
            "temperature_trend": temp_trend,
            "humidity_trend": humid_trend,
            "analysis_periods": 3,
            "readings_per_period": third
        }
    
    @staticmethod
    def _calculate_hourly_stats(readings: List[models.SensorReading]) -> List[Dict]:
        """Розрахувати статистику по годинах"""
        hourly_data = {}
        
        for reading in readings:
            hour_key = reading.timestamp.strftime("%Y-%m-%d %H:00")
            
            if hour_key not in hourly_data:
                hourly_data[hour_key] = {
                    "temperatures": [],
                    "humidities": []
                }
            
            if reading.temperature is not None:
                hourly_data[hour_key]["temperatures"].append(reading.temperature)
            if reading.humidity is not None:
                hourly_data[hour_key]["humidities"].append(reading.humidity)
        
        # Обчислити середні по годинах
        hourly_stats = []
        for hour, data in sorted(hourly_data.items()):
            stat = {
                "hour": hour,
                "temperature_avg": round(statistics.mean(data["temperatures"]), 2) if data["temperatures"] else None,
                "humidity_avg": round(statistics.mean(data["humidities"]), 2) if data["humidities"] else None,
                "readings_count": len(data["temperatures"]) + len(data["humidities"])
            }
            hourly_stats.append(stat)
        
        return hourly_stats
    
    @staticmethod
    def _analyze_anomalies(readings: List[models.SensorReading]) -> Dict[str, Any]:
        """Аналізувати аномалії"""
        anomalies = [r for r in readings if r.is_anomaly]
        
        if not anomalies:
            return {
                "total_anomalies": 0,
                "anomaly_rate": 0,
                "status": "no_anomalies"
            }
        
        # Групувати аномалії по типу (температура/вологість)
        temp_anomalies = []
        humid_anomalies = []
        
        for anomaly in anomalies:
            if anomaly.temperature is not None:
                temp_anomalies.append(anomaly.temperature)
            if anomaly.humidity is not None:
                humid_anomalies.append(anomaly.humidity)
        
        return {
            "total_anomalies": len(anomalies),
            "anomaly_rate": round(len(anomalies) / len(readings) * 100, 2),
            "temperature_anomalies": len(temp_anomalies),
            "humidity_anomalies": len(humid_anomalies),
            "first_anomaly": anomalies[0].timestamp.isoformat(),
            "last_anomaly": anomalies[-1].timestamp.isoformat()
        }
    
    @staticmethod
    def _generate_cache_key(params: Dict) -> str:
        """Згенерувати ключ для кешування"""
        key_string = json.dumps(params, sort_keys=True, default=str)
        return f"report_{hashlib.md5(key_string.encode()).hexdigest()}"
    
    @staticmethod
    def _cache_report(cache_key: str, report: Dict):
        """Кешувати результат (заглушка - можна використати Redis)"""
        # В реальному застосунку тут буде Redis
        pass


# ============================================
# ВИЯВЛЕННЯ АНОМАЛІЙ (існуюча логіка)
# ============================================

class AnomalyDetector:
    """Детектор аномалій у даних сенсорів"""
    
    @staticmethod
    def detect_anomaly(
        db: Session,
        sensor_id: int,
        temperature: Optional[float],
        humidity: Optional[float]
    ) -> bool:
        """
        Виявити аномалії у показниках сенсора
        
        Використовує метод стандартного відхилення:
        - Значення вважається аномальним, якщо воно відхиляється більш ніж на 3 sigma
        """
        # Отримати останні 100 показників для статистичного аналізу
        recent_readings = db.query(models.SensorReading).filter(
            models.SensorReading.sensor_id == sensor_id
        ).order_by(desc(models.SensorReading.timestamp)).limit(100).all()
        
        if len(recent_readings) < 10:
            # Недостатньо даних для виявлення аномалій
            return False
        
        is_anomaly = False
        
        # Перевірка температури
        if temperature is not None:
            temps = [r.temperature for r in recent_readings if r.temperature is not None]
            if len(temps) >= 10:
                is_anomaly = is_anomaly or AnomalyDetector._is_outlier(temperature, temps)
        
        # Перевірка вологості
        if humidity is not None:
            humids = [r.humidity for r in recent_readings if r.humidity is not None]
            if len(humids) >= 10:
                is_anomaly = is_anomaly or AnomalyDetector._is_outlier(humidity, humids)
        
        return is_anomaly
    
    @staticmethod
    def _is_outlier(value: float, historical_values: List[float]) -> bool:
        """Перевірити чи є значення аномальним (3-sigma правило)"""
        if len(historical_values) < 2:
            return False
        
        mean = statistics.mean(historical_values)
        stdev = statistics.stdev(historical_values)
        
        # Значення є аномальним якщо воно більше ніж 3 стандартних відхилення від середнього
        threshold = 3 * stdev
        return abs(value - mean) > threshold