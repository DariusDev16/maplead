"""
MAPLEAD terminal art: ANSI colouring, gradients and hand-built ASCII/Unicode
big-letter rendering. No third-party fonts required.
"""

from __future__ import annotations

import os
import shutil

from . import host

VERSION = "1.1.0"

# --------------------------------------------------------------------------- #
# colour plumbing
# --------------------------------------------------------------------------- #

_FORCE = os.environ.get("MAPLEAD_NO_COLOR", "") not in ("", "0", "false", "no")
FORCE_PLAIN = os.environ.get("MAPLEAD_ASCII", "") not in ("", "0", "false", "no")
# lets you keep the colours when piping:  ./maplead.py | less -R
_FORCE_COLOR = os.environ.get("MAPLEAD_FORCE_COLOR", "") not in ("", "0", "false", "no")

# Windows: switch the console to UTF-8 + VT sequences before anything is printed
ANSI_OK = host.enable_console()
CAN_UNICODE = host.console_unicode()


def _tty_ok() -> bool:
    if _FORCE:
        return False
    if not host.stdout_is_tty():
        return False
    # an unset TERM is normal on Windows; only an explicitly dumb terminal opts out
    return os.environ.get("TERM", "").strip().lower() != "dumb"


COLOR = ((_tty_ok() and ANSI_OK) or _FORCE_COLOR) and not FORCE_PLAIN
PLAIN = not COLOR or FORCE_PLAIN
# piped output stays plain ASCII (as before); a real console gets the box art when
# its code page can represent it
UNICODE = (not PLAIN) and CAN_UNICODE

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"
UNDER = "\x1b[4m"

# bright foreground helpers
FG = {
    "black": 30, "red": 31, "green": 32, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36, "white": 37,
}
_BRIGHT = {k: v + 60 for k, v in FG.items()}


def c(text: str, color: str = "", bold: bool = False, dim: bool = False) -> str:
    """Colour a string (no-op when the terminal cannot show colour)."""
    if PLAIN or not text:
        return text
    prefix = ""
    if color in _BRIGHT:
        prefix += f"\x1b[{_BRIGHT[color]}m"
    elif color in FG:
        prefix += f"\x1b[{FG[color]}m"
    elif isinstance(color, int):
        prefix += f"\x1b[38;5;{color}m"
    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    return f"{prefix}{text}{RESET}" if prefix else text


def c256(text: str, n: int, bold: bool = False) -> str:
    return c(text, int(n), bold=bold)


def gradient(text: str, start: int = 39, end: int = 207, bold: bool = True) -> str:
    """Paint each visible character with a smooth 256-colour ramp."""
    if PLAIN:
        return text
    out = []
    n = max(len(text) - 1, 1)
    step = 0
    for ch in text:
        if ch == " ":
            out.append(ch)
            continue
        out.append(c256(ch, round(start + (end - start) * step / n), bold=bold))
        step += 1
    return "".join(out)


def term_width(default: int = 96) -> int:
    try:
        return max(48, min(shutil.get_terminal_size((default, 24)).columns, 160))
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# box-drawing pieces (unicode + pure-ascii fallback)
# --------------------------------------------------------------------------- #

if not UNICODE:
    GLYPH = {
        "tl": "+", "tr": "+", "bl": "+", "br": "+",
        "h": "-", "v": "|", "arrow": ">", "dot": "*",
        "check": "OK", "cross": "X", "warn": "!!", "bullet": "-",
        "spin": ["|", "/", "-", "\\"],
    }
else:
    GLYPH = {
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "h": "─", "v": "│", "arrow": "›", "dot": "•",
        "check": "✔", "cross": "✘", "warn": "▲", "bullet": "▸",
        "spin": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    }


def hr(char: str | None = None, width: int | None = None, color: str = "") -> str:
    width = width or term_width()
    return c((char or GLYPH["h"]) * width, color, dim=True)


# --------------------------------------------------------------------------- #
# 3x5 block font  (renders any short text)
# --------------------------------------------------------------------------- #

