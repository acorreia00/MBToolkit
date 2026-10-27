#!/usr/bin/env python3
"""Master (poll) tab: one window per Slave / data area, polled over one COM.

The protocol and scheduling live in ``mb_master.py``; this mixin owns the
widgets. Each poll window has a model (``MasterWindow``) and a pane that can
sit in the tab's grid or be popped out into its own top-level window.
"""

import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

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
    MASTER_WORKSPACE_FORMATS,
    MASTER_WORKSPACE_VERSION,
    MODBUS_EXCEPTION_CODES,
    get_master_workspaces_folder,
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
    format_window_values,
    raw_text_for_scaled,
    register_groups,
    validate_read_definition,
)
from mb_table_ui import (
    SERIAL_PARITIES,
    SERIAL_STOP_BITS,
    TABLE_MAX_TITLE_LENGTH,
    TABLE_PANE_MAX_ROWS,
    TABLE_PANE_MIN_ROWS,
    TABLE_PANE_MIN_WIDTH,
    TableUiMixin,
    TableWorkspace,
    apply_format_to_rows,
    parse_int_field,
    validated_formats,
    validated_names,
    validated_scales,
)
from mb_table_ui import list_workspaces as _list_workspaces
from mb_table_ui import workspace_path as _workspace_path
from mb_theme import theme_colors
from mb_widgets import RefreshButton

MASTER_PARITIES = SERIAL_PARITIES
MASTER_STOP_BITS = SERIAL_STOP_BITS
MASTER_PANE_MIN_WIDTH = TABLE_PANE_MIN_WIDTH
MASTER_PANE_MIN_ROWS = TABLE_PANE_MIN_ROWS
MASTER_PANE_MAX_ROWS = TABLE_PANE_MAX_ROWS
MASTER_OK_MESSAGE_SECONDS = 3.0
MASTER_MAX_TITLE_LENGTH = TABLE_MAX_TITLE_LENGTH
MASTER_WHEEL_TAG = "MBToolkit.MasterWheel"


def workspace_path(name):
    """File of a Master workspace (in Workspaces\\Master)."""
    return _workspace_path(name, get_master_workspaces_folder())


def list_workspaces():
    """Names of the saved Master workspaces, sorted alphabetically."""
    return _list_workspaces(get_master_workspaces_folder())


def fc_choice_label(fc):
    return f"{fc:02d} {FUNCTION_NAMES[fc]}"


FC_CHOICES = tuple(fc_choice_label(fc) for fc in READ_FUNCTION_CODES)


