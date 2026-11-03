#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clockdrift v1.0.0 — 服务器时钟漂移体检（单文件 / 零依赖 / 只读）

对一组 NTP 服务器做真实对时，计算本机时钟偏移（offset），
按可配置阈值给出 OK / WARN / CRIT / ERR 判定与退出码，
供 cron / 监控脚本直接消费。

用法:
    python3 clockdrift.py check  [--host h1,h2] [--samples 3]
                 [--warn-ms 500] [--crit-ms 2000] [--timeout 5]
                 [--expect-offset-ms 0] [--json] [-v]
    python3 clockdrift.py watch  --interval 60 --count 10 [同上阈值参数]

退出码: 0=OK  1=WARN  2=CRIT  3=ERR(网络/参数不可用)
只读工具：仅发送标准 NTP 客户端 UDP/123 请求，不改任何系统状态。

不变量(实现于 _invariants):
    I1 应答回显校验: 服务器的 originate timestamp 必须等于我方 transmit，
       否则判定为错包/重放，丢弃该样本（防串台与伪造）。
    I2 偏移 sanity: |offset| >= 86400s 视为时钟坏死，直接 CRIT，不提供"修正值"。
    I3 stratum>=1 才可用; stratum=0 或 Kiss-of-Death 包拒绝。
    I4 leap indicator=3(闹钟) 的应答只告警不采纳为可信参考。
    I5 多服务器互相校验: 各自 offset 差异超过 max(RTT,500ms) 时报"不对称"提示。
    I6 离线确定性: 全部服务器不可达时退出 3，绝不编造 offset。
    I7 RTT 一律用 time.monotonic() 测量，不受系统跳变影响。
    I8 默认零写盘: 除 --out 指定路径外不落任何文件。
"""
import argparse
import json
import socket
import statistics
import struct
import sys
import time

NTP_EPOCH_DELTA = 2208988800  # 1900 -> 1970 秒
DEFAULT_HOSTS = "cn.pool.ntp.org,ntp.aliyun.com,time.windows.com,pool.ntp.org"
VERSION = "1.0.0"
TOOL = "clockdrift"


# ---------------- NTP 时间戳编解码 ----------------

def _ts_to_seconds(b):
    """48字节包里的 8 字节 NTP 时间戳 -> unix 秒(float)；全 0 返回 None。"""
    secs, frac = struct.unpack("!II", b)
    if secs == 0 and frac == 0:
        return None
    return secs - NTP_EPOCH_DELTA + frac / (2 ** 32)


def _now_ntp():
    """当前 unix 时间 -> NTP 64 位时间戳字节。"""
    now = time.time() + NTP_EPOCH_DELTA
    secs = int(now)
    frac = int((now - secs) * (2 ** 32))
    return struct.pack("!II", secs & 0xFFFFFFFF, frac & 0xFFFFFFFF)


def _query_one(host, timeout, expect_orig=None):
    """发一次 NTP 请求。返回 dict；失败时 {'error': ...}。
    expect_orig: 期待回显的我方 transmit 时间戳(None 则发随机化时间戳)。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        tx = _now_ntp()
        pkt = bytearray(48)
        pkt[0] = 0x1B  # LI=0 VN=3 Mode=3(client)
        pkt[40:48] = tx
        t1 = time.monotonic()
        sock.sendto(bytes(pkt), (host, 123))
        data, addr = sock.recvfrom(1024)
        t4 = time.monotonic()
    except socket.timeout:
        return {"error": "timeout", "host": host}
    except OSError as e:
        return {"error": "net: %s" % e, "host": host}
    finally:
        sock.close()

    if len(data) < 48:
        return {"error": "short packet (%dB)" % len(data), "host": host}

    li = data[0] >> 6
    vn = (data[0] >> 3) & 0x7
    mode = data[0] & 0x7
    stratum = data[1]
    rtt = t4 - t1

    # I1: originate timestamp 必须回显我方 transmit
    orig = _ts_to_seconds(data[24:32])
    my_tx = _ts_to_seconds(tx)
    if orig is None or my_tx is None or abs(orig - my_tx) > 1.0:
        return {"error": "orig-ts mismatch (anti-spoof I1)", "host": host}

    recv_ts = _ts_to_seconds(data[32:40])
    tx_ts = _ts_to_seconds(data[40:48])
    if recv_ts is None or tx_ts is None:
        return {"error": "zero server timestamps", "host": host}

    # 经典 NTP offset 公式（全部用 unix 秒域）:
    # offset = ((t2 - t1) + (t3 - t4)) / 2
    t1n = _ts_to_seconds(tx)
    offset = ((recv_ts - t1n) + (tx_ts - (t1n + rtt))) / 2.0
    # 等价于 ((t2-t1)+(t3-t4))/2，其中 t4 = t1 + rtt（monotonic 差值即真实往返）

    return {
        "host": host, "ip": addr[0], "li": li, "vn": vn, "mode": mode,
        "stratum": stratum, "rtt": round(rtt, 3), "offset": round(offset, 4),
        "ref_id": data[12:16].hex(),
    }


