# Orient-G 文档（`docs/`）

本目录存放**参考材料、实施手册、契约与归档**。**规制与实施计划**在仓库根目录 [`specs/`](../specs/README.md)。

---

## 分类

| 子目录 / 文件 | 类型 | 说明 |
|---------------|------|------|
| [`specs/`](../specs/)（根目录） | **规制 + 计划** | UI/功能规制、实施计划（改代码前优先查阅） |
| [`reference/`](reference/) | 参考 | 外部对标截图与说明（如 Kimi），**不约束实现** |
| [`guides/`](guides/) | 手册 | 环境、排查、迁移操作（逐步迁入） |
| [`archive/`](archive/) | 归档 | 过时方案，文首注明 superseded |
| [`specs/api/api-contract.md`](../specs/api/api-contract.md) | 契约（规制） | 前后端 API 约定；`docs/api-contract.md` 为重定向 |
| [`agent-skills-glossary.md`](agent-skills-glossary.md) | 术语 | Skill / Tool / Prompt 对照 |
| [`skills-guidelines.md`](skills-guidelines.md) | 指南 | 产品 Agent Skill 登记规范 |
| [`bigpdf-refactor-plan.md`](bigpdf-refactor-plan.md) | 归档候选 | 历史方案，以代码为准 |

仍位于 `docs/superpowers/` 的文件仅为**迁移重定向 stub**，正文见 `specs/`。

**与实现一致性审计**：[DOC-IMPLEMENTATION-AUDIT.md](DOC-IMPLEMENTATION-AUDIT.md)（不定期更新）。

---

## 手册类（根目录 `docs/*.md`，待迁入 `guides/`）

| 文件 | 用途 |
|------|------|
| [kb-vector-dev-setup.md](kb-vector-dev-setup.md) | 知识库向量开发环境 |
| [汇率-PostgreSQL排查.md](汇率-PostgreSQL排查.md) | 汇率与数据库排查 |
| [断网排查与ollama拉取.md](断网排查与ollama拉取.md) | 网络与 Ollama |
| [全局DoT稳定DNS（NetworkManager+systemd-resolved）.md](全局DoT稳定DNS（NetworkManager+systemd-resolved）.md) | DNS |
| [fpa-agent-audit-and-metrics-design.md](fpa-agent-audit-and-metrics-design.md) | FPA 审计设计（偏方案，可迁 `specs/features/`） |

---

## 内部目录（不上传 GitHub）

| 目录 | 说明 |
|------|------|
| [`规则/`](../规则/) | 强制约束 → [规则/文档索引.md](../规则/文档索引.md) |
| [`规划/`](../规划/) | 方案与路线图 → [规划/文档索引.md](../规划/文档索引.md) |

对外协作以 `README.md`、`CONTRIBUTING.md`、`docs/`、`specs/` 为准。
