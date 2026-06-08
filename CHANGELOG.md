# Changelog

本文件记录项目更新。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本/日期按发布记录。

## [Unreleased]

### Added

- **Agent KB 三路分流（Tier 0–2）**：`fast` / `hermes_lite` / `hermes_full` 路由；Evidence Pack 预检索、ask budget、KB scope 解析与 fast path 本地综合。
- **Hermes 集成**：`/api/agent` 阻塞/流式对话、运行注册与取消；`hermes_client`、token bridge、Orient-G MCP 工具与 `docker-compose.hermes.yml` 示例。
- **知识库检索增强**：检索计划/打包/直答（`kb_retrieval_plan`、`kb_retrieve_pack`、`kb_retrieve_answer`）、文件夹子树 scope、fixture bindings、RAG 审计桥接。
- **前端 Agent 体验**：AI 互动页 Agent 模式（auto/fast/standard/deep）、SSE Trace 面板、知识库浏览树（`KbBrowseTree`）、BigPDF 全局通知与任务 stage 归一。
- **规制目录 `specs/`**：API 契约迁至 `specs/api/api-contract.md`；Agent KB Router 计划与 UI spec 入库。
- **Alembic**：`kb_folders.parent_folder_id`；`kb_tasks` worker 租约/心跳/去重列与索引。

### Changed

- Hermes 流式：Runs/chat 双路径 `HermesRunsLoopGuard`；error 时 salvage 过程稿（`hermes_salvaged`）；Tier 1 pack 充分时跳过 supplemental；Tier 0 终稿统一 `finalize_agent_reply`。
- AI 互动页：Agent 流式期间防抖 session 持久化（修复 Maximum update depth）；Markdown 规范化拆至 `markdownNormalize.ts`。
- 用户可见文案：「AI互动」统一为 **「AI内网」**（路由 `/ai-interaction`、API 不变）；侧栏/知识库/合同/BigPDF 等引用 `frontend/app/lib/ui_labels.ts`。
- AI 互动页与知识库页布局/交互对齐 2026 spec；Markdown 气泡、KB 预检索与证据引用展示。
- BigPDF 队列：持久化 `kb_tasks`、worker 重启续跑、智能轮询与 UI 状态归一。
- `.env.example` 扩充 Hermes、Agent、Evidence Pack、上游白名单等配置项；Docling 代理改为可选（compose 不再硬编码内网 IP）。
- `CONTRIBUTING.md` / `README.md`：文档索引指向 `specs/`；`docs/superpowers/*` 大量迁移为指针文档。

### Removed

- `knowledge_retrieve_testharness.py`、旧 ACL smoke 测试（由新测试套件替代）。

### DB / Migrations

- **有迁移**；head：`20260522_122h_kb_tasks_worker`。
- 链：`122_schema` → `123_folder_resources` → `122g_bigpdf_refactor` → `08cd345b6500`（`parent_folder_id`）→ `122h`（worker 列）。
- **非破坏性**：`ADD COLUMN IF NOT EXISTS` + 索引 `IF NOT EXISTS`。
- 上线：`alembic -c backend/alembic.ini upgrade head`（生产若停在 `122g`，须连升至 `122h` 否则 worker 缺列）。

### Docs

- 新增 `docs/hermes.md`；BigPDF 重构计划标注为历史设计。
- `docs/reference/` 改为本地参考图目录（不入 Git）。
- `docs/hermes.md` §4：澄清 Hermes 上游 MCP 仅 connect-time env；生产多用户统一 `hermes_session_key` + token bridge（非静态 `ORIENTG_USER_TOKEN`）。
- 新增根目录 `待更新计划.md`：§1 记录「Hermes 页面互动书写 Skill 并全站配置」（待规划，未实现）。

---

## [1.2.1.1] - 2026-04-13

### Changed

- 待更新计划：修正「已完成/待完成」标注与序号，统一从上到下重排（内部规划 `规划/待更新计划.md`，不入 GitHub）。
- 股权全景（实验）：强调该能力为临时增加、后续可能移除（文档与版本说明同步）。

### DB / Migrations

- 新增 Alembic 迁移链（`backend/alembic/versions/`），用于落地「知识库文件夹 / 文件夹资源绑定 / 合同台账」等结构变更。
  - **非破坏性**：仅新增表/索引与 `ADD COLUMN IF NOT EXISTS`（无 drop column、无类型强转、无唯一约束收紧）。
  - 上线需执行：`alembic -c backend/alembic.ini upgrade head`。

### Docs

- `README.md`：版本号更新至 1.2.1.1，并补充本次变更说明。
- `CHANGELOG.md`：新增 1.2.1.1 条目。

