from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./wasel.db"
    redis_url: str = "redis://localhost:6379/0"

    otp_pepper: str = "change-me-in-prod"  # HMAC secret for hashing codes
    otp_ttl_seconds: int = 60
    otp_max_attempts: int = 5
    otp_cooldown_seconds: int = 60
    otp_daily_cap: int = 10
    otp_verify_fail_cap: int = 10
    otp_verify_fail_window_seconds: int = 900

    # JWT / sessions. Override jwt_secret via .env in any real env.
    jwt_secret: str = "change-me-in-prod"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    registration_token_minutes: int = 10

    # Expo push. No credentials needed in the backend — Apple/Google creds live
    # in the EAS project. The access token is optional (Expo "enhanced security").
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    expo_access_token: str | None = None


settings = Settings()  # pyright: ignore[reportCallIssue]
