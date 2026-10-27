#!/usr/bin/env python3
"""Slave (simulator) tab: the application answers a real master as Modbus slaves.

The data tables, request handling and serial loop live in ``mb_slave.py``;
this mixin owns the widgets. Each window shows one data table (Coils,
Discrete Inputs, Holding or Input Registers) of one simulated Slave ID; the
windows define which addresses exist. Values start at 0, are edited by
double-click and change when the master writes. Fault simulation is set per
Slave ID. The window grid, value table and Workspace menu are shared with the
Master tab (``mb_table_ui.py``).
"""

import time
import tkinter as tk
from tkinter import messagebox, ttk

from mb_config import (
    DISCOVERY_BAUD_RATES,
    MODBUS_EXCEPTION_CODES,
    SLAVE_FAULT_MAX_DELAY_MS,
    SLAVE_GENERATOR_TICK_MS,
    SLAVE_HIGHLIGHT_SECONDS,
    SLAVE_MAX_QTY,
    SLAVE_MAX_WINDOWS,
    SLAVE_WORKSPACE_FORMAT,
    SLAVE_WORKSPACE_VERSION,
    get_slave_workspaces_folder,
)
from mb_master import (
    DEFAULT_FORMAT,
    FORMAT_KEYS_BY_LABEL,
    FORMAT_LABELS,
    FORMAT_SIZES,
    encode_coil_value,
    encode_register_value,
    format_window_values,
    READ_FUNCTION_CODES,
    raw_text_for_scaled,
    register_groups,
    unscale_value,
)
from mb_slave import (
    BIT_GENERATORS,
    BIT_TABLES,
    FAULT_EXCEPTION_CODES,
    FC_TABLES,
    REGISTER_GENERATORS,
    TABLE_READ_FC,
    TABLES,
    SlaveEngine,
    SlaveStore,
    default_fault,
    fault_active,
    table_choice_label,
    table_label,
    validate_fault,
    validate_generator,
    ValueGenerator,
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
    list_workspaces,
    parse_int_field,
    validated_formats,
    validated_names,
    validated_scales,
)
from mb_theme import theme_colors
from mb_widgets import RefreshButton

SLAVE_WHEEL_TAG = "MBToolkit.SlaveWheel"
# Automatic value kinds as shown in the dialog (PT canonical captions).
GENERATOR_LABELS = {"counter": "Contador", "ramp": "Rampa", "sine": "Senoide",
                    "random": "Aleatório", "toggle": "Alternar 0/1"}
TABLE_CHOICES = tuple(table_choice_label(t) for t in TABLES)
TABLE_KEYS_BY_LABEL = {table_choice_label(t): t for t in TABLES}


def fault_parts(fault):
    """(PT template, values) pieces describing an active fault."""
    parts = []
    if fault.get("no_response"):
        parts.append(("sem resposta", {}))
    if fault.get("exception"):
        parts.append(("Exception {code:02X}", {"code": fault["exception"]}))
    if fault.get("bad_crc"):
        parts.append(("CRC errado", {}))
    if fault.get("delay_ms"):
        parts.append(("atraso {ms} ms", {"ms": fault["delay_ms"]}))
    return parts


class SlaveWindow:
    """State of one simulated data table (independent of where it is shown)."""

    def __init__(self, window_id, number, slave=1, table="holding", address=0, qty=10,
                 base=0, fmt=DEFAULT_FORMAT, names=None, title="", formats=None, scales=None,
                 generators=None):
        self.window_id = window_id
        self.number = number
        # User-chosen window name; empty means the default "Janela N".
        self.title = str(title or "").strip()[:TABLE_MAX_TITLE_LENGTH]
        self.slave = slave
        self.table = table
        self.address = address
        self.qty = qty
        self.base = base
        self.fmt = fmt
        self.names = dict(names or {})  # PDU address -> label
        self.formats = {int(a): f for a, f in (formats or {}).items() if f in FORMAT_SIZES}
        self.scales = {int(a): dict(s) for a, s in (scales or {}).items()}
        # PDU address -> automatic value (validate_generator()) of the value
        # that starts there.
        self.generators = {int(a): dict(g) for a, g in (generators or {}).items()}
        self.popped = False
        # Row index -> time.monotonic() until which it is shown as written.
        self.highlight = {}
        self.reset_counters()

    def reset_counters(self):
        self.requests = 0
        self.exceptions = 0
        self.last = ""

    @property
    def bits(self):
        return self.table in BIT_TABLES

    def area(self):
        return (self.slave, self.table, self.address, self.qty)

    def overlap(self, address, qty):
        """Row range of this window covered by [address, address + qty), or None."""
        first = max(self.address, address)
        last = min(self.address + self.qty, address + qty)
        return (first - self.address, last - self.address) if first < last else None

    def groups(self):
        return register_groups(self.qty, self.address, self.fmt, self.formats)

    def group_of_row(self, row):
        for offset, size, fmt in self.groups():
            if offset <= row < offset + size:
                return offset, size, fmt
        return row, 1, None

    def to_json(self):
        return {
            "title": self.title, "slave": self.slave, "table": self.table,
            "address": self.address, "qty": self.qty, "base": self.base,
            "format": self.fmt,
            "names": {str(a): n for a, n in sorted(self.names.items())},
            "formats": {str(a): f for a, f in sorted(self.formats.items())},
            "scales": {str(a): s for a, s in sorted(self.scales.items())},
            "generators": {str(a): g for a, g in sorted(self.generators.items())},
        }

    def drop_invalid_generators(self):
        """Keep only automatic values that still fit the window's area and table."""
        kept = {}
        for address, config in self.generators.items():
            if self.address <= address < self.address + self.qty:
                try:
                    kept[address] = validate_generator(config, self.bits)
                except ValueError:
                    continue
        self.generators = kept

    @staticmethod
    def validated_kwargs(data):
        """Validate one workspace window entry; raise ValueError if invalid."""
        if not isinstance(data, dict):
            raise ValueError("Janela inválida.")
        slave, table = int(data.get("slave", 1)), data.get("table", "holding")
        address, qty = int(data.get("address", 0)), int(data.get("qty", 10))
        validate_area(slave, table, address, qty)
        fmt = data.get("format", DEFAULT_FORMAT)
        return {
            "title": str(data.get("title", "") or "").strip()[:TABLE_MAX_TITLE_LENGTH],
            "slave": slave, "table": table, "address": address, "qty": qty,
            "base": 1 if data.get("base") == 1 else 0,
            "fmt": fmt if fmt in FORMAT_SIZES else DEFAULT_FORMAT,
            "names": validated_names(data.get("names", {})),
            "formats": validated_formats(data.get("formats", {})),
            "scales": validated_scales(data.get("scales", {})),
            "generators": validated_generators(data.get("generators", {}), table in BIT_TABLES),
        }


def validated_generators(generators, bits):
    """Automatic values of a workspace window entry; invalid ones are dropped."""
    result = {}
    for key, item in (generators.items() if isinstance(generators, dict) else ()):
        try:
            if str(key).isdigit() and int(key) <= 0xFFFF:
                result[int(key)] = validate_generator(item, bits)
        except ValueError:
            continue
    return result


def slave_definition_from_record(record):
    """Slave window (slave, table, address, qty) behind a Traffic record, or None.

    Reads (FC01–FC04) give their table and requested area; writes (FC05/06/
    15/16) the written Coils / Holding Registers. A REQUEST carries its own
    address; a RESPONSE/EXCEPTION of a read carries the one of its request.
    """
    try:
        slave = int(record.get("slave", ""))
        fc = int(str(record.get("fc", "")), 16) & 0x7F
    except (TypeError, ValueError):
        return None
    if fc not in FC_TABLES or not 1 <= slave <= 247:
        return None
    if record.get("type") == "REQUEST" or (fc not in READ_FUNCTION_CODES
                                           and record.get("type") == "RESPONSE"):
        address, qty = record.get("pdu_address"), record.get("qty")
    else:
        address, qty = record.get("request_pdu_address"), record.get("request_qty")
    if fc in (5, 6):
        qty = 1
    if address is None or qty is None:
        return None
    try:
        validate_area(slave, FC_TABLES[fc], address, qty)
    except (ValueError, TypeError):
        return None
    return {"slave": slave, "table": FC_TABLES[fc], "address": int(address), "qty": int(qty)}


