#!/usr/bin/env python3
"""Modbus TCP Client and Server tabs.

Both tabs are second instances of the serial tabs, run on ``TabInstance``:
``ClientTab`` is the Master tab over ``mb_tcp.ClientEngine`` and
``ServerTab`` is the Slave tab over ``mb_tcp.ServerEngine``. Windows,
formats, scales, names, writes, faults, automatic values and workspaces are
the same code as in the serial tabs; this module only replaces the
connection bar, the device of each Client window and the engines. The TCP
tabs do not use a serial port, so they run independently of the Sniffer,
the Finder, the Master and the Slave.
"""

import ipaddress
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from mb_config import (
    CLIENT_WORKSPACE_FORMAT,
    MASTER_DEFAULT_DELAY_MS,
    MASTER_DEFAULT_RESPONSE_TIMEOUT_MS,
    MASTER_MAX_DELAY_MS,
    MASTER_MAX_RESPONSE_TIMEOUT_MS,
    MASTER_MIN_DELAY_MS,
    MASTER_MIN_RESPONSE_TIMEOUT_MS,
    SERVER_DEFAULT_BIND,
    SERVER_WORKSPACE_FORMAT,
    TCP_DEFAULT_PORT,
    get_client_workspaces_folder,
    get_server_workspaces_folder,
)
from mb_master import validate_read_definition
from mb_master_ui import MasterMixin, MasterWindow
from mb_slave_ui import SlaveMixin
from mb_table_ui import TabInstance, parse_int_field
from mb_tcp import (
    ClientEngine,
    ClientPollDefinition,
    ServerEngine,
    list_ipv4_interfaces,
    validate_host,
    validate_tcp_port,
)
from mb_widgets import RefreshButton

LOCALHOST = "127.0.0.1"
ALL_INTERFACES = "0.0.0.0"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientWindow(MasterWindow):
    """Poll window of the Client: a Master window plus the device (host:port).

    ``slave`` holds the Unit ID, 0–255 in Modbus TCP.
    """

    def __init__(self, window_id, number, host=LOCALHOST, port=TCP_DEFAULT_PORT, **kwargs):
        super().__init__(window_id, number, **kwargs)
        self.host = host
        self.port = port

    def definition(self):
        return ClientPollDefinition(self.window_id, self.slave, self.fc, self.address, self.qty,
                                    self.scan_ms, self.enabled, host=self.host, port=self.port)

    def to_json(self):
        data = super().to_json()
        data.update(host=self.host, port=self.port)
        return data

    @staticmethod
    def validated_kwargs(data):
        if not isinstance(data, dict):
            raise ValueError("Janela inválida.")
        unit = int(data.get("slave", 1))
        if not 0 <= unit <= 255:
            raise ValueError("O Unit ID tem de estar entre 0 e 255.")
        kwargs = MasterWindow.validated_kwargs(dict(data, slave=1))
        kwargs.update(slave=unit, host=validate_host(data.get("host", LOCALHOST)),
                      port=validate_tcp_port(data.get("port", TCP_DEFAULT_PORT)))
        return kwargs