_BLOCK: dict[str, tuple[str, str, str, str, str]] = {
    "A": (".#.", "###", "#.#", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#.#", "###", "###", "#.#", "#.#"),
    "N": ("#.#", "###", "###", "###", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "###", ".##"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#.#", "#.#", "###", "###", "#.#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"),
    "3": ("##.", "..#", ".#.", "..#", "##."),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "##.", "#.#", ".##"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": (".#.", "#.#", ".#.", "#.#", ".#."),
    "9": (".##", "#.#", ".##", "..#", "##."),
    "-": ("...", "...", "###", "...", "..."),
    ".": ("...", "...", "...", "...", ".#."),
    ":": ("...", ".#.", "...", ".#.", "..."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "!": (".#.", ".#.", ".#.", "...", ".#."),
    "?": ("##.", "..#", ".#.", "...", ".#."),
    " ": ("...", "...", "...", "...", "..."),
}


def block_text(text: str, fill: str | None = None) -> list[str]:
    """Render `text` with the 3x5 block font -> list of 5 lines."""
    fill = fill or ("█" if UNICODE else "#")
    glyphs = [_BLOCK.get(ch.upper(), _BLOCK[" "]) for ch in text]
    lines = []
    for row in range(5):
        pixels = []
        for glyph in glyphs:
            pixels.append("".join(fill if px == "#" else " " for px in glyph[row]))
        lines.append(" ".join(pixels))
    return lines


# --------------------------------------------------------------------------- #
# the MAPLEAD wordmark  (figlet "standard"-style, 6 rows, hand-built)
# --------------------------------------------------------------------------- #

_WORDMARK: dict[str, tuple[str, ...]] = {
    "M": ("███╗   ██╗",
          "████╗  ██║",
          "██╔██╗ ██║",
          "██║╚██╗██║",
          "██║ ╚████║",
          "╚═╝  ╚═══╝"),
    "A": (" █████╗ ",
          "██╔══██╗",
          "███████║",
          "██╔══██╗",
          "██║  ██║",
          "╚═╝  ╚═╝"),
    "P": ("██████╗ ",
          "██╔══██╗",
          "██████╦╝",
          "██╔══██╗",
          "██║  ██║",
          "╚═╝  ╚═╝"),
    "L": ("██╗     ",
          "██║     ",
          "██║     ",
          "██║     ",
          "███████╗",
          "╚══════╝"),
    "E": ("███████╗",
          "██╔════╝",
          "█████╗  ",
          "██╔══╝  ",
          "███████╗",
          "╚══════╝"),
    "D": ("██████╗ ",
          "██╔══██╗",
          "██║  ██║",
          "██║  ██║",
          "██████╔╝",
          "╚═════╝ "),
}

_ASCII_WORDMARK: dict[str, tuple[str, ...]] = {
    k: tuple(row.replace("█", "#").replace("╗", "+").replace("╔", "+")
              .replace("╚", "+").replace("╝", "+").replace("║", "|")
              .replace("═", "=").replace("╠", "+").replace("╣", "+")
              .replace("╦", "+").replace("╩", "+").replace("╬", "+")
             for row in glyph)
    for k, glyph in _WORDMARK.items()
}


def wordmark(text: str = "MAPLEAD") -> list[str]:
    glyphs = _ASCII_WORDMARK if PLAIN else _WORDMARK
    rows = []
    for i in range(6):
        rows.append("".join(glyphs.get(ch.upper(), tuple(" " * 8 for _ in range(6)))[i]
                            for ch in text))
    return rows


# --------------------------------------------------------------------------- #
# composed banner
# --------------------------------------------------------------------------- #

_PIN = (
    "      ▄▄▄▄▄▄▄▄▄▄      ",
    "    ▄██▀▀    ▀▀██▄    ",
    "   ███▀   ▄▄▄   ▀███   ",
    "  ████   ██████   ████  ",
    "  ████    ▀██▀    ████  ",
    "   ███▄          ▄███   ",
    "    ▀██▄▄▄▄▄▄▄▄▄██▀    ",
    "      ▀▀▀██▀██▀▀      ",
    "           ▀▀▀         ",
)

_PIN_ASCII = (
    "      +----------+   ",
    "    .-'      '-.     ",
    "   /   .----.   \\    ",
    "  |   ( +++  )   |   ",
    "  |    '----'    |   ",
    "   \\            /    ",
    "    '-.______.-'     ",
    "        '  '         ",
    "                   ",
)


def _logo_width() -> int:
    return len((_PIN_ASCII if PLAIN else _PIN)[0])


def _status_line() -> str:
    if os.environ.get("MAPLEAD_STATUS"):
        return os.environ["MAPLEAD_STATUS"]
    return ""


def _caps() -> list[tuple[str, str]]:
    """Live stats shown next to the logo (never drifts out of date)."""
    from .data import cities as CT
    from .data import countries as CO
    from .data import fields as FD
    from .data import verticals as VT
    from . import exporters, providers

    return [
        ("countries", str(len(CO.COUNTRIES))),
        ("cities", str(CT.count())),
        ("business types", str(len(VT.VERTICALS))),
        ("data fields", str(len(FD.FIELDS))),
        ("api providers", str(len(providers.PROVIDERS) - 1)),
        ("export formats", str(len(exporters.FORMATS))),
    ]


def banner(width: int | None = None, subtitle: str | None = None,
           status: str | None = None, compact: bool = False) -> str:
    """The full cool banner: logo, gradient wordmark, tagline, status bar."""
    width = width or min(term_width(), 110)
    logo = _PIN_ASCII if PLAIN else _PIN
    mark = wordmark()
    tagline = subtitle or "G O O G L E   M A P S   L E A D   E X T R A C T O R"

    lw = _logo_width()
    gap = 3
    total = lw + gap + max(len(r) for r in mark)
    left = max(1, (width - total) // 2)
    left = 0 if total > width else left

    lines: list[str] = []
    lines.append(c(hr(GLYPH["h"], width, "cyan")))
    lines.append("")

    # wordmark rows, gradient across the whole block
    for row in mark:
        lines.append(" " * left + gradient(row, start=84, end=201))
    lines.append(" " * left + c(f"v{VERSION}", "cyan", bold=True))
    lines.append("")
    lines.append(" " * left + c(tagline, "cyan", dim=True))
    lines.append("")

    # logo + capability strip
    caps = _caps()
    cap_lines = [
        c("  " + a.ljust(16), "cyan") + c(b.rjust(2), "yellow", bold=True)
        for a, b in caps
    ]

    logo_rows = list(logo)
    for i in range(max(len(logo_rows), len(cap_lines))):
        art_ = logo_rows[i] if i < len(logo_rows) else " " * lw
        art_ = c(art_, "magenta", bold=True)
        side = cap_lines[i] if i < len(cap_lines) else ""
        lines.append(" " * left + art_ + "   " + side)

    lines.append("")
    if status is None:
        status = _status_line()
    if status:
        lines.append(" " * left + c(f"{GLYPH['dot']} {status}", "white", dim=True))
    if not compact:
        lines.append("")
        lines.append(c(hr(GLYPH["h"], width, "cyan")))
    return "\n".join(lines)


def mini_banner() -> str:
    """One-liner used when the big banner is suppressed."""
    mark = wordmark("MAPLEAD")[1]
    return gradient(mark, 84, 201) + c(f"  v{VERSION}  ", "cyan")


def section(title: str, width: int | None = None) -> str:
    """A titled horizontal rule."""
    width = width or min(term_width(), 110)
    text = f" {title} "
    pad = max(0, width - len(text) - 4)
    return "\n" + c(GLYPH["tl"] + GLYPH["h"] + text + GLYPH["h"] * pad + GLYPH["tr"],
                    "cyan", bold=True)


def panel(title: str, rows: list[str], width: int | None = None, color: str = "cyan") -> str:
    width = width or min(term_width(), 110)
    inner = width - 4
    head = f" {title} ".upper()
    out = [c(GLYPH["tl"] + head + GLYPH["h"] * max(0, inner - len(head)) + GLYPH["tr"], color, bold=True)]
    for r in rows:
        plain_len = len(_strip_ansi(r))
        out.append(c(GLYPH["v"], color) + " " + r + " " * max(0, inner - plain_len - 1) + c(GLYPH["v"], color))
    out.append(c(GLYPH["bl"] + GLYPH["h"] * (inner + 1) + GLYPH["br"], color))
    return "\n".join(out)


_ANSI_RESET = "\x1b[0m"


def _strip_ansi(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\x1b":
            j = i + 1
            if j < len(s) and s[j] == "[":
                j += 1
                while j < len(s) and not s[j].isalpha():
                    j += 1
                i = j + 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


# double-line frame used by success_block (has an ASCII twin for plain output)
if PLAIN:
    _FRAME = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "=", "v": "|"}
else:
    _FRAME = {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"}


def success_block(msg: str, detail: str = "") -> str:
    """5-row block-font DONE stamp + a one-line summary, framed.

    Anything wider than the terminal is printed underneath the box instead of
    inside it, so a long export path can never break the frame.
    """
    body = block_text("DONE", fill=("#" if PLAIN else "█"))
    if msg:
        body += ["", " " + msg]
    if detail:
        body.append(" " + detail)

    limit = max(28, term_width() - 6)
    inside = [row for row in body if len(_strip_ansi(row)) <= limit]
    spill = [row for row in body if len(_strip_ansi(row)) > limit]

    inner = max(len(_strip_ansi(row)) for row in inside)
    out = [c(_FRAME["tl"] + _FRAME["h"] * (inner + 2) + _FRAME["tr"], "green", bold=True)]
    for row in inside:
        pad = " " * (inner - len(_strip_ansi(row)))
        out.append(c(_FRAME["v"], "green", bold=True) + " " + row + pad + " " +
                   c(_FRAME["v"], "green", bold=True))
    out.append(c(_FRAME["bl"] + _FRAME["h"] * (inner + 2) + _FRAME["br"], "green", bold=True))
    out.extend(spill)
    return "\n".join(out)


def spinner(i: int) -> str:
    return GLYPH["spin"][i % len(GLYPH["spin"])]