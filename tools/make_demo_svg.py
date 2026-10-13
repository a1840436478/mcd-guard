"""生成 README 用的动态演示图（SVG + CSS 动画，GitHub 上直接显示）。

画面分两栏：左边是 AI 客户端（Claude Code），右边是麦麦护栏终端。
台词摘自 2026-10-13 用真实 Claude Code 接入护栏的录制，只保留关键行。
"""

import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logger import log  # noqa: E402

FONT = "'SFMono-Regular', Menlo, Consolas, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', monospace"
FONT_SIZE = 14
LINE_HEIGHT = 22
PANEL_WIDTH = 560
GAP = 20
PAD = 16
TITLE_HEIGHT = 32
ASCII_PX = FONT_SIZE * 0.6
CJK_PX = FONT_SIZE

COLORS = {
    "bg": "#0d1117", "panel": "#161b22", "title": "#21262d", "text": "#c9d1d9", "dim": "#8b949e",
    "user": "#58a6ff", "tool": "#d2a8ff", "ok": "#3fb950", "warn": "#d29922", "bad": "#f85149", "card": "#ffa657",
}

# 每行：(出现的秒数, 栏位 left/right, 颜色名, 文本)
SCENES = {
    "demo-confirm.svg": {
        "titles": ("Claude Code（AI 客户端）", "麦麦护栏终端"),
        "lines": [
            (0.5, "left", "user", "你 › 帮我在上海人民广场附近找一家麦当劳，到店自取，点一个麦辣鸡腿汉堡单品，直接帮我下单。"),
            (2.0, "left", "tool", "● query-nearby-stores → 华旭国际大厦餐厅（144 米，24 小时）"),
            (2.2, "right", "ok", "[放行] query-nearby-stores"),
            (3.2, "left", "tool", "● query-meals → 麦辣鸡腿汉堡单品 1440"),
            (3.4, "right", "ok", "[放行] query-meals"),
            (4.4, "left", "tool", "● calculate-price → 应付 ¥22.50"),
            (4.6, "right", "ok", "[放行] calculate-price"),
            (5.6, "left", "text", "AI › 现在提交下单，请到运行护栏的终端里确认。"),
            (6.4, "left", "tool", "● create-order …等待护栏"),
            (6.8, "right", "dim", "[核价] 官方试算 应付 ¥22.50"),
            (7.4, "right", "card", "══ 【麦麦护栏】AI 请求执行写操作 ══"),
            (7.4, "right", "card", "  操作：创建订单（create-order）"),
            (7.4, "right", "card", "  门店：1450713    方式：到店自取"),
            (7.4, "right", "card", "  餐品：麦辣鸡腿汉堡 x1"),
            (7.4, "right", "card", "  应付：¥22.50（官方试算）"),
            (7.4, "right", "card", "  今日已确认：¥0.00 / 上限 ¥200.00"),
            (7.4, "right", "warn", "输入 y 回车确认执行，输入其他内容拒绝"),
            (9.4, "right", "user", "> n"),
            (9.8, "right", "bad", "[拒绝] create-order 没有发给麦当劳"),
            (10.4, "left", "bad", "● create-order ✗ 用户在护栏终端拒绝"),
            (11.4, "left", "text", "AI › 订单没下成：你在护栏终端拒绝了「创建订单」，账户没有任何改动。按护栏规则我不会自动重试。"),
        ],
    },
    "demo-limit.svg": {
        "titles": ("Claude Code（AI 客户端）", "麦麦护栏终端"),
        "lines": [
            (0.5, "left", "user", "你 › 我们部门 12 个人点明天的午饭，人民广场那家 24 小时的麦当劳，每人一个麦辣鸡腿汉堡，直接帮我下单。"),
            (2.4, "left", "tool", "● query-nearby-stores / query-meals"),
            (2.6, "right", "ok", "[放行] query-nearby-stores"),
            (2.8, "right", "ok", "[放行] query-meals"),
            (3.8, "left", "tool", "● calculate-price → 12 份 应付 ¥270.00"),
            (4.0, "right", "ok", "[放行] calculate-price"),
            (5.0, "left", "tool", "● create-order …等待护栏"),
            (5.4, "right", "dim", "[核价] 官方试算 应付 ¥270.00"),
            (6.2, "right", "bad", "[拦截] 超过单笔上限 ¥100.00"),
            (6.2, "right", "bad", "       不弹确认，不发给麦当劳"),
            (7.0, "left", "bad", "● create-order ✗ 护栏已拦截：超过单笔上限 ¥100.00"),
            (8.0, "left", "text", "AI › 订单没有下成功：这单应付 ¥270.00，超过护栏的单笔上限 ¥100.00。护栏要求被拦截后不重试、不拆单，所以我没有再提交。"),
            (9.6, "left", "text", "AI › 如果确实要下，请调高 policy.json 里的上限并重启护栏，提交后仍需你在护栏终端确认。"),
        ],
    },
}