---

## [1.2.1] - 2026-04-10

### Added

- **股权全景（实验）**：参考公司股权架构图能力——`/equity` 及相关分析/对比/目标页增强；后端 `GET /api/equity/*` 图谱与地理等接口扩展。**本能力为临时增加，后续可能移除**，部署与验收请以 README 与 `docs/api-contract.md` 摘要为准。

### Changed

- 部署与运行：`docker-compose.yml`、`.env.example` 等与内网 Ollama/队列等约定对齐的小幅更新。
- 流程文档页、分析/对比/财务等页面的交互与展示调整（与股权全景联动处）。

### Docs

- `docs/api-contract.md`：补充「股权全景（实验性）」API 摘要。
- `README.md`：版本号与股权全景实验能力说明。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：项 16（Week 0 安全与运维）已完成；项 17（队列与观测）维持已完成状态。

---

## [1.2.0] - 2026-03-10

### Added

- 知识库文档管理：用户上传文档（list/upload/delete）与「共享到」不同知识库类型的能力。
- 知识库权限模型：新增知识库类型默认可读策略、特殊文档 ACL 覆盖、RAG 包列表与展示（知识库页右栏）。
- 管理后台知识库设置：默认可读勾选与特殊文档读权限勾选（简化视图，便于验收）。

### Changed

- MultiDept/MultiProject：文档可读范围按共享时选择的部门/项目（`share_scope`）过滤，而非“全员可读”。

### Docs

- `docs/api-contract.md`：补齐知识库相关 API 契约（options、我的文档、共享、后台默认策略、特殊文档与 share_scope）。
- `README.md`：补齐 Windows/venv 启动建议与知识库验收说明/测试账号。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：完成项 12、14、17、20、21 并标注。

---

## [1.1.5] - 2026-03-10

### Changed

- 会话超时：JWT 有效期由 30 分钟调整为 60 分钟，/me 滑动刷新同步。
- 汇率趋势页：拖动 Brush 滑块时不再误触发主图平移；cursor/pan 仅作用于主图区域。

### Fixed

- 汇率取数日志：`exchange_rates.py` 中 `url if "url" in dir()` 改为 `locals().get("url", api_base)`，避免依赖 `dir()` 作用域。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：新增项 15「后台鉴权（同时考虑用户信息使用数据库）」；v1.1.5 无新完成项。

---

## [1.1.4] - 2026-03-10

### Changed

- 代码梳理与冗余清理：经营数据解析合并默认结构（`_empty_overview` 统一），去除重复初始化。
- 文档同步：api-contract 补充 `policy-news/item`、`exchange/status` 接口说明；待更新计划标注 v1.1.4 维护版。
- 新增 `规则/提交检查清单.md`：提交前可复用检查项（该目录不上传 GitHub）。

---

## [1.1.3] - 2026-03-10

### Added

- 知识库入口与展位页：侧栏新增「知识库」、路由 `/knowledge`，页面分两块——外部知识库、内部知识库（展位，待后续对接）。
- 新闻政策卡片交互：鼠标移入时由「缩略图+标题」切换为「标题+预览」，预览区增加上滑动画（max-h + translate-y 过渡）。
- Open Graph / Twitter 分享元数据：`generateMetadata` 动态 baseUrl，新增 og-image.png（1200x630）供链接预览。

### Changed

- proxy 后台路径：直接请求后端取 admin_path，增加 5 秒内存缓存，保存路径后最多约 5 秒生效；admin 页提示同步更新。
- AuthGuard：路由切换时鉴权结果 5 秒缓存，减少重复请求。
- 竞品、新闻政策、实用工具页：副标题统一为展位/待接入表述。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：项 13「知识库入口与展位页」、项 14「新闻政策卡片上滑动画」已实现并标注。

---

## [1.1.2] - 2026-03-06

### Added

- 无新增功能（本版以体验与文档为主）。

### Changed

- 侧边栏不随页面变化而刷新：AuthGuard 仅在首次鉴权时显示全屏「加载中…」，路由在已鉴权范围内切换（如经营数据 ↔ 汇率趋势 ↔ 新闻政策）时保持 DashboardLayout 挂载，在后台静默鉴权，避免侧边栏每次切换都闪烁或重置。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：项 11「新闻政策页」已实现并标注。
- [docs/汇率-PostgreSQL排查.md](docs/汇率-PostgreSQL排查.md)：生产环境 Docker 部署补充「密码与 volume 一致性」说明（PostgreSQL 仅首次初始化时写密码，之后改 .env 不会更新库内密码；出现 password authentication failed 时的两种处理方式）；8.6 小结表增加对应行。

---

