#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clockdrift 自测（离线优先；--live 追加真实 NTP 一轮）。
覆盖: 编解码回环 / 阈值边界 / 中位与尖峰升级 / 不变量 / 离线确定性 / CLI 出口码。
全绿标准: 所有断言通过, 退出码 0。"""
import io
import json
import struct
import sys
import contextlib

sys.path.insert(0, "/Users/len/CodeBuddy/dx/clockdrift")
import clockdrift as cd  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  ok  " if cond else "  FAIL") + " T | %s %s" % (name, detail))


def t1_codec():
    print("T1 NTP 时间戳编解码回环")
    delta = cd.NTP_EPOCH_DELTA
    unix = 1793577600.0  # 2026-11-03 附近
    b = struct.pack("!II", int(unix) + delta, 0)
    back = cd._ts_to_seconds(b)
    check("整秒回环", abs(back - unix) < 0.001, "back=%s" % back)
    frac = int(0.5 * (2 ** 32))
    b2 = struct.pack("!II", int(unix) + delta, frac)
    check("半秒回环", abs(cd._ts_to_seconds(b2) - (unix + 0.5)) < 0.001)
    check("全零->None", cd._ts_to_seconds(b"\x00" * 8) is None)
    now_b = cd._now_ntp()
    now_back = cd._ts_to_seconds(now_b)
    check("now 回环", now_back is not None and abs(now_back - __import__("time").time()) < 2.0,
          "diff=%.3f" % abs(now_back - __import__("time").time()))


def t2_classify():
    print("T2 阈值判定边界")
    cases = [
        (0.10, 0, 500, 2000, "ok"),      # 100ms
        (0.50, 0, 500, 2000, "warn"),    # 恰在 warn 边界
        (1.99, 0, 500, 2000, "warn"),
        (2.00, 0, 500, 2000, "crit"),    # 恰在 crit 边界
        (0.30, 300, 500, 2000, "ok"),    # 期望偏移扣除后归零
        (0.80, 300, 500, 2000, "warn"),  # 扣除后 500ms
    ]
    for off, exp, warn, crit, want in cases:
        lvl, _ = cd.classify(off, exp, warn, crit)
        check("offset=%s exp=%s -> %s" % (off, exp, want), lvl == want, "got=%s" % lvl)


def t3_verdict():
    print("T3 中位判定与尖峰升级")
    mk = lambda offs: [{"host": "h%d" % i, "offset": o, "stratum": 2, "li": 0,
                        "rtt": 0.05, "ref_id": "aabbccdd", "ip": "10.213.0.1"}
                       for i, o in enumerate(offs)]
    lvl, why, med, _ = cd.verdict_of(mk([0.01, 0.02, 0.03]), 0, 500, 2000)
    check("全 ok", lvl == "ok", med)
    lvl, why, med, _ = cd.verdict_of(mk([0.01, 0.02, 9.0]), 0, 500, 2000)
    check("单尖峰升级 warn", lvl == "warn", "lvl=%s why=%s" % (lvl, why[:40]))
    check("尖峰不吞中位", med == 0.02, med)
    lvl, _, med, _ = cd.verdict_of(mk([3.0, 3.1, 2.9]), 0, 500, 2000)
    check("中位 crit", lvl == "crit", med)
    lvl, why, _, _ = cd.verdict_of([], 0, 500, 2000)
    check("空样本 -> err", lvl == "err")


def t4_invariants():
    print("T4 不变量体检")
    ok = [{"host": "a", "offset": 0.01, "stratum": 2, "li": 0, "rtt": 0.1}]
    check("干净样本零违规", cd._invariants(ok, []) == [])
    s0 = [{"host": "b", "offset": 0.01, "stratum": 0, "li": 0, "rtt": 0.1}]
    check("I3 stratum=0 捕获", any("I3" in x for x in cd._invariants(s0, [])))
    leap = [{"host": "c", "offset": 0.01, "stratum": 2, "li": 3, "rtt": 0.1}]
    check("I4 leap 闹钟捕获", any("I4" in x for x in cd._invariants(leap, [])))
    dead = [{"host": "d", "offset": 90000.0, "stratum": 2, "li": 0, "rtt": 0.1}]
    check("I2 时钟坏死捕获", any("I2" in x for x in cd._invariants(dead, [])))
    check("I6 全不可达捕获", any("I6" in x for x in cd._invariants([], [{"host": "e", "error": "timeout"}])))


def t5_offline_cli():
    print("T5 离线确定性（不可达地址 -> 退出码 3, 不编造 offset）")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cd.main(["check", "--host", "127.0.0.1", "--timeout", "1",
                      "--samples", "1", "--json"])
    out = buf.getvalue()
    check("退出码 3", rc == 3, "rc=%s" % rc)
    js = json.loads(out.strip())
    check("level=err", js["level"] == "err", js["level"])
    check("median=0.0 不编造", js["median_offset_s"] == 0.0, js["median_offset_s"])
    check("errors 含 timeout/net", len(js["errors"]) >= 1)


def t6_report_shape():
    print("T6 报告形状（文本+JSON 双轨字段齐全）")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cd.main(["check", "--host", "127.0.0.1", "--timeout", "1",
                      "--samples", "1", "--json"])
    js = json.loads(buf.getvalue().strip())
    for k in ("tool", "version", "ts", "level", "median_offset_s", "samples",
              "errors", "why", "warn_ms", "crit_ms", "expect_offset_ms"):
        check("json.%s 存在" % k, k in js)
    check("tool 名正确", js["tool"] == "clockdrift")
    check("version 1.0.0", js["version"] == "1.0.0")


def t7_no_write_by_default():
    print("T7 默认零写盘（I8）")
    import os
    import tempfile
    d = tempfile.mkdtemp(prefix="cd_probe_")
    cwd0 = os.getcwd()
    os.chdir(d)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cd.main(["check", "--host", "127.0.0.1", "--timeout", "1", "--samples", "1"])
        leftovers = os.listdir(d)
        check("无文件残留", leftovers == [], str(leftovers))
    finally:
        os.chdir(cwd0)


def t8_live():
    print("T8 LIVE 真实 NTP 一轮")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cd.main(["check", "--samples", "2", "--timeout", "5", "--json"])
    js = json.loads(buf.getvalue().strip())
    print("   live level=%s median=%s hosts_ok=%d hosts_err=%d"
          % (js["level"], js["median_offset_s"], len(js["samples"]), len(js["errors"])))
    check("live 有有效样本", len(js["samples"]) >= 1)
    check("live 偏移在 2s 内(健康本机)", js["level"] in ("ok", "warn"),
          "median=%s" % js["median_offset_s"])
    return js


if __name__ == "__main__":
    print("clockdrift selftest — 离线 7 项%s" % (" + LIVE 1 项" if "--live" in sys.argv else ""))
    t1_codec()
    t2_classify()
    t3_verdict()
    t4_invariants()
    t5_offline_cli()
    t6_report_shape()
    t7_no_write_by_default()
    live_js = None
    if "--live" in sys.argv:
        live_js = t8_live()
    print("\n===== selftest summary =====")
    print("PASS=%d FAIL=%d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n, d in FAIL:
            print("  FAILED:", n, d)
    if live_js is not None:
        with open("/tmp/clockdrift_live.json", "w") as f:
            json.dump(live_js, f, ensure_ascii=False, indent=2)
        print("live sample saved: /tmp/clockdrift_live.json")
    sys.exit(1 if FAIL else 0)
