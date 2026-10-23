#!/usr/bin/env python3
"""Shared parts of the Master and Slave window grids.

Both tabs show a grid of windows; each window has a header (name, summary,
Rename / Pop out / close), a value table with per-address formats, scales,
names, copy, address base, drag selection and zebra rows, and the tab has a
Workspace menu. This module holds what is common to both: module helpers
for workspace files and formats, and ``TableUiMixin`` with the widget code.
A "pane" is the dict of widgets of one window; a "window" is its model,
with ``address``, ``qty``, ``base``, ``fmt``, ``formats``, ``scales`` and
``group_of_row()``.
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from mb_master import FORMAT_SIZES, REGISTER_FORMATS, validate_scale
from mb_theme import theme_colors

TABLE_PANE_MIN_WIDTH = 600
TABLE_PANE_MIN_ROWS = 3
TABLE_PANE_MAX_ROWS = 15
# Background of every second table row: one step from the table background.
TABLE_STRIPE_LIGHT = "#f2f4f6"
TABLE_STRIPE_DARK = "#262d34"
# Rows just written by a remote master (Slave tab).
TABLE_WRITTEN_LIGHT = "#fff1b8"
TABLE_WRITTEN_DARK = "#5a4b12"
TABLE_MAX_TITLE_LENGTH = 40
SERIAL_PARITIES = ("None", "Even", "Odd")
SERIAL_STOP_BITS = ("1", "2")
WORKSPACE_SUFFIX = ".mbsw"
# Characters Windows does not allow in file names.
INVALID_FILENAME_CHARS = '<>:"/\\|?*'
RESERVED_FILENAMES = ({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)}
                      | {f"LPT{i}" for i in range(1, 10)})
WHEEL_GUARD_TAG = "MBToolkit.MouseWheelGuard"


def parse_int_field(text, minimum, maximum, message):
    try:
        value = int(str(text).strip())
    except ValueError:
        raise ValueError(message) from None
    if not minimum <= value <= maximum:
        raise ValueError(message)
    return value


def validate_workspace_name(name):
    """Return a cleaned workspace name usable as a Windows file name."""
    name = str(name or "").strip().rstrip(".")
    if not name:
        raise ValueError("O nome do workspace não pode ficar vazio.")
    if len(name) > 60 or any(ch in INVALID_FILENAME_CHARS for ch in name) \
            or any(ord(ch) < 32 for ch in name):
        raise ValueError("O nome do workspace não pode ter os caracteres < > : \" / \\ | ? *.")
    if name.split(".")[0].upper() in RESERVED_FILENAMES:
        raise ValueError("Esse nome está reservado pelo Windows.")
    return name


def workspace_path(name, folder):
    return folder / f"{validate_workspace_name(name)}{WORKSPACE_SUFFIX}"


def list_workspaces(folder):
    """Names of the saved workspaces in *folder*, sorted alphabetically."""
    try:
        files = folder.glob(f"*{WORKSPACE_SUFFIX}")
        return sorted((f.stem for f in files if f.is_file()), key=str.casefold)
    except OSError:
        return []


def apply_format_to_rows(window, rows, fmt):
    """Set the per-address format of the selected rows of *window*.

    16-bit formats apply to every selected row. Multi-register formats need
    consecutive rows in a multiple of the format size and are applied in
    groups (2 registers for 32-bit, 4 for 64-bit). *fmt* None restores the
    window format. Existing per-address formats overlapping the selection are
    removed. Raises ValueError (PT canonical message) for an invalid selection.
    """
    rows = sorted(set(int(r) for r in rows))
    if not rows:
        raise ValueError("Seleciona pelo menos um endereço.")
    size = FORMAT_SIZES[fmt] if fmt else 1
    if size > 1:
        if rows != list(range(rows[0], rows[0] + len(rows))):
            raise ValueError("Seleciona registos seguidos para este formato.")
        if len(rows) % size:
            raise ValueError(
                "Este formato ocupa {size} registos: seleciona {size} registos seguidos "
                "(ou um múltiplo de {size})."
            )
        if rows[-1] >= window.qty:
            raise ValueError("Seleciona registos seguidos para este formato.")

    covered = {window.address + r for r in rows}
    for start, existing in list(window.formats.items()):
        span = set(range(start, start + FORMAT_SIZES[existing]))
        if span & covered:
            del window.formats[start]
    if fmt is not None:
        for index in range(0, len(rows), size):
            window.formats[window.address + rows[index]] = fmt


def validated_names(names):
    return {int(k): str(v) for k, v in (names.items() if isinstance(names, dict) else ())
            if str(k).isdigit() and str(v).strip()}


def validated_formats(formats):
    return {int(k): v for k, v in (formats.items() if isinstance(formats, dict) else ())
            if str(k).isdigit() and int(k) <= 0xFFFF and v in FORMAT_SIZES}


def validated_scales(scales):
    """Scales of a workspace window entry; invalid ones are dropped."""
    result = {}
    for key, item in (scales.items() if isinstance(scales, dict) else ()):
        try:
            if not str(key).isdigit() or int(key) > 0xFFFF or not isinstance(item, dict):
                raise ValueError
            raw, eng = item.get("raw", []), item.get("eng", [])
            result[int(key)] = validate_scale(raw[0], raw[1], eng[0], eng[1],
                                              item.get("decimals", 1), item.get("unit", ""))
        except (ValueError, TypeError, IndexError):
            continue
    return result


class TableUiMixin:
    """Widget code shared by the Master and Slave window grids."""

    # -- dialogs -----------------------------------------------------------------
    def _table_dialog(self, title):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)
        self._table_apply_toplevel_palette(dialog)
        body = ttk.Frame(dialog, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        return dialog, body

    def _table_ask_text(self, title, caption, initial):
        """Small modal text prompt; returns the text or None when cancelled."""
        dialog, body = self._table_dialog(title)
        ttk.Label(body, text=caption).grid(row=0, column=0, columnspan=2, sticky="w")
        value = tk.StringVar(value=initial)
        entry = ttk.Entry(body, textvariable=value, width=36)
        entry.grid(row=1, column=0, columnspan=2, pady=(4, 10), sticky="ew")
        result = {"text": None}

        def accept(_event=None):
            result["text"] = value.get()
            dialog.destroy()

        ttk.Button(body, text=self.tr("OK"), command=accept,
                   style="MBS.Primary.TButton").grid(row=2, column=0, sticky="e", padx=(0, 6))
        ttk.Button(body, text=self.tr("Cancelar"), command=dialog.destroy).grid(
            row=2, column=1, sticky="e")
        entry.bind("<Return>", accept)
        entry.bind("<Escape>", lambda _e: dialog.destroy())
        entry.focus_set()
        entry.select_range(0, "end")
        dialog.grab_set()
        self.wait_window(dialog)
        return result["text"]

    def _table_ask_scale(self, window, starts):
        """Ask for a linear scale and set it on the values starting at *starts*."""
        current = window.scales.get(starts[0]) or {
            "raw": [0, 65535], "eng": [0, 100], "decimals": 1, "unit": ""}

        dialog, body = self._table_dialog(self.tr("Escala"))
        ttk.Label(body, text=self.trf("Escala de {count} valor(es) selecionado(s):",
                                      count=len(starts))).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        def number_text(value):
            return f"{value:g}"

        variables = {
            "raw_min": tk.StringVar(value=number_text(current["raw"][0])),
            "raw_max": tk.StringVar(value=number_text(current["raw"][1])),
            "eng_min": tk.StringVar(value=number_text(current["eng"][0])),
            "eng_max": tk.StringVar(value=number_text(current["eng"][1])),
            "decimals": tk.StringVar(value=str(current["decimals"])),
            "unit": tk.StringVar(value=current.get("unit", "")),
        }
        layout = (
            (1, 0, "Bruto mín.", "raw_min"), (1, 2, "Bruto máx.", "raw_max"),
            (2, 0, "Eng. mín.", "eng_min"), (2, 2, "Eng. máx.", "eng_max"),
            (3, 0, "Casas decimais", "decimals"), (3, 2, "Unidade", "unit"),
        )
        first_entry = None
        for row, column, caption, key in layout:
            ttk.Label(body, text=self.tr(caption)).grid(row=row, column=column, sticky="w",
                                                        padx=(0, 6), pady=2)
            entry = ttk.Entry(body, width=10, textvariable=variables[key])
            entry.grid(row=row, column=column + 1, sticky="w", padx=(0, 14), pady=2)
            first_entry = first_entry or entry
        ttk.Label(body, text=self.tr("Valor = Eng. mín. + (bruto − Bruto mín.) × "
                                     "(Eng. máx. − Eng. mín.) / (Bruto máx. − Bruto mín.)"),
                  style="TLabel").grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 4))
        message_var = tk.StringVar()
        ttk.Label(body, textvariable=message_var, style="MBS.Master.Error.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w")
        result = {"ok": False}

        def accept(_event=None):
            try:
                scale = validate_scale(
                    variables["raw_min"].get(), variables["raw_max"].get(),
                    variables["eng_min"].get(), variables["eng_max"].get(),
                    variables["decimals"].get(), variables["unit"].get(),
                )
            except ValueError as exc:
                message_var.set(self.tr(str(exc)))
                return
            for address in starts:
                window.scales[address] = dict(scale)
            result["ok"] = True
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=4, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=self.tr("Aplicar"), command=accept,
                   style="MBS.Primary.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Cancelar"), command=dialog.destroy).grid(
            row=0, column=1)
        dialog.bind("<Return>", accept)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        if first_entry is not None:
            first_entry.focus_set()
        dialog.grab_set()
        self.wait_window(dialog)
        return result["ok"]

    # -- pane parts ----------------------------------------------------------------
    def _table_build_header(self, frame, pane, rename, popout, close):
        """Window name + summary on the left; Rename / Pop out / ✕ on the right.

        Closing a window never depends on the pane being wide.
        """
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        header.columnconfigure(1, weight=1)
        pane["name_var"] = tk.StringVar()
        pane["summary_var"] = tk.StringVar()
        name_label = ttk.Label(header, textvariable=pane["name_var"],
                               style="MBS.Master.Title.TLabel")
        name_label.grid(row=0, column=0, sticky="w")
        name_label.bind("<Double-1>", lambda _e: rename())
        ttk.Label(header, textvariable=pane["summary_var"]).grid(
            row=0, column=1, sticky="w", padx=(10, 0))
        header_buttons = ttk.Frame(header)
        header_buttons.grid(row=0, column=2, sticky="e")
        ttk.Button(header_buttons, text="Renomear", width=10, command=rename).grid(
            row=0, column=0, padx=(0, 3))
        pane["popout_btn"] = ttk.Button(header_buttons, text="Destacar", width=10,
                                        command=popout)
        pane["popout_btn"].grid(row=0, column=1, padx=(0, 3))
        ttk.Button(header_buttons, text="✕", width=3, command=close).grid(row=0, column=2)
        pane["header"] = header
        return header_buttons

    def _table_build_tree(self, frame, pane, row, on_double, on_return, on_menu):
        """Value table (address / name / value) with a thin 1 px frame."""
        # Classic Tk highlight ring, coloured in _table_configure_tree_tags().
        table = tk.Frame(frame, borderwidth=0, highlightthickness=1)
        table.grid(row=row, column=0, sticky="nsew", padx=6, pady=(2, 6))
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        pane["table_frame"] = table
        tree = ttk.Treeview(table, columns=("address", "name", "value"), show="headings",
                            height=TABLE_PANE_MAX_ROWS, selectmode="extended")
        for column, caption, width, anchor in (
            ("address", "Endereço", 90, "center"),
            ("name", "Nome", 200, "w"),
            ("value", "Valor", 160, "e"),
        ):
            tree.heading(column, text=self.tr(caption), anchor="center")
            tree.column(column, width=width, minwidth=60, anchor=anchor, stretch=column != "address")
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.bind("<Double-1>", on_double)
        tree.bind("<Return>", lambda _e: on_return())
        tree.bind("<Button-3>", on_menu)
        tree.bind("<ButtonPress-1>", lambda e: self._table_drag_start(pane, e), add="+")
        tree.bind("<B1-Motion>", lambda e: self._table_drag_move(pane, e))
        tree.bind("<ButtonRelease-1>", lambda _e: self._table_drag_stop(pane), add="+")
        for sequence in ("<Control-c>", "<Control-C>"):
            tree.bind(sequence, lambda _e: self._table_copy_rows(pane) or "break")
        pane["tree"] = tree
        self._table_configure_tree_tags(tree)
        return tree

    def _table_translate_captions(self, *containers):
        """Captions are written in canonical PT; show them in the current language."""
        for widget in containers:
            for child in widget.winfo_children():
                try:
                    if "text" in child.keys() and child.cget("text"):
                        child.configure(text=self.tr(child.cget("text")))
                except tk.TclError:
                    pass

    def _table_translate_headings(self, pane):
        for column, caption in (("address", "Endereço"), ("name", "Nome"), ("value", "Valor")):
            try:
                pane["tree"].heading(column, text=self.tr(caption))
            except tk.TclError:
                pass

    @staticmethod
    def _table_row_tags(index):
        """Alternate rows get a slightly darker background (zebra striping)."""
        return ("odd",) if index % 2 else ()

    def _table_configure_tree_tags(self, tree):
        dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())
        colors = theme_colors(self, dark)
        try:
            tree.tag_configure("stale", foreground=colors["disabled"])
            tree.tag_configure("odd", background=TABLE_STRIPE_DARK if dark
                               else TABLE_STRIPE_LIGHT)
            # A written row carries only this tag (no zebra "odd" tag).
            tree.tag_configure("written", background=TABLE_WRITTEN_DARK if dark
                               else TABLE_WRITTEN_LIGHT)
            frame = tree.master
            if isinstance(frame, tk.Frame):
                frame.configure(highlightbackground=colors["border"],
                                highlightcolor=colors["border"],
                                background=colors["input"])
        except tk.TclError:
            pass

    # -- grid ------------------------------------------------------------------------
    def _table_reflow(self, canvas, grid, grid_item, frames, empty_label, uniform):
        """Arrange docked pane *frames* in as many equal columns as the width allows."""
        width = max(1, canvas.winfo_width())
        canvas.itemconfigure(grid_item, width=width)
        # Use the real requested pane width (it grows with Windows display
        # scaling) so columns never become narrower than their contents.
        pane_width = TABLE_PANE_MIN_WIDTH
        for frame in frames:
            pane_width = max(pane_width, frame.winfo_reqwidth() + 8)
        columns = max(1, width // pane_width)
        for column in range(8):
            grid.columnconfigure(column, weight=1 if column < columns else 0,
                                 uniform=uniform if column < columns else "")
        if not frames:
            empty_label.grid(row=0, column=0, sticky="w", padx=4, pady=8)
        else:
            empty_label.grid_remove()
        for index, frame in enumerate(frames):
            frame.grid(row=index // columns, column=index % columns,
                       sticky="nsew", padx=(0, 8), pady=(0, 8))

    def _table_build_scroll_grid(self, page, row):
        """Scrollable area that holds the window grid; returns (canvas, grid, item)."""
        holder = ttk.Frame(page)
        holder.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 12))
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(holder, highlightthickness=0, borderwidth=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        grid = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        return canvas, grid, item

    def _table_install_wheel_tags(self, root_widget, wheel_tag):
        """Give new widgets the global wheel guard; plain panels scroll the grid."""
        stack = [root_widget]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
                tags = tuple(t for t in widget.bindtags()
                             if t not in (WHEEL_GUARD_TAG, wheel_tag))
                if isinstance(widget, (ttk.Treeview, ttk.Scrollbar, tk.Toplevel)):
                    widget.bindtags((WHEEL_GUARD_TAG,) + tags)
                else:
                    widget.bindtags((wheel_tag, WHEEL_GUARD_TAG) + tags)
            except tk.TclError:
                continue

    @staticmethod
    def _table_wheel(canvas, event):
        if canvas is None:
            return "break"
        try:
            top, bottom = canvas.yview()
            if top <= 0.0 and bottom >= 1.0:
                return "break"
            if getattr(event, "num", None) == 4:
                step = -1
            elif getattr(event, "num", None) == 5:
                step = 1
            else:
                step = -1 if event.delta > 0 else 1
            canvas.yview_scroll(step * 3, "units")
        except tk.TclError:
            pass
        return "break"

    # -- drag selection ---------------------------------------------------------------
    # ttk.Treeview has no rubber-band selection: pressing on a row and dragging
    # selects every row from that row to the one under the pointer, scrolling
    # when the pointer leaves the table. Ctrl+drag adds the block to the
    # selection that existed before the press.
    def _table_drag_start(self, pane, event):
        tree = pane["tree"]
        row = tree.identify_row(event.y)
        if not row or tree.identify_region(event.x, event.y) != "cell":
            pane["drag"] = None
            return
        ctrl = bool(event.state & 0x0004)
        before = tuple(tree.selection())
        pane["drag"] = {"anchor": row, "base": before if ctrl else (), "y": event.y,
                        "after_id": None}

    def _table_drag_move(self, pane, event):
        drag = pane.get("drag")
        if not drag:
            return None
        drag["y"] = event.y
        self._table_drag_update(pane)
        return "break"

    def _table_drag_update(self, pane):
        drag = pane.get("drag")
        if not drag:
            return
        tree = pane["tree"]
        drag["after_id"] = None
        height = tree.winfo_height()
        y = drag["y"]
        if y < 0 or y > height:
            # Pointer outside the rows: scroll and keep extending the block.
            tree.yview_scroll(-1 if y < 0 else 1, "units")
            y = 1 if y < 0 else height - 2
            drag["after_id"] = self.after(60, lambda: self._table_drag_update(pane))
        row = tree.identify_row(y)
        rows = tree.get_children()
        if not row or drag["anchor"] not in rows:
            return
        first, last = sorted((rows.index(drag["anchor"]), rows.index(row)))
        block = rows[first:last + 1]
        tree.selection_set(tuple(dict.fromkeys(drag["base"] + tuple(block))))

    def _table_drag_stop(self, pane):
        drag = pane.get("drag")
        if drag and drag.get("after_id"):
            try:
                self.after_cancel(drag["after_id"])
            except tk.TclError:
                pass
        pane["drag"] = None

    # -- selection / copy / row menu -------------------------------------------------
    @staticmethod
    def _table_selected_rows(pane):
        if pane is None:
            return []
        return sorted(int(iid[1:]) for iid in pane["tree"].selection() if iid.startswith("r"))

    def _table_selected_group_starts(self, window, pane):
        """PDU addresses where the values of the selected rows start."""
        starts = []
        for row in self._table_selected_rows(pane):
            offset, _size, fmt = window.group_of_row(row)
            address = window.address + offset
            if fmt is not None and address not in starts:
                starts.append(address)
        return starts

    def _table_copy_rows(self, pane):
        """Copy the selected rows (all rows if none) as tab-separated text."""
        if pane is None:
            return
        tree = pane["tree"]
        rows = list(tree.selection()) or list(tree.get_children())
        lines = ["\t".join(str(v) for v in tree.item(iid, "values")) for iid in rows]
        if lines:
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))

    def _table_fill_row_menu(self, menu, pane, window, registers, *, set_format,
                             edit_scale, remove_scale, copy, set_base):
        """Right-click menu: Formato ▸, Repor, Escala…, Remover escala, Copiar, Base ▸."""
        menu.delete(0, "end")
        for child in menu.winfo_children():
            child.destroy()
        state = "normal" if registers else "disabled"
        format_menu = tk.Menu(menu, tearoff=False)
        sub_menus = {2: tk.Menu(format_menu, tearoff=False),
                     4: tk.Menu(format_menu, tearoff=False)}
        for key, label, size in REGISTER_FORMATS:
            target = format_menu if size == 1 else sub_menus[size]
            target.add_command(label=label, command=lambda k=key: set_format(k))
        format_menu.add_separator()
        format_menu.add_cascade(label=self.tr("32 bits (2 registos)"), menu=sub_menus[2])
        format_menu.add_cascade(label=self.tr("64 bits (4 registos)"), menu=sub_menus[4])
        menu.add_cascade(label=self.tr("Formato"), menu=format_menu, state=state)
        menu.add_command(label=self.tr("Repor formato da janela"),
                         command=lambda: set_format(None), state=state)
        menu.add_command(label=self.tr("Escala…"), command=edit_scale, state=state)
        menu.add_command(label=self.tr("Remover escala"), command=remove_scale, state=state)
        menu.add_separator()
        menu.add_command(label=self.tr("Copiar"), accelerator="Ctrl+C", command=copy)
        menu.add_separator()
        base_menu = tk.Menu(menu, tearoff=False)
        base_var = tk.IntVar(value=window.base)
        pane["menu_base_var"] = base_var  # keep a reference while the menu lives
        base_menu.add_radiobutton(label=self.tr("0 — PDU Address"), variable=base_var, value=0,
                                  command=lambda: set_base(0))
        base_menu.add_radiobutton(label=self.tr("1 — numeração dos manuais"), variable=base_var,
                                  value=1, command=lambda: set_base(1))
        menu.add_cascade(label=self.tr("Base de endereços"), menu=base_menu)

    @staticmethod
    def _table_popup(menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # -- workspace menu ---------------------------------------------------------------
    def _table_fill_workspace_menu(self, menu, names, *, save, open_, delete, folder):
        """Workspace menu with the saved workspaces listed directly in it."""
        menu.delete(0, "end")
        for child in menu.winfo_children():
            child.destroy()
        menu.add_command(label=self.tr("Guardar workspace…"), command=save)
        open_menu = tk.Menu(menu, tearoff=False)
        delete_menu = tk.Menu(menu, tearoff=False)
        for name in names:
            open_menu.add_command(label=name, command=lambda n=name: open_(n))
            delete_menu.add_command(label=name, command=lambda n=name: delete(n))
        if not names:
            for submenu in (open_menu, delete_menu):
                submenu.add_command(label=self.tr("(nenhum workspace guardado)"),
                                    state="disabled")
        menu.add_cascade(label=self.tr("Abrir workspace"), menu=open_menu)
        menu.add_cascade(label=self.tr("Apagar workspace"), menu=delete_menu)
        menu.add_separator()
        menu.add_command(label=self.tr("Abrir pasta dos workspaces"), command=folder)

    def _table_open_folder(self, folder):
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror(self.tr("Abrir pasta dos workspaces"), str(exc))

    # -- palette -------------------------------------------------------------------------
    def _table_apply_toplevel_palette(self, top):
        dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())
        try:
            top.configure(background=theme_colors(self, dark)["root"])
        except tk.TclError:
            pass

    def _table_apply_menus_palette(self, *menus):
        """Colour menus and every submenu below them (classic Tk widgets)."""
        dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())
        colors = theme_colors(self, dark)
        stack = [m for m in menus if m is not None]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
                widget.configure(
                    background=colors["panel"], foreground=colors["text"],
                    activebackground=colors["select"], activeforeground=colors["select_text"],
                    disabledforeground=colors["disabled"],
                )
            except tk.TclError:
                pass