def validate_area(slave, table, address, qty):
    """Raise ValueError (PT canonical message) for an invalid window area."""
    if not 1 <= int(slave) <= 247:
        raise ValueError("O Slave ID tem de estar entre 1 e 247.")
    if table not in TABLES:
        raise ValueError("Tabela inválida.")
    if not 0 <= int(address) <= 0xFFFF:
        raise ValueError("O endereço tem de estar entre 0 e 65535.")
    if not 1 <= int(qty) <= SLAVE_MAX_QTY:
        raise ValueError("A quantidade tem de estar entre 1 e 2000.")
    if int(address) + int(qty) > 0x10000:
        raise ValueError("O intervalo de endereços ultrapassa 65535.")


class SlaveMixin(TableUiMixin):
    """Slave (simulator) tab GUI."""

    # -- construction ----------------------------------------------------------
    def build_slave_tab(self, page):
        saved = getattr(self, "ui_settings", {}).get("slave", {})
        if not isinstance(saved, dict):
            saved = {}

        self.slave_windows = {}
        self._slave_panes = {}
        self._slave_next_id = 1
        self.slave_store = SlaveStore()
        # Slave ID -> fault settings (active ones only).
        self.slave_faults = {}
        self.slave_engine = None
        self.slave_serial = None
        self.slave_active = False
        self._slave_reflow_after_id = None
        self._slave_tick_after_id = None
        # (window_id, PDU address) -> (ValueGenerator, start time) of the
        # automatic values; recomputed every SLAVE_GENERATOR_TICK_MS.
        self._slave_generators = {}
        self._slave_generator_after_id = None
        self._slave_reset_stats()

        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        connection = ttk.LabelFrame(
            page, text="Ligação — o Slave responde aos pedidos de um master real")
        connection.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row = ttk.Frame(connection)
        row.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        ttk.Label(row, text="Porta COM").grid(row=0, column=0, padx=(0, 4))
        self.slave_port_var = tk.StringVar()
        self.slave_port_combo = ttk.Combobox(
            row, textvariable=self.slave_port_var, width=13, state="readonly"
        )
        self.slave_port_combo.grid(row=0, column=1)
        self.slave_refresh_btn = RefreshButton(row, command=self.refresh_ports, size=24)
        self.slave_refresh_btn.grid(row=0, column=2, padx=(4, 18))

        def _sync_refresh_square(_event=None):
            height = self.slave_port_combo.winfo_height()
            if height > 1:
                self.slave_refresh_btn.configure(width=height, height=height)

        self.slave_port_combo.bind("<Configure>", _sync_refresh_square, add="+")

        self.slave_baud_var = tk.StringVar(value=str(saved.get("baud", "9600")))
        self.slave_parity_var = tk.StringVar(value=saved.get("parity", "None"))
        self.slave_stop_var = tk.StringVar(value=str(saved.get("stop_bits", "1")))
        fields = (
            ("Baud rate", ttk.Combobox(row, textvariable=self.slave_baud_var, width=8,
                                       state="readonly",
                                       values=[str(b) for b in DISCOVERY_BAUD_RATES])),
            ("Parity", ttk.Combobox(row, textvariable=self.slave_parity_var, width=6,
                                    state="readonly", values=SERIAL_PARITIES)),
            ("Stop bits", ttk.Combobox(row, textvariable=self.slave_stop_var, width=3,
                                       state="readonly", values=SERIAL_STOP_BITS)),
        )
        column = 3
        self._slave_setting_widgets = [self.slave_port_combo]
        for caption, widget in fields:
            ttk.Label(row, text=caption).grid(row=0, column=column, padx=(0, 4))
            widget.grid(row=0, column=column + 1, padx=(0, 16))
            self._slave_setting_widgets.append(widget)
            column += 2
        ttk.Label(row, text="Data bits: 8").grid(row=0, column=column)

        controls = ttk.Frame(connection)
        controls.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        self.slave_safety_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="Confirmo que nenhum equipamento no barramento usa os Slave IDs simulados.",
            variable=self.slave_safety_var,
        ).grid(row=0, column=0, padx=(0, 18))
        self.slave_connect_btn = ttk.Button(
            controls, text="Ligar", command=self.slave_connect, style="MBS.Primary.TButton"
        )
        self.slave_connect_btn.grid(row=0, column=1, padx=(0, 6))
        self.slave_disconnect_btn = ttk.Button(
            controls, text="Desligar", command=self.slave_disconnect, state="disabled"
        )
        self.slave_disconnect_btn.grid(row=0, column=2, padx=(0, 18))
        self.slave_status_var = tk.StringVar(value=self.tr("Desligado"))
        ttk.Label(controls, textvariable=self.slave_status_var).grid(row=0, column=3)
        self.slave_stats_var = tk.StringVar()
        ttk.Label(connection, textvariable=self.slave_stats_var).grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 8))
        self._slave_render_stats()

        toolbar = ttk.Frame(page)
        toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        toolbar.columnconfigure(3, weight=1)
        ttk.Button(toolbar, text="Nova janela", command=self.slave_add_window).grid(
            row=0, column=0, padx=(0, 6))
        self.slave_workspace_btn = ttk.Menubutton(toolbar, text="Workspace")
        self.slave_workspace_btn.grid(row=0, column=1, padx=(0, 6))
        self.slave_workspace_menu = tk.Menu(
            self.slave_workspace_btn, tearoff=False,
            postcommand=self._slave_build_workspace_menu,
        )
        self.slave_workspace_btn.configure(menu=self.slave_workspace_menu)
        self.slave_workspace_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.slave_workspace_var).grid(
            row=0, column=2, padx=(0, 6))
        self.slave_workspace = TableWorkspace(
            self, folder=get_slave_workspaces_folder, formats=(SLAVE_WORKSPACE_FORMAT,),
            data=self.slave_workspace_data, load=self._slave_load_workspace_data,
            label_var=self.slave_workspace_var,
            close_question="Guardar alterações ao workspace do Slave \"{name}\"?",
        )
        ttk.Label(
            toolbar,
            text=("Duplo clique num valor para o alterar, num nome para o editar. "
                  "Clique direito: formato, escala, copiar e base."),
        ).grid(row=0, column=3, sticky="w", padx=(12, 0))

        self.slave_canvas, self.slave_grid, self._slave_grid_item = \
            self._table_build_scroll_grid(page, 2)
        self.slave_canvas.bind("<Configure>", self._slave_schedule_reflow, add="+")
        self.slave_empty_label = ttk.Label(
            self.slave_grid,
            text="Sem janelas. Usa \"Nova janela\" para simular um Slave.",
        )
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_class(SLAVE_WHEEL_TAG, sequence,
                            lambda e: self._table_wheel(self.slave_canvas, e))

        for variable in (self.slave_baud_var, self.slave_parity_var, self.slave_stop_var):
            variable.trace_add("write", lambda *_a: self._schedule_ui_settings_save())

        self._slave_row_menu = tk.Menu(self, tearoff=False)

        # Reopen the workspace used last time (never starts listening).
        last = saved.get("last_workspace", "")
        if last and last in list_workspaces(get_slave_workspaces_folder()):
            self.after(10, lambda: self._slave_restore_workspace(last))
        else:
            self.slave_add_window()

    def _slave_restore_workspace(self, name):
        if not self.slave_open_workspace(name, quiet=True):
            self.slave_add_window()

    # -- texts -------------------------------------------------------------------
    def _slave_reset_stats(self):
        self.slave_stats = {"requests": 0, "responses": 0, "exceptions": 0,
                            "broadcasts": 0, "others": 0}

    def _slave_render_stats(self):
        stats = self.slave_stats
        self.slave_stats_var.set(self.trf(
            "Pedidos: {requests}   Respostas: {responses}   Exceções: {exceptions}   "
            "Broadcast: {broadcasts}   Para outros IDs: {others}", **stats))

    def _slave_window_name(self, window):
        return window.title or self.trf("Janela {number}", number=window.number)

    def _slave_window_summary(self, window):
        return (f"Slave {window.slave} · FC{TABLE_READ_FC[window.table]:02d} "
                f"{table_label(window.table)} · "
                f"{window.address + window.base} · {window.qty}")

    def _slave_fault_text(self, slave):
        fault = self.slave_faults.get(slave)
        if not fault_active(fault):
            return ""
        text = ", ".join(self.trf(template, **values) for template, values in fault_parts(fault))
        if fault["probability"] < 100:
            text += f" · {fault['probability']}%"
        return self.trf("⚠ Falha simulada: {fault}", fault=text)

    def _slave_render_status(self, window):
        pane = self._slave_panes.get(window.window_id)
        if pane is None:
            return
        try:
            pane["counters_var"].set(self.trf(
                "Pedidos: {requests}   Exceções: {exceptions}",
                requests=window.requests, exceptions=window.exceptions))
            pane["last_var"].set(self.trf("Último: {request}", request=window.last)
                                 if window.last else "")
            pane["name_var"].set(self._slave_window_name(window))
            pane["summary_var"].set(self._slave_window_summary(window))
            fault = self._slave_fault_text(window.slave)
            pane["fault_var"].set(fault)
            if fault:
                pane["fault_label"].grid()
            else:
                pane["fault_label"].grid_remove()
            pane["popout_btn"].configure(text=self.tr("Ancorar" if window.popped else "Destacar"))
            if window.popped and pane.get("toplevel") is not None:
                pane["toplevel"].title(
                    f"MBToolkit — {self._slave_window_name(window)} — "
                    f"{self._slave_window_summary(window)}")
        except tk.TclError:
            pass

    # -- panes -------------------------------------------------------------------
    def _slave_build_pane(self, window, parent):
        frame = ttk.LabelFrame(parent, text="")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        pane = {"frame": frame}
        window_id = window.window_id

        header_buttons = self._table_build_header(
            frame, pane,
            rename=lambda: self.slave_rename_window(window_id),
            popout=lambda: self.slave_toggle_popout(window_id),
            close=lambda: self.slave_close_window(window_id),
        )
        # A fault of this Slave ID is shown under the name, never hidden.
        pane["fault_var"] = tk.StringVar()
        pane["fault_label"] = ttk.Label(pane["header"], textvariable=pane["fault_var"],
                                        style="MBS.Master.Error.TLabel")
        pane["fault_label"].grid(row=1, column=0, columnspan=3, sticky="w")

        definition = ttk.Frame(frame)
        definition.grid(row=1, column=0, sticky="w", padx=6, pady=(2, 2))
        pane["slave_var"] = tk.StringVar(value=str(window.slave))
        pane["table_var"] = tk.StringVar(value=table_choice_label(window.table))
        pane["address_var"] = tk.StringVar(value=str(window.address + window.base))
        pane["qty_var"] = tk.StringVar(value=str(window.qty))
        pane["format_var"] = tk.StringVar(value=FORMAT_LABELS[window.fmt])
        layout = (
            ("Slave", ttk.Spinbox(definition, from_=1, to=247, width=4,
                                  textvariable=pane["slave_var"])),
            ("Tabela", ttk.Combobox(definition, values=TABLE_CHOICES, width=22,
                                    state="readonly", textvariable=pane["table_var"])),
            ("Endereço", ttk.Entry(definition, width=6, textvariable=pane["address_var"])),
            ("Qtd.", ttk.Entry(definition, width=5, textvariable=pane["qty_var"])),
        )
        for index, (caption, widget) in enumerate(layout):
            ttk.Label(definition, text=caption).grid(row=0, column=index * 2, padx=(0, 3))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 10))

        definition2 = ttk.Frame(frame)
        definition2.grid(row=2, column=0, sticky="w", padx=6, pady=2)
        pane["format_combo"] = ttk.Combobox(
            definition2, values=[FORMAT_LABELS[k] for k in FORMAT_LABELS], width=20,
            state="readonly", textvariable=pane["format_var"],
        )
        ttk.Label(definition2, text="Formato").grid(row=0, column=0, padx=(0, 3))
        pane["format_combo"].grid(row=0, column=1, padx=(0, 10))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="w", padx=6, pady=(2, 2))
        actions = (
            ("Aplicar", lambda: self.slave_apply_window(window_id)),
            ("Duplicar", lambda: self.slave_duplicate_window(window_id)),
            ("Falhas…", lambda: self.slave_edit_faults(window_id)),
        )
        for index, (caption, command) in enumerate(actions):
            button = ttk.Button(buttons, text=caption, command=command, width=10)
            button.grid(row=0, column=index, padx=(0, 3))
            if caption == "Aplicar":
                pane["apply_btn"] = button

        status = ttk.Frame(frame)
        status.grid(row=4, column=0, sticky="ew", padx=6, pady=(2, 2))
        status.columnconfigure(1, weight=1)
        pane["counters_var"] = tk.StringVar()
        pane["last_var"] = tk.StringVar()
        ttk.Label(status, textvariable=pane["counters_var"]).grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=pane["last_var"]).grid(
            row=0, column=1, sticky="w", padx=(14, 0))

        self._table_build_tree(
            frame, pane, 5,
            on_double=lambda e: self._slave_on_double_click(window_id, e),
            on_return=lambda: self._slave_edit_value(window_id),
            on_menu=lambda e: self._slave_show_row_menu(window_id, e),
        )
        for widget in (definition, definition2):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                    child.bind("<Return>", lambda _e: self.slave_apply_window(window_id))
        self._table_translate_captions(definition, definition2, buttons, header_buttons)

        self._slave_panes[window_id] = pane
        for name in ("slave_var", "table_var", "address_var", "qty_var", "format_var"):
            pane[name].trace_add("write", lambda *_a: self._slave_update_apply_state(window_id))
        self._slave_fill_rows(window)
        self._slave_update_format_state(window)
        self._slave_render_status(window)
        self._slave_update_apply_state(window_id)
        self._table_install_wheel_tags(frame, SLAVE_WHEEL_TAG)
        return frame

    def _slave_update_format_state(self, window):
        pane = self._slave_panes.get(window.window_id)
        if pane is not None:
            pane["format_combo"].configure(state="disabled" if window.bits else "readonly")

    def _slave_fill_rows(self, window):
        pane = self._slave_panes.get(window.window_id)
        if pane is None:
            return
        tree = pane["tree"]
        tree.delete(*tree.get_children())
        tree.configure(height=max(TABLE_PANE_MIN_ROWS, min(TABLE_PANE_MAX_ROWS, window.qty)))
        for index in range(window.qty):
            pdu = window.address + index
            tree.insert("", "end", iid=f"r{index}", tags=self._table_row_tags(index),
                        values=(pdu + window.base, window.names.get(pdu, ""), ""))
        self._slave_render_values(window)

    def _slave_render_values(self, window):
        pane = self._slave_panes.get(window.window_id)
        if pane is None:
            return
        tree = pane["tree"]
        values = self.slave_store.read(window.slave, window.table, window.address, window.qty)
        if window.bits:
            texts = [str(v) for v in values]
        else:
            texts = format_window_values(values, window.address, window.fmt,
                                         window.formats, window.scales)
        now = time.monotonic()
        generated = set()
        for address in window.generators:
            offset, size, _fmt = window.group_of_row(address - window.address)
            generated.update(range(offset, offset + size))
        for index, text in enumerate(texts[:window.qty]):
            # The zebra tag would win over "written", so a written row has only it.
            tags = (("written",) if window.highlight.get(index, 0) > now
                    else self._table_row_tags(index))
            if index in generated:
                tags += ("generated",)
            try:
                tree.item(f"r{index}", tags=tags)
                tree.set(f"r{index}", "value", text)
            except tk.TclError:
                pass

    def _slave_render_table(self, slave, table):
        for window in self.slave_windows.values():
            if (window.slave, window.table) == (slave, table):
                self._slave_render_values(window)

    def _slave_schedule_reflow(self, _event=None):
        if self._slave_reflow_after_id is not None:
            try:
                self.after_cancel(self._slave_reflow_after_id)
            except tk.TclError:
                pass
        self._slave_reflow_after_id = self.after(80, self._slave_reflow)

    def _slave_reflow(self):
        self._slave_reflow_after_id = None
        docked = [w for w in sorted(self.slave_windows.values(), key=lambda w: w.number)
                  if not w.popped]
        frames = [self._slave_panes[w.window_id]["frame"] for w in docked
                  if w.window_id in self._slave_panes]
        self._table_reflow(self.slave_canvas, self.slave_grid, self._slave_grid_item,
                           frames, self.slave_empty_label, "slave_panes")

    # -- window actions --------------------------------------------------------------
    def _slave_sync_areas(self):
        """Tell the store which addresses exist (what the windows show)."""
        self.slave_store.set_areas(w.area() for w in self.slave_windows.values())

    def slave_add_window(self, kwargs=None):
        if len(self.slave_windows) >= SLAVE_MAX_WINDOWS:
            messagebox.showwarning(
                self.tr("Slave"),
                self.trf("Máximo de {count} janelas.", count=SLAVE_MAX_WINDOWS),
            )
            return None
        window_id = self._slave_next_id
        self._slave_next_id += 1
        numbers = {w.number for w in self.slave_windows.values()}
        number = next(n for n in range(1, SLAVE_MAX_WINDOWS + 2) if n not in numbers)
        window = SlaveWindow(window_id, number, **(kwargs or {}))
        self.slave_windows[window_id] = window
        window.drop_invalid_generators()
        self._slave_sync_areas()
        self._slave_sync_generators()
        self._slave_build_pane(window, self.slave_grid)
        self._slave_reflow()
        self._slave_mark_changed()
        return window

    def slave_duplicate_window(self, window_id):
        window = self.slave_windows.get(window_id)
        if window is not None:
            self.slave_add_window(SlaveWindow.validated_kwargs(window.to_json()))

    def slave_close_window(self, window_id):
        window = self.slave_windows.pop(window_id, None)
        if window is None:
            return
        self._slave_sync_areas()
        self._slave_sync_generators()
        pane = self._slave_panes.pop(window_id, None)
        if pane is not None:
            top = pane.get("toplevel")
            try:
                (top if top is not None else pane["frame"]).destroy()
            except tk.TclError:
                pass
        self._slave_reflow()
        if not self.slave_windows:
            self.slave_workspace.forget()
        else:
            self._slave_mark_changed()

    def _slave_fields_changed(self, window, pane):
        try:
            return (
                pane["slave_var"].get().strip() != str(window.slave)
                or pane["table_var"].get() != table_choice_label(window.table)
                or pane["address_var"].get().strip() != str(window.address + window.base)
                or pane["qty_var"].get().strip() != str(window.qty)
                or FORMAT_KEYS_BY_LABEL.get(pane["format_var"].get()) != window.fmt
            )
        except tk.TclError:
            return False

    def _slave_update_apply_state(self, window_id):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.get(window_id)
        if window is None or pane is None or "apply_btn" not in pane:
            return
        style = "MBS.Primary.TButton" if self._slave_fields_changed(window, pane) else "TButton"
        try:
            pane["apply_btn"].configure(style=style)
        except tk.TclError:
            pass

    def slave_apply_window(self, window_id):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.get(window_id)
        if window is None or pane is None:
            return False
        try:
            base = window.base
            slave = parse_int_field(pane["slave_var"].get(), 1, 247,
                                    "O Slave ID tem de estar entre 1 e 247.")
            table = TABLE_KEYS_BY_LABEL.get(pane["table_var"].get(), window.table)
            address = parse_int_field(pane["address_var"].get(), base, 0xFFFF + base,
                                      "O endereço tem de estar entre 0 e 65535.") - base
            qty = parse_int_field(pane["qty_var"].get(), 1, SLAVE_MAX_QTY,
                                  "A quantidade tem de estar entre 1 e 2000.")
            validate_area(slave, table, address, qty)
        except ValueError as exc:
            messagebox.showerror(self.tr("Janela inválida"), self.tr(str(exc)))
            return False
        fmt = FORMAT_KEYS_BY_LABEL.get(pane["format_var"].get(), DEFAULT_FORMAT)
        changed_area = (slave, table, address, qty) != window.area()
        changed = changed_area or fmt != window.fmt
        window.slave, window.table, window.address, window.qty = slave, table, address, qty
        window.fmt = fmt
        if changed_area:
            window.reset_counters()
            window.highlight = {}
            window.drop_invalid_generators()
            self._slave_sync_areas()
            self._slave_sync_generators()
        self._slave_fill_rows(window)
        self._slave_update_format_state(window)
        self._slave_render_status(window)
        self._slave_update_apply_state(window_id)
        if changed:
            self._slave_mark_changed()
        return True

    def slave_toggle_popout(self, window_id):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.pop(window_id, None)
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
            top.minsize(TABLE_PANE_MIN_WIDTH, 300)
            top.columnconfigure(0, weight=1)
            top.rowconfigure(0, weight=1)
            top.protocol("WM_DELETE_WINDOW", lambda: self.slave_toggle_popout(window_id))
            frame = self._slave_build_pane(window, top)
            frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
            self._slave_panes[window_id]["toplevel"] = top
            self._table_apply_toplevel_palette(top)
        else:
            self._slave_build_pane(window, self.slave_grid)
        self._slave_render_status(window)
        self._slave_reflow()

    def slave_rename_window(self, window_id, name=None):
        window = self.slave_windows.get(window_id)
        if window is None:
            return
        if name is None:
            name = self._table_ask_text(
                self.tr("Renomear janela"),
                self.tr("Nome da janela (vazio = nome por defeito)"),
                self._slave_window_name(window),
            )
            if name is None:
                return
        name = name.strip()[:TABLE_MAX_TITLE_LENGTH]
        if name == self.trf("Janela {number}", number=window.number):
            name = ""
        window.title = name
        self._slave_render_status(window)
        self._slave_mark_changed()

    # -- values and names ---------------------------------------------------------------
    def _slave_on_double_click(self, window_id, event):
        pane = self._slave_panes.get(window_id)
        if pane is None:
            return "break"
        tree = pane["tree"]
        row = tree.identify_row(event.y)
        if not row:
            return "break"
        tree.selection_set(row)
        if tree.identify_column(event.x) == "#2":
            self._slave_edit_name(window_id, row)
        else:
            self._slave_edit_value(window_id)
        return "break"

    def _slave_edit_name(self, window_id, row):
        window = self.slave_windows.get(window_id)
        if window is None:
            return
        pdu = window.address + int(row[1:])
        name = self._table_ask_text(
            self.tr("Nome"), self.trf("Nome do endereço {address}", address=pdu + window.base),
            window.names.get(pdu, ""),
        )
        if name is None:
            return
        name = name.strip()
        if name:
            window.names[pdu] = name
        else:
            window.names.pop(pdu, None)
        pane = self._slave_panes.get(window_id)
        if pane is not None:
            pane["tree"].set(row, "name", name)
        self._slave_mark_changed()

    def slave_set_value(self, window, row, text):
        """Store the value typed for *row* (first register of its value).

        Coils / discrete inputs accept 0 or 1; registers use the format (and
        scale) of the value. Raises ValueError (PT canonical message).
        """
        address = window.address + row
        if window.bits:
            values = [encode_coil_value(text)]
        else:
            offset, size, fmt = window.group_of_row(row)
            if fmt is None:
                raise ValueError("Este endereço não tem um valor completo no formato atual.")
            address = window.address + offset
            scale = window.scales.get(address)
            if scale is not None and fmt not in ("hex16", "bin16"):
                text = raw_text_for_scaled(text, scale, fmt)
            values = encode_register_value(text, fmt)
        self.slave_store.write(window.slave, window.table, address, values)
        self._slave_render_table(window.slave, window.table)
        return values

    def _slave_edit_value(self, window_id):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.get(window_id)
        if window is None or pane is None:
            return
        selection = pane["tree"].selection()
        if not selection:
            return
        row = int(selection[0][1:])
        if window.bits:
            # A bit is simply toggled.
            current = self.slave_store.read(window.slave, window.table, window.address + row, 1)
            self.slave_set_value(window, row, "0" if current[0] else "1")
            return
        offset, _size, fmt = window.group_of_row(row)
        if fmt is None:
            messagebox.showinfo(self.tr("Valor"), self.tr(
                "Este endereço não tem um valor completo no formato atual."))
            return
        current = pane["tree"].set(f"r{offset}", "value")
        scale = window.scales.get(window.address + offset)
        if scale is not None and fmt in ("hex16", "bin16"):
            scale = None
        if scale is not None and scale.get("unit"):
            current = current.rsplit(" ", 1)[0]

        dialog, body = self._table_dialog(self.tr("Valor"))
        format_text = FORMAT_LABELS[fmt]
        if scale is not None:
            format_text += " · " + self.trf("valores em unidades da escala {unit}",
                                            unit=scale.get("unit") or "")
        ttk.Label(body, text=self.trf("Valor do endereço {address} ({fmt})",
                                      address=window.address + offset + window.base,
                                      fmt=format_text)).grid(row=0, column=0, sticky="w")
        value_var = tk.StringVar(value=current)
        entry = ttk.Entry(body, textvariable=value_var, width=30)
        entry.grid(row=1, column=0, sticky="w", pady=(4, 4))
        message_var = tk.StringVar()
        ttk.Label(body, textvariable=message_var, style="MBS.Master.Error.TLabel").grid(
            row=2, column=0, sticky="w")

        def accept(_event=None):
            try:
                self.slave_set_value(window, offset, value_var.get())
            except ValueError as exc:
                message_var.set(self.tr(str(exc)))
                return
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=self.tr("Guardar"), command=accept,
                   style="MBS.Primary.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Cancelar"), command=dialog.destroy).grid(row=0, column=1)
        entry.bind("<Return>", accept)
        entry.bind("<Escape>", lambda _e: dialog.destroy())
        entry.focus_set()
        entry.select_range(0, "end")
        dialog.grab_set()

    # -- right-click menu ----------------------------------------------------------------
    def _slave_show_row_menu(self, window_id, event):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.get(window_id)
        if window is None or pane is None:
            return "break"
        tree = pane["tree"]
        row = tree.identify_row(event.y)
        if row and row not in tree.selection():
            tree.selection_set(row)
        self._table_fill_row_menu(
            self._slave_row_menu, pane, window, not window.bits,
            set_format=lambda fmt: self.slave_set_row_format(window_id, fmt),
            edit_scale=lambda: self.slave_edit_scale(window_id),
            remove_scale=lambda: self.slave_remove_scale(window_id),
            copy=lambda: self._table_copy_rows(self._slave_panes.get(window_id)),
            set_base=lambda base: self.slave_set_base(window_id, base),
            extra=(("Valor automático…", lambda: self.slave_edit_generator(window_id)),
                   ("Parar valor automático", lambda: self.slave_remove_generator(window_id))),
        )
        self._slave_apply_menu_palette()
        self._table_popup(self._slave_row_menu, event)
        return "break"

    def _slave_selected_rows(self, window_id):
        return self._table_selected_rows(self._slave_panes.get(window_id))

    def slave_set_row_format(self, window_id, fmt):
        window = self.slave_windows.get(window_id)
        if window is None:
            return False
        try:
            apply_format_to_rows(window, self._slave_selected_rows(window_id), fmt)
        except ValueError as exc:
            messagebox.showwarning(self.tr("Formato"),
                                   self.trf(str(exc), size=FORMAT_SIZES.get(fmt, 1)))
            return False
        self._slave_render_values(window)
        self._slave_mark_changed()
        return True

    def slave_edit_scale(self, window_id):
        window = self.slave_windows.get(window_id)
        if window is None:
            return False
        starts = self._table_selected_group_starts(window, self._slave_panes.get(window_id))
        if not starts:
            messagebox.showwarning(self.tr("Escala"), self.tr("Seleciona pelo menos um endereço."))
            return False
        if not self._table_ask_scale(window, starts):
            return False
        self._slave_render_values(window)
        self._slave_mark_changed()
        return True

    def slave_remove_scale(self, window_id):
        window = self.slave_windows.get(window_id)
        if window is None:
            return False
        removed = False
        for address in self._table_selected_group_starts(window, self._slave_panes.get(window_id)):
            removed = window.scales.pop(address, None) is not None or removed
        if removed:
            self._slave_render_values(window)
            self._slave_mark_changed()
        return removed

    def slave_set_base(self, window_id, base):
        window = self.slave_windows.get(window_id)
        pane = self._slave_panes.get(window_id)
        if window is None or pane is None or window.base == base:
            return
        window.base = base
        pane["address_var"].set(str(window.address + window.base))
        self._slave_fill_rows(window)
        self._slave_render_status(window)
        self._slave_update_apply_state(window_id)
        self._slave_mark_changed()

    # -- automatic values -------------------------------------------------------------------
    def _slave_sync_generators(self):
        """Rebuild the running automatic values from the windows' settings."""
        now = time.monotonic()
        running = {}
        for window in self.slave_windows.values():
            for address, config in window.generators.items():
                key = (window.window_id, address)
                current = self._slave_generators.get(key)
                if current is not None and current[0].config == config:
                    running[key] = current
                else:
                    running[key] = (ValueGenerator(config), now)
        self._slave_generators = running
        if running and self._slave_generator_after_id is None:
            self._slave_generator_after_id = self.after(
                SLAVE_GENERATOR_TICK_MS, self._slave_generate)

    def slave_generator_registers(self, window, address, value):
        """Registers (or bit) for an automatic *value* at *address*; None if it does not fit."""
        if window.bits:
            return [1 if value else 0]
        offset, _size, fmt = window.group_of_row(address - window.address)
        if fmt is None or window.address + offset != address:
            return None
        scale = window.scales.get(address)
        if scale is not None and fmt not in ("hex16", "bin16"):
            try:
                value = unscale_value(value, scale)
            except ValueError:
                return None
        if fmt.split("_")[0].startswith("float"):
            text, fmt_used = repr(float(value)), fmt
        else:
            text = str(int(round(value)))
            fmt_used = "uint16" if fmt in ("hex16", "bin16") else fmt
        try:
            return encode_register_value(text, fmt_used)
        except ValueError:
            return None

    def _slave_generate(self):
        """Write the current automatic values into the store and show them."""
        self._slave_generator_after_id = None
        if not self._slave_generators or getattr(self, "_closing", False):
            return
        now = time.monotonic()
        changed = set()
        for (window_id, address), (generator, started) in list(self._slave_generators.items()):
            window = self.slave_windows.get(window_id)
            if window is None:
                continue
            registers = self.slave_generator_registers(window, address,
                                                       generator.value(now - started))
            if registers is None:
                continue
            current = self.slave_store.read(window.slave, window.table, address, len(registers))
            if current != registers:
                self.slave_store.write(window.slave, window.table, address, registers)
                changed.add((window.slave, window.table))
        for slave, table in changed:
            self._slave_render_table(slave, table)
        try:
            self._slave_generator_after_id = self.after(SLAVE_GENERATOR_TICK_MS,
                                                        self._slave_generate)
        except tk.TclError:
            pass

    def slave_set_generator(self, window_id, starts, config):
        """Set (config) or remove (None) the automatic value of the given addresses."""
        window = self.slave_windows.get(window_id)
        if window is None:
            return
        for address in starts:
            if config is None:
                window.generators.pop(address, None)
            else:
                window.generators[address] = dict(config)
        self._slave_sync_generators()
        self._slave_render_values(window)
        self._slave_mark_changed()

    def slave_remove_generator(self, window_id):
        window = self.slave_windows.get(window_id)
        if window is None:
            return False
        starts = [a for a in self._table_selected_group_starts(
            window, self._slave_panes.get(window_id)) if a in window.generators]
        if starts:
            self.slave_set_generator(window_id, starts, None)
        return bool(starts)

    def slave_edit_generator(self, window_id):
        """Dialog: automatic value for the selected values."""
        window = self.slave_windows.get(window_id)
        if window is None:
            return
        starts = self._table_selected_group_starts(window, self._slave_panes.get(window_id))
        if not starts:
            messagebox.showwarning(self.tr("Valor automático"),
                                   self.tr("Seleciona pelo menos um endereço."))
            return
        kinds = BIT_GENERATORS if window.bits else REGISTER_GENERATORS
        current = window.generators.get(starts[0]) or {
            "kind": kinds[0], "min": 0, "max": 100, "step": 1, "period_s": 1}
        labels = [self.tr(GENERATOR_LABELS[k]) for k in kinds]

        dialog, body = self._table_dialog(self.tr("Valor automático"))
        ttk.Label(body, text=self.trf("Valor automático de {count} valor(es) selecionado(s):",
                                      count=len(starts))).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        def number_text(value):
            return f"{value:g}"

        kind_var = tk.StringVar(value=labels[kinds.index(current["kind"])]
                                if current["kind"] in kinds else labels[0])
        variables = {
            "min": tk.StringVar(value=number_text(current.get("min", 0))),
            "max": tk.StringVar(value=number_text(current.get("max", 100))),
            "step": tk.StringVar(value=number_text(current.get("step", 1))),
            "period_s": tk.StringVar(value=number_text(current.get("period_s", 1))),
        }
        ttk.Label(body, text=self.tr("Tipo")).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Combobox(body, values=labels, textvariable=kind_var, width=16,
                     state="readonly").grid(row=1, column=1, columnspan=3, sticky="w", pady=2)
        entries = {}
        for row, column, caption, key in ((2, 0, "Mínimo", "min"), (2, 2, "Máximo", "max"),
                                          (3, 0, "Passo", "step"), (3, 2, "Período (s)", "period_s")):
            ttk.Label(body, text=self.tr(caption)).grid(row=row, column=column, sticky="w",
                                                        padx=(0, 6), pady=2)
            entries[key] = ttk.Entry(body, width=10, textvariable=variables[key])
            entries[key].grid(row=row, column=column + 1, sticky="w", padx=(0, 14), pady=2)
        help_var = tk.StringVar()
        ttk.Label(body, textvariable=help_var).grid(row=4, column=0, columnspan=4, sticky="w",
                                                    pady=(6, 2))
        message_var = tk.StringVar()
        ttk.Label(body, textvariable=message_var, style="MBS.Master.Error.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w")
        help_texts = {
            "counter": "Soma o passo em cada período; depois do máximo volta ao mínimo.",
            "ramp": "Sobe do mínimo ao máximo durante o período e recomeça.",
            "sine": "Oscila entre o mínimo e o máximo; o período é uma volta completa.",
            "random": "Um valor ao acaso entre o mínimo e o máximo em cada período.",
            "toggle": "Alterna entre 0 e 1 em cada período.",
        }
        if window.bits:
            help_texts["random"] = "0 ou 1 ao acaso em cada período."

        def selected_kind():
            return kinds[labels.index(kind_var.get())]

        def refresh(*_args):
            kind = selected_kind()
            for key in ("min", "max"):
                entries[key].configure(state="disabled" if window.bits else "normal")
            entries["step"].configure(state="normal" if kind == "counter" else "disabled")
            help_var.set(self.tr(help_texts[kind]))

        kind_var.trace_add("write", refresh)
        refresh()

        def accept(_event=None):
            data = {key: var.get() for key, var in variables.items()}
            data["kind"] = selected_kind()
            try:
                config = validate_generator(data, window.bits)
            except ValueError as exc:
                message_var.set(self.tr(str(exc)))
                return
            self.slave_set_generator(window_id, starts, config)
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=4, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=self.tr("Aplicar"), command=accept,
                   style="MBS.Primary.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Cancelar"), command=dialog.destroy).grid(row=0, column=1)
        dialog.bind("<Return>", accept)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.grab_set()

    # -- opening windows from the Sniffer / Master ------------------------------------------
    def slave_open_definition(self, definition, port="", baud="", parity="", stopbits=""):
        """Add a Slave window and show the Slave tab.

        The serial settings (and port) are copied to the Slave connection only
        when it is not listening and they are valid.
        """
        if not self.slave_active:
            if str(baud) in [str(b) for b in DISCOVERY_BAUD_RATES]:
                self.slave_baud_var.set(str(baud))
            if parity in SERIAL_PARITIES:
                self.slave_parity_var.set(parity)
            if str(stopbits) in SERIAL_STOP_BITS:
                self.slave_stop_var.set(str(stopbits))
            if port and port in tuple(self.slave_port_combo["values"]):
                self.slave_port_var.set(port)
        window = self.slave_add_window(definition)
        try:
            self.main_notebook.select(self.slave_page)
        except tk.TclError:
            pass
        return window

    def slave_open_from_record(self, record):
        definition = slave_definition_from_record(record)
        if definition is None:
            messagebox.showinfo(
                self.tr("Abrir no Slave"),
                self.tr("Esta trama não tem um pedido FC01–FC06/FC15/FC16 com endereço "
                        "conhecido."),
            )
            return None
        port = "" if getattr(self, "capture_active", False) else self.port_a_var.get().strip()
        return self.slave_open_definition(
            definition, port=port, baud=self.baud_var.get(),
            parity=self.parity_var.get(), stopbits=self.stop_var.get(),
        )

    def slave_open_from_master(self, master_window):
        """Simulate the data area of a Master window (same names, formats and scales)."""
        definition = {
            "slave": master_window.slave, "table": FC_TABLES[master_window.fc],
            "address": master_window.address, "qty": master_window.qty,
            "base": master_window.base, "fmt": master_window.fmt,
            "title": master_window.title, "names": dict(master_window.names),
            "formats": dict(master_window.formats),
            "scales": {a: dict(s) for a, s in master_window.scales.items()},
        }
        return self.slave_open_definition(
            definition, baud=self.master_baud_var.get(),
            parity=self.master_parity_var.get(), stopbits=self.master_stop_var.get(),
        )

    # -- fault simulation -----------------------------------------------------------------
    def slave_set_fault(self, slave, fault):
        """Set (or clear, with None / an inactive fault) the fault of a Slave ID."""
        if fault_active(fault):
            self.slave_faults[slave] = dict(fault)
        else:
            self.slave_faults.pop(slave, None)
        self.slave_store.set_fault(slave, self.slave_faults.get(slave))
        for window in self.slave_windows.values():
            if window.slave == slave:
                self._slave_render_status(window)

    def slave_edit_faults(self, window_id):
        window = self.slave_windows.get(window_id)
        if window is None:
            return
        slave = window.slave
        current = self.slave_faults.get(slave) or default_fault()
        dialog, body = self._table_dialog(self.trf("Falhas do Slave {slave}", slave=slave))
        ttk.Label(body, text=self.trf(
            "Simulação de falhas do Slave {slave} (aplica-se a todas as janelas deste ID).",
            slave=slave)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        delay_var = tk.StringVar(value=str(current["delay_ms"]))
        silent_var = tk.BooleanVar(value=current["no_response"])
        exception_labels = [self.tr("Nenhuma")] + [
            f"{code:02X} {MODBUS_EXCEPTION_CODES.get(code, ('', ''))[0]}"
            for code in FAULT_EXCEPTION_CODES]
        exception_var = tk.StringVar(value=exception_labels[
            (FAULT_EXCEPTION_CODES.index(current["exception"]) + 1)
            if current["exception"] in FAULT_EXCEPTION_CODES else 0])
        crc_var = tk.BooleanVar(value=current["bad_crc"])
        probability_var = tk.StringVar(value=str(current["probability"]))

        ttk.Label(body, text=self.tr("Atraso na resposta (ms)")).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Spinbox(body, from_=0, to=SLAVE_FAULT_MAX_DELAY_MS, increment=50, width=8,
                    textvariable=delay_var).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Checkbutton(body, text=self.tr("Não responder"), variable=silent_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(body, text=self.tr("Responder com Exception")).grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Combobox(body, values=exception_labels, textvariable=exception_var, width=28,
                     state="readonly").grid(row=3, column=1, sticky="w", pady=2)
        ttk.Checkbutton(body, text=self.tr("CRC errado nas respostas"), variable=crc_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(body, text=self.tr("Probabilidade (%)")).grid(
            row=5, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Spinbox(body, from_=1, to=100, increment=5, width=8,
                    textvariable=probability_var).grid(row=5, column=1, sticky="w", pady=2)
        ttk.Label(body, text=self.tr(
            "A probabilidade decide, em cada pedido, se a falha acontece.")).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(6, 2))
        message_var = tk.StringVar()
        ttk.Label(body, textvariable=message_var, style="MBS.Master.Error.TLabel").grid(
            row=7, column=0, columnspan=2, sticky="w")

        def accept(_event=None):
            index = exception_labels.index(exception_var.get())
            try:
                fault = validate_fault({
                    "delay_ms": delay_var.get(), "no_response": silent_var.get(),
                    "exception": FAULT_EXCEPTION_CODES[index - 1] if index else 0,
                    "bad_crc": crc_var.get(), "probability": probability_var.get(),
                })
            except ValueError as exc:
                message_var.set(self.tr(str(exc)))
                return
            self.slave_set_fault(slave, fault)
            self._slave_mark_changed()
            dialog.destroy()

        def clear():
            self.slave_set_fault(slave, None)
            self._slave_mark_changed()
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=self.tr("Aplicar"), command=accept,
                   style="MBS.Primary.TButton").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Sem falhas"), command=clear).grid(
            row=0, column=1, padx=(0, 6))
        ttk.Button(buttons, text=self.tr("Cancelar"), command=dialog.destroy).grid(
            row=0, column=2)
        dialog.bind("<Return>", accept)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.grab_set()

    # -- connection --------------------------------------------------------------------
    def slave_connect(self):
        if self.slave_active:
            return
        if self.busy:
            messagebox.showwarning(
                self.tr("Slave"),
                self.tr("Para a captura, a pesquisa ou o Master em curso antes de ligar o Slave."),
            )
            return
        if not self.slave_safety_var.get():
            messagebox.showwarning(
                self.tr("Slave"),
                self.tr("Confirma primeiro que nenhum equipamento no barramento usa os "
                        "Slave IDs simulados."),
            )
            return
        serial, _ = self.get_serial_modules()
        if serial is None:
            messagebox.showerror(self.tr("pyserial em falta"), self.tr("pyserial não está instalado."))
            return
        port = self.slave_port_var.get().strip()
        if not port:
            messagebox.showerror(self.tr("Configuração inválida"),
                                 self.tr("Seleciona uma porta COM."))
            return
        for window_id in list(self.slave_windows):
            if not self.slave_apply_window(window_id):
                return
        if not self.slave_windows:
            messagebox.showwarning(self.tr("Slave"),
                                   self.tr("Cria primeiro uma janela com o Slave a simular."))
            return
        baud, parity, stopbits = (int(self.slave_baud_var.get()), self.slave_parity_var.get(),
                                  self.slave_stop_var.get())
        try:
            ser = self.open_discovery_serial_port(serial, port, baud, parity, stopbits)
        except Exception as exc:
            messagebox.showerror(
                self.tr("Slave"),
                self.trf("Não foi possível abrir {port}: {error}",
                         port=port, error=f"{type(exc).__name__}: {exc}"),
            )
            return

        self.slave_serial = ser
        self.slave_engine = SlaveEngine(
            ser, self.event_queue, self.slave_store, baud=baud, parity=parity,
            stopbits=stopbits, serial_module=serial,
            reopen=lambda: self.open_discovery_serial_port(serial, port, baud, parity, stopbits),
        )
        self._slave_reset_stats()
        self._slave_render_stats()
        for window in self.slave_windows.values():
            window.reset_counters()
            self._slave_render_status(window)
        self.slave_active = True
        self.busy = True
        self._slave_lock_other_features(True)
        self.slave_status_var.set(self.tr("A abrir a porta…"))
        self.slave_engine.start()

    def slave_disconnect(self):
        if self.slave_engine is None:
            return
        self.slave_status_var.set(self.tr("A desligar…"))
        self.slave_disconnect_btn.configure(state="disabled")
        self.slave_engine.stop()

    def _slave_lock_other_features(self, locked):
        """While the Slave listens, nothing else may use a serial port."""
        state = "disabled" if locked else "normal"
        self.slave_connect_btn.configure(state=state)
        self.slave_disconnect_btn.configure(state="normal" if locked else "disabled")
        for widget in self._slave_setting_widgets:
            try:
                widget.configure(state="disabled" if locked else "readonly")
            except tk.TclError:
                pass
        self.slave_refresh_btn.configure(state=state)
        for name in ("start_btn", "restart_btn", "master_connect_btn"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=state)
        self.set_sniffer_refresh_state(state)
        self.set_simulation_button_state(state)
        self.update_discovery_start_state()

    def _slave_finish_session(self, payload):
        if not self.slave_active:
            return  # already finished (a late slave_stopped event)
        engine = self.slave_engine
        self.slave_engine = None
        if engine is not None:
            engine.stop(join_timeout=0.5)
            self.slave_serial = engine.ser
        if self.slave_serial is not None:
            try:
                self.slave_serial.close()
            except Exception:
                pass
        self.slave_serial = None
        self.slave_active = False
        self.busy = False
        self._slave_lock_other_features(False)
        self.slave_status_var.set(self.tr("Desligado"))
        error = (payload or {}).get("error")
        if error:
            messagebox.showerror(self.tr("Slave"),
                                 self.trf("Erro na porta série: {error}", error=error))

    # -- worker events ---------------------------------------------------------------
    def handle_slave_event(self, event, payload):
        if event == "slave_ready":
            self.slave_status_var.set(self.tr("● A responder"))
        elif event == "slave_reconnecting":
            self.slave_status_var.set(self.trf(
                "A religar a {port}… (porta falhou: {error})",
                port=self.slave_port_var.get(), error=(payload or {}).get("error", ""),
            ))
        elif event == "slave_reconnected":
            engine = self.slave_engine
            if engine is not None:
                self.slave_serial = engine.ser
            self.slave_status_var.set(self.tr("● A responder"))
        elif event == "slave_stopped":
            self._slave_finish_session(payload)
        elif event == "slave_request":
            self._slave_apply_request(payload)

    def slave_request_text(self, info):
        """Short description of a request: "FC03 @ 0 × 10 → Exception 02"."""
        text = f"FC{info['fc']:02d}"
        if info.get("address") is not None:
            text += f" @ {info['address']}"
            if info.get("qty"):
                text += f" × {info['qty']}"
        status = info.get("status")
        if status == "exception":
            code = info.get("exception_code") or 0
            text += f" → Exception {code:02X}"
        elif status == "no_response":
            text += " → " + self.tr("sem resposta")
        elif status == "broadcast":
            text += " → broadcast"
        if info.get("fault"):
            text += " ⚠"
        return text

    def _slave_apply_request(self, info):
        stats = self.slave_stats
        status = info.get("status")
        if status == "ignored":
            stats["others"] += 1
            self._slave_render_stats()
            return
        stats["requests"] += 1
        if status == "broadcast":
            stats["broadcasts"] += 1
        elif status == "exception":
            stats["exceptions"] += 1
            stats["responses"] += 1
        elif status == "ok":
            stats["responses"] += 1
        self._slave_render_stats()

        stamp = time.strftime("%H:%M:%S", time.localtime(info.get("time", time.time())))
        text = f"{self.slave_request_text(info)}  {stamp}"
        address, qty = info.get("address"), info.get("qty") or 1
        targets = {(slave, table) for slave, table, _a, _q in info.get("written", [])}
        if status != "broadcast":
            targets.add((info.get("slave"), info.get("table")))
        until = time.monotonic() + SLAVE_HIGHLIGHT_SECONDS
        touched = False
        for window in self.slave_windows.values():
            if (window.slave, window.table) not in targets or address is None:
                continue
            rows = window.overlap(address, qty)
            if rows is None:
                continue
            window.requests += 1
            if status == "exception":
                window.exceptions += 1
            window.last = text
            for slave, table, w_address, w_qty in info.get("written", []):
                if (slave, table) == (window.slave, window.table):
                    written = window.overlap(w_address, w_qty)
                    if written is not None:
                        for row in range(*written):
                            window.highlight[row] = until
                        touched = True
            self._slave_render_status(window)
            if info.get("written"):
                self._slave_render_values(window)
        if touched:
            self._slave_schedule_tick()

    def _slave_schedule_tick(self):
        if self._slave_tick_after_id is None:
            self._slave_tick_after_id = self.after(250, self._slave_tick)

    def _slave_tick(self):
        """Remove expired write highlights."""
        self._slave_tick_after_id = None
        now = time.monotonic()
        pending = False
        for window in self.slave_windows.values():
            expired = [row for row, until in window.highlight.items() if until <= now]
            for row in expired:
                del window.highlight[row]
            if expired:
                self._slave_render_values(window)
            pending = pending or bool(window.highlight)
        if pending:
            self._slave_schedule_tick()

    # -- workspace -------------------------------------------------------------------
    def slave_workspace_data(self):
        """Configuration only: the register values are not saved."""
        used = {w.slave for w in self.slave_windows.values()}
        return {
            "format": SLAVE_WORKSPACE_FORMAT,
            "version": SLAVE_WORKSPACE_VERSION,
            "connection": {
                "port": self.slave_port_var.get(),
                "baud": self.slave_baud_var.get(),
                "parity": self.slave_parity_var.get(),
                "stop_bits": self.slave_stop_var.get(),
            },
            "windows": [w.to_json() for w in sorted(self.slave_windows.values(),
                                                     key=lambda w: w.number)],
            "faults": {str(slave): fault for slave, fault in sorted(self.slave_faults.items())
                       if slave in used},
        }

    def _slave_mark_changed(self):
        self.slave_workspace.mark_changed()

    def _slave_build_workspace_menu(self):
        self.slave_workspace.fill_menu(self.slave_workspace_menu)
        self._slave_apply_menu_palette()

    def slave_save_workspace(self, name=None):
        return self.slave_workspace.save(name)

    def slave_delete_workspace(self, name, confirm=True):
        return self.slave_workspace.delete(name, confirm)

    def slave_open_workspace(self, name, quiet=False):
        """Replace the windows and faults with a saved workspace; values restart at 0."""
        return self.slave_workspace.open(name, quiet)

    def _slave_load_workspace_data(self, data):
        """Replace windows and faults with those of *data*; returns the invalid count."""
        entries, skipped = [], 0
        for item in data.get("windows", [])[:SLAVE_MAX_WINDOWS]:
            try:
                entries.append(SlaveWindow.validated_kwargs(item))
            except (ValueError, TypeError):
                skipped += 1
        for window_id in list(self.slave_windows):
            self.slave_close_window(window_id)
        self.slave_store.clear_values()
        self.slave_store.clear_faults()
        self.slave_faults = {}
        connection = data.get("connection", {})
        if isinstance(connection, dict) and not self.slave_active:
            if str(connection.get("baud")) in [str(b) for b in DISCOVERY_BAUD_RATES]:
                self.slave_baud_var.set(str(connection["baud"]))
            if connection.get("parity") in SERIAL_PARITIES:
                self.slave_parity_var.set(connection["parity"])
            if str(connection.get("stop_bits")) in SERIAL_STOP_BITS:
                self.slave_stop_var.set(str(connection["stop_bits"]))
            if connection.get("port") in tuple(self.slave_port_combo["values"]):
                self.slave_port_var.set(connection["port"])
        faults = data.get("faults", {})
        for key, item in (faults.items() if isinstance(faults, dict) else ()):
            try:
                if str(key).isdigit() and 1 <= int(key) <= 247:
                    self.slave_set_fault(int(key), validate_fault(item))
            except ValueError:
                continue
        for kwargs in entries:
            self.slave_add_window(kwargs)
        return skipped

    def slave_confirm_close(self):
        """Ask to save a changed Slave workspace; False cancels closing."""
        workspace = getattr(self, "slave_workspace", None)
        return workspace is None or workspace.confirm_close()

    # -- language / palette / shutdown -----------------------------------------------
    def slave_apply_language(self):
        if not hasattr(self, "slave_windows"):
            return
        self.slave_workspace.update_label()
        self._slave_render_stats()
        for window in self.slave_windows.values():
            pane = self._slave_panes.get(window.window_id)
            if pane is not None:
                self._table_translate_headings(pane)
                self._slave_render_status(window)
        if not self.slave_active:
            self.slave_status_var.set(self.tr("Desligado"))
        elif self.slave_engine is not None:
            self.slave_status_var.set(self.tr("● A responder"))

    def _slave_apply_menu_palette(self):
        self._table_apply_menus_palette(getattr(self, "slave_workspace_menu", None),
                                        getattr(self, "_slave_row_menu", None))

    def slave_apply_palette(self, dark):
        self._slave_apply_menu_palette()
        canvas = getattr(self, "slave_canvas", None)
        if canvas is not None:
            canvas.configure(background=theme_colors(self, dark)["root"])
        for pane in getattr(self, "_slave_panes", {}).values():
            if pane.get("toplevel") is not None:
                self._table_apply_toplevel_palette(pane["toplevel"])
            self._table_configure_tree_tags(pane["tree"])
        button = getattr(self, "slave_refresh_btn", None)
        if button is not None:
            button.set_dark_mode(dark)

    def slave_shutdown(self):
        self._slave_generators = {}
        engine = getattr(self, "slave_engine", None)
        if engine is not None:
            engine.stop(join_timeout=0.8)
            self.slave_serial = engine.ser
        ser = getattr(self, "slave_serial", None)
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        self.slave_engine = None
        self.slave_serial = None
