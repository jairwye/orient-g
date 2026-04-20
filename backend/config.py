from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

    # Ollama（自然语言→流程文档等）：未配置则流程文档生成不可用
    ollama_url: Optional[str] = None
    ollama_model: str = "qwen3:8b-q4_K_M"
    # Ollama embeddings：用于 RAG 向量化（默认可与对话模型不同）
    ollama_embed_model: str = "bge-m3"

    # Knowledge RAG（向量检索）开关：默认关闭，走 keyword-only（更适合“小文档海”）
    kb_vector_enabled: bool = False
    # embeddings 维度（与所选 embedding 模型一致；bge-m3 常用为 1024）
    kb_embedding_dim: int = 1024

    # --- 队列 / 限流 / 降级（2.e）---
    # 进程内双队列容量上限（分别限制 high/low；用于 backpressure）
    queue_max_size_high: int = 20
    queue_max_size_low: int = 50
    # 在线请求降级阈值：当 high 队列堆积超过阈值时，在线路径直接降级/拒绝
    queue_degrade_high_threshold: int = 10
    # 持久化队列：租约/心跳/回收
    queue_worker_lease_seconds: int = 120
    queue_worker_heartbeat_seconds: int = 15
    queue_running_timeout_seconds: int = 300
    queue_queued_timeout_seconds: int = 7200
    queue_task_max_attempts: int = 3
    queue_retry_backoff_seconds: int = 30

    # GPU/推理资源并发（用于本机 Ollama、向量嵌入等需要“重资源”的调用）
    gpu_max_concurrency: int = 1
    gpu_acquire_timeout_s: int = 10

    # 在线互动限速（按用户；token-bucket）
    online_user_rps: float = 0.5  # 平均 2s 1 次
    online_user_burst: int = 3

    # Ollama 熔断（连续失败达到阈值后，在窗口期内快速失败）
    ollama_circuit_fail_threshold: int = 3
    ollama_circuit_open_seconds: int = 30

    @property
    def freshrss_configured(self) -> bool:
        return bool(
            self.freshrss_api_url and self.freshrss_user and self.freshrss_api_password
        )

    @property
    def ollama_configured(self) -> bool:
        return bool(self.ollama_url)

    # 飞书（流程文档同步）：未配置则同步飞书不可用
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_doc_folder_token: Optional[str] = None  # 可选，创建文档时放入的文件夹

    @property
    def feishu_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    # Docling：local=本进程 CLI（开发机）；http=独立 sidecar（Docker 生产推荐）
    docling_mode: str = "local"
    docling_http_base_url: Optional[str] = None
    docling_http_timeout_s: int = 600
    docling_http_connect_timeout_s: int = 10
    docling_http_read_timeout_s: int = 600
    docling_http_write_timeout_s: int = 60
    docling_http_pool_timeout_s: int = 30
    docling_http_max_retries: int = 2
    docling_http_retry_backoff_s: float = 1.5
    # 上游地址保护：默认阻断“开发机误连生产 AI 服务”
    ai_upstream_block_remote: bool = True
    ai_upstream_allowed_hosts: str = "localhost,127.0.0.1,::1,ollama,docling,host.docker.internal"

    # DB 迁移模式：
    # - legacy：启动时自动建表/补列（现状）
    # - alembic：schema 由 alembic 显式迁移管理（生产推荐）
    db_migration_mode: str = "legacy"


settings = Settings()
