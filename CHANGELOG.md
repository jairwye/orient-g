# Changelog

本文件记录项目更新。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本/日期按发布记录。

## [Unreleased]

（后续改进在此追加。）

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
