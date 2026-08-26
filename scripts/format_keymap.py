#!/usr/bin/env python3
"""Tidy a ZMK .keymap file: aligns binding columns and regenerates the
layer-diagram comments above each layer's bindings from the bindings
themselves. Safe to re-run any time — output is idempotent.

Usage:
    scripts/format_keymap.py [path/to/file.keymap ...]

Defaults to config/corne.keymap (relative to the repo root) when no
path is given.
"""

import re
import sys
from pathlib import Path

NCOLS = 12
THUMB_START = 3

TOKEN_RE = re.compile(r"&\S+(?:\s+[A-Za-z0-9_]+)*")
LAYER_BLOCK_RE = re.compile(
    r"(\w+_layer \{\n)"          # 1: layer opening line
    r"((?://[^\n]*\n)*)"         # 2: existing comment lines (discarded)
    r"(\s*bindings = <\n)"       # 3: bindings open
    r"(.*?)"                    # 4: bindings body
    r"(\n\s*>;)",                # 5: bindings close
    re.DOTALL,
)

MOD_SHORT = {
    "LCTRL": "CTRL", "RCTRL": "CTRL",
    "LSHFT": "SHFT", "RSHFT": "SHFT",
    "LALT": "ALT", "RALT": "ALT",
    "LGUI": "GUI", "RGUI": "GUI",
}
KEY_SYM = {
    "TAB": "TAB", "BSPC": "BSPC", "RET": "RET", "SPACE": "SPC", "ESC": "ESC",
    "SEMI": ";", "SQT": "'", "COMMA": ",", "DOT": ".", "FSLH": "/",
    "TILDE": "~", "GRAVE": "`", "EXCL": "!", "AT": "@", "HASH": "#",
    "DLLR": "$", "PRCNT": "%", "CARET": "^", "AMPS": "&", "ASTRK": "*",
    "LPAR": "(", "RPAR": ")", "PIPE": "PIPE", "UNDER": "_", "MINUS": "-",
    "PLUS": "+", "LBRC": "{", "RBRC": "}", "BSLH": "\\", "LBKT": "[",
    "RBKT": "]", "EQUAL": "=", "NUHS": "#",
    "N0": "0", "N1": "1", "N2": "2", "N3": "3", "N4": "4", "N5": "5",
    "N6": "6", "N7": "7", "N8": "8", "N9": "9",
    "UP": "UP", "DOWN": "DN", "LEFT": "LT", "RIGHT": "RT",
    **MOD_SHORT,
}
LAYER_SHORT = {
    "DEFAULT": "DEF", "SYMBOLS": "SYM", "NAV": "NAV", "NUMBERS": "NUM",
}


def sym(key):
    return KEY_SYM.get(key, key)


def label(token):
    """Short human-readable label for a single binding, e.g. '&mt LCTRL ESC' -> 'ESC/CTRL'."""
    parts = token.split()
    behavior = parts[0]
    if behavior == "&trans":
        return "·"  # ·
    if behavior == "&caps_word":
        return "CAPS"
    if behavior == "&kp":
        return sym(parts[1])
    if behavior == "&bt":
        if parts[1] == "BT_CLR":
            return "BTCLR"
        if parts[1] == "BT_SEL":
            return "BT" + parts[2]
    if behavior in ("&mt", "&bhm", "&hml", "&hmr"):
        mod, key = parts[1], parts[2]
        return f"{sym(key)}/{MOD_SHORT.get(mod, mod)}"
    if behavior == "&mo":
        return LAYER_SHORT.get(parts[1], parts[1])
    if behavior == "&lt":
        layer, key = parts[1], parts[2]
        return f"{sym(key)}/{LAYER_SHORT.get(layer, layer)}"
    return token


def parse_rows(bindings_body):
    lines = [l for l in bindings_body.split("\n") if l.strip() != ""]
    return [TOKEN_RE.findall(l.strip()) for l in lines]


def column_widths(rows_tokens):
    widths = [0] * NCOLS
    for tokens in rows_tokens:
        if len(tokens) == NCOLS:
            for i, t in enumerate(tokens):
                widths[i] = max(widths[i], len(t))
    for tokens in rows_tokens:
        if len(tokens) != NCOLS:
            for i, t in enumerate(tokens):
                widths[THUMB_START + i] = max(widths[THUMB_START + i], len(t))
    return widths


def format_bindings(rows_tokens, widths):
    base_indent = "   "
    gap = "  "
    mid_gap = "    "

    def join(pieces, start_col):
        out = ""
        for i, piece in enumerate(pieces):
            col = start_col + i
            if i > 0:
                out += mid_gap if col == NCOLS // 2 else gap
            out += piece
        return out

    out_lines = []
    for tokens in rows_tokens:
        if len(tokens) == NCOLS:
            pieces = [t.ljust(widths[i]) for i, t in enumerate(tokens)]
            line = base_indent + join(pieces, 0).rstrip()
        else:
            pad = 0
            for i in range(THUMB_START):
                pad += widths[i] + (mid_gap if i + 1 == NCOLS // 2 else len(gap))
            pieces = [t.ljust(widths[THUMB_START + i]) for i, t in enumerate(tokens)]
            line = base_indent + " " * pad + join(pieces, THUMB_START).rstrip()
        out_lines.append(line)
    return "\n".join(out_lines)


def build_comment(rows_tokens):
    grid = []
    for tokens in rows_tokens:
        labels = [label(t) for t in tokens]
        if len(labels) != NCOLS:
            padded = [""] * NCOLS
            for i, l in enumerate(labels):
                padded[THUMB_START + i] = l
            labels = padded
        grid.append(labels)

    widths = [0] * NCOLS
    for labels in grid:
        for i, l in enumerate(labels):
            widths[i] = max(widths[i], len(l))

    def cell(l, w):
        return " " + l.center(w) + " "

    def render_row(labels):
        left = "".join("|" + cell(labels[i], widths[i]) for i in range(6))
        right = "".join("|" + cell(labels[i], widths[i]) for i in range(6, 12))
        return "// " + left + "|" + "  " + "|" + right + "|"

    body_lines = [render_row(labels) for labels in grid]
    width_total = max(len(l) for l in body_lines)
    border = "// " + "-" * (width_total - 3)
    return "\n".join([border] + body_lines) + "\n"


def format_layer(match):
    header, _old_comments, bindings_open, bindings_body, bindings_close = match.groups()
    rows_tokens = parse_rows(bindings_body)
    widths = column_widths(rows_tokens)
    new_comment = build_comment(rows_tokens)
    new_bindings = format_bindings(rows_tokens, widths)
    return header + new_comment + bindings_open + new_bindings + bindings_close


def format_keymap(text):
    return LAYER_BLOCK_RE.subn(format_layer, text)


def main(argv):
    paths = [Path(p) for p in argv] or [Path("config/corne.keymap")]
    for path in paths:
        if not path.exists():
            print(f"skip: {path} not found", file=sys.stderr)
            continue
        original = path.read_text()
        updated, count = format_keymap(original)
        if updated != original:
            path.write_text(updated)
            print(f"formatted {count} layer(s) in {path}")
        else:
            print(f"already tidy: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
