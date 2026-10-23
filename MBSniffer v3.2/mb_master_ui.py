#!/usr/bin/env python3
"""Master (poll) tab: one window per Slave / data area, polled over one COM.

The protocol and scheduling live in ``mb_master.py``; this mixin owns the
widgets. Each poll window has a model (``MasterWindow``) and a pane that can
sit in the tab's grid or be popped out into its own top-level window.
"""

import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mb_config import (
    DISCOVERY_BAUD_RATES,
    DISCOVERY_IDLE_CHECK_SECONDS,
    MASTER_DEFAULT_DELAY_MS,
    MASTER_DEFAULT_RESPONSE_TIMEOUT_MS,
    MASTER_DEFAULT_SCAN_MS,
    MASTER_MAX_DELAY_MS,
    MASTER_MAX_RESPONSE_TIMEOUT_MS,
    MASTER_MAX_SCAN_MS,
    MASTER_MAX_WINDOWS,
    MASTER_MIN_DELAY_MS,
    MASTER_MIN_RESPONSE_TIMEOUT_MS,
    MASTER_WORKSPACE_FORMAT,
    MASTER_WORKSPACE_VERSION,
    MODBUS_EXCEPTION_CODES,
)
from mb_diagnostics import FUNCTION_NAMES
from mb_master import (
    BIT_FUNCTION_CODES,
    DEFAULT_FORMAT,
    FORMAT_KEYS_BY_LABEL,
    FORMAT_LABELS,
    FORMAT_SIZES,
    READ_FUNCTION_CODES,
    WRITABLE_READ_FCS,
    MasterEngine,
    PollDefinition,
    build_write_request,
    encode_coil_value,
    encode_register_value,
    format_register_values,
    validate_read_definition,
)
from mb_theme import theme_colors
from mb_widgets import RefreshButton

MASTER_PARITIES = ("None", "Even", "Odd")
MASTER_STOP_BITS = ("1", "2")
MASTER_PANE_MIN_WIDTH = 600
MASTER_PANE_ROWS = 10
MASTER_OK_MESSAGE_SECONDS = 3.0
WHEEL_GUARD_TAG = "MBSniffer.MouseWheelGuard"
MASTER_WHEEL_TAG = "MBSniffer.MasterWheel"


def fc_choice_label(fc):
    return f"{fc:02d} {FUNCTION_NAMES[fc]}"


FC_CHOICES = tuple(fc_choice_label(fc) for fc in READ_FUNCTION_CODES)


def parse_int_field(text, minimum, maximum, message):
    try:
        value = int(str(text).strip())
    except ValueError:
        raise ValueError(message) from None
    if not minimum <= value <= maximum:
        raise ValueError(message)
    return value


class MasterWindow:
    """State of one poll window (independent of where its pane is shown)."""

    def __init__(self, window_id, number, slave=1, fc=3, address=0, qty=10,
                 scan_ms=MASTER_DEFAULT_SCAN_MS, base=0, fmt=DEFAULT_FORMAT,
                 names=None, enabled=True):
        self.window_id = window_id
        self.number = number
        self.slave = slave
        self.fc = fc
        self.address = address
        self.qty = qty
        self.scan_ms = scan_ms
        self.base = base
        self.fmt = fmt
        self.names = dict(names or {})  # PDU address -> label
        self.enabled = enabled
        self.popped = False
        self.reset_counters()

    def reset_counters(self):
        self.tx = 0
        self.errors = 0
        self.timeouts = 0
        self.response_ms = None
        self.values = None
        # (canonical PT template, values, style) shown on the status line.
        self.message = ("", {}, "normal")
        self.message_at = 0.0

    def definition(self):
        return PollDefinition(self.window_id, self.slave, self.fc, self.address,
                              self.qty, self.scan_ms, self.enabled)

    def to_json(self):
        return {
            "slave": self.slave, "fc": self.fc, "address": self.address,
            "qty": self.qty, "scan_ms": self.scan_ms, "base": self.base,
            "format": self.fmt, "enabled": self.enabled,
            "names": {str(address): name for address, name in sorted(self.names.items())},
        }

    @staticmethod
    def validated_kwargs(data):
        """Validate one workspace window entry; raise ValueError if invalid."""
        if not isinstance(data, dict):
            raise ValueError("Janela inválida.")
        slave, fc = int(data.get("slave", 1)), int(data.get("fc", 3))
        address, qty = int(data.get("address", 0)), int(data.get("qty", 10))
        validate_read_definition(slave, fc, address, qty)
        scan_ms = int(data.get("scan_ms", MASTER_DEFAULT_SCAN_MS))
        if not 0 <= scan_ms <= MASTER_MAX_SCAN_MS:
            raise ValueError("Scan rate fora do intervalo.")
        fmt = data.get("format", DEFAULT_FORMAT)
        names = data.get("names", {})
        return {
            "slave": slave, "fc": fc, "address": address, "qty": qty,
            "scan_ms": scan_ms, "base": 1 if data.get("base") == 1 else 0,
            "fmt": fmt if fmt in FORMAT_SIZES else DEFAULT_FORMAT,
            "enabled": bool(data.get("enabled", True)),
            "names": {
                int(k): str(v) for k, v in (names.items() if isinstance(names, dict) else ())
                if str(k).isdigit() and str(v).strip()
            },
        }


