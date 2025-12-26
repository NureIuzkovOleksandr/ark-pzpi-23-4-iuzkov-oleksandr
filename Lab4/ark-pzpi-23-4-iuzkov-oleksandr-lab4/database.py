"""
Database configuration and connection setup
PostgreSQL + SQLAlchemy
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Завантаження змінних середовища з .env файлу
load_dotenv()

# Database URL з .env файлу
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:your_password@localhost:5432/climate_monitoring"
)

# Створення engine для підключення до PostgreSQL
engine = create_engine(
    DATABASE_URL,
    echo=True,  # Виводить SQL запити в консоль
    pool_pre_ping=True,  # Перевірка з'єднання перед використанням
    pool_size=10,  # Розмір пулу з'єднань
    max_overflow=20  # Максимальна кількість додаткових з'єднань
)

# SessionLocal - клас для створення сесій БД
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base клас для моделей SQLAlchemy
Base = declarative_base()

# Dependency для отримання сесії БД в роутерах
def get_db():
    """
    Dependency injection для database session
    Використовується в FastAPI endpoints
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Функція для створення всіх таблиць
def create_tables():
    """
    Створює всі таблиці в БД на основі моделей SQLAlchemy
    Викликається при запуску додатку
    """
    print("Using existing PostgreSQL tables")


# Функція для видалення всіх таблиць
def drop_tables():
    Base.metadata.drop_all(bind=engine)