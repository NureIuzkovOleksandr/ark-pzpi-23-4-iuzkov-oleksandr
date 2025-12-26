#include <Arduino.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// Forward declarations
void connectWiFi();
void sendDataToServer(float temp, float humidity);
void handleClimateControl(float temp, float humidity);
void checkLocalAnomalies(float temp, float humidity);
void updateThresholds();

// WiFi налаштування
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// API налаштування
String baseUrl = "https://climatemonitoring.redsky-323ad50b.northeurope.azurecontainerapps.io";
String processUrl = baseUrl + "/api/sensors/" + String(20) + "/readings/process";
String thresholdsUrl = baseUrl + "/api/climate-thresholds/room/" + String(7);

int sensorId = 20;
int roomId = 7;

// Піни
#define DHT_PIN 15
#define LED_RED 2
#define SERVO_PIN 4
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);
Servo climateServo;

// Пороги
float TEMP_MIN = 18.0;
float TEMP_MAX = 26.0;
float HUMIDITY_MIN = 30.0;
float HUMIDITY_MAX = 70.0;

// Таймери
unsigned long lastSendTime = 0;
unsigned long lastThresholdUpdate = 0;
const unsigned long sendInterval = 10000;
const unsigned long thresholdUpdateInterval = 10000;

void connectWiFi() {
  Serial.println("\nПідключення до WiFi...");
  Serial.print("SSID: ");
  Serial.println(ssid);
  
  if (strlen(password) == 0) {
    Serial.println("Відкрита мережа");
    WiFi.begin(ssid);
  } else {
    Serial.println("Захищена мережа");
    WiFi.begin(ssid, password);
  }
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi підключено!");
    Serial.print("IP адреса: ");
    Serial.println(WiFi.localIP());
    Serial.print("Сигнал: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println("\nПомилка підключення WiFi");
  }
}

void updateThresholds() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi не підключено для оновлення порогів");
    return;
  }

  HTTPClient http;
  http.begin(thresholdsUrl);
  http.setTimeout(5000);
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String response = http.getString();
    
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error) {
      TEMP_MIN = doc["min_temperature"] | 18.0;
      TEMP_MAX = doc["max_temperature"] | 26.0;
      HUMIDITY_MIN = doc["min_humidity"] | 30.0;
      HUMIDITY_MAX = doc["max_humidity"] | 70.0;
      
      Serial.println("\nПороги оновлено з сервера:");
      Serial.print("Температура: ");
      Serial.print(TEMP_MIN);
      Serial.print(" - ");
      Serial.println(TEMP_MAX);
      Serial.print("Вологість: ");
      Serial.print(HUMIDITY_MIN);
      Serial.print(" - ");
      Serial.println(HUMIDITY_MAX);
    }
  } else {
    Serial.print("Помилка отримання порогів: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

void sendDataToServer(float temp, float humidity) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi не підключено");
    return;
  }

  HTTPClient http;
  
  http.begin(processUrl);
  http.addHeader("Content-Type", "application/json");
  
  StaticJsonDocument<200> doc;
  if (!isnan(temp)) doc["temperature"] = temp;
  if (!isnan(humidity)) doc["humidity"] = humidity;
  
  String jsonData;
  serializeJson(doc, jsonData);
  
  Serial.println("\nВідправка даних на сервер:");
  Serial.println(processUrl);
  Serial.println(jsonData);
  
  int httpCode = http.POST(jsonData);
  
  if (httpCode > 0) {
    Serial.print("HTTP код відповіді: ");
    Serial.println(httpCode);
    
    if (httpCode == 200) {
      String response = http.getString();
      Serial.println("Відповідь сервера:");
      Serial.println(response);
      
      StaticJsonDocument<1024> responseDoc;
      DeserializationError error = deserializeJson(responseDoc, response);
      
      if (!error) {
        bool success = responseDoc["success"];
        bool isAnomaly = responseDoc["is_anomaly"];
        int commandsExecuted = responseDoc["commands_executed"];
        int alertsCreated = responseDoc["alerts_created"];
        
        Serial.println("\nРезультат обробки:");
        Serial.print("Успіх: ");
        Serial.println(success ? "ТАК" : "НІ");
        Serial.print("Аномалія: ");
        Serial.println(isAnomaly ? "ТАК" : "НІ");
        Serial.print("Команд виконано: ");
        Serial.println(commandsExecuted);
        Serial.print("Сповіщень створено: ");
        Serial.println(alertsCreated);
        
        handleClimateControl(temp, humidity);
      }
    }
  } else {
    Serial.print("Помилка HTTP: ");
    Serial.println(http.errorToString(httpCode));
  }
  
  http.end();
}

