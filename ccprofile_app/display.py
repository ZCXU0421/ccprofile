"""
display.py — Terminal UI panel drawing module for ccprofile.

Provides ANSI-colored box-drawing panels, key-value lines, status indicators,
and active-profile markers. Gracefully degrades to plain text when stdout is
not a TTY (e.g. piped or redirected output).

Layout geometry:
    panel width = w (total characters per line)
    inner = w - 2  (content between │ borders)

    ┌─ title ─── right_text ─┐   ← top border, width w
    │  content                │   ← body, width w (│ + inner + │)
    └─────────────────────────┘   ← bottom border, width w

    Sub-panels are indented 2 spaces within the inner area:
    │  ┌─ sub ───────────┐   │   ← prefix(2) + box(inner-3) + padding(1)
    │  │  content         │   │
    │  └─────────────────┘   │
"""

import shutil
import sys

from .i18n import t

# ---------------------------------------------------------------------------
# ANSI colour constants
# ---------------------------------------------------------------------------

CYAN    = "\x1b[36m"
GREEN   = "\x1b[32m"
RED     = "\x1b[31m"
YELLOW  = "\x1b[33m"
BOLD    = "\x1b[1m"
DIM     = "\x1b[2m"
REVERSE = "\x1b[7m"
RESET   = "\x1b[0m"

# ---------------------------------------------------------------------------
# TTY detection
# ---------------------------------------------------------------------------

def use_ansi() -> bool:
    """Return True if stdout is a TTY (colors enabled)."""
    return sys.stdout.isatty()


# When not a TTY, neutralise all escape sequences.
if not use_ansi():
    CYAN = GREEN = RED = YELLOW = BOLD = DIM = REVERSE = RESET = ""

# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


def _term_width() -> int:
    """Return effective terminal width, clamped to [40, 60]. Non-TTY: 80."""
    if not use_ansi():
        return 80
    return max(40, min(60, shutil.get_terminal_size().columns))


def _is_wide(ch: str) -> bool:
    """Return True if *ch* occupies 2 columns in a terminal (CJK, etc.)."""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF or   # CJK Unified Ideographs
        0x3400 <= code <= 0x4DBF or   # CJK Extension A
        0x3000 <= code <= 0x303F or   # CJK Symbols and Punctuation
        0x3040 <= code <= 0x309F or   # Hiragana
        0x30A0 <= code <= 0x30FF or   # Katakana
        0xFF01 <= code <= 0xFF60 or   # Fullwidth Forms
        0xAC00 <= code <= 0xD7AF or   # Hangul Syllables
        0xF900 <= code <= 0xFAFF      # CJK Compatibility Ideographs
    )


def _display_width(text: str) -> int:
    """Calculate the visual width of a string (CJK = 2, others = 1).

    ANSI escape sequences are stripped before measuring.
    Box-drawing characters (U+2500-U+257F) are correctly counted as width 1.
    """
    clean = ""
    i = 0
    while i < len(text):
        if text[i] == "\x1b":
            end = text.find("m", i)
            if end == -1:
                break
            i = end + 1
        else:
            clean += text[i]
            i += 1
    width = 0
    for ch in clean:
        width += 2 if _is_wide(ch) else 1
    return width


def _pad_to(text: str, target_width: int) -> str:
    """Pad *text* with trailing spaces so its display width equals *target_width*.

    If the text is already wider, return it unchanged.
    """
    dw = _display_width(text)
    if dw >= target_width:
        return text
    return text + " " * (target_width - dw)


def _truncate_to(text: str, target_width: int) -> str:
    """Truncate *text* so its display width is at most *target_width*."""
    if target_width <= 0:
        return ""
    dw = _display_width(text)
    if dw <= target_width:
        return text

    out = ""
    current_width = 0
    truncated = False
    i = 0
    while i < len(text):
        if text[i] == "\x1b":
            end = text.find("m", i)
            if end == -1:
                break
            out += text[i:end + 1]
            i = end + 1
            continue

        char_width = 2 if _is_wide(text[i]) else 1
        if current_width + char_width > target_width:
            truncated = True
            i += 1
            break

        out += text[i]
        current_width += char_width
        i += 1

    if truncated:
        while i < len(text):
            if text[i] == "\x1b":
                end = text.find("m", i)
                if end == -1:
                    break
                out += text[i:end + 1]
                i = end + 1
            else:
                i += 1

    return out

# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------


def status_dot(running: bool) -> str:
    """Coloured status indicator: green ● running / red ● stopped."""
    if running:
        return f"{GREEN}●{RESET} {t('display.proxy_running')}"
    return f"{RED}●{RESET} {t('display.proxy_stopped')}"


def active_marker() -> str:
    """Return the active-profile arrow marker (cyan bold ▸)."""
    return f"{CYAN}{BOLD}▸{RESET} "

# ---------------------------------------------------------------------------
# Key-value line
# ---------------------------------------------------------------------------


def kv(key: str, value: str, key_width: int = 14) -> str:
    """Format a key-value pair. Key is left-padded to *key_width* display chars."""
    return _pad_to(key, key_width) + value

# ---------------------------------------------------------------------------
# Sub-panel rendering
# ---------------------------------------------------------------------------


