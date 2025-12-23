"""
Authentication and security utilities
JWT tokens, password hashing, current user dependency
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv

from database import get_db
import models

load_dotenv()

# Конфігурація
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme для JWT
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login/form")


# ============================================
# PASSWORD UTILITIES
# ============================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Перевірити чи співпадає пароль з хешем"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Створити bcrypt хеш паролю"""
    return pwd_context.hash(password)


# ============================================
# JWT TOKEN UTILITIES
# ============================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Створити JWT access token
    
    Args:
        data: Дані для включення в токен (зазвичай user_id)
        expires_delta: Час життя токену
    
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def verify_token(token: str) -> Optional[int]:
    """
    Перевірити JWT token та витягнути user_id
    
    Args:
        token: JWT token string
    
    Returns:
        user_id якщо токен валідний, None інакше
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        
        if user_id is None:
            return None
        
        return int(user_id)
    
    except JWTError:
        return None


# ============================================
# AUTHENTICATION DEPENDENCY
# ============================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Dependency для отримання поточного аутентифікованого користувача
    Використовується у всіх захищених endpoint'ах
    
    Args:
        token: JWT token з Authorization header
        db: Database session
    
    Returns:
        User model instance
    
    Raises:
        HTTPException 401: Якщо токен невалідний або користувач не знайдений
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Перевірити токен та витягнути user_id
    user_id = verify_token(token)
    
    if user_id is None:
        raise credentials_exception
    
    # Знайти користувача в БД
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Dependency для перевірки що користувач активний"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


# ============================================
# USER AUTHENTICATION
# ============================================

def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Аутентифікувати користувача за email та паролем
    
    Args:
        db: Database session
        email: User email
        password: Plain text password
    
    Returns:
        User model якщо credentials правильні, None інакше
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if not user:
        return None
    
    if not verify_password(password, user.password_hash):
        return None
    
    return user