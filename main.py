"""Calculator Pro - a safe desktop calculator with history, memory and
scientific functions, built with CustomTkinter.

Requires:  pip install -r requirements.txt
Run:       python main.py
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from calculator_pro import Calculator
from calculator_pro.ui_common import (
    BUTTON_ROWS,
    GRID_COLUMNS,
    display_font_size,
    key_from_event,
    pick_font_family,
    shorten,
)

# Every color is a (light mode, dark mode) pair so the whole UI follows the theme.
COLORS = {
    "window": ("#f2f2f7", "#1c1c1e"),
    "panel": ("#ffffff", "#2a2a2d"),
    "panel_hover": ("#e5e5ea", "#3a3a3c"),
    "text": ("#111111", "#ffffff"),
    "muted": ("#6e6e73", "#9a9a9f"),
    "error": ("#d70015", "#ff6b6b"),
    "accent": ("#1f6aa5", "#4da3ff"),
}
# role -> (background, hover, text)
BUTTON_COLORS = {
    "digit": (("#e5e5ea", "#3a3a3c"), ("#d1d1d6", "#4a4a4d"), ("#1c1c1e", "#ffffff")),
    "function": (("#c7c7cc", "#5a5a5e"), ("#b4b4ba", "#6a6a6f"), ("#1c1c1e", "#ffffff")),
    "scientific": (("#dfe7f1", "#2f3a46"), ("#cdd9e7", "#3b4856"), ("#1f4e79", "#a9cdf5")),
    "memory": (("#f2f2f7", "#242426"), ("#e5e5ea", "#333336"), ("#1f6aa5", "#4da3ff")),
    "operator": (("#1f6aa5", "#1f6aa5"), ("#2b7fc2", "#2b7fc2"), ("#ffffff", "#ffffff")),
    "equals": (("#1f6aa5", "#1f6aa5"), ("#2b7fc2", "#2b7fc2"), ("#ffffff", "#ffffff")),
    "clear": (("#d35400", "#d35400"), ("#e8660f", "#e8660f"), ("#ffffff", "#ffffff")),
}
DISPLAY_FONT_SIZE = 38
CALC_WIDTH = 380
HISTORY_WIDTH = 260
WINDOW_HEIGHT = 680


class CalculatorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.calc = Calculator()
        self.font_family = pick_font_family(self)
        self._status = ""          # temporary message, e.g. "Copied"
        self._status_job = None
        self.history_visible = True

        self.title("Calculator Pro")
        self.geometry(f"{CALC_WIDTH + HISTORY_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(340, 620)
        self.configure(fg_color=COLORS["window"])

        # The history column is packed first so it always keeps its width.
        self.history_column = ctk.CTkFrame(self, fg_color=COLORS["panel"],
                                           corner_radius=0, width=HISTORY_WIDTH)
        self.history_column.pack(side="right", fill="y")
        self.history_column.pack_propagate(False)
        self.calc_column = ctk.CTkFrame(self, fg_color="transparent", width=CALC_WIDTH)
        self.calc_column.pack(side="left", fill="both", expand=True)

        self._build_header()
        self._build_display()
        self._build_buttons()
        self._build_history_panel()

        self.bind("<Key>", self._on_key)
        for sequence in ("<Control-c>", "<Control-C>", "<Command-c>"):
            try:
                self.bind(sequence, self._copy_result)
            except tk.TclError:
                pass  # e.g. <Command-c> only exists on macOS
        self._refresh()

    # -- UI construction ----------------------------------------------------
    def _font(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(self.font_family, size, weight)

    def _pill_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, width=96, height=30, corner_radius=15,
            fg_color=COLORS["panel"], hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"], font=self._font(13), command=command,
        )

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.calc_column, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 0))
        self.history_button = self._pill_button(header, "Hide history", self._toggle_history)
        self.history_button.pack(side="left")
        self.theme_button = self._pill_button(header, "", self._toggle_theme)
        self.theme_button.pack(side="right")
        self._update_theme_button()

    def _build_display(self) -> None:
        panel = ctk.CTkFrame(self.calc_column, corner_radius=16, fg_color=COLORS["panel"])
        panel.pack(fill="x", padx=16, pady=12)

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(10, 0))
        self.memory_label = ctk.CTkLabel(top, text="", anchor="w",
                                         text_color=COLORS["accent"], font=self._font(13, "bold"))
        self.memory_label.pack(side="left")
        self.previous_label = ctk.CTkLabel(top, text="", anchor="e",
                                           text_color=COLORS["muted"], font=self._font(14))
        self.previous_label.pack(side="right", fill="x", expand=True)

        self.display_font = self._font(DISPLAY_FONT_SIZE, "bold")
        self.display_label = ctk.CTkLabel(panel, text="0", anchor="e", height=60,
                                          text_color=COLORS["text"], font=self.display_font)
        self.display_label.pack(fill="x", padx=16, pady=(0, 10))

    def _build_buttons(self) -> None:
        grid = ctk.CTkFrame(self.calc_column, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=12, pady=(0, 14))

        for r, row in enumerate(BUTTON_ROWS):
            column = 0
            for spec in row:
                fg, hover, text_color = BUTTON_COLORS[spec.role]
                small = spec.role in ("memory", "scientific")
                button = ctk.CTkButton(
                    grid, text=spec.label,
                    fg_color=fg, hover_color=hover, text_color=text_color,
                    font=self._font(15 if small else 20,
                                    "normal" if spec.role == "digit" else "bold"),
                    corner_radius=12, height=40 if small else 52,
                    width=1,  # let the grid decide the width
                    command=lambda key=spec.key: self._press(key),
                )
                button.grid(row=r, column=column, columnspan=spec.span,
                            padx=4, pady=4, sticky="nsew")
                column += spec.span

        for c in range(GRID_COLUMNS):
            grid.columnconfigure(c, weight=1, uniform="col")
        for r, row in enumerate(BUTTON_ROWS):
            small = row[0].role in ("memory", "scientific")
            grid.rowconfigure(r, weight=2 if small else 3, uniform=f"row{small}")

    def _build_history_panel(self) -> None:
        top = ctk.CTkFrame(self.history_column, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))
        ctk.CTkLabel(top, text="History", text_color=COLORS["text"],
                     font=self._font(16, "bold")).pack(side="left")
        ctk.CTkButton(
            top, text="Clear", width=60, height=26, corner_radius=13,
            fg_color=COLORS["panel_hover"], hover_color=BUTTON_COLORS["function"][1],
            text_color=COLORS["text"], font=self._font(12),
            command=self._clear_history,
        ).pack(side="right")

        self.history_list = ctk.CTkScrollableFrame(self.history_column, fg_color="transparent")
        self.history_list.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        self.history_empty = ctk.CTkLabel(
            self.history_list, text="No calculations yet.\nClick an item to reuse its result.",
            text_color=COLORS["muted"], font=self._font(12), justify="center",
        )

    # -- behaviour ----------------------------------------------------------
    def _press(self, key: str) -> None:
        self.calc.press(key)
        self._refresh()

    def _on_key(self, event) -> None:
        if event.state & 0x4:   # Control is held: leave shortcuts alone
            return
        key = key_from_event(event.keysym, event.char)
        if key is not None:
            self._press(key)

    def _copy_result(self, _event=None) -> str:
        self.clipboard_clear()
        self.clipboard_append(self.calc.copy_text())
        self._show_status("Copied to clipboard")
        return "break"

    def _show_status(self, message: str) -> None:
        self._status = message
        if self._status_job is not None:
            self.after_cancel(self._status_job)
        self._status_job = self.after(1500, self._clear_status)
        self._refresh()

    def _clear_status(self) -> None:
        self._status = ""
        self._status_job = None
        self._refresh()

    def _use_history_entry(self, result: str) -> None:
        self.calc.insert_value(result)
        self._refresh()

    def _clear_history(self) -> None:
        self.calc.clear_history()
        self._refresh()

    def _refresh(self) -> None:
        text = self.calc.display
        self.display_font.configure(size=display_font_size(text, DISPLAY_FONT_SIZE))
        self.display_label.configure(text=text)

        if self.calc.error:
            self.previous_label.configure(text=self.calc.error, text_color=COLORS["error"])
        elif self._status:
            self.previous_label.configure(text=self._status, text_color=COLORS["accent"])
        else:
            self.previous_label.configure(text=shorten(self.calc.previous, 34),
                                          text_color=COLORS["muted"])

        memory = self.calc.memory_text
        self.memory_label.configure(text=f"M = {shorten(memory, 12)}" if memory else "")
        self._render_history()

    def _render_history(self) -> None:
        entries = self.calc.history
        signature = tuple(entries)
        if getattr(self, "_history_signature", None) == signature:
            return  # nothing changed
        self._history_signature = signature

        for child in self.history_list.winfo_children():
            if child is not self.history_empty:
                child.destroy()
        if not entries:
            self.history_empty.pack(pady=20)
            return
        self.history_empty.pack_forget()
        for entry in entries:
            self._add_history_item(entry)

    def _add_history_item(self, entry) -> None:
        """One clickable history row: expression (small) above result (bold)."""
        item = ctk.CTkFrame(self.history_list, fg_color="transparent",
                            corner_radius=10, cursor="hand2")
        item.pack(fill="x", padx=4, pady=2)
        expression = ctk.CTkLabel(item, text=f"{shorten(entry.expression, 28)} =",
                                  anchor="e", text_color=COLORS["muted"],
                                  font=self._font(12), height=18)
        expression.pack(fill="x", padx=10, pady=(6, 0))
        result = ctk.CTkLabel(item, text=shorten(entry.result, 18), anchor="e",
                              text_color=COLORS["text"], font=self._font(18, "bold"),
                              height=26)
        result.pack(fill="x", padx=10, pady=(0, 6))

        def on_click(_event, value=entry.result):
            self._use_history_entry(value)

        def set_hover(active: bool):
            item.configure(fg_color=COLORS["panel_hover"] if active else "transparent")

        for widget in (item, expression, result):
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>", lambda _e: set_hover(True))
            widget.bind("<Leave>", lambda _e: set_hover(False))

    def _toggle_history(self) -> None:
        self.history_visible = not self.history_visible
        height = self.winfo_height()
        if self.history_visible:
            self.calc_column.pack_forget()
            self.history_column.pack(side="right", fill="y")
            self.calc_column.pack(side="left", fill="both", expand=True)
            self.history_button.configure(text="Hide history")
            self.geometry(f"{CALC_WIDTH + HISTORY_WIDTH}x{height}")
        else:
            self.history_column.pack_forget()
            self.history_button.configure(text="Show history")
            self.geometry(f"{CALC_WIDTH}x{height}")

    def _toggle_theme(self) -> None:
        new_mode = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        self.theme_button.configure(
            text="Light mode" if ctk.get_appearance_mode() == "Dark" else "Dark mode"
        )


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = CalculatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
