from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/mgmt_web"
    upload_dir: str = "./uploads"
    frontend_origin: str = "http://localhost:3000"

    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
