# api/auth.py
"""
JWT authentication and authorization for StockJarvis API.
Handles user authentication, token generation, and password hashing.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import Session

from config.settings import settings
from core.logger import get_logger
from data.models import Base
from data.repository import repository

logger = get_logger(__name__)


# ==================== Security Configuration ====================

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for token-based authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# JWT configuration
SECRET_KEY = settings.app.secret_key if hasattr(settings.app, 'secret_key') else "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


# ==================== User Model (Database) ====================

class User(Base):
    """
    User model for authentication and authorization.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    
    # Status flags
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}')>"


# Ensure User table is created
def create_user_table():
    """Create user table if it doesn't exist."""
    try:
        User.__table__.create(repository.engine, checkfirst=True)
        logger.info("User table created/verified")
    except Exception as e:
        logger.error(f"Error creating user table: {e}")


# Create table on module import
create_user_table()


# ==================== Pydantic Schemas ====================

class Token(BaseModel):
    """
    Token response schema.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=ACCESS_TOKEN_EXPIRE_MINUTES * 60, description="Token expiration in seconds")


class TokenData(BaseModel):
    """
    Token payload data.
    """
    username: Optional[str] = None
    exp: Optional[datetime] = None


class UserBase(BaseModel):
    """
    Base user schema.
    """
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """
    User creation schema with password.
    """
    password: str = Field(..., min_length=8, max_length=100)


class UserResponse(UserBase):
    """
    User response schema (without password).
    """
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserInDB(UserBase):
    """
    User schema with hashed password (for internal use).
    """
    id: int
    hashed_password: str
    is_active: bool
    is_superuser: bool
    
    class Config:
        from_attributes = True


# ==================== Password Utilities ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database
    
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
    
    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


# ==================== JWT Token Utilities ====================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data to encode
        expires_delta: Token expiration time delta
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: JWT token string
    
    Returns:
        TokenData object with username and expiration
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))
        
        if username is None:
            raise credentials_exception
        
        return TokenData(username=username, exp=exp)
    
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise credentials_exception


# ==================== User Database Operations ====================

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by username.
    
    Args:
        db: Database session
        username: Username to search for
    
    Returns:
        User object or None
    """
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get user by email.
    
    Args:
        db: Database session
        email: Email to search for
    
    Returns:
        User object or None
    """
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, user: UserCreate) -> User:
    """
    Create a new user.
    
    Args:
        db: Database session
        user: User creation data
    
    Returns:
        Created user object
    
    Raises:
        ValueError: If username or email already exists
    """
    # Check if user already exists
    if get_user_by_username(db, user.username):
        raise ValueError(f"Username '{user.username}' already exists")
    
    if get_user_by_email(db, user.email):
        raise ValueError(f"Email '{user.email}' already exists")
    
    # Create new user
    db_user = User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=get_password_hash(user.password)
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"New user created: {user.username}")
    return db_user


def update_last_login(db: Session, user_id: int):
    """
    Update user's last login timestamp.
    
    Args:
        db: Database session
        user_id: User ID
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.last_login = datetime.utcnow()
        db.commit()


# ==================== Authentication Functions ====================

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate a user with username and password.
    
    Args:
        db: Database session
        username: Username
        password: Plain text password
    
    Returns:
        User object if authentication successful, None otherwise
    """
    user = get_user_by_username(db, username)
    
    if not user:
        logger.warning(f"Authentication failed: User '{username}' not found")
        return None
    
    if not verify_password(password, user.hashed_password):
        logger.warning(f"Authentication failed: Invalid password for user '{username}'")
        return None
    
    if not user.is_active:
        logger.warning(f"Authentication failed: User '{username}' is inactive")
        return None
    
    logger.info(f"User authenticated successfully: {username}")
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        token: JWT token from Authorization header
    
    Returns:
        Current user object
    
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode token
        token_data = decode_access_token(token)
        username = token_data.username
        
        if username is None:
            raise credentials_exception
        
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    with repository.get_session() as db:
        user = get_user_by_username(db, username)
        
        if user is None:
            raise credentials_exception
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to get the current active user.
    
    Args:
        current_user: User from get_current_user dependency
    
    Returns:
        Active user object
    
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure current user is a superuser.
    
    Args:
        current_user: User from get_current_user dependency
    
    Returns:
        Superuser object
    
    Raises:
        HTTPException: If user is not a superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Superuser access required."
        )
    return current_user


# ==================== Helper Functions ====================

def create_default_admin():
    """
    Create default admin user if no users exist.
    Should be called on application startup.
    """
    with repository.get_session() as db:
        user_count = db.query(User).count()
        
        if user_count == 0:
            admin_user = UserCreate(
                username="admin",
                email="admin@stockjarvis.local",
                password="admin123",  # Change this in production!
                full_name="Administrator"
            )
            
            try:
                user = create_user(db, admin_user)
                user.is_superuser = True
                db.commit()
                logger.info("Default admin user created: username='admin', password='admin123'")
                logger.warning("IMPORTANT: Change default admin password in production!")
            except Exception as e:
                logger.error(f"Failed to create default admin: {e}")


# Create default admin on module import (only in development)
if settings.app.env == "development":
    try:
        create_default_admin()
    except Exception as e:
        logger.error(f"Error creating default admin: {e}")