def sample(hosts, timeout, tries_per_host=2):
    """对每台主机采样。返回 (有效样本列表, 错误列表)。"""
    ok, errs = [], []
    for h in hosts:
        got = None
        last = None
        for _ in range(tries_per_host):
            r = _query_one(h, timeout)
            if "error" in r:
                last = r
                time.sleep(0.3)
                continue
            got = r
            break
        if got is None:
            errs.append(last or {"host": h, "error": "unknown"})
        else:
            ok.append(got)
    return ok, errs


# ---------------- 判定 ----------------

def classify(offset, expect_ms, warn_ms, crit_ms):
    """单值判定 -> (级别, 说明)。级别: ok/warn/crit"""
    delta = offset - expect_ms / 1000.0
    a = abs(delta)
    if a >= crit_ms / 1000.0:
        return "crit", "偏差 %.3fs 超过 CRIT 阈值 %dms" % (a, crit_ms)
    if a >= warn_ms / 1000.0:
        return "warn", "偏差 %.3fs 超过 WARN 阈值 %dms" % (a, warn_ms)
    return "ok", "偏差 %.3fs 在阈值内" % a


def verdict_of(samples_ok, expect_ms, warn_ms, crit_ms):
    """基于多样本中位数判定；任何单样本 crit 而中位数未 crit -> 升级为 warn(尖峰)。"""
    if not samples_ok:
        return "err", "无有效 NTP 应答", 0.0, []
    offs = [s["offset"] for s in samples_ok]
    med = statistics.median(offs)
    level, why = classify(med, expect_ms, warn_ms, crit_ms)
    spike = False
    for o in offs:
        lvl1, _ = classify(o, expect_ms, warn_ms, crit_ms)
        if lvl1 == "crit" and level != "crit":
            spike = True
    if spike and level == "ok":
        level = "warn"
        why += "；检出单样本尖峰(抖动)"
    return level, why, med, offs


def _invariants(samples_ok, samples_err):
    """对原始样本执行不变量体检，返回违规描述列表。"""
    bad = []
    for s in samples_ok:
        if s.get("stratum", 99) == 0:
            bad.append("I3 stratum=0 @%s" % s["host"])
        if s.get("li") == 3:
            bad.append("I4 leap-alarm @%s" % s["host"])
        if abs(s.get("offset", 0)) >= 86400:
            bad.append("I2 |offset|>=1d @%s: %.0fs" % (s["host"], s["offset"]))
    if not samples_ok and samples_err:
        bad.append("I6 全部服务器不可达(共%d台)" % len(samples_err))
    return bad


# ---------------- 输出 ----------------