void handleClimateControl(float temp, float humidity) {
  Serial.println("\nУправління кліматом:");
  
  if (temp < TEMP_MIN || humidity < HUMIDITY_MIN) {
    Serial.println("УВІМКНУТИ обігрів");
    Serial.println("Сервопривод -> 90°");
    climateServo.write(90);
  } else if (temp > TEMP_MAX || humidity > HUMIDITY_MAX) {
    Serial.println("УВІМКНУТИ охолодження");
    Serial.println("Сервопривод -> 180°");
    climateServo.write(180);
  } else {
    Serial.println("Клімат в нормі");
    Serial.println("Сервопривод -> 0°");
    climateServo.write(0);
  }
}

void checkLocalAnomalies(float temp, float humidity) {
  bool anomaly = false;
  
  if (!isnan(temp) && (temp < TEMP_MIN || temp > TEMP_MAX)) {
    Serial.print("ЛОКАЛЬНА АНОМАЛІЯ: Температура ");
    Serial.print(temp);
    Serial.println("°C поза нормою");
    anomaly = true;
  }
  
  if (!isnan(humidity) && (humidity < HUMIDITY_MIN || humidity > HUMIDITY_MAX)) {
    Serial.print("ЛОКАЛЬНА АНОМАЛІЯ: Вологість ");
    Serial.print(humidity);
    Serial.println("% поза нормою");
    anomaly = true;
  }
  
  digitalWrite(LED_RED, anomaly ? HIGH : LOW);
  Serial.print("Червоний світлодіод: ");
  Serial.println(anomaly ? "УВІМКНЕНО" : "ВИМКНЕНО");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║   IoT Climate Monitor - ESP32          ║");
  Serial.println("║   Інтеграція з FastAPI Backend        ║");
  Serial.println("╚════════════════════════════════════════╝");
  
  pinMode(LED_RED, OUTPUT);
  digitalWrite(LED_RED, LOW);
  
  dht.begin();
  
  climateServo.attach(SERVO_PIN);
  climateServo.write(0);
  
  Serial.println("\nКомпоненти ініціалізовано");
  
  connectWiFi();
  
  if (WiFi.status() == WL_CONNECTED) {
    updateThresholds();
  }
  
  Serial.println("\nСистема готова до роботи!");
  Serial.print("Base URL: ");
  Serial.println(baseUrl);
  Serial.print("Sensor ID: ");
  Serial.println(sensorId);
  Serial.println("════════════════════════════════════════\n");
}

void loop() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastThresholdUpdate >= thresholdUpdateInterval) {
    lastThresholdUpdate = currentTime;
    updateThresholds();
  }
  
  if (currentTime - lastSendTime >= sendInterval) {
    lastSendTime = currentTime;
    
    Serial.println("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    Serial.println("Новий цикл зчитування");
    
    float temp = dht.readTemperature();
    float humidity = dht.readHumidity();
    
    if (isnan(temp) || isnan(humidity)) {
      Serial.println("Помилка читання DHT22!");
      digitalWrite(LED_RED, HIGH);
      return;
    }
    
    Serial.print("Температура: ");
    Serial.print(temp);
    Serial.println(" °C");
    Serial.print("Вологість: ");
    Serial.print(humidity);
    Serial.println(" %");
    
    checkLocalAnomalies(temp, humidity);
    sendDataToServer(temp, humidity);
    
    Serial.println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  }
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWiFi відключено, спроба перепідключення...");
    connectWiFi();
  }
  
  delay(100);
}