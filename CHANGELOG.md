# Changelog

本文件记录项目更新。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本/日期按发布记录。

## [Unreleased]

（后续改进在此追加。）

---

## [1.1.3] - 2026-03-10

### Added

- 知识库入口与展位页：侧栏新增「知识库」、路由 `/knowledge`，页面分两块——外部知识库、内部知识库（展位，待后续对接）。
- 新闻政策卡片交互：鼠标移入时由「缩略图+标题」切换为「标题+预览」，预览区增加上滑动画（max-h + translate-y 过渡）。

### 文档与计划

- [docs/待更新计划.md](docs/待更新计划.md)：项 13「知识库入口与展位页」、项 14「新闻政策卡片上滑动画」已实现并标注。

---

## [1.1.2] - 2026-03-06

### Added

- 无新增功能（本版以体验与文档为主）。

### Changed

- 侧边栏不随页面变化而刷新：AuthGuard 仅在首次鉴权时显示全屏「加载中…」，路由在已鉴权范围内切换（如经营数据 ↔ 汇率趋势 ↔ 新闻政策）时保持 DashboardLayout 挂载，在后台静默鉴权，避免侧边栏每次切换都闪烁或重置。

### 文档与计划

- [docs/待更新计划.md](docs/待更新计划.md)：项 11「新闻政策页」已实现并标注。
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

- [docs/待更新计划.md](docs/待更新计划.md)：项 9「更新汇率趋势图缩放方式」已实现并标注。

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

- 新增 [docs/待更新计划.md](docs/待更新计划.md)，用于罗列待办并在实现后标注已更新。
- 新增本 CHANGELOG，约定每次项目有更新时在此追加条目。

### Changed

- 财务后台默认路径为 `/admin`，可在财务后台页面修改；修改后的路径仅存于后端配置（app_settings.json），代码库中不体现。