class MasterWindow:
    """State of one poll window (independent of where its pane is shown)."""

    def __init__(self, window_id, number, slave=1, fc=3, address=0, qty=10,
                 scan_ms=MASTER_DEFAULT_SCAN_MS, base=0, fmt=DEFAULT_FORMAT,
                 names=None, enabled=True, title="", formats=None, scales=None):
        self.window_id = window_id
        self.number = number
        # User-chosen window name; empty means the default "Janela N".
        self.title = str(title or "").strip()[:MASTER_MAX_TITLE_LENGTH]
        self.slave = slave
        self.fc = fc
        self.address = address
        self.qty = qty
        self.scan_ms = scan_ms
        self.base = base
        self.fmt = fmt
        self.names = dict(names or {})  # PDU address -> label
        # PDU address -> format of the value that starts there (per-address
        # formats chosen with the right-click menu); others use self.fmt.
        self.formats = {int(a): f for a, f in (formats or {}).items() if f in FORMAT_SIZES}
        # PDU address -> scale (raw/engineering points, decimals, unit) of the
        # value that starts there.
        self.scales = {int(a): dict(s) for a, s in (scales or {}).items()}
        self.enabled = enabled
        self.popped = False
        self.reset_counters()

    def reset_counters(self):
        self.tx = 0
        self.errors = 0
        self.timeouts = 0
        self.response_ms = None
        self.values = None
        # True when the latest read failed: the shown values are out of date.
        self.stale = False
        # (canonical PT template, values, style) shown on the status line.
        self.message = ("", {}, "normal")
        self.message_at = 0.0

    def definition(self):
        return PollDefinition(self.window_id, self.slave, self.fc, self.address,
                              self.qty, self.scan_ms, self.enabled)

    def to_json(self):
        return {
            "title": self.title,
            "slave": self.slave, "fc": self.fc, "address": self.address,
            "qty": self.qty, "scan_ms": self.scan_ms, "base": self.base,
            "format": self.fmt, "enabled": self.enabled,
            "names": {str(address): name for address, name in sorted(self.names.items())},
            "formats": {str(address): fmt for address, fmt in sorted(self.formats.items())},
            "scales": {str(address): scale for address, scale in sorted(self.scales.items())},
        }

    def groups(self):
        """[(row offset, size, fmt or None)] of the values shown in this window."""
        return register_groups(self.qty, self.address, self.fmt, self.formats)

    def group_of_row(self, row):
        for offset, size, fmt in self.groups():
            if offset <= row < offset + size:
                return offset, size, fmt
        return row, 1, None

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
        formats = data.get("formats", {})
        return {
            "title": str(data.get("title", "") or "").strip()[:MASTER_MAX_TITLE_LENGTH],
            "slave": slave, "fc": fc, "address": address, "qty": qty,
            "scan_ms": scan_ms, "base": 1 if data.get("base") == 1 else 0,
            "fmt": fmt if fmt in FORMAT_SIZES else DEFAULT_FORMAT,
            "enabled": bool(data.get("enabled", True)),
            "names": validated_names(names),
            "formats": validated_formats(formats),
            "scales": validated_scales(data.get("scales", {})),
        }