## [1.1.1] - 2026-03-04

### Added

- 经营数据页图表布局调整：左上利润趋势、左下项目利润对比、右侧整列为流水（实际 vs 目标）横向堆叠图；流水图支持完成率 Tooltip。
- 侧边栏可收放：默认收拢，外置收放按钮靠上；收拢仅图标、展开图标+文字；标题区取消，导航与页面标题上沿对齐；标题文案「财务内网」、展开宽度适配（w-40）。
- 汇率趋势页滚轮缩放：以鼠标位置为锚点，向上缩小显示天数（最少 7 天）、向下拉长至全量；与下方 Brush 同步。
- 汇率趋势页主图与 Brush 分离：主图仅展示当前选中范围，横轴刻度随可见天数自适应（≤7 天全显示、>7 天约 12 个刻度）；纵轴与标题左对齐、Brush 与横轴两端对齐；Brush 仅 traveller 蓝色高亮。
- 汇率趋势页币种切换为分段控制器样式；按钮组与图表横轴右对齐。

### Changed

- 经营数据：流水区块解析改为 10 列（与利润一致）；副标题改为「数据由财务于后台上传 Excel 表…」并置于右上右对齐；去掉刷新数据按钮；项目利润对比标题改为「项目利润（本年 vs 去年）」；柱条渐变改为颜色到 3/4 透明；柱条粗细统一 barSize 30；流水/利润对比 Tooltip 深色 cursor。
- 侧边栏：去掉「U1-财务」标题，导航顶对齐、展开宽度 w-40。
- 汇率趋势页：背景网格线加强（stroke 0.14、dash 3 3）；纵轴宽度 40px；去掉数据拉取中提示的页面展示。

### Fixed

- 汇率趋势页图表纵向无限拉长：主图与 Brush 分两段布局，主图区域 flex-1 min-h-0、Brush 区 shrink-0 固定高度。
- 汇率趋势页滚轮缩放：handleChartWheel 移至 chartData 定义之后，消除「chartData before initialization」报错。

### 文档与计划

- 内部规划更新（`规划/待更新计划.md`，不入 GitHub）：项 9「更新汇率趋势图缩放方式」已实现并标注。

---

## [1.1.0] - 2026-03-06

### Added

- 财务后台「用户管理」：支持多用户，现有用户列表、新增用户（仅填用户名，默认密码 123456）、重设为默认密码、删除用户（至少保留一名）。
- 前端 API 代理（`/api/*` → 后端）：由 `app/api/[[...path]]/route.ts` 转发请求并转发 Authorization/X-Auth-Token，保证关闭标签页后仅靠 sessionStorage 的 token 失效、重新打开需登录；生产 Docker 通过 `API_URL`/`API_BASE_SERVER` 指定后端地址。
- 登录态：token 存 sessionStorage + 请求头传递，关闭标签页即失效；后端仅从 Authorization/X-Auth-Token 读取，不读 Cookie；首次/默认密码登录须修改密码且不能改为 123456。
- 管理后台页面：标题改为「管理后台」；布局顺序为上传经营数据 → 用户管理 → 设置后台路径 → 启用登录。
- Next.js 16：middleware 迁移为 proxy（`proxy.ts`），消除弃用告警。
- 生产 Docker：后端支持 `AUTH_SECRET` 环境变量；README 与 .env.example 注明生产务必设置 AUTH_SECRET。

### Changed

- 财务后台路径、用户列表与登录开关存于 `uploads/app_settings.json`；用户列表为 `users` 数组，兼容旧版单用户 `admin_username`/`admin_password_hash` 自动迁移。
- 密码存储：SHA256 + bcrypt，兼容旧版 passlib 哈希；登录成功后统一为新格式。
- 会话：JWT 30 分钟、/me 滑动刷新；关闭标签页后需重新登录。

### Fixed

- 登录后持续跳转登录页：增加 `authCheckDone` 与在登录页清空，避免鉴权未完成即 redirect；/me 失败 502 或网络错误时自动重试一次；登录成功后短暂延迟再跳转以减轻冷启动影响。
- POST 代理 duplex 报错：转发 body 时设置 `duplex: "half"`。
- 代理错误时返回 JSON 而非 HTML，避免前端解析错误导致登录态错乱。

---

## [1.0.0] 及更早

### Added

- 内部新增待更新计划（`规划/待更新计划.md`，不入 GitHub），用于罗列待办并在实现后标注已更新。
- 新增本 CHANGELOG，约定每次项目有更新时在此追加条目。

### Changed

- 财务后台默认路径为 `/admin`，可在财务后台页面修改；修改后的路径仅存于后端配置（app_settings.json），代码库中不体现。
