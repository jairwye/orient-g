# 全局 DoT 稳定 DNS（NetworkManager + systemd-resolved）

适用场景：Ubuntu 24.04（或同系）使用 **NetworkManager** 管理网卡，DNS 由 **systemd-resolved** 提供 stub（`127.0.0.53`）。当出现如下现象时优先考虑本方案：

- `systemd-resolved` 日志反复出现 `Using degraded feature set UDP instead of UDP+EDNS0 ...`
- `sudo resolvectl statistics` 中 `Total Timeouts` 持续增长
- Docker/容器侧出现 `dockerd ... dns-server="udp:127.0.0.53:53" ... i/o timeout`

本文目标：将系统全局 DNS 优先迁移到 **DNS over TLS（DoT / TCP 853）**，并用 **opportunistic** 策略（可用则用，不可用自动回退），以绕开 UDP/EDNS0 在链路/网关/中间设备上的不稳定因素。

> 说明：本文假设你不依赖公司内网域名解析（仅公网域名）。如依赖内网域名，请不要直接照抄 DNS 列表。

---

## 0）快速自检（确认 DoT 端口可用）

```bash
# Cloudflare DoT（1.1.1.1:853）
timeout 3 bash -lc 'echo | openssl s_client -connect 1.1.1.1:853 -servername cloudflare-dns.com 2>/dev/null | head -n 1'
```

预期输出包含 `CONNECTED(...)`。

---

## 1）记录现状快照（用于对比与回滚）

```bash
set -e

echo "=== resolvectl status (all) ==="
resolvectl status

echo
echo "=== resolvectl statistics ==="
sudo resolvectl statistics

echo
echo "=== active NM connections ==="
nmcli -t -f NAME,UUID,TYPE,DEVICE,STATE con show --active

echo
echo "=== NM DNS settings (replace NAME) ==="
echo 'nmcli con show "netplan-enp3s0" | egrep -i "ipv4.dns|ipv4.ignore-auto-dns|ipv4.dns-priority|ipv4.method|ipv4.dns-search|ipv4.dns-options"'

echo
echo "=== resolved recent logs ==="
sudo journalctl -u systemd-resolved --no-pager -n 120
```

建议将上述输出保存为文件，便于前后对比：

```bash
mkdir -p ~/netdiag
{
  date
  resolvectl status
  sudo resolvectl statistics
  nmcli -t -f NAME,UUID,TYPE,DEVICE,STATE con show --active
  nmcli con show "netplan-enp3s0" | egrep -i "ipv4.dns|ipv4.ignore-auto-dns|ipv4.dns-priority|ipv4.method|ipv4.dns-search|ipv4.dns-options" || true
  sudo journalctl -u systemd-resolved --no-pager -n 120
} > ~/netdiag/dns_snapshot_$(date +%Y%m%d_%H%M%S).log
```

---

## 2）NetworkManager：固定公网 DNS + 忽略自动 DNS

以你当前连接名 `netplan-enp3s0` 为例：

```bash
sudo nmcli con mod "netplan-enp3s0" ipv4.dns "1.1.1.1 1.0.0.1"
sudo nmcli con mod "netplan-enp3s0" ipv4.ignore-auto-dns yes
sudo nmcli con down "netplan-enp3s0" && sudo nmcli con up "netplan-enp3s0"
```

验证 NM 侧已生效：

```bash
nmcli con show "netplan-enp3s0" | egrep -i "ipv4.dns|ipv4.ignore-auto-dns|ipv4.method"
```

---

## 3）systemd-resolved：启用 DoT（opportunistic）并指定 SNI

创建 drop-in（不直接改动原文件更安全、也更好回滚）：

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/dot.conf >/dev/null <<'EOF'
[Resolve]
DNSOverTLS=opportunistic
DNS=1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com
FallbackDNS=9.9.9.9#dns.quad9.net 149.112.112.112#dns.quad9.net
EOF

sudo systemctl restart systemd-resolved
```

> 说明：`IP#hostname` 的写法会用 `hostname` 做 TLS SNI/证书匹配，避免“连上了但证书不对”的隐性失败。

---

## 4）验证（必须做）

### 4.1 DoT 是否开启

```bash
resolvectl status enp3s0
```

预期看到 `Protocols` 中包含 `+DNSOverTLS`（且不再是 `-DNSOverTLS`）。

### 4.2 解析是否稳定

```bash
resolvectl query api.github.com
resolvectl query github.com
```

### 4.3 timeout 是否停止增长（关键）

间隔 10-30 分钟对比两次：

```bash
sudo resolvectl statistics
```

预期 `Total Timeouts` 不再快速增长。

### 4.4 resolved 是否还在“降级循环”

```bash
sudo journalctl -u systemd-resolved --no-pager -n 200
```

预期不再频繁出现 `Using degraded feature set ...`。

### 4.5 Docker/容器侧是否还在刷 resolver timeout

```bash
sudo journalctl -u docker --no-pager -n 200 | egrep -i "resolver|127\.0\.0\.53|timeout|i/o timeout" || true
```

---

## 5）回滚（最小回滚）

### 5.1 回滚 systemd-resolved 的 DoT 配置

```bash
sudo rm -f /etc/systemd/resolved.conf.d/dot.conf
sudo systemctl restart systemd-resolved
```

### 5.2 回滚 NetworkManager 的 DNS 固定

将 `ignore-auto-dns` 恢复为 `no`，并清空手工 DNS（或改回你原来的 DNS）：

```bash
sudo nmcli con mod "netplan-enp3s0" ipv4.ignore-auto-dns no
sudo nmcli con mod "netplan-enp3s0" ipv4.dns ""
sudo nmcli con down "netplan-enp3s0" && sudo nmcli con up "netplan-enp3s0"
```

---

## 6）常见坑

- **只改 NM 不改 resolved**：可能仍会走明文 UDP，且继续触发 EDNS0 降级；建议两者一起做。\n+- **只改 resolved 不固定 NM**：DHCP/网关可能继续下发不稳定 DNS，导致解析路径不可控。\n+- **内网域名需求**：如果你需要解析公司内部域名，请不要直接把 DNS 改成公网；应保留公司 DNS 或做分域解析。\n+
