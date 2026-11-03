# Changelog

## 1.0.0 (2026-11-03)

- 首发版：`check` / `watch` 双子命令，单文件零依赖，只读
- 多服务器交叉采样 + 中位数判定 + 单样本尖峰升级（WARN）
- 八条不变量：I1 回显防伪 / I2 坏死判定 / I3 stratum 门槛 / I4 leap 披露 /
  I5 不对称披露 / I6 离线确定性 / I7 monotonic RTT / I8 默认零写盘
- `--expect-offset-ms` 良性基线扣除，`--json` 机读输出，退出码 0/1/2/3
- 自测 40 项全绿（离线 7 组 + LIVE 真实 NTP 1 组）
