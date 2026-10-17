"""
MAPLEAD interactive terminal UI: prompts, menus, tables, progress.
Pure stdlib - works over ssh, in pipes, and in dumb terminals.
"""

from __future__ import annotations

import shutil
import sys
import time
from typing import Any, Callable, Sequence

from . import art
from .art import GLYPH, PLAIN, _strip_ansi, c, panel, section  # noqa: F401  (re-exported)

# names this module re-exports from .art for the CLI's convenience
__all__ = [
    "GLYPH", "PLAIN", "art", "c", "panel", "section", "_strip_ansi",
    "term_size", "out", "raw_in", "vwidth", "pad", "trunc", "n_columns",
    "col_width", "page_fit", "grid", "step", "hint", "warn", "error", "ok",
    "info", "ask_text", "ask_number", "ask_choice", "ask_multiselect",
    "ask_yesno", "table", "Progress", "clear_screen",
]

# --------------------------------------------------------------------------- #
# low level io
# --------------------------------------------------------------------------- #

WIDTH = min(art.term_width(), 110)
COL_GAP = 4


def term_size() -> tuple[int, int]:
    """(width, height) of the terminal, with sane fallbacks."""
    try:
        size = shutil.get_terminal_size((96, 24))
        return max(48, size.columns), max(10, size.lines)
    except Exception:
        return 96, 24


