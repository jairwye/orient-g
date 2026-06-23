from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定项目根 .env，避免从 backend/ 等子目录启动时读不到 HERMES_* / DATABASE_URL
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(_ENV_FILE), ".env", "../.env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://user:password@localhost:5432/mgmt_web"
    upload_dir: str = "./uploads"
    frontend_origin: str = "http://localhost:3000"
    auth_secret: str = "orient-g-auth-secret-change-in-production"
    # 运行环境：development / production
    app_env: str = "development"
    # 显式安全守卫：拒绝使用默认 AUTH_SECRET 启动（可与 app_env=production 叠加）
    enforce_non_default_auth_secret: bool = False
    # 兼容旧 data-parse session（无 owner）：允许首次访问时绑定 owner
    data_parse_legacy_session_claim_enabled: bool = True

    # FreshRSS（新闻政策页）：未配置则新闻政策模块不拉取、接口返回空
    freshrss_api_url: Optional[str] = None
    freshrss_user: Optional[str] = None
    freshrss_api_password: Optional[str] = None
    freshrss_labels: str = "游戏观点,游戏新闻,AI新闻"  # 对应按钮 观点/新闻/AI
    freshrss_max_items: int = 80
    freshrss_fetch_interval_minutes: int = 10
    freshrss_cache_ttl_seconds: int = 600  # 10 分钟

    # Ollama：主要用于 embeddings（/api/embed）；可选仍用于对话/生成（未配置 LLM_* 时）
    ollama_url: Optional[str] = None
    ollama_model: str = "qwen3:8b-q4_K_M"
    # Ollama embeddings：用于 RAG 向量化（默认可与对话模型不同）
    ollama_embed_model: str = "bge-m3"

    # OpenAI 兼容 LLM（对话、数据解析工具链、流程文档生成等）：LLM_BASE_URL + LLM_MODEL 同时配置则优先使用
    # LLM_API_KEY 可选（部分本机网关可不校验）
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None

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
    # 大 PDF + 远程 Docling 可能跑数小时；租约/心跳过短会误回收为 queued（UI 仍显示排队中）
    queue_worker_lease_seconds: int = 3600
    queue_worker_heartbeat_seconds: int = 15
    queue_running_timeout_seconds: int = 7200
    queue_queued_timeout_seconds: int = 7200
    queue_task_max_attempts: int = 3
    queue_retry_backoff_seconds: int = 30
    queue_retry_backoff_max_seconds: int = 900
    queue_worker_idle_min_s: float = 0.2
    queue_worker_idle_max_s: float = 5.0
    queue_worker_idle_backoff: bool = True

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

    @property
    def llm_chat_configured(self) -> bool:
        return bool((self.llm_base_url or "").strip() and (self.llm_model or "").strip())

    @property
    def chat_llm_available(self) -> bool:
        """对话/解读/流程文档等「聊天类」能力是否可用（OpenAI 兼容 或 回退 Ollama）。"""
        return self.llm_chat_configured or self.ollama_configured

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
    # 普通文档解析的 HTTP 连接参数（大 PDF 已改为异步队列 + 轮询，不依赖这些超时）
    docling_http_connect_timeout_s: int = 10
    docling_http_write_timeout_s: int = 60
    # 上游地址保护：默认阻断“开发机误连生产 AI 服务”
    ai_upstream_block_remote: bool = True
    ai_upstream_allowed_hosts: str = "localhost,127.0.0.1,::1,ollama,docling,host.docker.internal"

    # DB 迁移模式：
    # - legacy：启动时自动建表/补列（现状）
    # - alembic：schema 由 alembic 显式迁移管理（生产推荐）
    db_migration_mode: str = "legacy"

    # Hermes Agent（内网 HTTP，见 specs/features/1.2.3）
    hermes_enabled: bool = False
    hermes_base_url: Optional[str] = None  # 例：http://hermes-agent:8642（Hermes API gateway，无 /v1 后缀）
    hermes_internal_token: Optional[str] = None  # 与 Hermes API_SERVER_KEY 一致
    hermes_model: str = "hermes-agent"
    hermes_request_timeout_s: int = 300
    hermes_searxng_enabled: bool = False
    hermes_lark_cli_enabled: bool = False
    # Windows 等无 Docker/Hermes 的开发机：/agent 直接调 orientg MCP 工具（不走 Hermes HTTP）
    hermes_dev_mock: bool = False
    # True：Hermes 前注入 KB 预检索摘要（不阻止 Hermes 再调 MCP）；False：完全由 Hermes 工具环检索
    hermes_agent_kb_prefetch: bool = True
    # True：有 kb_scope 时走 Hermes 编排（多轮 MCP，产品默认）；False：仅本地 LLM（调试/无 Hermes）
    hermes_agent_kb_synthesize: bool = True
    # True：预检索已有 citations 时跳过 Hermes MCP（兼容旧配置；优先用 agent_kb_router）
    hermes_agent_kb_fast_path: bool = False
    # Agent KB 三路分流默认文档语义：tier0 | hermes_lite | hermes_full（见 1.2.3.b evidence pack）
    hermes_agent_route_default: str = "tier0"
    # 多 query 预检索 + Evidence Pack（标准模式 Tier 0 前置）；env: KB_MULTI_QUERY 或 HERMES_AGENT_KB_MULTI_QUERY
    kb_multi_query: bool | None = None
    hermes_agent_kb_multi_query: bool = True
    # auto：pack 足够且无需多轮编排时走 Tier 0；「标准」模式固定 Tier 1（见 agent_kb_router）
    hermes_agent_standard_tier0: bool = True
    hermes_agent_kb_ask_budget_lite: int = 2
    hermes_agent_simple_query_fast: bool = True
    # Agent 回复走 Hermes SSE 流式（/api/agent/chat/stream）
    hermes_agent_stream: bool = True
    # True：在 Gateway 支持时改用 POST /v1/runs + GET .../events（可 POST .../stop 中断）
    hermes_agent_use_runs_api: bool = False
    # False：Hermes 上下文 orientg_stream_reasoning=false，与 LLM 侧关闭 think/reasoning 一致
    hermes_stream_reasoning: bool = False
    # 证据综合时单 chunk 最大字符（与 kb_documents.max_section_chars 对齐；超长才截断）
    kb_evidence_chunk_max_chars: int = 15000
    # True：带 kb_scope 的 /api/agent/chat/stream 须带 X-Agent-Run-Id（防 Hermes loopback 重放）
    agent_require_run_id: bool = False

    # 竞品财报：无 upload Snapshot 时回退到仓库内 YYCQ 蓝本 fixture（None=按 app_env：dev 开、production 关）
    competitor_fixture_fallback: bool | None = None
    # 纵向 PDF zip：内网中文文件名 → canonical id 规则（JSON 数组，仅生产 .env；勿提交 Git）
    vertical_company_rules_json: str | None = None

    @property
    def effective_competitor_fixture_fallback(self) -> bool:
        if self.competitor_fixture_fallback is not None:
            return bool(self.competitor_fixture_fallback)
        return self.app_env != "production"

    @property
    def effective_kb_multi_query(self) -> bool:
        if self.kb_multi_query is not None:
            return bool(self.kb_multi_query)
        return bool(self.hermes_agent_kb_multi_query)

    @property
    def hermes_configured(self) -> bool:
        return bool(self.hermes_enabled and (self.hermes_base_url or "").strip())


settings = Settings()
