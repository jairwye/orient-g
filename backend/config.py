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

    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
