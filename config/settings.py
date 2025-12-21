"""
Centralized configuration management using Pydantic.
All settings are loaded from environment variables or .env file.
"""

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pathlib import Path


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=3306, description="Database port")
    user: str = Field(description="Database username")
    password: str = Field(description="Database password")
    database: str = Field(default="stockjarvis", description="Database name")
    pool_size: int = Field(default=5, description="Connection pool size")
    pool_recycle: int = Field(default=3600, description="Pool recycle time in seconds")
    
    @property
    def url(self) -> str:
        """Generate SQLAlchemy connection URL."""
        return f"mysql+mysqlconnector://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    model_config = SettingsConfigDict(env_prefix="DB_")


class QuandlSettings(BaseSettings):
    """Quandl API configuration."""
    
    api_key: str = Field(description="Quandl API key")
    rate_limit_calls: int = Field(default=50, description="Calls per day on free tier")
    
    model_config = SettingsConfigDict(env_prefix="QUANDL_")


class ZerodhaSettings(BaseSettings):
    """Zerodha Kite Connect API configuration."""
    
    api_key: str = Field(description="Kite Connect API key")
    api_secret: str = Field(description="Kite Connect API secret")
    access_token: Optional[str] = Field(default=None, description="Kite access token (generated after login)")
    request_token: Optional[str] = Field(default=None, description="Request token from OAuth")
    redirect_url: str = Field(default="http://localhost:5000/jarvispostback", description="OAuth redirect URL")
    
    model_config = SettingsConfigDict(env_prefix="ZERODHA_")


class NotificationSettings(BaseSettings):
    """Notification service configuration."""
    
    sendgrid_api_key: Optional[str] = Field(default=None, description="SendGrid API key")
    email_from: str = Field(default="jarvis@stocktrading.com", description="Sender email address")
    email_to: List[str] = Field(default=["admin@example.com"], description="Recipient email addresses")
    
    way2sms_username: Optional[str] = Field(default=None, description="Way2SMS username")
    way2sms_password: Optional[str] = Field(default=None, description="Way2SMS password")
    sms_to: List[str] = Field(default=[], description="SMS recipient phone numbers")
    
    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_")
    
    @validator("email_to", "sms_to", pre=True)
    def parse_list(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class TradingSettings(BaseSettings):
    """Trading parameters and risk management."""
    
    mode: str = Field(default="paper", description="Trading mode: paper or live")
    max_positions: int = Field(default=5, description="Maximum concurrent positions")
    risk_per_trade: float = Field(default=0.02, description="Risk per trade as % of capital (0.02 = 2%)")
    min_strategy_accuracy: float = Field(default=0.65, description="Minimum strategy success rate (0.65 = 65%)")
    min_risk_reward: float = Field(default=2.0, description="Minimum risk:reward ratio")
    capital: float = Field(default=100000.0, description="Total trading capital")
    
    model_config = SettingsConfigDict(env_prefix="TRADING_")
    
    @validator("mode")
    def validate_mode(cls, v):
        """Ensure trading mode is valid."""
        if v not in ["paper", "live"]:
            raise ValueError("Trading mode must be 'paper' or 'live'")
        return v


class RedisSettings(BaseSettings):
    """Redis configuration for Celery task queue."""
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    
    @property
    def url(self) -> str:
        """Generate Redis connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")


class AppSettings(BaseSettings):
    """Application-wide settings."""
    
    env: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path = Field(default=Path("logs/jarvis.log"), description="Log file path")
    
    # Security
    secret_key: str = Field(
        default="your-secret-key-change-in-production-use-openssl-rand-hex-32",
        description="Secret key for JWT token signing"
    )
    
    # API settings
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_workers: int = Field(default=4, description="Number of API workers")
    
    # Data collection settings
    data_update_schedule: str = Field(default="0 18 * * 1-5", description="Cron schedule for daily data updates")
    scanner_schedule: str = Field(default="30 9,15 * * 1-5", description="Cron schedule for strategy scans")
    
    model_config = SettingsConfigDict(env_prefix="APP_")
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Ensure log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()


class Settings(BaseSettings):
    """Main settings class combining all configuration sections."""
    
    # Sub-settings
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    quandl: QuandlSettings = Field(default_factory=QuandlSettings)
    zerodha: ZerodhaSettings = Field(default_factory=ZerodhaSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