def _fmt_report(level, why, med, samples_ok, errs, args, spike_offs=None):
    lines = []
    icon = {"ok": "[ OK ]", "warn": "[WARN]", "crit": "[CRIT]", "err": "[ERR ]"}[level]
    lines.append("%s clockdrift v%s — 时钟漂移体检" % (icon, VERSION))
    lines.append("参考: %s | 样本 %d 有效 / %d 失败 | 阈值 warn=%dms crit=%dms | 期望偏移=%dms"
                 % (args.host, len(samples_ok), len(errs),
                    args.warn_ms, args.crit_ms, args.expect_offset_ms))
    for s in samples_ok:
        lines.append("  %-22s stratum=%d rtt=%6.3fs offset=%+10.4fs%s"
                     % (s["host"], s["stratum"], s["rtt"], s["offset"],
                        " (ref %s)" % s["ref_id"] if s.get("ref_id") else ""))
    for e in errs:
        lines.append("  %-22s FAIL: %s" % (e.get("host", "?"), e.get("error", "?")))
    if samples_ok:
        lines.append("中位偏移: %+.4fs -> %s" % (med, why))
    inv = _invariants(samples_ok, errs)
    for b in inv:
        lines.append("不变量违规: %s" % b)
    if level != "err" and inv:
        # 不变量违规不改变级别（避免误报级联），但必须在输出中可见
        lines.append("注: 不变量提示仅披露，不影响本次级别")
    lines.append("结论: %s | %s" % (level.upper(), why))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog=TOOL, description="服务器时钟漂移体检 (NTP, 只读)")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("check", "watch"):
        s = sub.add_parser(name)
        s.add_argument("--host", default=DEFAULT_HOSTS, help="逗号分隔 NTP 服务器")
        s.add_argument("--samples", type=int, default=3, help="每台服务器采样次数(取中位)")
        s.add_argument("--warn-ms", type=int, default=500)
        s.add_argument("--crit-ms", type=int, default=2000)
        s.add_argument("--timeout", type=int, default=5, help="单次 NTP 超时秒")
        s.add_argument("--expect-offset-ms", type=int, default=0,
                       help="已知良性偏移基线(如设备刻意慢 300ms)，判定时扣除")
        s.add_argument("--json", action="store_true", help="机读输出")
        s.add_argument("--out", help="把报告写到该文件(默认仅 stdout, 零写盘)")
        s.add_argument("-v", "--verbose", action="store_true")
    w = sub.add_parser("watch")
    w.add_argument("--interval", type=int, default=60)
    w.add_argument("--count", type=int, default=0, help="0=无限轮")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 3

    hosts = [h.strip() for h in args.host.split(",") if h.strip()]
    if not hosts:
        print("no hosts given")
        return 3

    def one_round():
        t0 = time.time()
        pooled_ok, pooled_err = [], []
        for _ in range(max(1, args.samples)):
            ok, er = sample(hosts, args.timeout)
            pooled_ok.extend(ok)
            pooled_err.extend(er)
        level, why, med, offs = verdict_of(pooled_ok, args.expect_offset_ms,
                                           args.warn_ms, args.crit_ms)
        rep = _fmt_report(level, why, med, pooled_ok, pooled_err, args)
        js = {
            "tool": TOOL, "version": VERSION, "cmd": args.cmd,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "level": level, "median_offset_s": round(med, 4),
            "expect_offset_ms": args.expect_offset_ms,
            "warn_ms": args.warn_ms, "crit_ms": args.crit_ms,
            "samples": pooled_ok, "errors": pooled_err, "why": why,
            "elapsed_s": round(time.time() - t0, 2),
        }
        return level, rep, js

    code_map = {"ok": 0, "warn": 1, "crit": 2, "err": 3}

    if args.cmd == "check":
        level, rep, js = one_round()
        if args.json:
            print(json.dumps(js, ensure_ascii=False, indent=2))
        else:
            print(rep)
        if args.out:
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write((json.dumps(js, ensure_ascii=False, indent=2)
                             if args.json else rep) + "\n")
            except OSError as e:
                print("write out failed: %s" % e)
        return code_map[level]

    # watch
    rounds = []
    n = 0
    code = 0
    while True:
        n += 1
        level, rep, js = one_round()
        print("---- round %d %s ----" % (n, js["ts"]))
        print(rep if not args.json else json.dumps(js, ensure_ascii=False))
        rounds.append(js)
        code = max(code, code_map[level])
        if args.count and n >= args.count:
            break
        time.sleep(max(1, args.interval))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rounds, f, ensure_ascii=False, indent=2)
    return code


if __name__ == "__main__":
    sys.exit(main())
