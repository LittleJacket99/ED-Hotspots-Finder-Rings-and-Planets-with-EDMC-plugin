#!/usr/bin/env python3

"""Consolidated final visual/menu layer for the v8 desktop UI.

This module replaces the former final_base + final_menus split while keeping the
same behaviour and inheritance order over the tested visual layer.
"""

import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import ttk

from hotspots_finder_gui_v8_visual import FinderV8VisualApp, THEME


MINERALS_TABLE_URL = "https://docs.google.com/spreadsheets/d/1SVTKW-Uy6sjjR0oFqKjCI5tDvYAu97ORmocXwl1ckU0/edit?gid=0#gid=0"
VOLCANISM_TABLE_URL = "https://wiknow.pages.dev/ref/ground-mining"


class FinderV8FinalBaseApp(FinderV8VisualApp):
    """Final mockup-driven visual refinements."""

    SYSTEM_FILTERS_X = 16
    SYSTEM_FILTERS_Y = 575
    SYSTEM_FILTERS_WIDTH = 496
    SYSTEM_FILTERS_HEIGHT = 167
    SYSTEM_FILTERS_TOP_ROW_Y = 610
    SYSTEM_FILTERS_BOTTOM_ROW_Y = 670

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except tk.TclError:
            pass

        super()._configure_styles()

        style = ttk.Style(self)
        style.configure(
            "FlatResults.TNotebook",
            background=THEME["field"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        try:
            style.layout("FlatResults.TNotebook.Tab", [])
        except tk.TclError:
            pass

        style.configure(
            "TCombobox",
            fieldbackground=THEME["field"],
            background=THEME["panel2"],
            foreground=THEME["text"],
            arrowcolor=THEME["muted"],
            bordercolor=THEME["line2"],
            lightcolor=THEME["line2"],
            darkcolor=THEME["line2"],
            borderwidth=1,
            relief="flat",
            padding=(4, 1, 1, 1),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", THEME["field"])],
            foreground=[("readonly", THEME["text"])],
            selectbackground=[("readonly", THEME["field"])],
            selectforeground=[("readonly", THEME["text"])],
        )

    def _build_ui(self):
        super()._build_ui()
        self.bind_all("<Button-1>", self._clear_input_focus_on_click, add="+")
        self.after_idle(self._install_flat_result_tabs)

    @staticmethod
    def _is_text_input_widget(widget):
        return isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

    def _clear_input_focus(self, clicked_widget=None):
        try:
            focused = self.focus_get()
        except tk.TclError:
            return

        if focused is None or not self._is_text_input_widget(focused):
            return
        if clicked_widget is not None and self._is_text_input_widget(clicked_widget):
            return

        try:
            target = clicked_widget.winfo_toplevel() if clicked_widget is not None else self
            target.focus_set()
        except tk.TclError:
            try:
                self.focus_set()
            except tk.TclError:
                pass

    def _clear_input_focus_on_click(self, event):
        self._clear_input_focus(getattr(event, "widget", None))

    def _install_flat_result_tabs(self):
        notebook = getattr(self, "notebook", None)
        panel = getattr(self, "_results_panel", None)
        if notebook is None or panel is None:
            return
        if getattr(self, "_flat_tabs_bar", None) is not None:
            return

        try:
            notebook.configure(style="FlatResults.TNotebook")
            if notebook.winfo_manager() == "pack":
                notebook.pack_configure(pady=(31, 8))
        except tk.TclError:
            pass

        self._flat_tabs_bar = tk.Frame(
            panel,
            bg=THEME["panel"],
            bd=0,
            highlightthickness=0,
        )
        self._flat_tabs_bar.place(x=12, y=43, height=31)

        self._flat_tab_widgets = {}
        self._rebuild_flat_result_tabs()
        notebook.bind("<<NotebookTabChanged>>", self._on_flat_tab_changed, add="+")
        self._schedule_flat_tab_sync()

    def _rebuild_flat_result_tabs(self):
        bar = getattr(self, "_flat_tabs_bar", None)
        notebook = getattr(self, "notebook", None)
        if bar is None or notebook is None:
            return

        for child in bar.winfo_children():
            child.destroy()
        self._flat_tab_widgets = {}

        try:
            tabs = list(notebook.tabs())
        except tk.TclError:
            return

        for tab_id in tabs:
            try:
                text = str(notebook.tab(tab_id, "text") or "")
            except tk.TclError:
                text = ""

            label = tk.Label(
                bar,
                text=text,
                bg=THEME["panel2"],
                fg=THEME["text"],
                font=("Segoe UI", 9),
                padx=12,
                pady=6,
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground=THEME["line"],
                highlightcolor=THEME["line2"],
                cursor="hand2",
            )
            label.pack(side="left", padx=(0, 2))
            label.bind(
                "<Button-1>",
                lambda _event, tab=tab_id: self._select_flat_tab(tab),
            )
            label.bind(
                "<Enter>",
                lambda _event, tab=tab_id: self._hover_flat_tab(tab, True),
            )
            label.bind(
                "<Leave>",
                lambda _event, tab=tab_id: self._hover_flat_tab(tab, False),
            )
            self._flat_tab_widgets[tab_id] = label

        self._refresh_flat_tab_states()

    def _select_flat_tab(self, tab_id):
        notebook = getattr(self, "notebook", None)
        if notebook is None:
            return
        try:
            notebook.select(tab_id)
        except tk.TclError:
            return
        self._refresh_flat_tab_states()

    def _hover_flat_tab(self, tab_id, entering):
        notebook = getattr(self, "notebook", None)
        label = getattr(self, "_flat_tab_widgets", {}).get(tab_id)
        if notebook is None or label is None:
            return

        try:
            selected = notebook.select()
        except tk.TclError:
            selected = ""
        if tab_id == selected:
            return

        try:
            label.configure(
                bg=THEME["hover"] if entering else THEME["panel2"],
                highlightbackground=THEME["line2"] if entering else THEME["line"],
            )
        except tk.TclError:
            pass

    def _on_flat_tab_changed(self, _event=None):
        self._refresh_flat_tab_states()

    def _refresh_flat_tab_states(self):
        notebook = getattr(self, "notebook", None)
        widgets = getattr(self, "_flat_tab_widgets", {})
        if notebook is None or not widgets:
            return

        try:
            selected = notebook.select()
        except tk.TclError:
            selected = ""

        for tab_id, label in widgets.items():
            try:
                label.configure(
                    bg=THEME["field"] if tab_id == selected else THEME["panel2"],
                    fg=THEME["accent"] if tab_id == selected else THEME["text"],
                    highlightbackground=(
                        THEME["line2"] if tab_id == selected else THEME["line"]
                    ),
                )
            except tk.TclError:
                pass

    def _schedule_flat_tab_sync(self):
        if not self.winfo_exists():
            return

        notebook = getattr(self, "notebook", None)
        widgets = getattr(self, "_flat_tab_widgets", {})
        if notebook is not None and widgets:
            try:
                tabs = list(notebook.tabs())
            except tk.TclError:
                tabs = []

            if set(tabs) != set(widgets):
                self._rebuild_flat_result_tabs()
            else:
                for tab_id in tabs:
                    label = widgets.get(tab_id)
                    if label is None:
                        continue
                    try:
                        text = str(notebook.tab(tab_id, "text") or "")
                        if str(label.cget("text")) != text:
                            label.configure(text=text)
                    except tk.TclError:
                        pass
                self._refresh_flat_tab_states()

        self.after(250, self._schedule_flat_tab_sync)

    def _position_system_filter_controls(self):
        placements = {
            "_faction_box": (18, self.SYSTEM_FILTERS_TOP_ROW_Y, 237, 55),
            "_power_box": (285, self.SYSTEM_FILTERS_TOP_ROW_Y, 225, 55),
            "_reference_box": (18, self.SYSTEM_FILTERS_BOTTOM_ROW_Y, 142, 55),
            "_distance_box": (165, self.SYSTEM_FILTERS_BOTTOM_ROW_Y, 90, 55),
            "_power_states_box": (285, self.SYSTEM_FILTERS_BOTTOM_ROW_Y, 225, 70),
        }
        for name, (x, y, width, height) in placements.items():
            frame = getattr(self, name, None)
            if frame is None:
                continue
            try:
                frame.place(x=x, y=y, width=width, height=height)
                frame.lift()
            except tk.TclError:
                pass

    def _build_system_filters_backplate(self):
        self._system_filters_backplate = tk.Frame(
            self._stage,
            bg=THEME["panel"],
            highlightthickness=1,
            highlightbackground=THEME["line"],
            bd=0,
        )
        self._system_filters_backplate.place(
            x=self.SYSTEM_FILTERS_X,
            y=self.SYSTEM_FILTERS_Y,
            width=self.SYSTEM_FILTERS_WIDTH,
            height=self.SYSTEM_FILTERS_HEIGHT,
        )
        self._system_filters_backplate.lower()

        self._system_filters_caption = tk.Label(
            self._system_filters_backplate,
            text="SYSTEM FILTERS",
            bg=THEME["panel"],
            fg=THEME["accent"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            bd=0,
            highlightthickness=0,
        )
        self._system_filters_caption.place(x=10, y=7, width=160, height=25)
        self._position_system_filter_controls()

    def _refresh_unified_system_filters_panel(self):
        backplate = getattr(self, "_system_filters_backplate", None)
        if backplate is None or getattr(self, "_results_expanded", False):
            return

        try:
            backplate.place(
                x=self.SYSTEM_FILTERS_X,
                y=self.SYSTEM_FILTERS_Y,
                width=self.SYSTEM_FILTERS_WIDTH,
                height=self.SYSTEM_FILTERS_HEIGHT,
            )
            backplate.lower()
            self._position_system_filter_controls()
            caption = getattr(self, "_system_filters_caption", None)
            if caption is not None:
                caption.lift()
        except tk.TclError:
            return

        self._normalize_system_filters_colors()

    def _apply_visual_theme(self):
        super()._apply_visual_theme()
        self._normalize_system_filters_colors()
        self._style_mockup_controls(self)
        self._refresh_flat_tab_states()

    def _normalize_system_filters_colors(self):
        backplate = getattr(self, "_system_filters_backplate", None)
        if backplate is not None:
            try:
                backplate.configure(bg=THEME["panel"])
            except tk.TclError:
                pass

        for name in (
            "_faction_box",
            "_power_box",
            "_power_states_box",
            "_reference_box",
            "_distance_box",
        ):
            frame = getattr(self, name, None)
            if frame is None:
                continue
            try:
                frame.configure(bg=THEME["panel"], highlightthickness=0, bd=0)
            except tk.TclError:
                pass
            for child in frame.winfo_children():
                try:
                    if isinstance(child, (tk.Label, tk.Checkbutton)):
                        child.configure(bg=THEME["panel"])
                except tk.TclError:
                    pass

        caption = getattr(self, "_system_filters_caption", None)
        if caption is not None:
            try:
                caption.configure(bg=THEME["panel"])
            except tk.TclError:
                pass

    def _ensure_checkbox_images(self):
        if hasattr(self, "_checkbox_unchecked_image"):
            return

        unchecked = tk.PhotoImage(master=self, width=15, height=11)
        checked = tk.PhotoImage(master=self, width=15, height=11)
        unchecked.put(THEME["line2"], to=(0, 1, 9, 10))
        unchecked.put(THEME["field"], to=(1, 2, 8, 9))
        checked.put(THEME["accent"], to=(0, 1, 9, 10))
        checked.put(THEME["accent"], to=(1, 2, 8, 9))
        self._checkbox_unchecked_image = unchecked
        self._checkbox_checked_image = checked

    def _style_mockup_controls(self, parent):
        self._ensure_checkbox_images()
        for widget in parent.winfo_children():
            try:
                if isinstance(widget, tk.Button):
                    self._style_mockup_button(widget)
                elif isinstance(widget, tk.Checkbutton):
                    self._style_mockup_checkbutton(widget)
                elif isinstance(widget, tk.Entry):
                    self._style_mockup_entry(widget)
                elif isinstance(widget, tk.Text):
                    self._style_mockup_text(widget)
            except tk.TclError:
                pass
            try:
                self._style_mockup_controls(widget)
            except tk.TclError:
                pass

    def _style_mockup_entry(self, entry):
        try:
            entry.configure(
                bg=THEME["field"],
                fg=THEME["text"],
                insertbackground=THEME["text"],
                relief="flat",
                bd=3,
                highlightthickness=1,
                highlightbackground=THEME["line2"],
                highlightcolor=THEME["accent"],
            )
        except tk.TclError:
            pass

    def _style_mockup_text(self, text_widget):
        is_system_input = text_widget is getattr(self, "systems_text", None)
        try:
            text_widget.configure(
                bg=THEME["field"],
                fg=THEME["text"],
                insertbackground=THEME["text"],
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=THEME["line2"],
                highlightcolor=THEME["accent"],
                padx=4 if is_system_input else 0,
                pady=2 if is_system_input else 0,
            )
        except tk.TclError:
            pass

    def _remove_regular_button_border(self, button):
        for line in getattr(button, "_edhf_border_lines", ()):
            try:
                line.destroy()
            except tk.TclError:
                pass
        button._edhf_border_lines = []

    def _sync_regular_button_border(self, button):
        lines = getattr(button, "_edhf_border_lines", None)
        if not lines or len(lines) != 4:
            return
        try:
            if not button.winfo_exists() or not button.winfo_ismapped():
                for line in lines:
                    line.place_forget()
                return
            x, y = button.winfo_x(), button.winfo_y()
            width, height = button.winfo_width(), button.winfo_height()
            if width < 2 or height < 2:
                return
            positions = (
                (x, y, width, 1),
                (x, y + height - 1, width, 1),
                (x, y, 1, height),
                (x + width - 1, y, 1, height),
            )
            for line, (lx, ly, lw, lh) in zip(lines, positions):
                line.place(x=lx, y=ly, width=lw, height=lh)
                line.lift(button)
        except tk.TclError:
            pass

    def _ensure_regular_button_border(self, button):
        lines = getattr(button, "_edhf_border_lines", None)
        if lines and len(lines) == 4:
            self.after_idle(lambda w=button: self._sync_regular_button_border(w))
            return

        try:
            lines = [
                tk.Frame(
                    button.master,
                    bg=THEME["line2"],
                    bd=0,
                    highlightthickness=0,
                    cursor="hand2",
                )
                for _ in range(4)
            ]
        except tk.TclError:
            return
        button._edhf_border_lines = lines

        def _border_click(_event, w=button):
            self._clear_input_focus(w)
            try:
                if str(w.cget("state")) != "disabled":
                    w.invoke()
            except tk.TclError:
                pass
            return "break"

        def _border_enter(_event, w=button):
            try:
                if str(w.cget("state")) != "disabled":
                    w.configure(bg=w._edhf_hover_bg)
            except tk.TclError:
                pass

        def _border_leave(_event, w=button):
            try:
                w.configure(bg=w._edhf_base_bg)
            except tk.TclError:
                pass

        for line in lines:
            line.bind("<Button-1>", _border_click)
            line.bind("<Enter>", _border_enter)
            line.bind("<Leave>", _border_leave)

        button.bind(
            "<Configure>",
            lambda _event, w=button: self.after_idle(
                lambda: self._sync_regular_button_border(w)
            ),
            add="+",
        )
        button.bind(
            "<Map>",
            lambda _event, w=button: self.after_idle(
                lambda: self._sync_regular_button_border(w)
            ),
            add="+",
        )
        button.bind(
            "<Unmap>",
            lambda _event, ls=lines: [line.place_forget() for line in ls],
            add="+",
        )
        self.after_idle(lambda w=button: self._sync_regular_button_border(w))

    def _style_mockup_button(self, button):
        text = str(button.cget("text") or "").strip().upper()
        if text == "SCAN":
            base_bg, hover_bg = THEME["accent"], THEME["accent2"]
            fg = active_fg = "#121512"
            self._remove_regular_button_border(button)
        elif text == "STOP":
            base_bg, hover_bg = "#3b2d2d", "#503737"
            fg, active_fg = "#d9bcbc", "#f0d6d6"
            self._remove_regular_button_border(button)
        else:
            base_bg, hover_bg = THEME["panel2"], THEME["hover"]
            fg = active_fg = THEME["text"]

        try:
            button.configure(
                bg=base_bg,
                fg=fg,
                activebackground=hover_bg,
                activeforeground=active_fg,
                relief="flat",
                overrelief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
        except tk.TclError:
            return

        button._edhf_base_bg = base_bg
        button._edhf_hover_bg = hover_bg
        if text not in {"SCAN", "STOP"}:
            self._ensure_regular_button_border(button)
        if getattr(button, "_edhf_mockup_bound", False):
            return
        button._edhf_mockup_bound = True

        button.bind("<Button-1>", lambda _e, w=button: self._clear_input_focus(w), add="+")

        def _enter(_event, w=button):
            try:
                if str(w.cget("state")) != "disabled":
                    w.configure(bg=w._edhf_hover_bg)
            except tk.TclError:
                pass

        def _leave(_event, w=button):
            try:
                w.configure(bg=w._edhf_base_bg)
            except tk.TclError:
                pass

        button.bind("<Enter>", _enter, add="+")
        button.bind("<Leave>", _leave, add="+")

    def _style_mockup_checkbutton(self, checkbutton):
        try:
            bg = str(checkbutton.cget("bg") or THEME["panel"])
            checkbutton.configure(
                image=self._checkbox_unchecked_image,
                selectimage=self._checkbox_checked_image,
                indicatoron=False,
                compound="left",
                bg=bg,
                fg=THEME["text"],
                activebackground=bg,
                activeforeground=THEME["text"],
                selectcolor=bg,
                relief="flat",
                overrelief="flat",
                offrelief="flat",
                bd=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                cursor="arrow",
            )
        except tk.TclError:
            return

        if getattr(checkbutton, "_edhf_mockup_bound", False):
            return
        checkbutton._edhf_mockup_bound = True

        def _click(_event, w=checkbutton):
            self._clear_input_focus(w)
            try:
                if str(w.cget("state")) != "disabled":
                    w.invoke()
            except tk.TclError:
                pass
            return "break"

        checkbutton.bind("<Button-1>", _click)

    def _open_settings_dialog(self):
        super()._open_settings_dialog()
        window = getattr(self, "_settings_window", None)
        if window is not None:
            self.after_idle(lambda: self._style_mockup_controls(window))

    def _apply_brand_header(self):
        header = getattr(self, "_header_frame", None)
        if header is None:
            return
        try:
            header.configure(bg=THEME["header"])
            for child in header.winfo_children():
                child.destroy()

            title_block = tk.Frame(
                header,
                bg=THEME["header"],
                bd=0,
                highlightthickness=0,
            )
            title_block.place(x=24, y=12, width=390, height=58)

            tk.Label(
                title_block,
                text="ED Hotspots Finder",
                bg=THEME["header"],
                fg=THEME["accent"],
                font=("Segoe UI", 17, "bold"),
                anchor="w",
            ).pack(anchor="w")

            subtitle_row = tk.Frame(
                title_block,
                bg=THEME["header"],
                bd=0,
                highlightthickness=0,
            )
            subtitle_row.pack(anchor="w", fill="x", pady=(2, 0))
            tk.Label(
                subtitle_row,
                text="Rings & Planets",
                bg=THEME["header"],
                fg=THEME["text"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            ).pack(side="left")
            tk.Label(
                subtitle_row,
                text="•",
                bg=THEME["header"],
                fg=THEME["muted"],
                font=("Segoe UI", 8, "bold"),
                anchor="center",
            ).pack(side="left", padx=(7, 6), pady=(1, 0))
            tk.Label(
                subtitle_row,
                text="v8",
                bg=THEME["header"],
                fg=THEME["muted"],
                font=("Segoe UI", 8),
                anchor="w",
            ).pack(side="left", pady=(1, 0))
        except tk.TclError:
            return


class FinderV8FinalUIApp(FinderV8FinalBaseApp):
    """Final custom popup/menu and Results outline layer."""

    RESULTS_OUTLINE = "#59616b"
    RESULTS_OUTLINE_THICKNESS = 1
    RESULTS_NATIVE_MASK = 3

    MENU_BG = "#252a2f"
    MENU_HOVER = "#30363d"
    MENU_BORDER = "#59616b"
    MENU_TEXT = "#e8edf2"
    MENU_MUTED = "#939ba5"
    MENU_SEPARATOR = "#59616b"
    MENU_SELECTED_BG = "#1d321e"
    MENU_SELECTED_TEXT = "#5acd57"

    FILTER_MENU_MIN_WIDTH = 180
    FILTER_MENU_MAX_WIDTH = 420
    FILTER_MENU_MAX_LIST_HEIGHT = 300
    FILTER_MENU_ROW_HEIGHT = 28

    def _configure_styles(self):
        super()._configure_styles()
        style = ttk.Style(self)
        style.configure(
            "FlatResults.TNotebook",
            background=THEME["field"],
            bordercolor=THEME["field"],
            lightcolor=THEME["field"],
            darkcolor=THEME["field"],
            relief="flat",
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )

    def _build_ui(self):
        self._custom_popup = None
        super()._build_ui()
        self.after_idle(self._install_results_outline)

    def _dismiss_custom_popup(self, _event=None):
        popup = getattr(self, "_custom_popup", None)
        self._custom_popup = None
        if popup is None:
            return
        try:
            if popup.winfo_exists():
                popup.destroy()
        except tk.TclError:
            pass

    def _run_custom_popup_command(self, command):
        self._dismiss_custom_popup()
        if command is not None:
            self.after_idle(command)

    def _place_custom_popup(self, popup, x_root, y_root, width, height):
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        x = min(max(0, int(x_root)), max(0, screen_width - int(width)))
        y = min(max(0, int(y_root)), max(0, screen_height - int(height)))
        geometry = f"{int(width)}x{int(height)}+{x}+{y}"
        popup.geometry(geometry)
        popup.deiconify()
        popup.lift()
        popup.update_idletasks()
        popup.geometry(geometry)

    def _show_custom_popup(self, items, x_root, y_root, *, min_width=0):
        self._dismiss_custom_popup()
        popup = tk.Toplevel(self)
        self._custom_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=self.MENU_BORDER)

        outer = tk.Frame(popup, bg=self.MENU_BORDER, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=self.MENU_BG, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        for item in items:
            if item is None:
                tk.Frame(
                    inner,
                    bg=self.MENU_SEPARATOR,
                    bd=0,
                    highlightthickness=0,
                    height=1,
                ).pack(fill="x", padx=7, pady=4)
                continue
            label_text, command, enabled = item
            entry = tk.Label(
                inner,
                text=label_text,
                bg=self.MENU_BG,
                fg=self.MENU_TEXT if enabled else self.MENU_MUTED,
                anchor="w",
                justify="left",
                padx=10,
                pady=5,
                bd=0,
                relief="flat",
                highlightthickness=0,
                font=("Segoe UI", 9),
                cursor="hand2" if enabled else "",
            )
            entry.pack(fill="x")
            if enabled:
                entry.bind(
                    "<Enter>",
                    lambda _e, w=entry: w.configure(bg=self.MENU_HOVER),
                    add="+",
                )
                entry.bind(
                    "<Leave>",
                    lambda _e, w=entry: w.configure(bg=self.MENU_BG),
                    add="+",
                )
                entry.bind(
                    "<ButtonRelease-1>",
                    lambda _e, cb=command: self._run_custom_popup_command(cb),
                    add="+",
                )

        popup.update_idletasks()
        width = max(int(min_width), popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        self._place_custom_popup(popup, x_root, y_root, width, height)
        popup.bind("<Escape>", self._dismiss_custom_popup, add="+")
        popup.bind(
            "<FocusOut>",
            lambda _e: self.after_idle(self._dismiss_custom_popup),
            add="+",
        )
        try:
            popup.focus_force()
        except tk.TclError:
            pass
        return popup

    def _build_reference_tables_button(self):
        self.reference_tables_button = tk.Button(
            self._stage,
            text="Reference Tables ▾",
            command=self._show_reference_tables_menu,
            bg="#3a4148",
            fg=self.MENU_TEXT,
            activebackground="#46515c",
            activeforeground=self.MENU_TEXT,
            relief="flat",
            padx=10,
            pady=3,
            font=("Segoe UI", 9),
        )
        self.reference_tables_button.place(x=1170, y=20, width=170, height=30)

    def _show_reference_tables_menu(self):
        button = self.reference_tables_button
        items = [
            ("Minerals Table", lambda: webbrowser.open(MINERALS_TABLE_URL, new=2), True),
            ("Volcanism Table", lambda: webbrowser.open(VOLCANISM_TABLE_URL, new=2), True),
        ]
        self._show_custom_popup(
            items,
            button.winfo_rootx(),
            button.winfo_rooty() + button.winfo_height(),
            min_width=button.winfo_width(),
        )

    def _build_result_context_menu(self):
        for tree in (
            self.hotspot_tree,
            self.planet_tree,
            self.community_tree,
            self.systems_result_tree,
        ):
            tree.bind("<Button-3>", self._show_result_context_menu, add="+")
            tree.bind("<Control-c>", self._copy_selected_rows_shortcut, add="+")

    def _show_result_context_menu(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if not iid:
            self._dismiss_custom_popup()
            return "break"
        if iid not in tree.selection():
            tree.selection_set(iid)
        tree.focus(iid)
        self._context_tree = tree
        self._context_iid = iid
        selected_iids = self._selected_context_iids()
        selected_systems = self._selected_context_systems()
        row_count = len(selected_iids)
        system_count = len(selected_systems)
        items = [
            (
                "Copy row" if row_count == 1 else f"Copy {row_count} rows",
                self._copy_context_row,
                bool(row_count),
            ),
            (
                "Copy system" if system_count <= 1 else f"Copy {system_count} systems",
                self._copy_context_system,
                bool(system_count),
            ),
        ]
        if row_count == 1 and system_count == 1:
            items.extend(
                [
                    None,
                    ("Open system in Inara", lambda: self._open_context_system("inara"), True),
                    ("Open system in Spansh", lambda: self._open_context_system("spansh"), True),
                    ("Open system in EDSM", lambda: self._open_context_system("edsm"), True),
                ]
            )
        self._show_custom_popup(items, event.x_root, event.y_root, min_width=215)
        return "break"

    def _show_column_filter(self, table, column):
        selected = self._column_filter_state[table].get(column)
        choices = self._choices_for_column(table, column)
        labels = [self._filter_label(value) for value in choices]
        self._dismiss_custom_popup()

        popup = tk.Toplevel(self)
        self._custom_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=self.MENU_BORDER)
        outer = tk.Frame(popup, bg=self.MENU_BORDER, bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=self.MENU_BG, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        menu_font = tkfont.Font(root=self, family="Segoe UI", size=9)
        longest = max(["All", *labels], key=lambda text: menu_font.measure(text))
        content_width = max(
            self.FILTER_MENU_MIN_WIDTH,
            min(self.FILTER_MENU_MAX_WIDTH, menu_font.measure(longest) + 34),
        )

        def choose(value):
            self._dismiss_custom_popup()
            self.after_idle(lambda v=value: self._set_column_filter(table, column, v))

        def make_entry(parent, text, value, is_selected):
            normal_bg = self.MENU_SELECTED_BG if is_selected else self.MENU_BG
            normal_fg = self.MENU_SELECTED_TEXT if is_selected else self.MENU_TEXT
            entry = tk.Label(
                parent,
                text=text,
                bg=normal_bg,
                fg=normal_fg,
                anchor="w",
                justify="left",
                padx=12,
                pady=5,
                bd=0,
                relief="flat",
                highlightthickness=0,
                font=("Segoe UI", 9),
                cursor="hand2",
            )
            entry.pack(fill="x")
            entry.bind(
                "<Enter>",
                lambda _e, w=entry, fg=normal_fg: w.configure(
                    bg=self.MENU_HOVER,
                    fg=fg,
                ),
                add="+",
            )
            entry.bind(
                "<Leave>",
                lambda _e, w=entry, bg=normal_bg, fg=normal_fg: w.configure(
                    bg=bg,
                    fg=fg,
                ),
                add="+",
            )
            entry.bind(
                "<ButtonRelease-1>",
                lambda _e, v=value: choose(v),
                add="+",
            )
            return entry

        make_entry(inner, "All", None, selected is None)
        tk.Frame(
            inner,
            bg=self.MENU_SEPARATOR,
            bd=0,
            highlightthickness=0,
            height=1,
        ).pack(fill="x", padx=7, pady=(3, 4))

        list_height = min(
            max(self.FILTER_MENU_ROW_HEIGHT, len(choices) * self.FILTER_MENU_ROW_HEIGHT),
            self.FILTER_MENU_MAX_LIST_HEIGHT,
        )
        needs_scroll = (
            len(choices) * self.FILTER_MENU_ROW_HEIGHT
            > self.FILTER_MENU_MAX_LIST_HEIGHT
        )

        if choices:
            list_host = tk.Frame(inner, bg=self.MENU_BG, bd=0, highlightthickness=0)
            list_host.pack(fill="both", expand=True)
            canvas = tk.Canvas(
                list_host,
                bg=self.MENU_BG,
                bd=0,
                highlightthickness=0,
                relief="flat",
                width=content_width,
                height=list_height,
            )
            if needs_scroll:
                scrollbar = ttk.Scrollbar(
                    list_host,
                    orient="vertical",
                    command=canvas.yview,
                    style="Vertical.TScrollbar",
                )
                canvas.configure(yscrollcommand=scrollbar.set)
                scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            list_frame = tk.Frame(canvas, bg=self.MENU_BG, bd=0, highlightthickness=0)
            window_id = canvas.create_window((0, 0), window=list_frame, anchor="nw")
            for value, label in zip(choices, labels):
                make_entry(list_frame, label, value, value == selected)

            def sync_scroll_region(_event=None):
                try:
                    canvas.configure(scrollregion=canvas.bbox("all"))
                except tk.TclError:
                    pass

            def sync_list_width(event):
                try:
                    canvas.itemconfigure(window_id, width=event.width)
                except tk.TclError:
                    pass

            list_frame.bind("<Configure>", sync_scroll_region, add="+")
            canvas.bind("<Configure>", sync_list_width, add="+")
            sync_scroll_region()

            if needs_scroll:
                def on_mousewheel(event):
                    try:
                        steps = int(-event.delta / 120)
                    except (TypeError, ValueError):
                        steps = 0
                    if steps:
                        canvas.yview_scroll(steps, "units")
                    return "break"

                popup.bind("<MouseWheel>", on_mousewheel, add="+")
        else:
            tk.Label(
                inner,
                text="(No values)",
                bg=self.MENU_BG,
                fg=self.MENU_MUTED,
                anchor="w",
                justify="left",
                padx=12,
                pady=5,
                bd=0,
                relief="flat",
                highlightthickness=0,
                font=("Segoe UI", 9),
            ).pack(fill="x")

        popup.update_idletasks()
        width = content_width + 2
        height = popup.winfo_reqheight()
        self._place_custom_popup(
            popup,
            self.winfo_pointerx(),
            self.winfo_pointery(),
            width,
            height,
        )
        popup.bind("<Escape>", self._dismiss_custom_popup, add="+")
        popup.bind(
            "<FocusOut>",
            lambda _e: self.after_idle(self._dismiss_custom_popup),
            add="+",
        )
        try:
            popup.focus_force()
        except tk.TclError:
            pass

    def _install_results_outline(self):
        notebook = getattr(self, "notebook", None)
        panel = getattr(self, "_results_panel", None)
        if notebook is None or panel is None:
            return
        if getattr(self, "_results_outline_lines", None):
            self._sync_results_outline()
            return
        try:
            self._results_outline_masks = [
                tk.Frame(panel, bg=THEME["field"], bd=0, highlightthickness=0)
                for _ in range(4)
            ]
            self._results_outline_lines = [
                tk.Frame(panel, bg=self.RESULTS_OUTLINE, bd=0, highlightthickness=0)
                for _ in range(4)
            ]
        except tk.TclError:
            return

        notebook.bind(
            "<Configure>",
            self._schedule_results_outline_sync,
            add="+",
        )
        notebook.bind(
            "<Map>",
            self._schedule_results_outline_sync,
            add="+",
        )
        self.bind(
            "<Configure>",
            self._schedule_results_outline_sync,
            add="+",
        )
        self._sync_results_outline()

    def _schedule_results_outline_sync(self, event=None):
        # Root bindings also receive descendant Configure events. Ignore those
        # from the decorative lines themselves and coalesce notebook/root work.
        if event is not None and event.widget not in (self, self.notebook):
            return
        if getattr(self, "_results_outline_after_id", None) is None:
            self._results_outline_after_id = self.after_idle(self._run_results_outline_sync)

    def _run_results_outline_sync(self):
        self._results_outline_after_id = None
        self._sync_results_outline()

    def _sync_results_outline(self):
        notebook = getattr(self, "notebook", None)
        masks = getattr(self, "_results_outline_masks", None)
        lines = getattr(self, "_results_outline_lines", None)
        if (
            notebook is None
            or not masks
            or len(masks) != 4
            or not lines
            or len(lines) != 4
        ):
            return

        try:
            if not notebook.winfo_exists() or not notebook.winfo_ismapped():
                for widget in (*masks, *lines):
                    widget.place_forget()
                return

            x, y = notebook.winfo_x(), notebook.winfo_y()
            width, height = notebook.winfo_width(), notebook.winfo_height()
            t, m = self.RESULTS_OUTLINE_THICKNESS, self.RESULTS_NATIVE_MASK
            if width <= m * 2 or height <= m * 2:
                return

            mask_positions = (
                (x, y, width, m),
                (x, y + height - m, width, m),
                (x, y, m, height),
                (x + width - m, y, m, height),
            )
            for mask, (lx, ly, lw, lh) in zip(masks, mask_positions):
                mask.place(x=lx, y=ly, width=lw, height=lh)
                mask.lift()

            line_positions = (
                (x, y, width, t),
                (x, y + height - t, width, t),
                (x, y, t, height),
                (x + width - t, y, t, height),
            )
            for line, (lx, ly, lw, lh) in zip(lines, line_positions):
                line.place(x=lx, y=ly, width=lw, height=lh)
                line.lift()
        except tk.TclError:
            pass