def out(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def raw_in(prompt: str) -> str | None:
    try:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        line = sys.stdin.readline()
        if line == "":
            return None
        return line.rstrip("\n").rstrip("\r")
    except (EOFError, KeyboardInterrupt):
        out()
        return None


def vwidth(text: str) -> int:
    return len(_strip_ansi(text))


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - vwidth(text))
    if align == "right":
        return " " * gap + text
    if align == "center":
        return " " * (gap // 2) + text + " " * (gap - gap // 2)
    return text + " " * gap


def trunc(text: str, width: int) -> str:
    text = str(text if text is not None else "")
    if vwidth(text) <= width:
        return text
    if width <= 1:
        return "…"
    return text[: width - 1] + "…"


# --------------------------------------------------------------------------- #
# multi-column layout (keeps long lists on one screen - no endless scrolling)
# --------------------------------------------------------------------------- #

def n_columns(count: int, min_col: int = 30, max_cols: int = 3) -> int:
    """How many columns of `min_col` chars still fit in the terminal."""
    avail = max(24, WIDTH - 3)
    n = 1
    while n < min(count, max_cols) and (n + 1) * (min_col + COL_GAP) - COL_GAP <= avail:
        n += 1
    return n


def col_width(ncols: int, min_col: int = 30) -> int:
    """Printable width of one column once `ncols` of them share the line."""
    avail = max(24, WIDTH - 3)
    return max(10, (avail - COL_GAP * (ncols - 1)) // ncols)


def page_fit(ncols: int, lines_per_item: int = 1, reserve: int = 11) -> int:
    """How many items fit on one screen, so a list needs no scrolling."""
    rows = max(3, (term_size()[1] - reserve) // max(1, lines_per_item))
    return max(6, rows * ncols)


def grid(cells: Sequence[str], min_col: int = 30, max_cols: int = 3,
         indent: str = "   ") -> list[str]:
    """
    Lay out cells side by side, left to right, then top to bottom.

    Every cell may hold several lines ("label\\nsub-label") - the rows are
    aligned so the columns stay visually straight. Cell *i* lands in column
    i % ncols, so keeping the numbering in step with `cells` keeps the
    reading order left-to-right as well.
    """
    if not cells:
        return []
    ncols = n_columns(len(cells), min_col, max_cols)
    if ncols == 1:
        return [indent + line for cell in cells for line in cell.split("\n")]

    width = col_width(ncols, min_col)
    blocks = [cell.split("\n") for cell in cells]
    lines: list[str] = []
    for start in range(0, len(blocks), ncols):
        row = blocks[start:start + ncols]
        height = max(len(b) for b in row)
        for r in range(height):
            parts = [pad(trunc(b[r] if r < len(b) else "", width), width) for b in row]
            lines.append(indent + (" " * COL_GAP).join(parts).rstrip())
    return lines


# --------------------------------------------------------------------------- #
# prompt widgets
# --------------------------------------------------------------------------- #

def step(n: int, total: int, title: str) -> None:
    """Print a numbered step header."""
    tag = c(f"[{n}/{total}]", "yellow", bold=True)
    out()
    out(f" {tag} {c(title.upper(), 'white', bold=True)}")


def hint(text: str) -> None:
    out(f"   {c(text, 'white', dim=True)}")


def warn(text: str) -> None:
    out(f"   {c(GLYPH['warn'], 'yellow')} {c(text, 'yellow')}")


def error(text: str) -> None:
    out(f"   {c(GLYPH['cross'], 'red')} {c(text, 'red')}")


def ok(text: str) -> None:
    out(f"   {c(GLYPH['check'], 'green')} {c(text, 'green')}")


def info(text: str) -> None:
    out(f"   {c(GLYPH['bullet'], 'cyan')} {text}")


def ask_text(question: str, default: str = "", placeholder: str = "",
              required: bool = False, allow_skip: bool = False) -> str:
    """Free-text input with default + placeholder ghosting."""
    while True:
        label = c(question, "white")
        if default:
            label += c(f" [{default}]", "white", dim=True)
        elif placeholder:
            label += c(f" ({placeholder})", "white", dim=True)
        if allow_skip:
            label += c("   (enter = skip)", "white", dim=True)
        raw = raw_in(f"   {label} {GLYPH['arrow']} ")
        if raw is None:
            raise KeyboardInterrupt
        raw = raw.strip()
        if not raw:
            if default:
                return default
            if not required or allow_skip:
                return ""
            error("this one is required - type a value or press enter to skip")
            continue
        return raw


def ask_number(question: str, default: int, minimum: int = 1,
               maximum: int = 100_000, suffix: str = "") -> int:
    while True:
        label = c(question, "white") + c(f" [{default}{suffix}]", "white", dim=True)
        raw = raw_in(f"   {label} {GLYPH['arrow']} ")
        if raw is None:
            raise KeyboardInterrupt
        raw = raw.strip()
        if not raw:
            return default
        try:
            val = int(raw.replace(" ", "").replace("k", "000"))
        except ValueError:
            error(f"'{raw}' is not a number")
            continue
        if val < minimum or val > maximum:
            error(f"please pick between {minimum} and {maximum}")
            continue
        return val


def ask_choice(question: str, items: Sequence[Any],
               labeler: Callable[[Any], str] | None = None,
               default_index: int = 0, page: int = 0,
               sublabeler: Callable[[Any], str] | None = None,
               extra: Sequence[tuple[str, str]] = (),
               min_col: int = 30, max_cols: int = 3) -> Any:
    """
    Numbered picker with type-to-filter, laid out in as many columns as fit.
      - number            -> choose
      - substring         -> filter the list (a single remaining match auto-selects)
      - any of `extra`    -> e.g. "other" / "__custom__"

    page=0 means "size the page to the terminal", which is what stops the long
    catalogues (65 countries, 68 verticals) from turning into a scroll marathon.
    """
    labeler = labeler or (lambda x: str(x))
    sublabeler = sublabeler or (lambda x: "")
    extra_keys = [k for k, _ in extra]

    # how much room one item needs -> how many fit on screen
    probe = list(items)[:60]
    per_item = 2 if any(sublabeler(it) for it in probe) else 1
    ncols = n_columns(len(items), min_col, max_cols)
    colw = col_width(ncols, min_col)
    limit = page if page > 0 else page_fit(ncols, per_item)

    term = ""
    while True:
        matches = items
        if term:
            needle = term.lower()
            matches = [it for it in items
                       if needle in labeler(it).lower()
                       or (sublabeler(it) and needle in sublabeler(it).lower())]
        out()
        out(f"   {c(question, 'white', bold=True)}")
        if term:
            out(f"   {c(f'filter: {term!r}', 'yellow')} "
                f"{c('(clear: .)', 'white', dim=True)}")
        if not matches:
            error("nothing matches that filter - press . to clear it")
            term = ""
            continue
        if term and len(matches) == 1:
            hit = matches[0]
            ok(f"selected {c(labeler(hit), 'yellow', bold=True)}"
               + (f"  {c(sublabeler(hit), 'white', dim=True)}" if sublabeler(hit) else ""))
            return hit

        shown = matches[:limit]
        cells = []
        for i, it in enumerate(shown, 1):
            num = c(f"{i:>2}", "cyan", bold=True)
            cell = f"{num} {trunc(labeler(it), colw)}"
            sub = sublabeler(it)
            if sub:
                cell += "\n   " + trunc(sub, colw)
            cells.append(cell)
        for line in grid(cells, min_col=min_col, max_cols=max_cols):
            out(line)
        if len(matches) > len(shown):
            hidden = len(matches) - len(shown)
            out(f"   {c(f'… {hidden} more match' + ('es' if hidden != 1 else ''), 'white', dim=True)}"
                f" {c(f'({len(matches)} total - keep typing to narrow it)', 'white', dim=True)}")
        out(f"   {c('· type text to filter', 'white', dim=True)}")

        for key, desc in extra:
            out(f"   {c('  ·', 'green')} {c(key, 'green', bold=True)} {c(desc, 'white', dim=True)}")

        tip = f"#{default_index + 1}" if not term else "#"
        raw = raw_in(f"   {c(tip, 'white', dim=True)} {GLYPH['arrow']} ")
        if raw is None:
            raise KeyboardInterrupt
        raw = raw.strip()
        if not raw:
            return matches[min(default_index, len(matches) - 1)]
        if raw == ".":
            term = ""
            continue
        if raw in extra_keys:
            return raw
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(shown):
                return shown[idx]
            error(f"pick between 1 and {len(shown)}")
            continue
        term = raw
        default_index = 0


def _parse_selection(raw: str, names: Sequence[str]) -> list[int] | None:
    """Parse '1,3-5,all,none,rec,name substring'. None => invalid."""
    raw = raw.strip().lower()
    if raw in ("all", "a", "*"):
        return list(range(len(names)))
    if raw in ("none", "n", "-"):
        return []
    picks: list[int] = []
    for chunk in raw.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk and not chunk.startswith("-"):
            a, _, b = chunk.partition("-")
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                picks.extend(range(max(lo, 1) - 1, min(hi, len(names))))
                continue
        if chunk.isdigit():
            n = int(chunk)
            if 1 <= n <= len(names):
                picks.append(n - 1)
                continue
            return None
        hits = [i for i, n in enumerate(names) if chunk in n.lower()]
        if not hits:
            return None
        picks.extend(hits)
    seen, out_ = set(), []
    for p in picks:
        if p not in seen:
            seen.add(p)
            out_.append(p)
    return out_


def ask_multiselect(question: str, items: Sequence[tuple[str, str]],
                    recommended: Sequence[str] = (),
                    page: int = 0,
                    presets: Sequence[tuple[str, str, Sequence[str]]] = (),
                    min_col: int = 46, max_cols: int = 2) -> list[str]:
    """
    items: sequence of (key, label). recommended: subset of keys.
    Accepts: 1,4-9 / all / none / rec / keyword / .  (clear)
    presets: sequence of (token, description, keys) e.g. ('rec', 'recommended', (...))
    Rendered in columns, sized to the terminal.
    """
    names = [k for k, _ in items]
    labels = dict(items)
    defaults = [k for k in names if k in recommended] or names
    preset_map = {token: list(keys) for token, _, keys in presets}

    ncols = n_columns(len(items), min_col, max_cols)
    colw = col_width(ncols, min_col)
    limit = page if page > 0 else page_fit(ncols, 1, reserve=9)

    while True:
        out()
        out(f"   {c(question, 'white', bold=True)}")
        out(f"   {c('default =', 'white', dim=True)} {c(','.join(defaults), 'yellow')}")
        shown = names[:limit]
        cells = []
        text_w = max(8, colw - 5)          # 2 for the number, 2 for the "*" mark
        for i, k in enumerate(shown, 1):
            mark = c(f"{i:>2}", "cyan", bold=True)
            star = c(" *", "yellow", bold=True) if k in recommended else "  "
            cells.append(f"{mark} " + pad(trunc(labels[k], text_w), text_w) + star)
        for line in grid(cells, min_col=min_col, max_cols=max_cols):
            out(line)
        if len(names) > len(shown):
            out(f"   {c(f'… {len(names) - len(shown)} more (use all / rec / a range)', 'white', dim=True)}")
        chips = [("all", "everything"), ("none", "empty")] + \
                [(tok, desc) for tok, desc, _ in presets]
        out("   ".join(f"{c('·', 'green')} {c(t, 'green', bold=True)} "
                       f"{c(d, 'white', dim=True)}" for t, d in chips))
        raw = raw_in(f"   {c(','.join(defaults)[:40], 'white', dim=True)} {GLYPH['arrow']} ")
        if raw is None:
            raise KeyboardInterrupt
        raw = raw.strip()
        if not raw or raw.lower() in ("rec", "recommended"):
            return list(defaults)
        if raw.lower() in preset_map:
            return list(preset_map[raw.lower()])
        sel = _parse_selection(raw, names)
        if sel is None:
            error("could not parse that - try: 1,3-5  or  all  or  rec  or a keyword")
            continue
        return [names[i] for i in sel]


def ask_yesno(question: str, default: bool = True) -> bool:
    opts = "Y/n" if default else "y/N"
    while True:
        raw = raw_in(f"   {c(question, 'white')} {c('[' + opts + ']', 'white', dim=True)} {GLYPH['arrow']} ")
        if raw is None:
            raise KeyboardInterrupt
        raw = raw.strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        error("answer y or n")


# --------------------------------------------------------------------------- #
# tables
# --------------------------------------------------------------------------- #

def table(headers: Sequence[str], rows: Sequence[Sequence[Any]],
          aligns: Sequence[str] | None = None, max_width: int | None = None,
          head_color: str = "cyan") -> str:
    """Compact column-aligned table (ANSI aware, truncates to terminal width)."""
    if not rows:
        return c("   (nothing to show)", "white", dim=True)
    cols = len(headers)
    aligns = list(aligns or ["left"] * cols)
    budget = max_width or WIDTH - 4

    data = [[("" if v is None else str(v)) for v in r] for r in rows]
    widths = [max(vwidth(h), *(vwidth(r[i]) for r in data)) if data else vwidth(h)
              for i, h in enumerate(headers) for _ in [0]]
    widths = []
    for i, h in enumerate(headers):
        w = vwidth(h)
        for r in data:
            w = max(w, vwidth(r[i]))
        widths.append(w)

    gap = 2
    while sum(widths) + gap * (cols - 1) > budget:
        widest = max(range(cols), key=lambda i: widths[i])
        if widths[widest] <= 8:
            break
        widths[widest] -= 1

    out_lines = []
    head = "   " + "  ".join(c(pad(trunc(h, widths[i]), widths[i], "center"),
                               head_color, bold=True) for i, h in enumerate(headers))
    out_lines.append(head)
    out_lines.append("   " + c(GLYPH["h"] * (min(sum(widths) + gap * (cols - 1), budget)), "cyan", dim=True))
    for r in data:
        cells = []
        for i in range(cols):
            cells.append(pad(trunc(r[i], widths[i]), widths[i], aligns[i]))
        out_lines.append("   " + c("  ", "cyan", dim=True).join(cells))
    return "\n".join(out_lines)


# --------------------------------------------------------------------------- #
# progress
# --------------------------------------------------------------------------- #

class Progress:
    """Single-line live progress. Degrades to periodic lines when piped."""

    def __init__(self, label: str = "working", total: int | None = None):
        self.label = label
        self.total = total
        self.n = 0
        self.live = sys.stdout.isatty()
        self.t0 = time.time()
        self._i = 0
        self._last = 0.0
        self._lastline = ""

    def advance(self, amount: int = 1, note: str = "") -> None:
        self.n += amount
        self._render(note)

    def update(self, note: str = "") -> None:
        self._render(note)

    def _render(self, note: str) -> None:
        if not self.live or PLAIN:
            now = time.time()
            if now - self._last < 1.0 and self.n != (self.total or 0):
                return
            self._last = now
            tail = f"  {note}" if note else ""
            out(f"   {c(GLYPH['dot'], 'cyan')} {self.label}{tail}")
            return
        now = time.time()
        if now - self._last < 0.08:
            return
        self._last = now
        self._i += 1
        sp = art.spinner(self._i)
        cnt = f"{self.n}/{self.total}" if self.total else f"{self.n}"
        line = f"   {c(sp, 'cyan')} {self.label}  {c(cnt, 'yellow', bold=True)}{('  ' + note) if note else ''}"
        width = max(0, WIDTH - vwidth(line))
        self._lastline = line
        sys.stdout.write("\r" + line + " " * width)
        sys.stdout.flush()

    def done(self, message: str = "") -> None:
        self._render("")
        if self.live and not PLAIN:
            sys.stdout.write("\r" + " " * (WIDTH + 4) + "\r")
            sys.stdout.flush()
        if message:
            out(f"   {c(GLYPH['check'], 'green')} {c(message, 'green')}")

    def stop(self) -> None:
        if self.live and not PLAIN and self._lastline:
            sys.stdout.write("\r" + " " * (WIDTH + 4) + "\r")
            sys.stdout.flush()


def clear_screen() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()