class MasterMixin(TableUiMixin):
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
        # Workspace menu: the saved workspaces are listed directly in it.
        self.master_workspace_btn = ttk.Menubutton(toolbar, text="Workspace")
        self.master_workspace_btn.grid(row=0, column=1, padx=(0, 6))
        self.master_workspace_menu = tk.Menu(
            self.master_workspace_btn, tearoff=False,
            postcommand=self._master_build_workspace_menu,
        )
        self.master_workspace_btn.configure(menu=self.master_workspace_menu)
        self.master_workspace_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.master_workspace_var).grid(
            row=0, column=2, padx=(0, 6))
        self.master_workspace = TableWorkspace(
            self, folder=get_master_workspaces_folder,
            formats=MASTER_WORKSPACE_FORMATS, data=self.master_workspace_data,
            load=self._master_load_workspace_data, label_var=self.master_workspace_var,
            close_question="Guardar alterações ao workspace \"{name}\"?",
        )
        title_font = tkfont.nametofont("TkDefaultFont").copy()
        title_font.configure(weight="bold")
        self._master_title_font = title_font
        self.ui_style.configure("MBS.Master.Title.TLabel", font=title_font)
        ttk.Label(
            toolbar,
            text=("Duplo clique num valor para escrever, num nome para o editar. "
                  "Clique direito: formato, copiar e base."),
        ).grid(row=0, column=3, sticky="w", padx=(12, 0))

        self.master_canvas, self.master_grid, self._master_grid_item = \
            self._table_build_scroll_grid(page, 2)
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

        self._master_build_row_menu()

        # Reopen the workspace used last time; it is loaded once the window is
        # complete so the COM port list is already known. Never connects.
        last = saved.get("last_workspace", "")
        if last and last in list_workspaces():
            self.after(10, lambda: self._master_restore_workspace(last))
        else:
            self.master_add_window()

    def _master_restore_workspace(self, name):
        if not self.master_open_workspace(name, quiet=True):
            self.master_add_window()

    # -- helpers ---------------------------------------------------------------
    def _master_install_wheel_tags(self, root_widget):
        self._table_install_wheel_tags(root_widget, MASTER_WHEEL_TAG)

    def _master_wheel(self, event):
        return self._table_wheel(getattr(self, "master_canvas", None), event)

    def _master_window_name(self, window):
        return window.title or self.trf("Janela {number}", number=window.number)

    def _master_window_summary(self, window):
        return (f"Slave {window.slave} · FC{window.fc:02d} {FUNCTION_NAMES[window.fc]} · "
                f"{window.address + window.base} · {window.qty}")

    def _master_window_title(self, window):
        return f"{self._master_window_name(window)} — {self._master_window_summary(window)}"

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
            pane["name_var"].set(self._master_window_name(window))
            pane["summary_var"].set(self._master_window_summary(window))
            pane["pause_btn"].configure(text=self.tr("Retomar" if not window.enabled else "Pausar"))
            pane["popout_btn"].configure(text=self.tr("Ancorar" if window.popped else "Destacar"))
            if window.popped and pane.get("toplevel") is not None:
                pane["toplevel"].title(f"MBToolkit — {self._master_window_title(window)}")
        except tk.TclError:
            pass

    # -- panes -------------------------------------------------------------------
    def _master_build_pane(self, window, parent):
        frame = ttk.LabelFrame(parent, text="")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        pane = {"frame": frame}
        window_id = window.window_id

        header_buttons = self._table_build_header(
            frame, pane,
            rename=lambda: self.master_rename_window(window_id),
            popout=lambda: self.master_toggle_popout(window_id),
            close=lambda: self.master_close_window(window_id),
        )

        definition = ttk.Frame(frame)
        definition.grid(row=1, column=0, sticky="w", padx=6, pady=(2, 2))
        pane["slave_var"] = tk.StringVar(value=str(window.slave))
        pane["fc_var"] = tk.StringVar(value=fc_choice_label(window.fc))
        pane["address_var"] = tk.StringVar(value=str(window.address + window.base))
        pane["qty_var"] = tk.StringVar(value=str(window.qty))
        pane["scan_var"] = tk.StringVar(value=str(window.scan_ms))
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
        definition2.grid(row=2, column=0, sticky="w", padx=6, pady=2)
        format_combo = ttk.Combobox(
            definition2, values=[FORMAT_LABELS[k] for k in FORMAT_LABELS], width=20,
            state="readonly", textvariable=pane["format_var"],
        )
        layout2 = (
            ("Scan (ms)", ttk.Entry(definition2, width=7, textvariable=pane["scan_var"])),
            ("Formato", format_combo),
        )
        for index, (caption, widget) in enumerate(layout2):
            ttk.Label(definition2, text=caption).grid(row=0, column=index * 2, padx=(0, 3))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 10))
        pane["format_combo"] = format_combo

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="w", padx=6, pady=(2, 2))
        actions = (
            ("Aplicar", lambda: self.master_apply_window(window_id)),
            ("Pausar", lambda: self.master_toggle_pause(window_id)),
            ("Ler 1x", lambda: self.master_read_once(window_id)),
            ("Duplicar", lambda: self.master_duplicate_window(window_id)),
        )
        for index, (caption, command) in enumerate(actions):
            button = ttk.Button(buttons, text=caption, command=command, width=10)
            button.grid(row=0, column=index, padx=(0, 3))
            if caption == "Pausar":
                pane["pause_btn"] = button
            elif caption == "Aplicar":
                pane["apply_btn"] = button

        status = ttk.Frame(frame)
        status.grid(row=4, column=0, sticky="ew", padx=6, pady=(2, 2))
        status.columnconfigure(1, weight=1)
        pane["counters_var"] = tk.StringVar()
        pane["message_var"] = tk.StringVar()
        ttk.Label(status, textvariable=pane["counters_var"]).grid(row=0, column=0, sticky="w")
        pane["message_label"] = ttk.Label(status, textvariable=pane["message_var"])
        pane["message_label"].grid(row=0, column=1, sticky="w", padx=(14, 0))

        self._table_build_tree(
            frame, pane, 5,
            on_double=lambda e: self._master_on_double_click(window_id, e),
            on_return=lambda: self._master_edit_value(window_id),
            on_menu=lambda e: self._master_show_row_menu(window_id, e),
        )

        for widget in (definition, definition2):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                    child.bind("<Return>", lambda _e: self.master_apply_window(window_id))

        self._table_translate_captions(definition, definition2, buttons, header_buttons)

        self._master_panes[window_id] = pane
        for name in ("slave_var", "fc_var", "address_var", "qty_var", "scan_var", "format_var"):
            pane[name].trace_add("write",
                                 lambda *_a: self._master_update_apply_state(window_id))
        self._master_fill_rows(window)
        self._master_update_format_state(window)
        self._master_render_status(window)
        self._master_update_apply_state(window_id)
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
        tree.configure(height=max(MASTER_PANE_MIN_ROWS, min(MASTER_PANE_MAX_ROWS, window.qty)))
        for index in range(window.qty):
            pdu = window.address + index
            tree.insert("", "end", iid=f"r{index}", tags=self._table_row_tags(index),
                        values=(pdu + window.base, window.names.get(pdu, ""), ""))
        self._master_render_values(window)

    def _master_render_values(self, window):
        pane = self._master_panes.get(window.window_id)
        if pane is None:
            return
        tree = pane["tree"]
        stale = ("stale",) if window.stale else ()
        if window.values is None:
            texts = [""] * window.qty
        elif window.fc in BIT_FUNCTION_CODES:
            texts = [str(v) for v in window.values]
        else:
            texts = format_window_values(window.values, window.address, window.fmt,
                                         window.formats, window.scales)
        for index, text in enumerate(texts[:window.qty]):
            try:
                tree.item(f"r{index}", tags=self._table_row_tags(index) + stale)
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
        docked = [w for w in sorted(self.master_windows.values(), key=lambda w: w.number)
                  if not w.popped]
        frames = [self._master_panes[w.window_id]["frame"] for w in docked
                  if w.window_id in self._master_panes]
        self._table_reflow(self.master_canvas, self.master_grid, self._master_grid_item,
                           frames, self.master_empty_label, "master_panes")

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
        self._master_mark_changed()
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
        if not self.master_windows:
            # Closing every window leaves no workspace open.
            self.master_workspace.forget()
        else:
            self._master_mark_changed()

    def master_apply_window(self, window_id):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None:
            return False
        try:
            base = window.base
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

        fmt = FORMAT_KEYS_BY_LABEL.get(pane["format_var"].get(), DEFAULT_FORMAT)
        changed_area = (slave, fc, address, qty) != (window.slave, window.fc,
                                                     window.address, window.qty)
        changed = changed_area or (scan_ms, fmt) != (window.scan_ms, window.fmt)
        window.slave, window.fc, window.address, window.qty = slave, fc, address, qty
        window.scan_ms, window.fmt = scan_ms, fmt
        if changed_area:
            window.reset_counters()
        self._master_fill_rows(window)
        self._master_update_format_state(window)
        self._master_render_status(window)
        self._master_update_apply_state(window_id)
        if self.master_engine is not None:
            self.master_engine.set_poll(window.definition())
        if changed:
            self._master_mark_changed()
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
        self._master_mark_changed()

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
            self._table_apply_toplevel_palette(top)
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

    def _master_edit_name(self, window_id, row):
        window = self.master_windows.get(window_id)
        if window is None:
            return
        pdu = window.address + int(row[1:])
        dialog, body = self._table_dialog(self.tr("Nome"))
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
            self._master_mark_changed()
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
        if bits:
            size, fmt = 1, None
        else:
            # Multi-register values start on the first register of their group.
            index, size, fmt = window.group_of_row(index)
            if fmt is None:
                messagebox.showinfo(
                    self.tr("Escrita"),
                    self.tr("Este endereço não tem um valor completo no formato atual."),
                )
                return
        current = ""
        try:
            current = pane["tree"].set(f"r{index}", "value")
        except tk.TclError:
            pass
        if not bits and window.scales.get(window.address + index, {}).get("unit"):
            current = current.rsplit(" ", 1)[0]

        dialog, body = self._table_dialog(self.tr("Escrever"))
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
        scale = None if bits else window.scales.get(window.address + index)
        if scale is not None and fmt in ("hex16", "bin16"):
            scale = None
        format_text = "0 / 1" if bits else FORMAT_LABELS[fmt]
        if scale is not None:
            format_text += " · " + self.trf("valores em unidades da escala {unit}",
                                            unit=scale.get("unit") or "")
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
                    window, slave_var.get(), address_var.get(), value_var.get(),
                    fc_var.get(), fmt, scale,
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

    def master_build_write(self, window, slave_text, address_text, values_text, fc,
                           fmt=None, scale=None):
        """Validate the write dialog fields and return (request, description).

        *fmt* is the format of the clicked value (per-address or window format).
        With *scale*, the typed values are engineering units and are converted
        back to raw values before encoding.
        """
        fmt = fmt or window.fmt
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
                if scale is not None:
                    part = raw_text_for_scaled(part, scale, fmt)
                values.extend(encode_register_value(part, fmt))
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
                self.tr("Para a captura, a pesquisa ou o Slave em curso antes de ligar o Master."),
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
            reopen=lambda: self.open_discovery_serial_port(
                serial, settings["port"], settings["baud"], settings["parity"],
                settings["stopbits"],
            ),
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
        slave_button = getattr(self, "slave_connect_btn", None)
        if slave_button is not None:
            slave_button.configure(state=state)
        self.start_btn.configure(state=state)
        self.restart_btn.configure(state=state)
        self.set_sniffer_refresh_state(state)
        self.set_simulation_button_state(state)
        self.update_discovery_start_state()

    def _master_finish_session(self, payload):
        if not self.master_active:
            return  # already finished (a late master_stopped event)
        engine = self.master_engine
        self.master_engine = None
        if engine is not None:
            engine.stop(join_timeout=0.5)
            self.master_serial = engine.ser
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
        for window in self.master_windows.values():
            if window.values is not None and not window.stale:
                window.stale = True
                self._master_render_values(window)

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
        elif event == "master_reconnecting":
            self.master_status_var.set(self.trf(
                "A religar a {port}… (porta falhou: {error})",
                port=self.master_port_var.get(), error=(payload or {}).get("error", ""),
            ))
            for window in self.master_windows.values():
                if window.values is not None and not window.stale:
                    window.stale = True
                    self._master_render_values(window)
        elif event == "master_reconnected":
            engine = self.master_engine
            if engine is not None:
                self.master_serial = engine.ser
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
                window.stale = False
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
        if result["kind"] == "read" and not window.stale:
            window.stale = True
            self._master_render_values(window)
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

    def _master_mark_changed(self):
        self.master_workspace.mark_changed()

    def _master_build_workspace_menu(self):
        """Rebuild the Workspace menu from the files in the workspace folder."""
        self.master_workspace.fill_menu(self.master_workspace_menu)
        self._master_apply_menu_palette()

    def master_save_workspace(self, name=None):
        return self.master_workspace.save(name)

    def master_delete_workspace(self, name, confirm=True):
        return self.master_workspace.delete(name, confirm)

    def master_open_workspace(self, name, quiet=False):
        return self.master_workspace.open(name, quiet)

    def _master_load_workspace_data(self, data):
        """Replace the windows with those of *data*; returns the invalid count."""
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
        return skipped

    # -- window rename ---------------------------------------------------------------
    def master_rename_window(self, window_id, name=None):
        window = self.master_windows.get(window_id)
        if window is None:
            return
        if name is None:
            name = self._table_ask_text(
                self.tr("Renomear janela"),
                self.tr("Nome da janela (vazio = nome por defeito)"),
                self._master_window_name(window),
            )
            if name is None:
                return
        name = name.strip()[:MASTER_MAX_TITLE_LENGTH]
        if name == self.trf("Janela {number}", number=window.number):
            name = ""
        window.title = name
        self._master_render_status(window)
        self._master_mark_changed()

    # -- apply highlight / table tags -------------------------------------------------
    def _master_fields_changed(self, window, pane):
        """True when the definition fields differ from what was last applied."""
        try:
            return (
                pane["slave_var"].get().strip() != str(window.slave)
                or pane["fc_var"].get() != fc_choice_label(window.fc)
                or pane["address_var"].get().strip() != str(window.address + window.base)
                or pane["qty_var"].get().strip() != str(window.qty)
                or pane["scan_var"].get().strip() != str(window.scan_ms)
                or FORMAT_KEYS_BY_LABEL.get(pane["format_var"].get()) != window.fmt
            )
        except tk.TclError:
            return False

    def _master_update_apply_state(self, window_id):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None or "apply_btn" not in pane:
            return
        style = ("MBS.Primary.TButton" if self._master_fields_changed(window, pane)
                 else "TButton")
        try:
            pane["apply_btn"].configure(style=style)
        except tk.TclError:
            pass

    def _master_row_tags(index):
        """Alternate rows get a slightly darker background (zebra striping)."""
        return ("odd",) if index % 2 else ()

    # -- right-click menu: per-address format, copy, base ---------------------------
    def _master_build_row_menu(self):
        self._master_row_menu = tk.Menu(self, tearoff=False)

    def _master_selected_rows(self, window_id):
        return self._table_selected_rows(self._master_panes.get(window_id))

    def _master_show_row_menu(self, window_id, event):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None:
            return "break"
        tree = pane["tree"]
        row = tree.identify_row(event.y)
        if row and row not in tree.selection():
            tree.selection_set(row)
        self._table_fill_row_menu(
            self._master_row_menu, pane, window, window.fc not in BIT_FUNCTION_CODES,
            set_format=lambda fmt: self.master_set_row_format(window_id, fmt),
            edit_scale=lambda: self.master_edit_scale(window_id),
            remove_scale=lambda: self.master_remove_scale(window_id),
            copy=lambda: self.master_copy_rows(window_id),
            set_base=lambda base: self.master_set_base(window_id, base),
            extra=(("Abrir no Slave", lambda: self.slave_open_from_master(window)),)
            if hasattr(self, "slave_open_from_master") else (),
        )
        self._master_apply_menu_palette()
        self._table_popup(self._master_row_menu, event)
        return "break"

    def master_set_row_format(self, window_id, fmt):
        """Apply *fmt* (None = window format) to the selected rows."""
        window = self.master_windows.get(window_id)
        if window is None:
            return False
        try:
            apply_format_to_rows(window, self._master_selected_rows(window_id), fmt)
        except ValueError as exc:
            size = FORMAT_SIZES.get(fmt, 1)
            messagebox.showwarning(self.tr("Formato"), self.trf(str(exc), size=size))
            return False
        self._master_render_values(window)
        self._master_mark_changed()
        return True

    # -- opening windows from Sniffer / Bus Slave Finder ------------------------------
    def master_definition_from_record(self, record):
        """Read definition (slave, fc, address, qty) behind a Traffic record, or None.

        A REQUEST carries its own address/quantity; a matched RESPONSE or
        EXCEPTION carries the ones of its request. Only FC01–FC04 qualify.
        """
        try:
            slave = int(record.get("slave", ""))
            fc = int(str(record.get("fc", "")), 16) & 0x7F
        except (TypeError, ValueError):
            return None
        if fc not in READ_FUNCTION_CODES or not 1 <= slave <= 247:
            return None
        if record.get("type") == "REQUEST":
            address, qty = record.get("pdu_address"), record.get("qty")
        else:
            address, qty = record.get("request_pdu_address"), record.get("request_qty")
        if address is None or qty is None:
            return None
        try:
            validate_read_definition(slave, fc, address, qty)
        except ValueError:
            return None
        return {"slave": slave, "fc": fc, "address": int(address), "qty": int(qty)}

    def master_open_from_record(self, record):
        definition = self.master_definition_from_record(record)
        if definition is None:
            messagebox.showinfo(
                self.tr("Abrir no Master"),
                self.tr("Esta trama não tem um pedido de leitura FC01–FC04 com endereço "
                        "conhecido."),
            )
            return None
        port = ""
        if not getattr(self, "capture_active", False):
            port = self.port_a_var.get().strip()
        return self.master_open_definition(
            definition, port=port, baud=self.baud_var.get(),
            parity=self.parity_var.get(), stopbits=self.stop_var.get(),
        )

    def master_open_definition(self, definition, port="", baud="", parity="", stopbits=""):
        """Add a Master window and show the Master tab.

        The serial settings (and port) are copied to the Master connection only
        when it is not connected and they are valid for the Master.
        """
        if not self.master_active:
            if str(baud) in [str(b) for b in DISCOVERY_BAUD_RATES]:
                self.master_baud_var.set(str(baud))
            if parity in MASTER_PARITIES:
                self.master_parity_var.set(parity)
            if str(stopbits) in MASTER_STOP_BITS:
                self.master_stop_var.set(str(stopbits))
            if port and port in tuple(self.master_port_combo["values"]):
                self.master_port_var.set(port)
        window = self.master_add_window(definition)
        try:
            self.main_notebook.select(self.master_page)
        except tk.TclError:
            pass
        return window

    def _master_selected_group_starts(self, window):
        """PDU addresses where the values of the selected rows start."""
        return self._table_selected_group_starts(window, self._master_panes.get(window.window_id))

    def master_edit_scale(self, window_id):
        """Ask for a linear scale and apply it to the selected values."""
        window = self.master_windows.get(window_id)
        if window is None:
            return False
        starts = self._master_selected_group_starts(window)
        if not starts:
            messagebox.showwarning(self.tr("Escala"),
                                   self.tr("Seleciona pelo menos um endereço."))
            return False
        if not self._table_ask_scale(window, starts):
            return False
        self._master_render_values(window)
        self._master_mark_changed()
        return True

    def master_remove_scale(self, window_id):
        window = self.master_windows.get(window_id)
        if window is None:
            return False
        removed = False
        for address in self._master_selected_group_starts(window):
            removed = window.scales.pop(address, None) is not None or removed
        if removed:
            self._master_render_values(window)
            self._master_mark_changed()
        return removed

    def master_copy_rows(self, window_id):
        """Copy the selected rows (all rows if none) as tab-separated text."""
        self._table_copy_rows(self._master_panes.get(window_id))

    def master_set_base(self, window_id, base):
        window = self.master_windows.get(window_id)
        pane = self._master_panes.get(window_id)
        if window is None or pane is None or window.base == base:
            return
        window.base = base
        pane["address_var"].set(str(window.address + window.base))
        self._master_fill_rows(window)
        self._master_render_status(window)
        self._master_update_apply_state(window_id)
        self._master_mark_changed()

    # -- closing the application ------------------------------------------------------
    def master_confirm_close(self):
        """Ask to save a changed workspace; False cancels closing the application."""
        workspace = getattr(self, "master_workspace", None)
        return workspace is None or workspace.confirm_close()

    # -- language / palette / shutdown -----------------------------------------------
    def master_apply_language(self):
        if not hasattr(self, "master_windows"):
            return
        self.master_workspace.update_label()
        for window in self.master_windows.values():
            pane = self._master_panes.get(window.window_id)
            if pane is None:
                continue
            self._table_translate_headings(pane)
            self._master_render_status(window)
        if not self.master_active:
            self.master_status_var.set(self.tr("Desligado"))
        elif self.master_engine is not None:
            self.master_status_var.set(self.tr("● Ligado"))

    def _master_apply_menu_palette(self):
        self._table_apply_menus_palette(getattr(self, "master_workspace_menu", None),
                                        getattr(self, "_master_row_menu", None))

    def master_apply_palette(self, dark):
        self._master_apply_menu_palette()
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
                self._table_apply_toplevel_palette(pane["toplevel"])
            self._table_configure_tree_tags(pane["tree"])
        button = getattr(self, "master_refresh_btn", None)
        if button is not None:
            button.set_dark_mode(dark)

    def master_shutdown(self):
        engine = getattr(self, "master_engine", None)
        if engine is not None:
            engine.stop(join_timeout=0.8)
            self.master_serial = engine.ser
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
