#!/usr/bin/env python3
"""clockdrift 公众号封面 900x383（对话钩子形态：白句提问 + 金句硬指标）。"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/Users/len/Desktop/clockdrift-cover.png"
FONT_CJK = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"
W, H = 900, 383
BG_TOP, BG_BOT = (11, 14, 26), (26, 15, 46)
GOLD = (240, 180, 41)
WHITE = (235, 240, 245)
GREY = (139, 148, 158)
GREEN = (63, 185, 80)

_fc = {}
def F(path, size):
    key = (path, size)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(path, size)
    return _fc[key]

img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
# 渐变底
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))

# 左金竖条锚
d.rectangle([28, 40, 34, 200], fill=GOLD)

# 栏目标签
d.text((52, 44), "自研工具 · 运维取证套件", font=F(FONT_CJK, 17), fill=GOLD)

# 双行大字钩子
d.text((52, 86), "你的服务器时钟", font=F(FONT_CJK, 44), fill=WHITE)
d.text((52, 146), "究竟漂了几秒?", font=F(FONT_CJK, 44), fill=WHITE)

# 副标
d.text((52, 216), "多 NTP 交叉采样 · 中位数判定 · 单文件零依赖", font=F(FONT_CJK, 18), fill=GREY)

# 右侧数据区（硬指标）
d.text((636, 96), "40", font=F(FONT_MONO, 58), fill=GOLD)
d.text((726, 122), "自测全绿", font=F(FONT_CJK, 20), fill=WHITE)
d.text((636, 178), "8", font=F(FONT_MONO, 58), fill=GREEN)
d.text((676, 204), "条不变量", font=F(FONT_CJK, 20), fill=WHITE)

# 底部信息条（重点行黑衬底）
d.rectangle([0, 316, W, H], fill=(8, 10, 18))
d.text((52, 336), "clockdrift", font=F(FONT_MONO, 24), fill=GOLD)
d.text((240, 342), "退出码 0/1/2/3 直接接告警 · 只读不改系统", font=F(FONT_CJK, 17), fill=GREY)

img.save(OUT)
print("saved", OUT, os.path.getsize(OUT), "bytes")