class MasterMixin:
    """Master (poll) tab GUI."""

    # -- construction ----------------------------------------------------------
    def build_master_tab(self, page):
        saved = getattr(self, "ui_settings", {}).get("master", {})
        if not isinstance(saved, dict):
            saved = {}

        self.master_windows = {}
        self._master_panes = {}
        self._master_next_id = 1
        self.master_engine = None
        self.master_serial = None
        self.master_active = False
        self._master_reflow_after_id = None

        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        connection = ttk.LabelFrame(page, text="Ligação — o Master transmite no barramento")
        connection.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self._master_connection_frame = connection
        row = ttk.Frame(connection)
        row.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        ttk.Label(row, text="Porta COM").grid(row=0, column=0, padx=(0, 4))
        self.master_port_var = tk.StringVar()
        self.master_port_combo = ttk.Combobox(
            row, textvariable=self.master_port_var, width=13, state="readonly"
        )
        self.master_port_combo.grid(row=0, column=1)
        self.master_refresh_btn = RefreshButton(row, command=self.refresh_ports, size=24)
        self.master_refresh_btn.grid(row=0, column=2, padx=(4, 18))

        def _sync_refresh_square(_event=None):
            height = self.master_port_combo.winfo_height()
            if height > 1:
                self.master_refresh_btn.configure(width=height, height=height)

        self.master_port_combo.bind("<Configure>", _sync_refresh_square, add="+")

        self.master_baud_var = tk.StringVar(value=str(saved.get("baud", "9600")))
        self.master_parity_var = tk.StringVar(value=saved.get("parity", "None"))
        self.master_stop_var = tk.StringVar(value=str(saved.get("stop_bits", "1")))
        self.master_timeout_var = tk.StringVar(
            value=str(saved.get("response_timeout_ms", MASTER_DEFAULT_RESPONSE_TIMEOUT_MS))
        )
        self.master_delay_var = tk.StringVar(
            value=str(saved.get("delay_ms", MASTER_DEFAULT_DELAY_MS))
        )
        fields = (
            ("Baud rate", ttk.Combobox(row, textvariable=self.master_baud_var, width=8,
                                       state="readonly",
                                       values=[str(b) for b in DISCOVERY_BAUD_RATES])),
            ("Parity", ttk.Combobox(row, textvariable=self.master_parity_var, width=6,
                                    state="readonly", values=MASTER_PARITIES)),
            ("Stop bits", ttk.Combobox(row, textvariable=self.master_stop_var, width=3,
                                       state="readonly", values=MASTER_STOP_BITS)),
            ("Timeout resposta (ms)", ttk.Spinbox(
                row, textvariable=self.master_timeout_var, width=6, increment=50,
                from_=MASTER_MIN_RESPONSE_TIMEOUT_MS, to=MASTER_MAX_RESPONSE_TIMEOUT_MS)),
            ("Atraso entre pedidos (ms)", ttk.Spinbox(
                row, textvariable=self.master_delay_var, width=6, increment=5,
                from_=MASTER_MIN_DELAY_MS, to=MASTER_MAX_DELAY_MS)),
        )
        column = 3
        self._master_setting_widgets = [self.master_port_combo]
        for caption, widget in fields:
            ttk.Label(row, text=caption).grid(row=0, column=column, padx=(0, 4))
            widget.grid(row=0, column=column + 1, padx=(0, 16))
            self._master_setting_widgets.append(widget)
            column += 2
        ttk.Label(row, text="Data bits: 8").grid(row=0, column=column)

        controls = ttk.Frame(connection)
        controls.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        self.master_safety_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="Confirmo que não existe outro master ativo no barramento.",
            variable=self.master_safety_var,
        ).grid(row=0, column=0, padx=(0, 18))
        self.master_connect_btn = ttk.Button(
            controls, text="Ligar", command=self.master_connect, style="MBS.Primary.TButton"
        )
        self.master_connect_btn.grid(row=0, column=1, padx=(0, 6))
        self.master_disconnect_btn = ttk.Button(
            controls, text="Desligar", command=self.master_disconnect, state="disabled"
        )
        self.master_disconnect_btn.grid(row=0, column=2, padx=(0, 18))
        self.master_status_var = tk.StringVar(value=self.tr("Desligado"))
        ttk.Label(controls, textvariable=self.master_status_var).grid(row=0, column=3)

        toolbar = ttk.Frame(page)
        toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        toolbar.columnconfigure(3, weight=1)
        ttk.Button(toolbar, text="Nova janela", command=self.master_add_window).grid(
            row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Abrir workspace", command=self.master_open_workspace).grid(
            row=0, column=1, padx=(0, 6))
        ttk.Button(toolbar, text="Guardar workspace", command=self.master_save_workspace).grid(
            row=0, column=2, padx=(0, 6))
        ttk.Label(
            toolbar,
            text=("Uma janela por Slave / zona de memória. Duplo clique num valor para "
                  "escrever; duplo clique num nome para o editar."),
        ).grid(row=0, column=3, sticky="w", padx=(12, 0))

        holder = ttk.Frame(page)
        holder.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.master_canvas = tk.Canvas(holder, highlightthickness=0, borderwidth=0)
        self.master_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.master_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.master_canvas.configure(yscrollcommand=scrollbar.set)
        self.master_grid = ttk.Frame(self.master_canvas)
        self._master_grid_item = self.master_canvas.create_window(
            (0, 0), window=self.master_grid, anchor="nw"
        )
        self.master_grid.bind(
            "<Configure>",
            lambda _e: self.master_canvas.configure(scrollregion=self.master_canvas.bbox("all")),
        )
        self.master_canvas.bind("<Configure>", self._master_schedule_reflow, add="+")
        self.master_empty_label = ttk.Label(
            self.master_grid,
            text="Sem janelas. Usa \"Nova janela\" para começar a ler um Slave.",
        )

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_class(MASTER_WHEEL_TAG, sequence, self._master_wheel)

        for variable in (self.master_baud_var, self.master_parity_var, self.master_stop_var,
                         self.master_timeout_var, self.master_delay_var):
            variable.trace_add("write", lambda *_a: self._schedule_ui_settings_save())

        self.master_add_window()

    # -- helpers ---------------------------------------------------------------
    def _master_install_wheel_tags(self, root_widget):
        """Give new widgets the global wheel guard; plain panels scroll the grid."""
        stack = [root_widget]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
                tags = tuple(t for t in widget.bindtags()
                             if t not in (WHEEL_GUARD_TAG, MASTER_WHEEL_TAG))
                if isinstance(widget, (ttk.Treeview, ttk.Scrollbar, tk.Toplevel)):
                    widget.bindtags((WHEEL_GUARD_TAG,) + tags)
                else:
                    widget.bindtags((MASTER_WHEEL_TAG, WHEEL_GUARD_TAG) + tags)
            except tk.TclError:
                continue

    def _master_wheel(self, event):
        canvas = getattr(self, "master_canvas", None)
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

    def _master_window_title(self, window):
        shown = window.address + window.base
        return self.trf(
            "Janela {number} — Slave {slave} · FC{fc:02d} · {address} · {qty}",
            number=window.number, slave=window.slave, fc=window.fc,
            address=shown, qty=window.qty,
        )

    def _master_counters_text(self, window):
        response = f"{window.response_ms:.1f} ms" if window.response_ms is not None else "—"
        return (f"Tx: {window.tx}   Err: {window.errors}   "
                f"Timeouts: {window.timeouts}   Resp.: {response}")

    def _master_set_message(self, window, template, style="normal", **values):
        window.message = (template, values, style)
        window.message_at = time.monotonic()
        self._master_render_status(window)

    def _master_render_status(self, window):
        pane = self._master_panes.get(window.window_id)
        if pane is None:
            return
        template, values, style = window.message
        if not window.enabled and style != "error":
            template, values, style = "Pausada", {}, "normal"
        text = self.trf(template, **values) if template else ""
        try:
            pane["counters_var"].set(self._master_counters_text(window))
            pane["message_var"].set(text)
            pane["message_label"].configure(style={
                "error": "MBS.Master.Error.TLabel",
                "ok": "MBS.Master.Ok.TLabel",
            }.get(style, "TLabel"))
            pane["frame"].configure(text=self._master_window_title(window))
            pane["pause_btn"].configure(text=self.tr("Retomar" if not window.enabled else "Pausar"))
            pane["popout_btn"].configure(text=self.tr("Ancorar" if window.popped else "Destacar"))
            if window.popped and pane.get("toplevel") is not None:
                pane["toplevel"].title(f"MBSniffer — {self._master_window_title(window)}")
        except tk.TclError:
            pass

    # -- panes -------------------------------------------------------------------
    def _master_build_pane(self, window, parent):
        frame = ttk.LabelFrame(parent, text=self._master_window_title(window))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        pane = {"frame": frame}

        definition = ttk.Frame(frame)
        definition.grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        pane["slave_var"] = tk.StringVar(value=str(window.slave))
        pane["fc_var"] = tk.StringVar(value=fc_choice_label(window.fc))
        pane["address_var"] = tk.StringVar(value=str(window.address + window.base))
        pane["qty_var"] = tk.StringVar(value=str(window.qty))
        pane["scan_var"] = tk.StringVar(value=str(window.scan_ms))
        pane["base_var"] = tk.StringVar(value=str(window.base))
        pane["format_var"] = tk.StringVar(value=FORMAT_LABELS[window.fmt])

        layout = (
            ("Slave", ttk.Spinbox(definition, from_=1, to=247, width=4,
                                  textvariable=pane["slave_var"])),
            ("FC", ttk.Combobox(definition, values=FC_CHOICES, width=24, state="readonly",
                                textvariable=pane["fc_var"])),
            ("Endereço", ttk.Entry(definition, width=6, textvariable=pane["address_var"])),
            ("Qtd.", ttk.Entry(definition, width=5, textvariable=pane["qty_var"])),
        )
        for index, (caption, widget) in enumerate(layout):
            ttk.Label(definition, text=caption).grid(row=0, column=index * 2, padx=(0, 3))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 10))

        definition2 = ttk.Frame(frame)
        definition2.grid(row=1, column=0, sticky="w", padx=6, pady=2)
        format_combo = ttk.Combobox(
            definition2, values=[FORMAT_LABELS[k] for k in FORMAT_LABELS], width=20,
            state="readonly", textvariable=pane["format_var"],
        )
        layout2 = (
            ("Scan (ms)", ttk.Entry(definition2, width=7, textvariable=pane["scan_var"])),
            ("Base", ttk.Combobox(definition2, values=("0", "1"), width=2, state="readonly",
                                  textvariable=pane["base_var"])),
            ("Formato", format_combo),
        )
        for index, (caption, widget) in enumerate(layout2):
            ttk.Label(definition2, text=caption).grid(row=0, column=index * 2, padx=(0, 3))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 10))
        pane["format_combo"] = format_combo

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="w", padx=6, pady=(2, 2))
        window_id = window.window_id
        actions = (
            ("Aplicar", lambda: self.master_apply_window(window_id)),
            ("Pausar", lambda: self.master_toggle_pause(window_id)),
            ("Ler 1x", lambda: self.master_read_once(window_id)),
            ("Duplicar", lambda: self.master_duplicate_window(window_id)),
            ("Destacar", lambda: self.master_toggle_popout(window_id)),
            ("Fechar", lambda: self.master_close_window(window_id)),
        )
        for index, (caption, command) in enumerate(actions):
            button = ttk.Button(buttons, text=caption, command=command, width=10)
            button.grid(row=0, column=index, padx=(0, 3))
            if caption == "Pausar":
                pane["pause_btn"] = button
            elif caption == "Destacar":
                pane["popout_btn"] = button

        status = ttk.Frame(frame)
        status.grid(row=3, column=0, sticky="ew", padx=6, pady=(2, 2))
        status.columnconfigure(1, weight=1)
        pane["counters_var"] = tk.StringVar()
        pane["message_var"] = tk.StringVar()
        ttk.Label(status, textvariable=pane["counters_var"]).grid(row=0, column=0, sticky="w")
        pane["message_label"] = ttk.Label(status, textvariable=pane["message_var"])
        pane["message_label"].grid(row=0, column=1, sticky="w", padx=(14, 0))

        table = ttk.Frame(frame)
        table.grid(row=4, column=0, sticky="nsew", padx=6, pady=(2, 6))
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        tree = ttk.Treeview(table, columns=("address", "name", "value"), show="headings",
                            height=MASTER_PANE_ROWS, selectmode="browse")
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
        tree.bind("<Double-1>", lambda e: self._master_on_double_click(window_id, e))
        tree.bind("<Return>", lambda e: self._master_edit_value(window_id))
        pane["tree"] = tree

        for widget in (definition, definition2):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                    child.bind("<Return>", lambda _e: self.master_apply_window(window_id))

        # Captions were written in canonical PT; show them in the current language.
        for widget in (definition, definition2, buttons):
            for child in widget.winfo_children():
                try:
                    if "text" in child.keys() and child.cget("text"):
                        child.configure(text=self.tr(child.cget("text")))
                except tk.TclError:
                    pass

        self._master_panes[window_id] = pane
        self._master_fill_rows(window)
        self._master_update_format_state(window)
        self._master_render_status(window)
        self._master_install_wheel_tags(frame)
        return frame

    def _master_update_format_state(self, window):
        pane = self._master_panes.get(window.window_id)
        if pane is not None:
            state = "disabled" if window.fc in BIT_FUNCTION_CODES else "readonly"
            pane["format_combo"].configure(state=state)

    def _master_fill_rows(self, window):
        pane = self._master_panes.get(window.window_id)
        if pane is None:
            return
        tree = pane["tree"]
        tree.delete(*tree.get_children())
        for index in range(window.qty):
            pdu = window.address + index
            tree.insert("", "end", iid=f"r{index}",
                        values=(pdu + window.base, window.names.get(pdu, ""), ""))
        self._master_render_values(window)

    def _master_render_values(self, window):
        pane = self._master_panes.get(window.window_id)
        if pane is None or window.values is None:
            return
        if window.fc in BIT_FUNCTION_CODES:
            texts = [str(v) for v in window.values]
        else:
            texts = format_register_values(window.values, window.fmt)
        tree = pane["tree"]
        for index, text in enumerate(texts[:window.qty]):
            try:
                tree.set(f"r{index}", "value", text)
            except tk.TclError:
                pass

    def _master_schedule_reflow(self, _event=None):
        if self._master_reflow_after_id is not None:
            try:
                self.after_cancel(self._master_reflow_after_id)
            except tk.TclError:
                pass
        self._master_reflow_after_id = self.after(80, self._master_reflow)

    def _master_reflow(self):
        """Arrange docked panes in as many equal columns as the width allows."""
        self._master_reflow_after_id = None
        canvas = self.master_canvas
        width = max(1, canvas.winfo_width())
        canvas.itemconfigure(self._master_grid_item, width=width)
        docked = [w for w in sorted(self.master_windows.values(), key=lambda w: w.number)
                  if not w.popped]
        columns = max(1, width // MASTER_PANE_MIN_WIDTH)
        for column in range(8):
            self.master_grid.columnconfigure(column, weight=1 if column < columns else 0,
                                             uniform="master_panes" if column < columns else "")
        if not docked:
            self.master_empty_label.grid(row=0, column=0, sticky="w", padx=4, pady=8)
        else:
            self.master_empty_label.grid_remove()
        for index, window in enumerate(docked):
            pane = self._master_panes.get(window.window_id)
            if pane is not None:
                pane["frame"].grid(row=index // columns, column=index % columns,
                                   sticky="nsew", padx=(0, 8), pady=(0, 8))

    # -- window actions --------------------------------------------------------
    def master_add_window(self, kwargs=None):
        if len(self.master_windows) >= MASTER_MAX_WINDOWS:
            messagebox.showwarning(
                self.tr("Master"),
                self.trf("Máximo de {count} janelas.", count=MASTER_MAX_WINDOWS),
            )
            return None
        window_id = self._master_next_id
        self._master_next_id += 1
        numbers = {w.number for w in self.master_windows.values()}
        number = next(n for n in range(1, MASTER_MAX_WINDOWS + 2) if n not in numbers)
        window = MasterWindow(window_id, number, **(kwargs or {}))
        self.master_windows[window_id] = window
        self._master_build_pane(window, self.master_grid)
        self._master_reflow()
        if self.master_engine is not None:
            self.master_engine.set_poll(window.definition())
        return window

    def master_duplicate_window(self, window_id):
        window = self.master_windows.get(window_id)
        if window is not None:
            data = MasterWindow.validated_kwargs(window.to_json())
            self.master_add_window(data)

    def master_close_window(self, window_id):
        window = self.master_windows.pop(window_id, None)
        if window is None:
            return
        if self.master_engine is not None:
            self.master_engine.remove_poll(window_id)
        pane = self._master_panes.pop(window_id, None)
        if pane is not None:
            top = pane.get("toplevel")
            try:
                (top if top is not None else pane["frame"]).destroy()
            except tk.TclError:
                pass
        self._master_reflow()

    def master_apply_window(self, window_id):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None:
            return False
        try:
            base = 1 if pane["base_var"].get() == "1" else 0
            slave = parse_int_field(pane["slave_var"].get(), 1, 247,
                                    "O Slave ID de leitura tem de estar entre 1 e 247.")
            fc = int(pane["fc_var"].get()[:2])
            address = parse_int_field(pane["address_var"].get(), base, 0xFFFF + base,
                                      "O endereço tem de estar entre 0 e 65535.") - base
            qty = parse_int_field(pane["qty_var"].get(), 1, 2000,
                                  "Quantidade fora do limite desta função.")
            scan_ms = parse_int_field(pane["scan_var"].get(), 0, MASTER_MAX_SCAN_MS,
                                      "Scan rate fora do intervalo.")
            validate_read_definition(slave, fc, address, qty)
        except ValueError as exc:
            messagebox.showerror(self.tr("Janela inválida"), self.tr(str(exc)))
            return False

        changed_area = (slave, fc, address, qty) != (window.slave, window.fc,
                                                     window.address, window.qty)
        window.slave, window.fc, window.address, window.qty = slave, fc, address, qty
        window.scan_ms, window.base = scan_ms, base
        window.fmt = FORMAT_KEYS_BY_LABEL.get(pane["format_var"].get(), DEFAULT_FORMAT)
        if changed_area:
            window.reset_counters()
        self._master_fill_rows(window)
        self._master_update_format_state(window)
        self._master_render_status(window)
        if self.master_engine is not None:
            self.master_engine.set_poll(window.definition())
        return True

    def master_toggle_pause(self, window_id):
        window = self.master_windows.get(window_id)
        if window is None:
            return
        window.enabled = not window.enabled
        if window.enabled and window.message[0] == "Pausada":
            window.message = ("", {}, "normal")
        self._master_render_status(window)
        if self.master_engine is not None:
            self.master_engine.set_poll(window.definition())

    def master_read_once(self, window_id):
        if self.master_engine is None:
            messagebox.showinfo(self.tr("Master"), self.tr("Liga primeiro o Master."))
            return
        self.master_engine.read_once(window_id)

    def master_toggle_popout(self, window_id):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.pop(window_id, None)
        if window is None or pane is None:
            return
        old_top = pane.get("toplevel")
        try:
            pane["frame"].destroy()
            if old_top is not None:
                old_top.destroy()
        except tk.TclError:
            pass

        window.popped = not window.popped
        if window.popped:
            top = tk.Toplevel(self)
            top.geometry("660x420")
            top.minsize(MASTER_PANE_MIN_WIDTH, 300)
            top.columnconfigure(0, weight=1)
            top.rowconfigure(0, weight=1)
            top.protocol("WM_DELETE_WINDOW", lambda: self.master_toggle_popout(window_id))
            frame = self._master_build_pane(window, top)
            frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
            self._master_panes[window_id]["toplevel"] = top
            self._master_apply_toplevel_palette(top)
        else:
            self._master_build_pane(window, self.master_grid)
        self._master_render_status(window)
        self._master_reflow()

    # -- value / name editing --------------------------------------------------
    def _master_on_double_click(self, window_id, event):
        pane = self._master_panes.get(window_id)
        if pane is None:
            return "break"
        tree = pane["tree"]
        row = tree.identify_row(event.y)
        if not row:
            return "break"
        tree.selection_set(row)
        if tree.identify_column(event.x) == "#2":
            self._master_edit_name(window_id, row)
        else:
            self._master_edit_value(window_id)
        return "break"

    def _master_dialog(self, title):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)
        self._master_apply_toplevel_palette(dialog)
        body = ttk.Frame(dialog, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        return dialog, body

    def _master_edit_name(self, window_id, row):
        window = self.master_windows.get(window_id)
        if window is None:
            return
        pdu = window.address + int(row[1:])
        dialog, body = self._master_dialog(self.tr("Nome"))
        ttk.Label(body, text=self.trf("Nome do endereço {address}",
                                      address=pdu + window.base)).grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar(value=window.names.get(pdu, ""))
        entry = ttk.Entry(body, textvariable=name_var, width=36)
        entry.grid(row=1, column=0, pady=(4, 8))

        def save(_event=None):
            name = name_var.get().strip()
            if name:
                window.names[pdu] = name
            else:
                window.names.pop(pdu, None)
            pane = self._master_panes.get(window_id)
            if pane is not None:
                pane["tree"].set(row, "name", name)
            dialog.destroy()

        ttk.Button(body, text=self.tr("Guardar"), command=save).grid(row=2, column=0, sticky="e")
        entry.bind("<Return>", save)
        entry.focus_set()
        dialog.grab_set()

    def _master_edit_value(self, window_id):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None:
            return
        selection = pane["tree"].selection()
        if not selection:
            return
        index = int(selection[0][1:])
        write_fcs = WRITABLE_READ_FCS.get(window.fc)
        if write_fcs is None:
            messagebox.showinfo(
                self.tr("Escrita"),
                self.tr("FC02 e FC04 são só de leitura: abre uma janela FC01 ou FC03 para escrever."),
            )
            return
        bits = window.fc in BIT_FUNCTION_CODES
        size = 1 if bits else FORMAT_SIZES[window.fmt]
        index -= index % size  # 32-bit values start on the first register of the pair
        current = ""
        try:
            current = pane["tree"].set(f"r{index}", "value")
        except tk.TclError:
            pass

        dialog, body = self._master_dialog(self.tr("Escrever"))
        slave_var = tk.StringVar(value=str(window.slave))
        address_var = tk.StringVar(value=str(window.address + index + window.base))
        value_var = tk.StringVar(value=current)
        single_fc, multiple_fc = write_fcs
        fc_var = tk.IntVar(value=single_fc if size == 1 else multiple_fc)

        rows = (
            ("Slave (0 = broadcast)", ttk.Spinbox(body, from_=0, to=247, width=6,
                                                  textvariable=slave_var)),
            ("Endereço", ttk.Entry(body, width=8, textvariable=address_var)),
            ("Valor(es)", ttk.Entry(body, width=30, textvariable=value_var)),
        )
        for row_index, (caption, widget) in enumerate(rows):
            ttk.Label(body, text=self.tr(caption)).grid(row=row_index, column=0, sticky="w",
                                                        pady=2, padx=(0, 8))
            widget.grid(row=row_index, column=1, sticky="w", pady=2)
        functions = ttk.Frame(body)
        functions.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 2))
        single = ttk.Radiobutton(functions, text=fc_choice_label_write(single_fc),
                                 variable=fc_var, value=single_fc)
        single.grid(row=0, column=0, sticky="w")
        if size != 1:
            single.configure(state="disabled")
        ttk.Radiobutton(functions, text=fc_choice_label_write(multiple_fc),
                        variable=fc_var, value=multiple_fc).grid(row=1, column=0, sticky="w")
        format_text = "0 / 1" if bits else FORMAT_LABELS[window.fmt]
        ttk.Label(
            body,
            text=self.trf("Formato: {fmt}. Vários valores (FC15/FC16): separar com ;",
                          fmt=format_text),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 8))
        message_var = tk.StringVar()
        ttk.Label(body, textvariable=message_var, style="MBS.Master.Error.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w")

        def send(_event=None):
            try:
                request, description = self.master_build_write(
                    window, slave_var.get(), address_var.get(), value_var.get(), fc_var.get()
                )
            except ValueError as exc:
                message_var.set(self.tr(str(exc)))
                return
            if self.master_engine is None:
                message_var.set(self.tr("Liga primeiro o Master."))
                return
            self.master_engine.queue_write(window.window_id, request, description)
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=self.tr("Enviar"), command=send,
                   style="MBS.Primary.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Cancelar"), command=dialog.destroy).grid(row=0, column=1)
        rows[2][1].bind("<Return>", send)
        rows[2][1].focus_set()
        rows[2][1].select_range(0, "end")
        dialog.grab_set()

    def master_build_write(self, window, slave_text, address_text, values_text, fc):
        """Validate the write dialog fields and return (request, description)."""
        slave = parse_int_field(slave_text, 0, 247,
                                "O Slave ID de escrita tem de estar entre 0 (broadcast) e 247.")
        address = parse_int_field(address_text, window.base, 0xFFFF + window.base,
                                  "O endereço tem de estar entre 0 e 65535.") - window.base
        parts = [p for p in str(values_text).split(";") if p.strip()]
        if not parts:
            raise ValueError("Valor vazio.")
        if window.fc in BIT_FUNCTION_CODES:
            values = [encode_coil_value(p) for p in parts]
        else:
            values = []
            for part in parts:
                values.extend(encode_register_value(part, window.fmt))
        if fc in (5, 6) and len(values) != 1:
            raise ValueError("FC05/FC06 escrevem um único valor; usa FC15/FC16 para vários.")
        request = build_write_request(slave, fc, address, values)
        description = f"FC{fc:02d} @ {address + window.base} × {len(values)}"
        return request, description

    # -- connection --------------------------------------------------------------
    def _master_connection_settings(self):
        timeout = parse_int_field(
            self.master_timeout_var.get(), MASTER_MIN_RESPONSE_TIMEOUT_MS,
            MASTER_MAX_RESPONSE_TIMEOUT_MS,
            "O timeout de resposta tem de estar entre 10 e 10000 ms.")
        delay = parse_int_field(
            self.master_delay_var.get(), MASTER_MIN_DELAY_MS, MASTER_MAX_DELAY_MS,
            "O atraso entre pedidos tem de estar entre 0 e 10000 ms.")
        return {
            "port": self.master_port_var.get().strip(),
            "baud": int(self.master_baud_var.get()),
            "parity": self.master_parity_var.get(),
            "stopbits": self.master_stop_var.get(),
            "response_timeout_ms": timeout,
            "delay_ms": delay,
        }

    def master_connect(self):
        if self.master_active:
            return
        if self.busy:
            messagebox.showwarning(
                self.tr("Master"),
                self.tr("Para a captura ou a pesquisa em curso antes de ligar o Master."),
            )
            return
        if not self.master_safety_var.get():
            messagebox.showwarning(
                self.tr("Master"),
                self.tr("Confirma primeiro que não existe outro master ativo no barramento."),
            )
            return
        serial, _ = self.get_serial_modules()
        if serial is None:
            messagebox.showerror(self.tr("pyserial em falta"), self.tr("pyserial não está instalado."))
            return
        try:
            settings = self._master_connection_settings()
            if not settings["port"]:
                raise ValueError("Seleciona uma porta COM.")
        except ValueError as exc:
            messagebox.showerror(self.tr("Configuração inválida"), self.tr(str(exc)))
            return
        for window_id in list(self.master_windows):
            if not self.master_apply_window(window_id):
                return
        try:
            ser = self.open_discovery_serial_port(
                serial, settings["port"], settings["baud"], settings["parity"],
                settings["stopbits"],
            )
        except Exception as exc:
            messagebox.showerror(
                self.tr("Master"),
                self.trf("Não foi possível abrir {port}: {error}",
                         port=settings["port"], error=f"{type(exc).__name__}: {exc}"),
            )
            return

        self.master_serial = ser
        self.master_engine = MasterEngine(
            ser, self.event_queue, baud=settings["baud"], parity=settings["parity"],
            stopbits=settings["stopbits"],
            response_timeout_ms=settings["response_timeout_ms"],
            delay_ms=settings["delay_ms"], serial_module=serial,
            idle_check_seconds=DISCOVERY_IDLE_CHECK_SECONDS,
        )
        for window in self.master_windows.values():
            window.reset_counters()
            self._master_render_status(window)
            self.master_engine.set_poll(window.definition())
        self.master_active = True
        self.busy = True
        self._master_lock_other_features(True)
        self.master_status_var.set(self.tr("A verificar se o barramento está livre…"))
        self.master_engine.start()

    def master_disconnect(self):
        if self.master_engine is None:
            return
        self.master_status_var.set(self.tr("A desligar…"))
        self.master_disconnect_btn.configure(state="disabled")
        self.master_engine.stop()

    def _master_lock_other_features(self, locked):
        state = "disabled" if locked else "normal"
        self.master_connect_btn.configure(state=state)
        self.master_disconnect_btn.configure(state="normal" if locked else "disabled")
        for widget in self._master_setting_widgets:
            try:
                widget.configure(state="disabled" if locked else "readonly"
                                 if isinstance(widget, ttk.Combobox) else "normal")
            except tk.TclError:
                pass
        self.master_refresh_btn.configure(state=state)
        self.start_btn.configure(state=state)
        self.restart_btn.configure(state=state)
        self.set_sniffer_refresh_state(state)
        self.set_simulation_button_state(state)
        self.update_discovery_start_state()

    def _master_finish_session(self, payload):
        engine = self.master_engine
        self.master_engine = None
        if engine is not None:
            engine.stop(join_timeout=0.5)
        if self.master_serial is not None:
            try:
                self.master_serial.close()
            except Exception:
                pass
        self.master_serial = None
        self.master_active = False
        self.busy = False
        self._master_lock_other_features(False)
        self.master_status_var.set(self.tr("Desligado"))

        error = (payload or {}).get("error")
        if error:
            kind, detail, count = error
            if kind == "traffic":
                text = self.trf(
                    "Foi detetado tráfego em {port} antes de transmitir "
                    "({count} bytes: {raw}). Pode existir outro master "
                    "ativo no barramento; a pesquisa não foi iniciada.",
                    port=self.master_port_var.get(), count=count, raw=detail,
                )
            else:
                text = self.trf("Erro na porta série: {error}", error=detail)
            messagebox.showerror(self.tr("Master"), text)

    # -- worker events -------------------------------------------------------------
    def handle_master_event(self, event, payload):
        if event == "master_ready":
            self.master_status_var.set(self.tr("● Ligado"))
        elif event == "master_stopped":
            self._master_finish_session(payload)
        elif event == "master_result":
            self._master_apply_result(payload)

    def _master_apply_result(self, result):
        window = self.master_windows.get(result.get("window_id"))
        if window is None:
            return
        status = result["status"]
        if status == "stopped":
            return
        window.tx += 1
        if result.get("response_ms") is not None:
            window.response_ms = result["response_ms"]

        if result["kind"] == "read":
            if (result.get("fc"), result.get("address")) != (window.fc, window.address):
                return  # definition changed while the request was on the bus
            if status == "ok":
                window.values = result["values"]
                self._master_render_values(window)
                # A successful read clears errors; a write confirmation stays
                # visible for a few seconds so the user can see it.
                if (window.message[2] != "ok"
                        or time.monotonic() - window.message_at > MASTER_OK_MESSAGE_SECONDS):
                    self._master_set_message(window, "")
                return
        elif status == "ok":
            self._master_set_message(window, "Escrita OK: {what}", "ok",
                                     what=result.get("description", ""))
            if self.master_engine is not None:
                self.master_engine.read_once(window.window_id)
            return
        elif status == "broadcast":
            self._master_set_message(window, "Escrita broadcast enviada: {what}", "ok",
                                     what=result.get("description", ""))
            return

        window.errors += 1
        if status == "timeout":
            window.timeouts += 1
            self._master_set_message(window, "Timeout", "error")
        elif status == "exception":
            code = result.get("exception_code") or 0
            name = MODBUS_EXCEPTION_CODES.get(code, ("Unknown/Reserved Exception", ""))[0]
            self._master_set_message(window, "Exception 0x{code:02X} — {name}", "error",
                                     code=code, name=name)
        else:
            self._master_set_message(window, "Resposta inválida (CRC ou formato): {rx}",
                                     "error", rx=result.get("rx", "")[:47])

    # -- workspace -------------------------------------------------------------------
    def master_workspace_data(self):
        return {
            "format": MASTER_WORKSPACE_FORMAT,
            "version": MASTER_WORKSPACE_VERSION,
            "connection": {
                "port": self.master_port_var.get(),
                "baud": self.master_baud_var.get(),
                "parity": self.master_parity_var.get(),
                "stop_bits": self.master_stop_var.get(),
                "response_timeout_ms": self.master_timeout_var.get(),
                "delay_ms": self.master_delay_var.get(),
            },
            "windows": [w.to_json() for w in sorted(self.master_windows.values(),
                                                     key=lambda w: w.number)],
        }

    def master_save_workspace(self, path=None):
        if path is None:
            path = filedialog.asksaveasfilename(
                parent=self, title=self.tr("Guardar workspace"), defaultextension=".mbsw",
                filetypes=[("MBSniffer workspace", "*.mbsw"), ("JSON", "*.json")],
            )
        if not path:
            return False
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.master_workspace_data(), handle, indent=2, ensure_ascii=False)
            return True
        except OSError as exc:
            messagebox.showerror(self.tr("Guardar workspace"), str(exc))
            return False

    def master_open_workspace(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, title=self.tr("Abrir workspace"),
                filetypes=[("MBSniffer workspace", "*.mbsw"), ("JSON", "*.json")],
            )
        if not path:
            return False
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict) or data.get("format") != MASTER_WORKSPACE_FORMAT:
                raise ValueError(self.tr("O ficheiro não é um workspace do MBSniffer."))
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.tr("Abrir workspace"), str(exc))
            return False

        entries, skipped = [], 0
        for item in data.get("windows", [])[:MASTER_MAX_WINDOWS]:
            try:
                entries.append(MasterWindow.validated_kwargs(item))
            except (ValueError, TypeError):
                skipped += 1

        for window_id in list(self.master_windows):
            self.master_close_window(window_id)
        connection = data.get("connection", {})
        if isinstance(connection, dict) and not self.master_active:
            if str(connection.get("baud")) in [str(b) for b in DISCOVERY_BAUD_RATES]:
                self.master_baud_var.set(str(connection["baud"]))
            if connection.get("parity") in MASTER_PARITIES:
                self.master_parity_var.set(connection["parity"])
            if str(connection.get("stop_bits")) in MASTER_STOP_BITS:
                self.master_stop_var.set(str(connection["stop_bits"]))
            for key, var in (("response_timeout_ms", self.master_timeout_var),
                             ("delay_ms", self.master_delay_var)):
                if str(connection.get(key, "")).isdigit():
                    var.set(str(connection[key]))
            if connection.get("port") in tuple(self.master_port_combo["values"]):
                self.master_port_var.set(connection["port"])
        for kwargs in entries:
            self.master_add_window(kwargs)
        if skipped:
            messagebox.showwarning(
                self.tr("Abrir workspace"),
                self.trf("{count} janela(s) inválida(s) foram ignoradas.", count=skipped),
            )
        return True

    # -- language / palette / shutdown -----------------------------------------------
    def master_apply_language(self):
        if not hasattr(self, "master_windows"):
            return
        for window in self.master_windows.values():
            pane = self._master_panes.get(window.window_id)
            if pane is None:
                continue
            for column, caption in (("address", "Endereço"), ("name", "Nome"), ("value", "Valor")):
                try:
                    pane["tree"].heading(column, text=self.tr(caption))
                except tk.TclError:
                    pass
            self._master_render_status(window)
        if not self.master_active:
            self.master_status_var.set(self.tr("Desligado"))
        elif self.master_engine is not None:
            self.master_status_var.set(self.tr("● Ligado"))

    def _master_apply_toplevel_palette(self, top):
        dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())
        try:
            top.configure(background=theme_colors(self, dark)["root"])
        except tk.TclError:
            pass

    def master_apply_palette(self, dark):
        colors = theme_colors(self, dark)
        if hasattr(self, "master_canvas"):
            self.master_canvas.configure(background=colors["root"])
        if hasattr(self, "ui_style"):
            self.ui_style.configure("MBS.Master.Error.TLabel",
                                    foreground="#ff8a80" if dark else "#b42318")
            self.ui_style.configure("MBS.Master.Ok.TLabel",
                                    foreground="#a7e4b8" if dark else "#1f6b3a")
        for pane in getattr(self, "_master_panes", {}).values():
            if pane.get("toplevel") is not None:
                self._master_apply_toplevel_palette(pane["toplevel"])
        button = getattr(self, "master_refresh_btn", None)
        if button is not None:
            button.set_dark_mode(dark)

    def master_shutdown(self):
        engine = getattr(self, "master_engine", None)
        if engine is not None:
            engine.stop(join_timeout=0.8)
        ser = getattr(self, "master_serial", None)
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        self.master_engine = None
        self.master_serial = None


def fc_choice_label_write(fc):
    return f"FC{fc:02d} {FUNCTION_NAMES[fc]}"