def char_px(ch):
    """单个字符的显示宽度（像素），中文等宽字符按一个字号算。"""
    return CJK_PX if ord(ch) > 0x2E7F else ASCII_PX


def wrap(text, width_px):
    """
    按显示宽度折行。

    :param text: 原文
    :param width_px: 每行最大像素宽度
    :return: list[str]
    """
    lines, cur, cur_px = [], "", 0.0
    for ch in text:
        w = char_px(ch)
        if cur and cur_px + w > width_px:
            lines.append(cur)
            cur, cur_px = "  ", 2 * ASCII_PX
        cur += ch
        cur_px += w
    lines.append(cur)
    return lines


def layout(lines):
    """
    把台词排进两栏，算出每个文本行的坐标和出现时间。

    :param lines: SCENES 中的 lines
    :return: (行列表 [(t, x, y, color, text)], 每栏行数最大值)
    """
    rows = {"left": 0, "right": 0}
    placed = []
    for t, side, color, text in lines:
        x = PAD + (0 if side == "left" else PANEL_WIDTH + GAP) + PAD
        for part in wrap(text, PANEL_WIDTH - 2 * PAD):
            y = TITLE_HEIGHT + PAD + (rows[side] + 1) * LINE_HEIGHT
            placed.append((t, x, y, COLORS[color], part))
            rows[side] += 1
    return placed, max(rows.values())


def render(scene, hold_sec):
    """
    生成一个场景的 SVG 文本。

    :param scene: SCENES 中的一项
    :param hold_sec: 全部出现后停留的秒数，然后循环
    :return: SVG 字符串
    """
    placed, max_rows = layout(scene["lines"])
    total = max(t for t, *_ in placed) + hold_sec
    width = 2 * PANEL_WIDTH + GAP + 2 * PAD
    height = TITLE_HEIGHT + 2 * PAD + (max_rows + 1) * LINE_HEIGHT + PAD
    css, body = [], []
    for i, (t, x, y, color, text) in enumerate(placed):
        start = t / total * 100
        css.append(f"@keyframes k{i}{{0%,{start:.2f}%{{opacity:0}}{min(start + 0.5, 99.9):.2f}%,100%{{opacity:1}}}}"
                   f".l{i}{{animation:k{i} {total:.1f}s linear infinite}}")
        body.append(f'<text class="l{i}" x="{x}" y="{y}" fill="{color}">{escape(text)}</text>')
    panels = []
    for idx, title in enumerate(scene["titles"]):
        px = PAD + idx * (PANEL_WIDTH + GAP)
        panels.append(
            f'<rect x="{px}" y="{PAD}" width="{PANEL_WIDTH}" height="{height - 2 * PAD}" rx="8" fill="{COLORS["panel"]}"/>'
            f'<path d="M{px} {PAD + 8}a8 8 0 0 1 8-8h{PANEL_WIDTH - 16}a8 8 0 0 1 8 8v{TITLE_HEIGHT - 8}h-{PANEL_WIDTH}z" '
            f'fill="{COLORS["title"]}"/>'
            + "".join(f'<circle cx="{px + 16 + k * 18}" cy="{PAD + TITLE_HEIGHT / 2}" r="5" fill="{c}"/>'
                      for k, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")))
            + f'<text x="{px + PANEL_WIDTH / 2}" y="{PAD + TITLE_HEIGHT / 2 + 5}" fill="{COLORS["dim"]}" '
              f'text-anchor="middle">{escape(title)}</text>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" xml:space="preserve" font-family="{escape(FONT)}" font-size="{FONT_SIZE}">'
            f'<style>text{{white-space:pre}}{"".join(css)}</style>'
            f'<rect width="{width}" height="{height}" rx="12" fill="{COLORS["bg"]}"/>'
            f'{"".join(panels)}{"".join(body)}</svg>')


def main(out_dir, hold_sec):
    """
    生成全部演示图。

    :param out_dir: 输出目录
    :param hold_sec: 每个场景播完后停留的秒数
    :return: None
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, scene in SCENES.items():
        path = out_dir / name
        path.write_text(render(scene, hold_sec), encoding="utf-8")
        log(f"生成演示图: 路径={path}, 字节数={path.stat().st_size}")


if __name__ == "__main__":
    OUT_DIR = Path(__file__).resolve().parent.parent / "docs"  # 输出目录
    HOLD_SEC = 6  # 播完后停留秒数，然后从头循环
    main(OUT_DIR, HOLD_SEC)
