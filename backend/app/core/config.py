from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://smp:smp_password@localhost:5432/smp"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 480
    otp_token_expire_minutes: int = 10
    vault_key: str = ""  # base64 of 32 random bytes

    frontend_origin: str = "http://localhost:5173"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "smp@example.com"
    smtp_tls: bool = True

    # DeepSeek account whose balance is read to measure daily API cost (see services/usage.py)
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com"
    deepseek_sync_minutes: int = 15  # the running app reads the balance this often; 0 = only the job / button

    app_timezone: str = "Asia/Dhaka"
    environment: str = "development"

    max_failed_logins: int = 5
    lockout_minutes: int = 15
    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
