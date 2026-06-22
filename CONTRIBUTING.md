# Orient-G 协作开发指南（Contributing）

本文档用于多人协作开发时的**统一口径**，确保新同事能快速上手、避免环境/迁移/发布踩坑。

| 你想… | 读哪里 |
|--------|--------|
| 本地安装、启动、迁移 | `README.md` |
| 分支、PR、提交、校验 | **本文档** |
| API 契约 | [`specs/api/api-contract.md`](specs/api/api-contract.md) |
| **UI/功能规制与实施计划** | [`specs/README.md`](specs/README.md) |
| 排查手册、参考截图 | [`docs/README.md`](docs/README.md) |
| 强制约束、版本路线图（内网） | `规则/`、`规划/`（不上传 GitHub，见各目录 `文档索引.md`） |

---

## 1. 快速开始（建议顺序）

- 先读 `README.md` 完成本地环境与启动（前端/后端/本机 PostgreSQL）。
- 再读 [`specs/api/api-contract.md`](specs/api/api-contract.md)：理解前后端契约与模块边界。
- 若你要改 **UI 或较大功能**：先查 [`specs/`](specs/README.md) 是否已有规制/计划（例如 [`specs/ui/ai-interaction.md`](specs/ui/ai-interaction.md)）。
- 若你要改数据库结构：先读 `README.md` 的「数据库结构迁移（Alembic）」并遵守下文「DB 迁移约束」。

---

## 2. 分支与合并策略（建议）

- **主分支**：`main`（或仓库实际默认分支），保持可部署。
- **功能分支命名**（二选一即可）：
  - `feature/<short-desc>`（新功能）
  - `fix/<short-desc>`（修复）
- **合并方式**：优先使用 PR 合并；避免在主分支直接提交。
- **GitHub 仓库侧的保护与权限配置（建议）**：开启 `main` 分支保护（Require PR、至少 1 人审批、required checks、conversation resolution），并统一合并策略（推荐 squash）。

---

## 3. 提交（commit）与 PR（建议）

- **提交粒度**：一次提交尽量只做一类事情（一个功能/一类修复/一次迁移）。
- **提交信息**：首行简洁说明“做了什么 + 为什么”，必要时在正文补充风险点（尤其是 DB 迁移与破坏性变更）。
- **PR 描述至少包含**：
  - Summary：做了什么、影响范围
  - Test plan：你如何验证（本地启动、关键页面/接口抽查）
  - DB / Migrations：是否包含迁移、上线如何执行、是否破坏性

---

## 4. 代码质量与本地验证（提交前最低要求）

### 前端（在 `frontend/`）

- **每次改动**：`npm run lint`（CI 门槛：0 warnings）
- **push 到 `main` 前**（涉及 frontend）：`npm run build`  
  Docker CI 在镜像内执行 `next build`，会跑 ESLint；仅 lint 通过不代表 build 一定过。
- **可选、最接近 CI**（需 Docker，约 5–15 分钟）：在仓库根目录  
  `.\scripts\ci-docker-build-local.ps1`  
  构建 backend + frontend 本地镜像，**不 push**；frontend 默认 `--no-cache` 与 workflow 一致。加速可加 `-CacheFrontend`。

### 后端（仓库根目录）

- `python -m pytest -q`（如本仓库存在测试）

> 若你本次改动不涉及某端，可说明原因，但不要跳过与改动相关的校验。

---

## 5. 数据库结构变更（DB / Migrations）硬约束

### 5.1 什么时候算“结构变更”

包括但不限于：新表/删表、加字段/删字段、索引、唯一约束、外键、枚举/类型、默认值、not null 等。

### 5.2 强制要求（不满足就不要合并/发布）

- **必须**提供 Alembic 迁移脚本并提交到 git：`backend/alembic/versions/`
- 禁止“只改开发库/生产库的结构但不写迁移脚本”
- 禁止把破坏性 SQL 放到服务启动路径里自动执行（上线必须可控、可回滚）

### 5.3 多人协作常见坑：多 head

