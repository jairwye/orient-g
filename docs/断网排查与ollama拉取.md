# 断网排查与 Ollama 拉取指南

服务器在拉取 Ollama 模型时曾出现「Network error: Software caused connection abort」后无法连上，恢复时 `uptime` 显示刚重启。本文档说明：如何用 tmux/screen 安全拉取、如何留意内存与稳定性、以及断网/重启后如何取证。

---

## 1. 用 tmux 跑 `ollama pull`（推荐）

拉取大模型时 SSH 可能断或会话超时，用 tmux 可让任务在服务器上持续运行，断线后重连即可恢复。

### 安装 tmux（若未装）

```bash
sudo apt update && sudo apt install -y tmux
```

### 每次拉模型

```bash
# 新建名为 ollama 的会话
tmux new -s ollama

# 在容器内拉模型（容器名按实际修改，如 ollama）
docker exec -it ollama ollama pull qwen3:8b-q4_K_M

# 断开会话但保持运行：Ctrl+B 再按 d（detach）
# 或拉完后直接 exit 结束会话
```

### SSH 断线后恢复

```bash
tmux attach -t ollama
```

### 使用 screen 的等价方式

```bash
screen -S ollama
docker exec -it ollama ollama pull qwen3:8b-q4_K_M
# 断开会话：Ctrl+A 再按 d
# 重连：screen -r ollama
```

---

## 2. 拉模型时留意内存与稳定性

- 另开一个 SSH 会话（或 tmux 新窗口），在**宿主机**执行：

  ```bash
  watch -n 2 'free -h; echo "---"; uptime'
  ```

  或偶尔看一次：

  ```bash
  free -h && uptime
  ```

- 关注 `free -h` 里的 **available** 和 **swap**：若 available 很少且 swap 用满，可能触发 OOM 或卡死，可先停掉其它占内存服务或改用更小/量化模型。

- 拉模型期间尽量避免其它重负载（大编译、其它容器大量占内存等）。

---

## 3. 再次出现「拉模型后连不上」时的取证

重新能 SSH 登录后**立刻**执行（避免新日志覆盖上一 boot）：

```bash
# 查看上一轮关机前最后约 200 条日志
journalctl -b -1 -n 200 --no-pager

# 保存到文件，便于后续分析（文件名带时间戳）
journalctl -b -1 -n 200 --no-pager > ~/last_boot_$(date +%Y%m%d_%H%M).log
```

在保存的文件中搜索可能的诱因：

```bash
grep -iE "oom|kill|oom_reaper|out of memory|error|fail|thermal|acpi|watchdog|reboot|shutdown" ~/last_boot_*.log
```

**建议**：把「能登录后立刻执行上述 journalctl 并保存」记入个人或团队检查清单，避免忘记。

---

## 4. 小结

| 事项 | 操作 |
|------|------|
| 以后用 tmux 跑 ollama pull | `tmux new -s ollama` → 在会话内执行 `docker exec -it ollama ollama pull ...`，断线后 `tmux attach -t ollama` |
| 留意内存与稳定性 | 另开终端执行 `watch -n 2 'free -h; uptime'`，关注 available 与 swap |
| 再次出现拉模型后连不上 | 能登录后立刻执行 `journalctl -b -1 -n 200 --no-pager > ~/last_boot_$(date +%Y%m%d_%H%M).log`，再在文件中搜索 oom/error/thermal 等关键字 |

补充：如果你的症状更像 **DNS 解析抖动**（`systemd-resolved` 反复降级、`Total Timeouts` 增长、或 Docker 刷 `127.0.0.53 i/o timeout`），参考：

- `docs/全局DoT稳定DNS（NetworkManager+systemd-resolved）.md`
