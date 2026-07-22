from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_maps_api_key: str = ""
    anthropic_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    class Config:
        env_file = ".env"


settings = Settings()
