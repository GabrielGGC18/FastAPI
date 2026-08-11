from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DATABASE_URL: str = "sqlite:///./banco.db"  

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite:///./banco.db"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    