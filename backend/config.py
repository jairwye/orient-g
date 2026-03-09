from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/mgmt_web"
    upload_dir: str = "./uploads"
    frontend_origin: str = "http://localhost:3000"
    auth_secret: str = "orient-g-auth-secret-change-in-production"

    # FreshRSS（新闻政策页）：未配置则新闻政策模块不拉取、接口返回空
    freshrss_api_url: Optional[str] = None
    freshrss_user: Optional[str] = None
    freshrss_api_password: Optional[str] = None
    freshrss_labels: str = "游戏观点,游戏新闻,AI新闻"  # 对应按钮 观点/新闻/AI
    freshrss_max_items: int = 80
    freshrss_fetch_interval_minutes: int = 10
    freshrss_cache_ttl_seconds: int = 600  # 10 分钟

    @property
    def freshrss_configured(self) -> bool:
        return bool(
            self.freshrss_api_url and self.freshrss_user and self.freshrss_api_password
        )

    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
