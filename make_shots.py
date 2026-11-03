#!/usr/bin/env python3
"""clockdrift 公众号证据图（6 张，内容=2026-11-03 真实运行输出）。"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/Users/len/CodeBuddy/dx/clockdrift/screenshots"
os.makedirs(OUT, exist_ok=True)
FONT_CJK = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"
W, H = 1200, 675
BG, BAR, LINE = "#1b1d23", "#2a2d35", "#0d1117"
GREEN, WHITE, GREY, RED, GOLD, BLUE = "#98c379", "#e6edf3", "#7f8794", "#e06c75", "#e5c07b", "#61afef"

_fc = {}
def F(size, mono):
    key = (size, mono)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(FONT_MONO if mono else FONT_CJK, size)
    return _fc[key]

def has_cjk(t):
    return any('\u2e80' <= ch <= '\u9fff' or ch in '，。：；「」（）｜→·⏳％×' for ch in t)

def shot(name, lines, title="dev — zsh"):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 44], fill=BAR)
    d.ellipse([24, 15, 36, 27], fill="#ff5f57"); d.ellipse([44, 15, 56, 27], fill="#febc2e"); d.ellipse([64, 15, 76, 27], fill="#28c840")
    tw = d.textlength(title, font=F(16, False))
    d.text(((W - tw) / 2, 13), title, font=F(16, False), fill="#8b90a0")
    d.rectangle([0, 44, W, 46], fill=LINE)
    y = 70
    for text, color, size, mono in lines:
        if text:
            font = F(size, mono and not has_cjk(text))
            d.text((56, y), text, font=font, fill=color)
        y += int(size * 1.8)
    img.save("%s/%s.png" % (OUT, name))
    print(name, "OK")

# ── 1 首跑体检：OK 判定（今日真实输出）──
shot("01_first_check", [
    ("$ python3 clockdrift.py check", WHITE, 22, True),
    ("", WHITE, 8, True),
    ("[ OK ] clockdrift v1.0.0", GREEN, 26, True),
    ("参考: 4 台 NTP | 样本 8 有效 / 0 失败 | warn=500ms crit=2000ms", GREY, 19, True),
    ("", WHITE, 8, True),
    ("cn.pool.ntp.org    stratum=2 rtt= 0.023s offset=  -0.0044s", WHITE, 20, True),
    ("ntp.aliyun.com     stratum=2 rtt= 0.063s offset=  -0.0008s", WHITE, 20, True),
    ("time.windows.com   stratum=4 rtt= 0.103s offset=  +0.0009s", WHITE, 20, True),
    ("pool.ntp.org       stratum=2 rtt= 0.023s offset=  -0.0024s", WHITE, 20, True),
    ("", WHITE, 8, True),
    ("中位偏移: -0.0016s -> 偏差 0.002s 在阈值内", GREEN, 21, False),
    ("结论: OK", GREEN, 24, True),
], title="clockdrift — 体检")

# ── 2 退出码语义：ERR 演示（全不可达 -> 3，绝不编造偏移）──
shot("02_exit_codes", [
    ("$ python3 clockdrift.py check --host 127.0.0.1 --timeout 1", WHITE, 20, True),
    ("", WHITE, 8, True),
    ("[ERR ] 无有效 NTP 应答 (1 台全部超时)", RED, 24, True),
    ("  127.0.0.1  FAIL: timeout", RED, 20, True),
    ("", WHITE, 8, True),
    ("$ echo $?", GREY, 20, True),
    ("3", GOLD, 30, True),
    ("", WHITE, 10, True),
    ("退出码: 0=OK  1=WARN  2=CRIT  3=ERR", BLUE, 21, False),
    ("全部不可达 -> 退出 3，绝不编造偏移 (I6)", GREY, 20, False),
    ("cron 里直接: clockdrift || 告警", GREY, 20, False),
], title="clockdrift — 退出码")

# ── 3 JSON 机读输出（给监控平台）──
shot("03_json_mode", [
    ("$ python3 clockdrift.py check --json", WHITE, 22, True),
    ("", WHITE, 8, True),
    ('{', GREY, 18, True),
    ('  "tool": "clockdrift", "version": "1.0.0",', GREEN, 18, True),
    ('  "ts": "2026-11-03T11:04:42+0800",', GREEN, 18, True),
    ('  "level": "ok",', GOLD, 20, True),
    ('  "median_offset_s": -0.0004,', GREEN, 18, True),
    ('  "samples": [ { "host": "cn.pool.ntp.org", ... } ]', GREEN, 18, True),
    ('}', GREY, 18, True),
    ("", WHITE, 8, True),
    ("夜莺/Prometheus webhook 直接吃 level 和退出码", GREY, 20, False),
    ("每台服务器的 offset/rtt/stratum 全在 samples 里", GREY, 20, False),
], title="clockdrift — JSON")

# ── 4 严格阈值：WARN 抖动可见 ──
shot("04_strict_warn", [
    ("$ python3 clockdrift.py check --samples 1 --warn-ms 1", WHITE, 20, True),
    ("", WHITE, 8, True),
    ("[WARN] 偏差 0.003s 超过 WARN 阈值 1ms", GOLD, 24, True),
    ("", WHITE, 8, True),
    ("单台抽风不背锅:", WHITE, 20, False),
    ("  多服务器交叉采样取中位数", GREY, 20, False),
    ("  4 台里 1 台漂了 -> 中位不动", GREY, 20, False),
    ("", WHITE, 8, True),
    ("抖动可见:", WHITE, 20, False),
    ("  中位正常但有单样本超 CRIT -> 升级 WARN", GREY, 20, False),
    ("  阈值不合适? --expect-offset-ms 扣良性基线", GREY, 20, False),
], title="clockdrift — 阈值")

# ── 5 自测全绿 ──
shot("05_selftest", [
    ("$ python3 selftest.py --live", WHITE, 22, True),
    ("", WHITE, 8, True),
    ("T1 NTP 时间戳编解码回环        ok", GREEN, 20, True),
    ("T2 阈值判定边界 (6 组)         ok", GREEN, 20, True),
    ("T3 中位判定与尖峰升级          ok", GREEN, 20, True),
    ("T4 不变量体检 I2/I3/I4/I6      ok", GREEN, 20, True),
    ("T5 离线确定性 (退出码 3)       ok", GREEN, 20, True),
    ("T6 报告形状 JSON 字段          ok", GREEN, 20, True),
    ("T7 默认零写盘 (I8)            ok", GREEN, 20, True),
    ("T8 LIVE 真实 NTP 8 样本        ok", GREEN, 20, True),
    ("", WHITE, 8, True),
    ("===== selftest summary =====", GREY, 20, True),
    ("PASS=40 FAIL=0", GOLD, 30, True),
], title="clockdrift — 自测")

# ── 6 套件链条 ──
shot("06_toolchain", [
    ("运维取证套件 · 这条链我每天在用", GOLD, 24, False),
    ("", WHITE, 10, True),
    ("cronguard     定时任务半夜死了谁知道", WHITE, 21, False),
    ("   |", GREY, 20, True),
    ("logwhisperer  出事了先考古日志", WHITE, 21, False),
    ("   |", GREY, 20, True),
    ("clockdrift    日志顺序乱/握手失败? 先查时钟", GOLD, 21, False),
    ("   |", GREY, 20, True),
    ("debugkit      立案取证修复结案", WHITE, 21, False),
    ("   |", GREY, 20, True),
    ("porteye       顺手看暴露面对不对", WHITE, 21, False),
    ("", WHITE, 10, True),
    ("每个都是单文件零依赖, 拼起来就是值班台", GREY, 20, False),
], title="toolchain")

print("done:", len(os.listdir(OUT)), "files")
