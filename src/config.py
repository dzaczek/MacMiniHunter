from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://tracker:change_me_in_production@db:5432/mac_tracker"

    # Matrix (Element) notifications
    matrix_homeserver: str = "https://matrix.org"
    matrix_access_token: str = ""
    matrix_room_id: str = ""

    # Scraper
    scrape_interval_hours: int = 18
    request_delay_min: float = 5.0
    request_delay_max: float = 15.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