- 合并前必须确保迁移头唯一：`alembic heads` 只能有 1 个 head  
  若出现多个 head：需要 `alembic merge` 生成合并迁移并一并提交（避免生产升级路径不唯一）。

### 5.4 破坏性变更必须分阶段发布

以下任一情况都属于高风险：`DROP COLUMN`、改类型、加唯一约束但可能已有重复数据、加 not null 且无默认值。  
要求：按“先兼容、后清理”的两次发布策略执行，并明确备份点与回滚方案。

---

## 6. 文档与契约同步（协作必做）

- API 形状或语义变更：同步更新 [`specs/api/api-contract.md`](specs/api/api-contract.md)
- **UI 或页面级行为变更**：先更新 [`specs/`](specs/README.md) 中对应规制（如 `specs/ui/<page>.md`），再改 `frontend/`
- 功能规制 / 实施计划：写在 `specs/features/`、`specs/plans/`，勿在 `docs/superpowers/` 新增正文
- 新增/变更环境变量：同步更新 `.env.example` 与 `README.md` 中对应说明
- 发版变更：更新 `changelog.md`（并在 Unreleased/版本条目里注明是否有 DB 迁移）

---

## 7. 产品 Agent Skill 与开发机 Cursor 技能（边界）

术语总表与表格化对照见 [`docs/agent-skills-glossary.md`](docs/agent-skills-glossary.md) 第 6 节。

本仓库《规则》中「Agent Skill 包仅来自本仓或内网配置」等表述，**在协作上按下述范围理解**，避免与 Cursor 生态里的第三方技能包混淆。

### 7.1 产品侧（对内网交付物生效）

- **唯一登记入口**：`backend/data/agent_skills/manifest.json` 中列出的技能 ID。
- **唯一指令体来源**：与各 ID 对应的 `backend/data/agent_skills/<skill_id>/SKILL.md`（由后端加载，见 `backend/services/agent_skills_loader.py`）。
- **交付物**：随仓库/内网构建发布的应用与配置中，**仅**上述路径下的 Agent Skill 属于「Orient-G 产品登记技能」；须遵守 `docs/skills-guidelines.md` 与《规则》中的内网、本地化 AI、数据不外泄等约束。

### 7.2 开发机侧（可选，不等同于产品技能）

以下安装在**开发者本机 Cursor** 目录或插件缓存中，用于本地写代码、跑计划文档中的 agentic 工作流提示等，**不属于**上一节的产品登记范围，**也无需**写入 `manifest.json`：

- **Cursor Superpowers 等插件**及其随插件分发的技能（如 `superpowers:*` 工作流；产品规制已迁到 [`specs/plans/`](specs/plans/)）。
- **[gstack](https://github.com/garrytan/gstack)**（若个人安装）：与本仓库产品技能**分列**；**不得**将 gstack 登记进 `manifest.json`，**不得**将 gstack 作为 Orient-G 内网交付物或运行时依赖打包进发布产物。

### 7.3 使用提醒

开发机工具**不免除**《规则》对**业务数据、对话、代码**不外泄、不违规使用外网能力等要求；若使用带浏览器、外网模型、遥测等能力的工具，仍须遵守公司与项目安全策略。

---

## 8. 常见问题（FAQ）

- **为什么我看不到 `规则/`、`规划/`？**  
  这两个目录按仓库约定不上传到 GitHub；对内见 `规则/文档索引.md`、`规划/文档索引.md`。对外协作请以 `README.md`、`specs/`、`docs/`、`CONTRIBUTING.md` 为准。

- **`CONTRIBUTING.md` 是干什么的？**  
  对外（含 GitHub）协作的**操作手册**：怎么装环境、怎么提 PR、怎么跑 lint/test、DB 迁移硬约束、文档写在哪。不替代 `规则/` 里的安全与架构约束，也不替代 `specs/` 里的 UI 规制。

- **为什么 Windows 下没问题，部署到 Linux/容器就报找不到文件？**  
  常见原因是路径大小写不一致。仓库里版本记录文件为 `changelog.md`（全小写），请按实际文件名引用。

