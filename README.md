# clockdrift — 服务器时钟漂移体检

单文件 / 零依赖 / 只读的 NTP 时钟体检 CLI。一次对多台 NTP 服务器真实对时，
算出本机时钟偏移，按可配置阈值给出 `OK / WARN / CRIT / ERR` 判定与退出码，
cron 和监控脚本拿来就能用。

## 为什么需要它

- 日志排序乱、TLS 握手失败、Kerberos/JWT 报「时间无效」，九成是时钟漂了
- `ntpdate` 已被弃用；`chronyc tracking` 只看单一上游，上游抽风你以为自己漂了
- 监控脚本要的不是人类可读的表格，是**退出码**：0/1/2/3 直接接告警

clockdrift 的做法：多服务器交叉采样取中位数（单台抽风不背锅）、
应答回显校验防伪包（I1）、单样本尖峰升级告警（抖动可见）、
全部不可达时退出 3 绝不编造偏移（I6）。

## 快速开始

```bash
# 体检一轮（默认 4 台 NTP，每台采样 3 次取中位）
python3 clockdrift.py check

# 只看结论级别 + JSON（给监控用）
python3 clockdrift.py check --json

# 严格模式：偏移超过 200ms 就 WARN，1s 判 CRIT
python3 clockdrift.py check --warn-ms 200 --crit-ms 1000

# 已知本机设备刻意慢 300ms（良性），判定时扣除
python3 clockdrift.py check --expect-offset-ms 300

# 持续盯：60 秒一轮，共 10 轮，落盘 JSON
python3 clockdrift.py watch --interval 60 --count 10 --json --out drift.json

# 自测（离线 7 项 + 真实 NTP 1 项）
python3 selftest.py --live
```

## 退出码

| 码 | 含义 |
|----|------|
| 0 | OK，偏移在阈值内 |
| 1 | WARN，超过 warn-ms |
| 2 | CRIT，超过 crit-ms |
| 3 | ERR，网络/参数不可用（不编造偏移） |

## 八条不变量

| # | 不变量 |
|---|--------|
| I1 | 应答回显校验：originate 必须等于我方 transmit，错包/重放直接丢弃 |
| I2 | 偏移 sanity：|offset| ≥ 1 天视为时钟坏死，直接 CRIT |
| I3 | stratum ≥ 1 才可用，stratum=0 拒绝 |
| I4 | leap indicator=3（闹钟）只披露不采纳 |
| I5 | 多服务器互相校验，各台差异过大披露「不对称」线索 |
| I6 | 全部服务器不可达 → 退出 3，绝不编造 offset |
| I7 | RTT 一律 `time.monotonic()`，不受系统跳变影响 |
| I8 | 默认零写盘，除 `--out` 外不落任何文件 |

## 参数

```
--host            逗号分隔 NTP 服务器（默认 cn.pool.ntp.org,ntp.aliyun.com,time.windows.com,pool.ntp.org）
--samples N       每台采样次数，判定取中位数（默认 3）
--warn-ms N       WARN 阈值毫秒（默认 500）
--crit-ms N       CRIT 阈值毫秒（默认 2000）
--timeout N       单次 NTP 超时秒（默认 5）
--expect-offset-ms N  已知良性偏移基线，判定时扣除（默认 0）
--json            机读输出
--out FILE        报告落盘（默认仅 stdout）
-v                预留
watch 子命令      --interval 秒 / --count 轮数（0=无限）
```

## 设计取舍

- **UDP/123 标准客户端协议**，不依赖 ntpd/chronyd 是否装了、也不需要 root
- **中位数而非均值**：均值会被尖峰拖走，中位数对 3 台里 1 台抽风免疫
- **尖峰升级而不是吞掉**：中位正常但有单样本 CRIT → 整体 WARN，抖动不该不可见
- **--expect-offset-ms 兜底**：有些场景时钟本来就「刻意偏」（录像机回放、离线补录），
  阈值判定应扣基线而不是逼你把阈值拉到天级

## License

MIT
