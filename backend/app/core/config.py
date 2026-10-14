from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_FROM = "smp@example.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://smp:smp_password@localhost:5432/smp"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 480
    otp_token_expire_minutes: int = 10
    vault_key: str = ""  # base64 of 32 random bytes

    frontend_origin: str = "http://localhost:5173"

    # Email. With no mail server the messages (and sign-in codes) are written to the server log instead.
    smtp_host: str = ""
    smtp_port: int = 587  # 587 = STARTTLS (smtp_tls), 465 = SSL
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = DEFAULT_FROM
    smtp_tls: bool = True
    # Gmail shortcut: GMAIL_USER + GMAIL_APP_PASSWORD (a 16-letter app password) fill in the SMTP settings
    gmail_user: str = ""
    gmail_app_password: str = ""
    mail_enabled: bool = True  # false = never send, only log

    @model_validator(mode="after")
    def _gmail_shortcut(self):
        if self.gmail_user and not self.smtp_host:
            self.smtp_host, self.smtp_port, self.smtp_tls = "smtp.gmail.com", 587, True
            self.smtp_user = self.smtp_user or self.gmail_user
            # Google shows app passwords in groups of four ("abcd efgh ijkl mnop")
            self.smtp_password = self.smtp_password or self.gmail_app_password.replace(" ", "")
        if self.smtp_host.endswith("gmail.com") and self.smtp_from == DEFAULT_FROM:
            self.smtp_from = self.smtp_user  # Gmail sends only as the signed-in account
        return self

    @property
    def mail_on(self) -> bool:
        return self.mail_enabled and bool(self.smtp_host)

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