def sub_panel(title: str, body_lines: list, indent: int = 2, width: int = None) -> str:
    """Render an indented sub-panel.

    Each returned line has exactly ``width`` display characters, ready to be
    wrapped with ``│...│`` by the parent panel.

    Parameters
    ----------
    title : str
        Sub-panel title shown in the top border.
    body_lines : list
        Content lines (str) or nested ``("sub", title, lines)`` tuples.
    indent : int
        Left indent (spaces) within the parent's inner area.
    width : int or None
        Total available width (= parent's inner). Defaults to ``_term_width() - 2``.

    Returns the rendered string (no trailing newline).
    """
    w = width or (_term_width() - 2)
    prefix = " " * indent
    # Sub-panel box width = w - indent - 1 (leave 1 space right padding)
    box_w = w - indent - 1
    # Box inner = content between sub-panel's own │ borders
    box_inner = box_w - 2  # subtract left │ and right │

    if not use_ansi():
        lines_out = [f"{prefix}{title}"]
        for line in body_lines:
            if isinstance(line, str):
                lines_out.append(f"{prefix}  {line}")
            elif isinstance(line, tuple) and line[0] == "sub":
                nested = sub_panel(line[1], line[2], indent=indent + 2, width=w)
                lines_out.append(nested)
        return "\n".join(lines_out)

    # TTY: full box-drawing
    title_dw = _display_width(title)
    # Top: ┌─ title ──────┐
    # Width = 1(┌) + 1(─) + 1(space) + title_dw + 1(space) + dashes + 1(┐) = box_w
    dashes = max(1, box_w - title_dw - 5)
    top = f"{prefix}{CYAN}┌─{RESET} {BOLD}{title}{RESET} {CYAN}{'─' * dashes}┐{RESET}"
    lines_out = [_pad_to(top, w)]

    for line in body_lines:
        if isinstance(line, str):
            content = _pad_to(f"  {line}", box_inner)
            row = f"{prefix}{CYAN}│{RESET}{content}{CYAN}│{RESET}"
            lines_out.append(_pad_to(row, w))
        elif isinstance(line, tuple) and line[0] == "sub":
            nested = sub_panel(line[1], line[2], indent=indent + 2, width=w)
            lines_out.append(nested)

    # Bottom: └──────...──┘
    bottom = f"{prefix}{CYAN}└{'─' * (box_w - 2)}┘{RESET}"
    lines_out.append(_pad_to(bottom, w))
    return "\n".join(lines_out)

# ---------------------------------------------------------------------------
# Top-level panel rendering
# ---------------------------------------------------------------------------


def panel(title: str, right_text: str, body_lines: list, width: int = None) -> str:
    """Render a top-level panel.

    Parameters
    ----------
    title : str
        Left-side title (shown in bold).
    right_text : str
        Right-side annotation (e.g. "共 3 个", "单一模式").
    body_lines : list
        Content lines. Each element is either a plain string or a
        ``("sub", sub_title, sub_lines)`` tuple for a nested sub-panel.
    width : int or None
        Total panel width. Defaults to ``_term_width()`` (clamped 40-60).

    Returns the rendered panel string (no trailing newline).
    """
    w = width or _term_width()
    inner = w - 2  # content width between │ borders

    if not use_ansi():
        lines_out = [f"  {title}  {right_text}"]
        for line in body_lines:
            if isinstance(line, str):
                lines_out.append(f"    {line}")
            elif isinstance(line, tuple) and line[0] == "sub":
                nested = sub_panel(line[1], line[2], indent=2, width=inner)
                lines_out.append(nested)
        return "\n".join(lines_out)

    # TTY: full box-drawing
    # Top border: ┌──────...──────┐
    top = f"{CYAN}┌{'─' * (w - 2)}┐{RESET}"
    lines_out = [top]

    # Title line: │  title              right_text  │
    title_content = f"  {BOLD}{title}{RESET}"
    right_part = f"{DIM}{right_text}{RESET}"
    title_dw = _display_width(title_content)
    right_dw = _display_width(right_part)
    gap = inner - title_dw - right_dw
    if gap < 2:
        right_part = _truncate_to(right_part, max(1, inner - title_dw - 2))
        right_dw = _display_width(right_part)
    title_line = f"{CYAN}│{RESET}{_pad_to(title_content, inner - right_dw)}{right_part}{CYAN}│{RESET}"
    lines_out.append(title_line)

    # Separator: ├──────...──────┤
    sep = f"{CYAN}├{'─' * (w - 2)}┤{RESET}"
    lines_out.append(sep)

    # Body lines
    for line in body_lines:
        if isinstance(line, str):
            content = _pad_to(f" {line}", inner)
            lines_out.append(f"{CYAN}│{RESET}{content}{CYAN}│{RESET}")
        elif isinstance(line, tuple) and line[0] == "sub":
            nested = sub_panel(line[1], line[2], indent=2, width=inner)
            for nl in nested.split("\n"):
                lines_out.append(f"{CYAN}│{RESET}{_pad_to(nl, inner)}{CYAN}│{RESET}")

    # Bottom border: └──────...──────┘
    bottom = f"{CYAN}└{'─' * (w - 2)}┘{RESET}"
    lines_out.append(bottom)

    return "\n".join(lines_out)
