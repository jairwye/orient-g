# 还原 uploads/business.xlsx

经营数据页只读 **`UPLOAD_DIR/business.xlsx`**（本地默认 `项目根/uploads/business.xlsx`）。该目录在 `.gitignore` 中，**Git 无法恢复**。

## 1. Synology Drive 历史版本（优先）

1. 打开 **Synology Drive** 网页或客户端。
2. 进入：`游艺春秋/Projects/orient-g/uploads/`
3. 若存在 `business.xlsx`：右键 → **浏览历史版本** / **版本历史**，选 **2026-05-25 15:43 之前** 的版本还原。
4. 若文件已被删：在 Drive **回收站** 中查找 `business.xlsx` 后还原。

还原后刷新经营数据页（`/`）。

## 2. 从生产/其他机器拷贝

若生产 Docker 使用 volume `uploads_data`：

```bash
# 在部署机上（示例）
docker compose exec backend ls -la /app/uploads/business.xlsx
docker compose cp backend:/app/uploads/business.xlsx ./business.xlsx
```

拷到本机：

`Projects/orient-g/uploads/business.xlsx`

## 3. 从财务原始表重新上传

管理员登录 → **财务后台** `/finance` → 上传经营数据 Excel（覆盖 `business.xlsx`）。

## 4. 开发样例（仅演示，非真实数据）

```powershell
.\.venv\Scripts\python.exe scripts\seed_business_dashboard_xlsx.py
```

当前会话曾生成的样例已改名为：`uploads/business.xlsx.dev_seed_backup_20260525`（约 5.5KB，流水 12580 等为假数据）。