class ClientTab(MasterMixin, TabInstance):
    """Modbus TCP Client tab: the Master tab with one TCP device per window."""

    _master_tab_name = "Client"
    _master_settings_key = "client"
    _master_page_attr = "client_page"
    _master_wheel_tag = "MBToolkit.ClientWheel"
    _master_window_class = ClientWindow
    _master_ws_folder = staticmethod(get_client_workspaces_folder)
    _master_ws_formats = (CLIENT_WORKSPACE_FORMAT,)
    _master_ws_close_question = "Guardar alterações ao workspace do Client \"{name}\"?"
    _master_id_label = "Unit ID"
    _master_id_range = (0, 255)
    _master_id_message = "O Unit ID tem de estar entre 0 e 255."
    _master_write_id_label = "Unit ID"
    _master_write_id_range = (0, 255)
    _master_connect_first = "Liga primeiro o Client."
    _master_open_in_slave = ("Abrir no Server", "open_in_server")

    def __init__(self, app):
        super().__init__(app)
        # The TCP tabs never take the application's serial busy lock.
        self.busy = False

    # -- connection bar ------------------------------------------------------------
    def _master_build_connection(self, page, saved):
        connection = ttk.LabelFrame(
            page, text="Ligação — o Client liga-se a equipamentos Modbus TCP")
        connection.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row = ttk.Frame(connection)
        row.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.master_timeout_var = tk.StringVar(
            value=str(saved.get("response_timeout_ms", MASTER_DEFAULT_RESPONSE_TIMEOUT_MS)))
        self.master_delay_var = tk.StringVar(
            value=str(saved.get("delay_ms", MASTER_DEFAULT_DELAY_MS)))
        fields = (
            ("Timeout resposta (ms)", ttk.Spinbox(
                row, textvariable=self.master_timeout_var, width=6, increment=50,
                from_=MASTER_MIN_RESPONSE_TIMEOUT_MS, to=MASTER_MAX_RESPONSE_TIMEOUT_MS)),
            ("Atraso entre pedidos (ms)", ttk.Spinbox(
                row, textvariable=self.master_delay_var, width=6, increment=5,
                from_=MASTER_MIN_DELAY_MS, to=MASTER_MAX_DELAY_MS)),
        )
        self._master_setting_widgets = []
        for index, (caption, widget) in enumerate(fields):
            ttk.Label(row, text=caption).grid(row=0, column=index * 2, padx=(0, 4))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 16))
            self._master_setting_widgets.append(widget)
        ttk.Label(row, text="O IP, a porta e o Unit ID de cada equipamento ficam em cada janela.") \
            .grid(row=0, column=len(fields) * 2)

        controls = ttk.Frame(connection)
        controls.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        self.master_connect_btn = ttk.Button(
            controls, text="Ligar", command=self.master_connect, style="MBS.Primary.TButton")
        self.master_connect_btn.grid(row=0, column=0, padx=(0, 6))
        self.master_disconnect_btn = ttk.Button(
            controls, text="Desligar", command=self.master_disconnect, state="disabled")
        self.master_disconnect_btn.grid(row=0, column=1, padx=(0, 18))
        self.master_status_var = tk.StringVar(value=self.tr("Desligado"))
        ttk.Label(controls, textvariable=self.master_status_var).grid(row=0, column=2)

        for variable in (self.master_timeout_var, self.master_delay_var):
            variable.trace_add("write", lambda *_a: self._schedule_ui_settings_save())

    def _master_connection_json(self):
        return {"response_timeout_ms": self.master_timeout_var.get(),
                "delay_ms": self.master_delay_var.get()}

    def _master_apply_connection(self, connection):
        for key, var in (("response_timeout_ms", self.master_timeout_var),
                         ("delay_ms", self.master_delay_var)):
            if str(connection.get(key, "")).isdigit():
                var.set(str(connection[key]))

    def settings_json(self):
        data = self._master_connection_json()
        data["last_workspace"] = self.master_workspace.current
        return data

    # -- device of each window ------------------------------------------------------
    def _master_build_target(self, frame, pane, window):
        target = ttk.Frame(frame)
        target.grid(row=1, column=0, sticky="w", padx=6, pady=(2, 0))
        pane["host_var"] = tk.StringVar(value=window.host)
        pane["port_var"] = tk.StringVar(value=str(window.port))
        pane["target_vars"] = ("host_var", "port_var")
        for index, (caption, widget) in enumerate((
            ("IP", ttk.Entry(target, width=16, textvariable=pane["host_var"])),
            ("Porta", ttk.Entry(target, width=6, textvariable=pane["port_var"])),
        )):
            ttk.Label(target, text=caption).grid(row=0, column=index * 2, padx=(0, 3))
            widget.grid(row=0, column=index * 2 + 1, padx=(0, 10))
        return target

    def _master_parse_target(self, pane):
        return {"host": validate_host(pane["host_var"].get()),
                "port": validate_tcp_port(pane["port_var"].get())}

    def _master_validate_definition(self, slave, fc, address, qty):
        # The Unit ID (0–255) was checked by the field; validate the rest.
        validate_read_definition(1, fc, address, qty)

    def _master_fields_changed(self, window, pane):
        try:
            if (pane["host_var"].get().strip() != window.host
                    or pane["port_var"].get().strip() != str(window.port)):
                return True
        except (KeyError, tk.TclError):
            return False
        return super()._master_fields_changed(window, pane)

    def _master_window_summary(self, window):
        return f"{window.host}:{window.port} · {super()._master_window_summary(window)}"

    def master_build_write(self, window, slave_text, address_text, values_text, fc,
                           fmt=None, scale=None):
        """Write request for the Unit ID (0–255); never a broadcast in Modbus TCP."""
        unit = parse_int_field(slave_text, 0, 255, "O Unit ID tem de estar entre 0 e 255.")
        request, description = super().master_build_write(
            window, "1", address_text, values_text, fc, fmt, scale)
        return bytes((unit,)) + request[1:], description

    def open_in_server(self, window):
        return self.app.server_tab.slave_open_from_master(window)

    # -- connect -------------------------------------------------------------------
    def _master_connection_settings(self):
        return {
            "response_timeout_ms": parse_int_field(
                self.master_timeout_var.get(), MASTER_MIN_RESPONSE_TIMEOUT_MS,
                MASTER_MAX_RESPONSE_TIMEOUT_MS,
                "O timeout de resposta tem de estar entre 10 e 10000 ms."),
            "delay_ms": parse_int_field(
                self.master_delay_var.get(), MASTER_MIN_DELAY_MS, MASTER_MAX_DELAY_MS,
                "O atraso entre pedidos tem de estar entre 0 e 10000 ms."),
        }

    def master_connect(self):
        if self.master_active:
            return
        try:
            settings = self._master_connection_settings()
        except ValueError as exc:
            messagebox.showerror(self.tr("Configuração inválida"), self.tr(str(exc)))
            return
        for window_id in list(self.master_windows):
            if not self.master_apply_window(window_id):
                return
        self.master_engine = ClientEngine(self.event_queue, **settings)
        for window in self.master_windows.values():
            window.reset_counters()
            self._master_render_status(window)
            self.master_engine.set_poll(window.definition())
        self.master_active = True
        self.busy = True
        self._master_lock_other_features(True)
        self.master_status_var.set(self.tr("A ligar…"))
        self.master_engine.start()

    def _master_lock_other_features(self, locked):
        """Only this tab's own controls: TCP does not lock the serial features."""
        self.master_connect_btn.configure(state="disabled" if locked else "normal")
        self.master_disconnect_btn.configure(state="normal" if locked else "disabled")
        for widget in self._master_setting_widgets:
            try:
                widget.configure(state="disabled" if locked else "normal")
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ServerTab(SlaveMixin, TabInstance):
    """Modbus TCP Server tab: the Slave tab listening on an IP and TCP port."""

    _slave_tab_name = "Server"
    _slave_settings_key = "server"
    _slave_page_attr = "server_page"
    _slave_wheel_tag = "MBToolkit.ServerWheel"
    _slave_ws_folder = staticmethod(get_server_workspaces_folder)
    _slave_ws_format = SERVER_WORKSPACE_FORMAT
    _slave_ws_close_question = "Guardar alterações ao workspace do Server \"{name}\"?"
    _slave_id_label = "Unit ID"
    _slave_fault_title = "Falhas do Unit ID {slave}"
    _slave_fault_intro = ("Simulação de falhas do Unit ID {slave} (aplica-se a todas as janelas "
                          "deste ID).")
    _slave_bad_reply = "MBAP inválido"
    _slave_bad_reply_option = "Cabeçalho MBAP inválido nas respostas"

    def __init__(self, app):
        super().__init__(app)
        self.busy = False
        self._server_clients = {}     # peer -> True while connected
        self._server_interfaces = []  # [(ip, interface name)] found on this PC
        self._server_address = ""

    # -- connection bar ---------------------------------------------------------------
    def _slave_build_connection(self, page, saved):
        connection = ttk.LabelFrame(
            page, text="Ligação — o Server responde a clientes Modbus TCP")
        connection.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row = ttk.Frame(connection)
        row.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self._server_bind = saved.get("bind", SERVER_DEFAULT_BIND)
        self.server_bind_var = tk.StringVar()
        ttk.Label(row, text="Escutar em").grid(row=0, column=0, padx=(0, 4))
        self.server_bind_combo = ttk.Combobox(row, textvariable=self.server_bind_var, width=36,
                                              state="readonly")
        self.server_bind_combo.grid(row=0, column=1)
        self.server_bind_combo.bind("<<ComboboxSelected>>", self._server_bind_selected)
        self.slave_refresh_btn = RefreshButton(row, command=self.server_refresh_interfaces,
                                               size=24)
        self.slave_refresh_btn.grid(row=0, column=2, padx=(4, 18))

        def _sync_refresh_square(_event=None):
            height = self.server_bind_combo.winfo_height()
            if height > 1:
                self.slave_refresh_btn.configure(width=height, height=height)

        self.server_bind_combo.bind("<Configure>", _sync_refresh_square, add="+")
        self.server_port_var = tk.StringVar(value=str(saved.get("port", TCP_DEFAULT_PORT)))
        ttk.Label(row, text="Porta TCP").grid(row=0, column=3, padx=(0, 4))
        port_entry = ttk.Entry(row, width=7, textvariable=self.server_port_var)
        port_entry.grid(row=0, column=4)
        self._slave_setting_widgets = [self.server_bind_combo, port_entry]

        controls = ttk.Frame(connection)
        controls.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        self.slave_safety_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="Confirmo que o Server pode ficar acessível na rede escolhida.",
            variable=self.slave_safety_var,
        ).grid(row=0, column=0, padx=(0, 18))
        self.slave_connect_btn = ttk.Button(
            controls, text="Ligar", command=self.slave_connect, style="MBS.Primary.TButton")
        self.slave_connect_btn.grid(row=0, column=1, padx=(0, 6))
        self.slave_disconnect_btn = ttk.Button(
            controls, text="Desligar", command=self.slave_disconnect, state="disabled")
        self.slave_disconnect_btn.grid(row=0, column=2, padx=(0, 18))
        self.slave_status_var = tk.StringVar(value=self.tr("Desligado"))
        ttk.Label(controls, textvariable=self.slave_status_var).grid(row=0, column=3)
        self.slave_stats_var = tk.StringVar()
        ttk.Label(connection, textvariable=self.slave_stats_var).grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 8))

        self.server_port_var.trace_add("write", lambda *_a: self._schedule_ui_settings_save())
        self._server_fill_interfaces()
        self.server_refresh_interfaces()

    # -- network interfaces ------------------------------------------------------------
    def _server_choices(self):
        """[(ip, caption)] offered in "Escutar em", this PC first, all last."""
        choices = [(LOCALHOST, self.tr("Só este PC (127.0.0.1)"))]
        for ip, name in self._server_interfaces:
            choices.append((ip, f"{ip} — {name}" if name else ip))
        known = {ip for ip, _caption in choices} | {ALL_INTERFACES}
        if self._server_bind not in known:
            # Remembered address of an adapter that is not present now.
            choices.append((self._server_bind,
                            self.trf("{ip} (não encontrado)", ip=self._server_bind)))
        choices.append((ALL_INTERFACES, self.tr("Todas as interfaces (0.0.0.0)")))
        return choices

    def _server_fill_interfaces(self):
        choices = self._server_choices()
        self.server_bind_combo["values"] = [caption for _ip, caption in choices]
        caption = next((c for ip, c in choices if ip == self._server_bind), choices[0][1])
        self.server_bind_var.set(caption)

    def _server_bind_selected(self, _event=None):
        caption = self.server_bind_var.get()
        for ip, text in self._server_choices():
            if text == caption:
                self._server_bind = ip
        self._schedule_ui_settings_save()

    def server_refresh_interfaces(self):
        """List this PC's IPv4 interfaces in the background (PowerShell can take 1 s)."""
        event_queue = self.event_queue

        def worker():
            event_queue.put(("server_interfaces", list_ipv4_interfaces()))

        threading.Thread(target=worker, daemon=True).start()

    def _slave_connection_json(self):
        return {"bind": self._server_bind, "port": self.server_port_var.get()}

    def _slave_apply_connection(self, connection):
        bind = connection.get("bind")
        try:
            if bind is not None:
                self._server_bind = str(ipaddress.IPv4Address(str(bind)))
                self._server_fill_interfaces()
        except ValueError:
            pass
        if str(connection.get("port", "")).isdigit():
            self.server_port_var.set(str(connection["port"]))

    def settings_json(self):
        data = self._slave_connection_json()
        data["last_workspace"] = self.slave_workspace.current
        return data

    # -- texts ---------------------------------------------------------------------
    def _slave_render_stats(self):
        stats = self.slave_stats
        self.slave_stats_var.set(self.trf(
            "Clientes ligados: {clients}   Pedidos: {requests}   Respostas: {responses}   "
            "Exceções: {exceptions}", clients=len(getattr(self, "_server_clients", {})),
            **stats))

    def _server_status_text(self):
        return self.trf("● A responder em {address}", address=self._server_address)

    # -- connect -------------------------------------------------------------------
    def slave_connect(self):
        if self.slave_active:
            return
        try:
            port = validate_tcp_port(self.server_port_var.get())
        except ValueError as exc:
            messagebox.showerror(self.tr("Configuração inválida"), self.tr(str(exc)))
            return
        if self._server_bind != LOCALHOST and not self.slave_safety_var.get():
            messagebox.showwarning(
                self.tr(self._slave_tab_name),
                self.tr("Escolheste uma interface de rede: confirma primeiro que o Server pode "
                        "ficar acessível nessa rede."),
            )
            return
        for window_id in list(self.slave_windows):
            if not self.slave_apply_window(window_id):
                return
        if not self.slave_windows:
            messagebox.showwarning(self.tr(self._slave_tab_name),
                                   self.tr("Cria primeiro uma janela com o Slave a simular."))
            return
        self.slave_engine = ServerEngine(self.event_queue, self.slave_store,
                                         host=self._server_bind, port=port)
        self._slave_reset_stats()
        self._server_clients = {}
        self._slave_render_stats()
        for window in self.slave_windows.values():
            window.reset_counters()
            self._slave_render_status(window)
        self.slave_active = True
        self.busy = True
        self._slave_lock_other_features(True)
        self.slave_status_var.set(self.tr("A iniciar o Server…"))
        self.slave_engine.start()

    def _slave_lock_other_features(self, locked):
        """Only this tab's own controls: TCP does not lock the serial features."""
        self.slave_connect_btn.configure(state="disabled" if locked else "normal")
        self.slave_disconnect_btn.configure(state="normal" if locked else "disabled")
        self.slave_refresh_btn.configure(state="disabled" if locked else "normal")
        for widget in self._slave_setting_widgets:
            try:
                widget.configure(state="disabled" if locked
                                 else "readonly" if isinstance(widget, ttk.Combobox) else "normal")
            except tk.TclError:
                pass

    def _slave_finish_session(self, payload):
        if not self.slave_active:
            return
        engine = self.slave_engine
        self.slave_engine = None
        if engine is not None:
            engine.stop(join_timeout=0.5)
        self.slave_active = False
        self.busy = False
        self._server_clients = {}
        self._slave_lock_other_features(False)
        self.slave_status_var.set(self.tr("Desligado"))
        self._slave_render_stats()
        error = (payload or {}).get("error")
        if error:
            messagebox.showerror(
                self.tr(self._slave_tab_name),
                self.trf("Não foi possível escutar em {host}:{port}: {error}",
                         host=self._server_bind, port=self.server_port_var.get(), error=error),
            )

    def handle_server_event(self, event, payload):
        if event == "server_ready":
            self._server_address = f"{payload['host']}:{payload['port']}"
            self.slave_status_var.set(self._server_status_text())
        elif event == "server_client":
            if payload.get("connected"):
                self._server_clients[payload["peer"]] = True
            else:
                self._server_clients.pop(payload["peer"], None)
            self._slave_render_stats()
        elif event == "server_request":
            self._slave_apply_request(payload)
        elif event == "server_stopped":
            self._slave_finish_session(payload)
        elif event == "server_interfaces":
            self._server_interfaces = list(payload or [])
            if not self.slave_active:
                self._server_fill_interfaces()

    def slave_apply_language(self):
        super().slave_apply_language()
        if hasattr(self, "server_bind_combo"):
            self._server_fill_interfaces()
        if self.slave_active and self._server_address:
            self.slave_status_var.set(self._server_status_text())

    def slave_shutdown(self):
        self._slave_generators = {}
        engine = getattr(self, "slave_engine", None)
        if engine is not None:
            engine.stop(join_timeout=0.8)
        self.slave_engine = None
