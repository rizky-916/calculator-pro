"""Button layout, keyboard mapping and font helpers for the GUI."""

from __future__ import annotations

from typing import NamedTuple


class ButtonSpec(NamedTuple):
    label: str      # text on the button
    key: str        # key sent to Calculator.press()
    role: str       # memory, scientific, function, clear, digit, operator, equals
    span: int = 1   # number of grid columns


GRID_COLUMNS = 4

BUTTON_ROWS: list[list[ButtonSpec]] = [
    [ButtonSpec("MC", "MC", "memory"), ButtonSpec("MR", "MR", "memory"),
     ButtonSpec("M+", "M+", "memory"), ButtonSpec("M−", "M-", "memory")],
    [ButtonSpec("√x", "√", "scientific"), ButtonSpec("x²", "²", "scientific"),
     ButtonSpec("xʸ", "^", "scientific"), ButtonSpec("1/x", "INV", "scientific")],
    [ButtonSpec("C", "C", "clear"), ButtonSpec("(", "(", "function"),
     ButtonSpec(")", ")", "function"), ButtonSpec("⌫", "BACK", "function")],
    [ButtonSpec("7", "7", "digit"), ButtonSpec("8", "8", "digit"),
     ButtonSpec("9", "9", "digit"), ButtonSpec("÷", "/", "operator")],
    [ButtonSpec("4", "4", "digit"), ButtonSpec("5", "5", "digit"),
     ButtonSpec("6", "6", "digit"), ButtonSpec("×", "*", "operator")],
    [ButtonSpec("1", "1", "digit"), ButtonSpec("2", "2", "digit"),
     ButtonSpec("3", "3", "digit"), ButtonSpec("−", "-", "operator")],
    [ButtonSpec("±", "NEG", "function"), ButtonSpec("0", "0", "digit"),
     ButtonSpec(".", ".", "digit"), ButtonSpec("+", "+", "operator")],
    [ButtonSpec("%", "%", "function"), ButtonSpec("=", "=", "equals", span=3)],
]

_DIRECT_CHARS = set("0123456789.+-*/^%()")
_KEYSYM_MAP = {
    "Return": "=",
    "KP_Enter": "=",
    "BackSpace": "BACK",
    "Escape": "C",
    "Delete": "C",
}


def key_from_event(keysym: str, char: str) -> str | None:
    """Translate a Tk keyboard event into a Calculator key (or None)."""
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]
    if char == "=":
        return "="
    if len(char) == 1 and char in _DIRECT_CHARS:
        return char
    return None


_FONT_CANDIDATES = (
    "Segoe UI",          # Windows
    "SF Pro Display",    # macOS
    "Helvetica Neue",    # macOS (older)
    "Ubuntu",
    "Cantarell",
    "Noto Sans",
    "DejaVu Sans",       # most Linux distributions
    "Arial",
)


def pick_font_family(root) -> str:
    """Return the first nice sans-serif font installed on this system."""
    from tkinter import font as tkfont

    installed = set(tkfont.families(root))
    for family in _FONT_CANDIDATES:
        if family in installed:
            return family
    return "TkDefaultFont"


def display_font_size(text: str, base: int) -> int:
    """Shrink the main display font for long input so it stays visible.

    Very long input is still clipped on the left, so the end being typed
    stays visible (like most phone calculators).
    """
    length = len(text)
    if length <= 10:
        return base
    if length <= 13:
        return int(base * 0.78)
    if length <= 17:
        return int(base * 0.6)
    if length <= 22:
        return int(base * 0.47)
    return int(base * 0.4)


def shorten(text: str, limit: int) -> str:
    """Keep the end of a long string: '…' + last characters."""
    return text if len(text) <= limit else "…" + text[-(limit - 1):]
