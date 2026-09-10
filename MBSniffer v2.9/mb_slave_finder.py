#!/usr/bin/env python3
"""Active Modbus RTU Bus Slave Finder logic and GUI mixin."""

import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from mb_config import (
    DISCOVERY_BAUD_RATES,
    DISCOVERY_PARITIES,
    DISCOVERY_STOP_BITS,
    DISCOVERY_DEFAULT_MIN_TIMEOUT_MS,
    DISCOVERY_MIN_TIMEOUT_MS,
    DISCOVERY_MAX_TIMEOUT_MS,
    DISCOVERY_PROBE_ADDRESS,
    DISCOVERY_PROBE_QTY,
    DISCOVERY_WRITE_TIMEOUT_SECONDS,
    DISCOVERY_WRITE_RETRIES,
    DISCOVERY_RX_BUFFER_LIMIT,
    MODBUS_EXCEPTION_CODES,
)
from mb_protocol import append_crc, crc_ok, hex_bytes
from mb_widgets import RefreshButton

def build_discovery_probe(slave: int, fc: int) -> bytes:
    """Build a read-only discovery probe: FC03/FC04, Address 0, Qty 1."""
    if not (1 <= int(slave) <= 247):
        raise ValueError("Slave ID fora do intervalo 1..247")
    if int(fc) not in (3, 4):
        raise ValueError("A descoberta ativa suporta apenas FC03/FC04")

    payload = bytes((
        int(slave),
        int(fc),
        0x00, DISCOVERY_PROBE_ADDRESS & 0xFF,
        0x00, DISCOVERY_PROBE_QTY & 0xFF,
    ))
    return append_crc(payload)

def discovery_bits_per_char(parity: str, stopbits: str) -> float:
    """Return serial bits/character: start + 8 data + parity + stop."""
    parity_bits = 0 if parity == "None" else 1
    stop_value = float(stopbits)
    return 1.0 + 8.0 + parity_bits + stop_value

def discovery_response_timeout_seconds(
    baud: int,
    parity: str,
    stopbits: str,
    minimum_timeout_ms: float = DISCOVERY_DEFAULT_MIN_TIMEOUT_MS,
) -> float:
    """
    Adaptive response deadline after the request has left the serial driver.

    The deadline includes the on-wire duration of a normal 7-byte FC03/FC04
    response plus processing/inter-frame margin, with a user-configurable
    minimum.
    """
    baud = max(1, int(baud))
    bits_per_char = discovery_bits_per_char(parity, stopbits)
    char_s = bits_per_char / float(baud)
    normal_response_s = 7.0 * char_s
    serial_margin_s = max(0.012, 3.5 * char_s)
    calculated = normal_response_s + serial_margin_s
    return max(float(minimum_timeout_ms) / 1000.0, calculated)

def discovery_request_transmit_seconds(baud: int, parity: str, stopbits: str) -> float:
    """Estimated on-wire duration of the fixed 8-byte discovery request."""
    return 8.0 * discovery_bits_per_char(parity, stopbits) / float(max(1, int(baud)))

def find_discovery_response(buffer: bytes, slave: int, fc: int):
    """
    Find a valid normal or exception response for one discovery probe.

    Any CRC-valid Modbus exception counts as proof that the slave exists.
    The scanner intentionally ignores other traffic and request echoes.
    """
    data = bytes(buffer)
    slave = int(slave)
    fc = int(fc)

    for offset in range(max(0, len(data) - 3)):
        if data[offset] != slave or offset + 2 > len(data):
            continue

        response_fc = data[offset + 1]

        if response_fc == (fc | 0x80):
            end = offset + 5
            if end <= len(data):
                frame = data[offset:end]
                if crc_ok(frame):
                    code = frame[2]
                    return {
                        "kind": "EXCEPTION",
                        "frame": frame,
                        "exception_code": code,
                    }

        if response_fc == fc and offset + 3 <= len(data):
            byte_count = data[offset + 2]
            # FC03/04 register responses must contain an even positive byte count.
            if byte_count > 0 and byte_count % 2 == 0 and byte_count <= 250:
                end = offset + 5 + byte_count
                if end <= len(data):
                    frame = data[offset:end]
                    if crc_ok(frame):
                        return {
                            "kind": "RESPONSE",
                            "frame": frame,
                            "exception_code": None,
                        }

    return None

def read_discovery_response(ser, slave, fc, timeout_s, stop_event):
    """Read non-blocking serial bytes until a valid probe response or timeout."""
    deadline = time.perf_counter() + max(0.001, float(timeout_s))
    buffer = bytearray()

    while time.perf_counter() < deadline:
        if stop_event.is_set():
            return None

        # Do not hide serial-driver failures as ordinary slave timeouts.
        waiting = int(getattr(ser, "in_waiting", 0) or 0)

        if waiting:
            chunk = ser.read(waiting)
            if chunk:
                buffer.extend(chunk)
                if len(buffer) > DISCOVERY_RX_BUFFER_LIMIT:
                    del buffer[:-DISCOVERY_RX_BUFFER_LIMIT]
                found = find_discovery_response(buffer, slave, fc)
                if found is not None:
                    return found
        else:
            # Event.wait() keeps the Stop button responsive.
            if stop_event.wait(0.001):
                return None

    return find_discovery_response(buffer, slave, fc)

def cancel_serial_io(ser):
    """Best-effort cancellation of pending serial I/O."""
    if ser is None:
        return
    for method_name in ("cancel_read", "cancel_write"):
        method = getattr(ser, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass

def recover_discovery_write(ser):
    """Best-effort cleanup after a discovery write timeout."""
    cancel = getattr(ser, "cancel_write", None)
    if callable(cancel):
        try:
            cancel()
        except Exception:
            pass
    try:
        ser.reset_output_buffer()
    except Exception:
        pass
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

def write_discovery_request(
    ser, request, baud, parity, stopbits, stop_event, serial_module
):
    """
    Transmit one discovery request robustly.

    A write timeout is retried once after cancelling/clearing TX. ser.flush()
    is deliberately avoided because some USB-serial drivers can block there.
    The helper also waits for the request's estimated physical on-wire time so
    the slave response timeout starts at a sensible point on slow baud rates.
    """
    request = bytes(request)
    timeout_exc = getattr(serial_module, "SerialTimeoutException", TimeoutError)
    serial_exc = getattr(serial_module, "SerialException", OSError)
    attempts = DISCOVERY_WRITE_RETRIES + 1
    last_error = None
    bits_per_char = discovery_bits_per_char(parity, stopbits)
    char_time_s = bits_per_char / float(max(1, int(baud)))
    request_wire_s = len(request) * char_time_s
    retry_silence_s = max(0.050, request_wire_s + 3.5 * char_time_s)

    for attempt in range(attempts):
        if stop_event.is_set():
            return False

        started_write = time.perf_counter()
        try:
            written_total = 0
            while written_total < len(request):
                if stop_event.is_set():
                    return False
                written = ser.write(request[written_total:])
                written = 0 if written is None else int(written)
                if written <= 0:
                    raise timeout_exc(
                        "A porta série não aceitou bytes para transmissão."
                    )
                written_total += written

            elapsed_write_s = time.perf_counter() - started_write
            remaining_wire_s = max(0.0, request_wire_s - elapsed_write_s)
            if remaining_wire_s > 0 and stop_event.wait(remaining_wire_s):
                return False
            return True

        except timeout_exc as exc:
            last_error = exc
            recover_discovery_write(ser)
            if attempt + 1 >= attempts or stop_event.is_set():
                raise
            # If any fragment reached the wire before the driver timed out,
            # leave enough silence for that fragment to finish and for a full
            # Modbus RTU frame gap before retrying.
            if stop_event.wait(retry_silence_s):
                return False

        except serial_exc:
            raise

    if last_error is not None:
        raise last_error
    return False

def format_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class SlaveFinderMixin:
    """Methods that implement the active Bus Slave Finder tab."""

    def build_discovery_tab(self, page):
        """Build the full-window active Modbus RTU slave-discovery workspace."""
        finder_saved = getattr(self, "ui_settings", {}).get(
            "bus_slave_finder", {}
        )
        if not isinstance(finder_saved, dict):
            finder_saved = {}

        saved_bauds = set(
            finder_saved.get("baud_rates", [9600, 19200])
        )
        saved_parities = set(
            finder_saved.get("parities", ["None", "Even"])
        )
        saved_stops = set(
            finder_saved.get("stop_bits", ["1"])
        )

        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        warning = ttk.LabelFrame(page, text="Pesquisa ativa — transmite no barramento")
        warning.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        warning.columnconfigure(0, weight=1)
        ttk.Label(
            warning,
            text=(
                "Esta ferramenta atua temporariamente como master Modbus RTU e envia apenas "
                "pedidos de leitura. Não a utilizes com outro master ativo no mesmo barramento."
            ),
            wraplength=1100,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        self.discovery_safety_var = tk.BooleanVar(value=False)
        safety_cb = ttk.Checkbutton(
            warning,
            text="Confirmo que não existe outro master ativo no barramento.",
            variable=self.discovery_safety_var,
            command=self.update_discovery_start_state,
        )
        safety_cb.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        options = ttk.LabelFrame(page, text="Configuração da pesquisa")
        options.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        options.columnconfigure(0, weight=1)

        top_row = ttk.Frame(options)
        top_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top_row.columnconfigure(3, weight=1)

        ttk.Label(top_row, text="Porta COM").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        self.discovery_port_var = tk.StringVar()
        self.discovery_port_combo = ttk.Combobox(
            top_row,
            textvariable=self.discovery_port_var,
            width=13,
            state="readonly",
        )
        self.discovery_port_combo.grid(
            row=0, column=1, sticky="w", padx=(0, 0)
        )
        self.discovery_port_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.update_discovery_start_state(),
        )

        self.discovery_refresh_btn = RefreshButton(
            top_row,
            command=self.refresh_ports,
            size=24,
        )
        self.discovery_refresh_btn.grid(
            row=0, column=2, sticky="w", padx=(4, 0)
        )

        def _sync_discovery_refresh_square(_event=None):
            height = self.discovery_port_combo.winfo_height()
            if height > 1:
                self.discovery_refresh_btn.configure(
                    width=height, height=height
                )

        self.discovery_port_combo.bind(
            "<Configure>", _sync_discovery_refresh_square, add="+"
        )

        ttk.Label(
            top_row,
            text="Data bits: 8 (fixo)",
        ).grid(row=0, column=4, sticky="w", padx=(28, 20))
        ttk.Label(
            top_row,
            text="Probe: FC03 / Address 0 / Qty 1",
        ).grid(row=0, column=5, sticky="w")

        # Baud-rate checkboxes. Defaults keep a normal industrial scan quick.
        baud_frame = ttk.LabelFrame(options, text="Baud rate")
        baud_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.discovery_baud_vars = {}
        for idx in range(len(DISCOVERY_BAUD_RATES)):
            baud_frame.columnconfigure(idx, weight=1, uniform="baud")
        for idx, baud in enumerate(DISCOVERY_BAUD_RATES):
            var = tk.BooleanVar(value=baud in saved_bauds)
            self.discovery_baud_vars[baud] = var
            cb = ttk.Checkbutton(baud_frame, text=str(baud), variable=var)
            cb.grid(row=0, column=idx, sticky="w", padx=8, pady=5)
            var.trace_add("write", lambda *_a: self.on_discovery_options_changed())

        serial_frame = ttk.Frame(options)
        serial_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        serial_frame.columnconfigure(0, weight=1)
        serial_frame.columnconfigure(1, weight=1)
        serial_frame.columnconfigure(2, weight=1)

        parity_box = ttk.LabelFrame(serial_frame, text="Parity")
        parity_box.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        for idx in range(len(DISCOVERY_PARITIES)):
            parity_box.columnconfigure(idx, weight=1, uniform="parity")
        self.discovery_parity_vars = {}
        for idx, parity in enumerate(DISCOVERY_PARITIES):
            var = tk.BooleanVar(value=parity in saved_parities)
            self.discovery_parity_vars[parity] = var
            ttk.Checkbutton(parity_box, text=parity, variable=var).grid(
                row=0, column=idx, sticky="w", padx=8, pady=5
            )
            var.trace_add("write", lambda *_a: self.on_discovery_options_changed())
        stop_box = ttk.LabelFrame(serial_frame, text="Stop bits")
        stop_box.grid(row=0, column=1, sticky="nsew", padx=5)
        for idx in range(len(DISCOVERY_STOP_BITS)):
            stop_box.columnconfigure(idx, weight=1, uniform="stop")
        self.discovery_stop_vars = {}
        for idx, stopbits in enumerate(DISCOVERY_STOP_BITS):
            var = tk.BooleanVar(value=stopbits in saved_stops)
            self.discovery_stop_vars[stopbits] = var
            ttk.Checkbutton(stop_box, text=stopbits, variable=var).grid(
                row=0, column=idx, sticky="w", padx=10, pady=5
            )
            var.trace_add("write", lambda *_a: self.on_discovery_options_changed())
        range_box = ttk.LabelFrame(serial_frame, text="Slave IDs / velocidade")
        range_box.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        ttk.Label(range_box, text="De").grid(row=0, column=0, padx=(8, 3), pady=5)
        self.discovery_slave_start_var = tk.StringVar(value=finder_saved.get("slave_start", "1"))
        self.discovery_slave_start_spin = ttk.Spinbox(
            range_box, from_=1, to=247, width=5, textvariable=self.discovery_slave_start_var
        )
        self.discovery_slave_start_spin.grid(row=0, column=1, padx=3, pady=5)
        ttk.Label(range_box, text="até").grid(row=0, column=2, padx=3, pady=5)
        self.discovery_slave_end_var = tk.StringVar(value=finder_saved.get("slave_end", "247"))
        self.discovery_slave_end_spin = ttk.Spinbox(
            range_box, from_=1, to=247, width=5, textvariable=self.discovery_slave_end_var
        )
        self.discovery_slave_end_spin.grid(row=0, column=3, padx=3, pady=5)

        ttk.Label(range_box, text="Timeout mín.").grid(row=1, column=0, padx=(8, 3), pady=5)
        self.discovery_min_timeout_var = tk.StringVar(
            value=finder_saved.get(
                "min_timeout_ms",
                str(DISCOVERY_DEFAULT_MIN_TIMEOUT_MS),
            )
        )
        self.discovery_min_timeout_spin = ttk.Spinbox(
            range_box,
            from_=DISCOVERY_MIN_TIMEOUT_MS,
            to=DISCOVERY_MAX_TIMEOUT_MS,
            increment=5,
            width=6,
            textvariable=self.discovery_min_timeout_var,
        )
        self.discovery_min_timeout_spin.grid(row=1, column=1, padx=3, pady=5)
        ttk.Label(range_box, text="ms").grid(row=1, column=2, padx=3, pady=5)

        self.discovery_fc04_fallback_var = tk.BooleanVar(value=finder_saved.get("fc04_fallback", False))
        fallback_cb = ttk.Checkbutton(
            range_box,
            text="FC04 fallback",
            variable=self.discovery_fc04_fallback_var,
        )
        fallback_cb.grid(row=1, column=3, columnspan=2, sticky="w", padx=8, pady=5)

        for var in (
            self.discovery_slave_start_var,
            self.discovery_slave_end_var,
            self.discovery_min_timeout_var,
            self.discovery_fc04_fallback_var,
        ):
            var.trace_add("write", lambda *_a: self.on_discovery_options_changed())

        ttk.Label(
            options,
            text=(
                "FC03 é o modo rápido. Uma resposta normal OU uma Modbus Exception com CRC válido "
                "conta como slave encontrado. Ativa FC04 fallback apenas para dispositivos que "
                "possam ignorar FC03 sem devolver Exception."
            ),
            wraplength=1120,
        ).grid(row=3, column=0, sticky="w", padx=10, pady=(4, 8))

        controls = ttk.LabelFrame(page, text="Pesquisa")
        controls.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        controls.columnconfigure(4, weight=1)

        self.discovery_start_btn = ttk.Button(
            controls, text="Iniciar pesquisa", command=self.start_discovery_scan
        )
        self.discovery_start_btn.grid(row=0, column=0, padx=(10, 5), pady=8)
        self.discovery_stop_btn = ttk.Button(
            controls, text="Parar", command=self.stop_discovery_scan, state="disabled"
        )
        self.discovery_stop_btn.grid(row=0, column=1, padx=5, pady=8)
        self.discovery_clear_btn = ttk.Button(
            controls, text="Limpar resultados", command=self.clear_discovery_results
        )
        self.discovery_clear_btn.grid(row=0, column=2, padx=5, pady=8)

        self.discovery_found_var = tk.StringVar(value="Encontrados: 0")
        ttk.Label(controls, textvariable=self.discovery_found_var).grid(
            row=0, column=3, padx=(18, 8), pady=8, sticky="w"
        )

        self.discovery_status_var = tk.StringVar(value="Parado")
        ttk.Label(controls, textvariable=self.discovery_status_var).grid(
            row=0, column=4, padx=8, pady=8, sticky="w"
        )

        self.discovery_progress_var = tk.DoubleVar(value=0.0)
        self.discovery_progress = ttk.Progressbar(
            controls, variable=self.discovery_progress_var, maximum=100.0
        )
        self.discovery_progress.grid(
            row=1, column=0, columnspan=5, sticky="ew", padx=10, pady=(0, 5)
        )

        self.discovery_progress_text_var = tk.StringVar(value="0 / 0")
        self.discovery_estimate_var = tk.StringVar(value="")
        ttk.Label(controls, textvariable=self.discovery_progress_text_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8)
        )
        ttk.Label(controls, textvariable=self.discovery_estimate_var).grid(
            row=2, column=2, columnspan=3, sticky="e", padx=10, pady=(0, 8)
        )

        results = ttk.LabelFrame(page, text="Slaves encontrados")
        results.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 12))
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)

        columns = ("slave", "baud", "config", "fc", "result", "resp", "raw")
        self.discovery_tree = ttk.Treeview(
            results, columns=columns, show="headings", selectmode="browse"
        )
        headings = {
            "slave": "Slave",
            "baud": "Baud",
            "config": "Config.",
            "fc": "FC",
            "result": "Resultado",
            "resp": "Resp. (ms)",
            "raw": "Raw Hex",
        }
        widths = {
            "slave": 70, "baud": 90, "config": 85, "fc": 55,
            "result": 260, "resp": 95, "raw": 350,
        }
        for col in columns:
            self.discovery_tree.heading(col, text=headings[col], anchor="center")
            self.discovery_tree.column(
                col, width=widths[col], minwidth=55,
                anchor="w" if col in ("result", "raw") else "center",
                stretch=col in ("result", "raw"),
            )

        discovery_y = ttk.Scrollbar(
            results, orient="vertical", command=self.discovery_tree.yview
        )
        self.discovery_tree.configure(yscrollcommand=discovery_y.set)
        self.discovery_tree.grid(row=0, column=0, sticky="nsew")
        discovery_y.grid(row=0, column=1, sticky="ns")

        self.update_discovery_estimate()
        self.update_discovery_start_state()

    def on_discovery_options_changed(self):
        if hasattr(self, "discovery_estimate_var"):
            self.update_discovery_estimate()
            self.update_discovery_start_state()

    def selected_discovery_configs(self):
        bauds = [baud for baud in DISCOVERY_BAUD_RATES if self.discovery_baud_vars[baud].get()]
        parities = [p for p in DISCOVERY_PARITIES if self.discovery_parity_vars[p].get()]
        stops = [s for s in DISCOVERY_STOP_BITS if self.discovery_stop_vars[s].get()]
        return [
            (baud, parity, stopbits)
            for baud in bauds
            for parity in parities
            for stopbits in stops
        ]

    def selected_discovery_slaves(self):
        start = int(self.discovery_slave_start_var.get())
        end = int(self.discovery_slave_end_var.get())
        if not (1 <= start <= 247 and 1 <= end <= 247):
            raise ValueError("Os Slave IDs têm de estar entre 1 e 247.")
        if start > end:
            raise ValueError("O Slave ID inicial não pode ser superior ao final.")
        return list(range(start, end + 1))

    def selected_discovery_min_timeout_ms(self):
        value = float(self.discovery_min_timeout_var.get())
        if not (DISCOVERY_MIN_TIMEOUT_MS <= value <= DISCOVERY_MAX_TIMEOUT_MS):
            raise ValueError(
                f"O timeout mínimo tem de estar entre {DISCOVERY_MIN_TIMEOUT_MS} e "
                f"{DISCOVERY_MAX_TIMEOUT_MS} ms."
            )
        return value

    def discovery_config_label(self, parity, stopbits):
        parity_letter = {"None": "N", "Even": "E", "Odd": "O"}[parity]
        return f"8{parity_letter}{stopbits}"

    def update_discovery_estimate(self):
        try:
            configs = self.selected_discovery_configs()
            slaves = self.selected_discovery_slaves()
            minimum_timeout_ms = self.selected_discovery_min_timeout_ms()
        except Exception:
            self.discovery_estimate_var.set("Máx. estimado: —")
            self.discovery_progress_text_var.set("0 / 0")
            return

        total_units = len(configs) * len(slaves)
        probes_per_unit = 2 if self.discovery_fc04_fallback_var.get() else 1

        seconds = 0.0
        for baud, parity, stopbits in configs:
            per_probe = (
                discovery_request_transmit_seconds(baud, parity, stopbits)
                + discovery_response_timeout_seconds(
                    baud, parity, stopbits, minimum_timeout_ms
                )
            )
            seconds += len(slaves) * probes_per_unit * per_probe
            seconds += 0.025  # small reopen/reconfigure allowance

        self.discovery_progress_text_var.set(f"0 / {total_units}")
        suffix = " (com FC04 fallback)" if probes_per_unit == 2 else ""
        self.discovery_estimate_var.set(
            f"{len(configs)} config. × {len(slaves)} slaves — "
            f"máx. estimado: {format_duration(seconds)}{suffix}"
        )

    def update_discovery_start_state(self):
        if not hasattr(self, "discovery_start_btn"):
            return
        enabled = (
            not self.discovery_active
            and not self.busy
            and bool(self.discovery_port_var.get().strip())
            and bool(self.discovery_safety_var.get())
        )
        try:
            enabled = enabled and bool(self.selected_discovery_configs())
            self.selected_discovery_slaves()
            self.selected_discovery_min_timeout_ms()
        except Exception:
            enabled = False
        self.discovery_start_btn.configure(state="normal" if enabled else "disabled")

    def clear_discovery_results(self):
        if self.discovery_active:
            return
        for iid in self.discovery_tree.get_children():
            self.discovery_tree.delete(iid)
        self.discovery_found_count = 0
        self.discovery_found_var.set("Encontrados: 0")
        self.discovery_progress_var.set(0.0)
        self.discovery_status_var.set("Parado")
        self.update_discovery_estimate()

    def open_discovery_serial_port(self, serial, port, baud, parity, stopbits):
        parity_map = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
        }
        stop_map = {
            "1": serial.STOPBITS_ONE,
            "2": serial.STOPBITS_TWO,
        }

        ser = serial.Serial()
        ser.port = port
        ser.baudrate = int(baud)
        ser.bytesize = serial.EIGHTBITS
        ser.parity = parity_map[parity]
        ser.stopbits = stop_map[stopbits]
        ser.timeout = 0

        ser.write_timeout = DISCOVERY_WRITE_TIMEOUT_SECONDS
        ser.xonxoff = False
        ser.rtscts = False
        ser.dsrdtr = False

        # Do not force RTS/DTR levels. Many USB-RS485 adapters manage direction
        # internally and forcing modem-control lines can interfere with some
        # adapters/drivers. Hardware flow control is disabled above.
        ser.open()

        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        try:
            ser.reset_output_buffer()
        except Exception:
            pass

        return ser

    def start_discovery_scan(self):
        if self.busy or self.discovery_active:
            return

        serial, _ = self.get_serial_modules()
        if serial is None:
            messagebox.showerror(
                "pyserial em falta",
                "pyserial não está instalado. O build_exe.bat inclui-o automaticamente no EXE."
            )
            return

        if not self.discovery_safety_var.get():
            messagebox.showwarning(
                "Pesquisa ativa",
                "Confirma primeiro que não existe outro master ativo no barramento."
            )
            return

        try:
            port = self.discovery_port_var.get().strip()
            if not port:
                raise ValueError("Seleciona uma porta COM.")
            configs = self.selected_discovery_configs()
            if not configs:
                raise ValueError("Seleciona pelo menos uma configuração série.")
            slaves = self.selected_discovery_slaves()
            minimum_timeout_ms = self.selected_discovery_min_timeout_ms()
        except Exception as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return

        fallback_fc04 = bool(self.discovery_fc04_fallback_var.get())

        self.clear_discovery_results()
        self.discovery_active = True
        self.busy = True
        self.discovery_stop_event.clear()
        self.discovery_found_count = 0
        self.discovery_progress_var.set(0.0)
        self.discovery_status_var.set("A iniciar pesquisa…")

        self.discovery_start_btn.configure(state="disabled")
        self.discovery_stop_btn.configure(state="normal")
        self.discovery_clear_btn.configure(state="disabled")
        self.discovery_refresh_btn.configure(state="disabled")
        self.discovery_port_combo.configure(state="disabled")

        # Prevent passive capture/simulation from being started concurrently.
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.restart_btn.configure(state="disabled")
        self.set_sniffer_refresh_state("disabled")
        self.set_simulation_button_state("disabled")

        immutable_configs = list(configs)
        immutable_slaves = list(slaves)

        self.discovery_thread = threading.Thread(
            target=self.discovery_worker,
            args=(
                serial, port, immutable_configs, immutable_slaves,
                minimum_timeout_ms, fallback_fc04
            ),
            daemon=True,
        )
        try:
            self.discovery_thread.start()
        except Exception as exc:
            # Restore the interface if the worker cannot even be started.
            self.discovery_active = False
            self.busy = False
            self.discovery_thread = None
            self.discovery_stop_btn.configure(state="disabled")
            self.discovery_clear_btn.configure(state="normal")
            self.discovery_refresh_btn.configure(state="normal")
            self.discovery_port_combo.configure(state="readonly")
            self.start_btn.configure(state="normal")
            self.restart_btn.configure(state="normal")
            self.set_sniffer_refresh_state("normal")
            self.set_simulation_button_state("normal")
            self.discovery_status_var.set("Erro ao iniciar pesquisa")
            self.update_discovery_start_state()
            messagebox.showerror(
                "Erro na Bus Slave Finder",
                f"Não foi possível iniciar a thread de pesquisa:\n\n"
                f"{type(exc).__name__}: {exc}"
            )

    def stop_discovery_scan(self):
        if self.discovery_active:
            self.discovery_status_var.set("A parar…")
            self.discovery_stop_event.set()
            self.discovery_stop_btn.configure(state="disabled")
            # Wake/cancel pending driver I/O without closing the handle from
            # the Tk thread while the discovery worker may still be using it.
            cancel_serial_io(self.discovery_serial)

    def discovery_worker(
        self, serial, port, configs, slaves, minimum_timeout_ms, fallback_fc04
    ):
        started = time.perf_counter()
        total_units = len(configs) * len(slaves)
        completed = 0
        found_count = 0
        fatal_error = None
        context = str(port)

        try:
            for baud, parity, stopbits in configs:
                if self.discovery_stop_event.is_set():
                    break

                config_label = self.discovery_config_label(parity, stopbits)
                context = f"{port} — {baud} / {config_label}"
                self.event_queue.put((
                    "discovery_status",
                    f"A configurar {baud} / {config_label}…"
                ))

                ser = None
                try:
                    try:
                        ser = self.open_discovery_serial_port(
                            serial, port, baud, parity, stopbits
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            f"Não foi possível abrir {port} em {baud} / {config_label}: "
                            f"{type(exc).__name__}: {exc}"
                        ) from exc

                    self.discovery_serial = ser
                    if self.discovery_stop_event.wait(0.025):
                        break

                    response_timeout_s = discovery_response_timeout_seconds(
                        baud, parity, stopbits, minimum_timeout_ms
                    )
                    char_gap_s = (
                        3.5 * discovery_bits_per_char(parity, stopbits)
                        / float(baud)
                    )

                    for slave in slaves:
                        if self.discovery_stop_event.is_set():
                            break

                        result = None
                        used_fc = None
                        elapsed_ms = None
                        probe_fcs = [3, 4] if fallback_fc04 else [3]

                        for fc in probe_fcs:
                            if self.discovery_stop_event.is_set():
                                break

                            context = (
                                f"{port} — {baud} / {config_label} / "
                                f"Slave {slave} / FC{fc:02X}"
                            )

                            # If this fails, the COM/driver is unhealthy. Do not
                            # disguise it as a normal no-response slave timeout.
                            try:
                                ser.reset_input_buffer()
                            except Exception as exc:
                                raise RuntimeError(
                                    f"Falha ao preparar a receção em {context}: "
                                    f"{type(exc).__name__}: {exc}"
                                ) from exc

                            request = build_discovery_probe(slave, fc)
                            started_probe = time.perf_counter()
                            try:
                                sent = write_discovery_request(
                                    ser, request, baud, parity, stopbits,
                                    self.discovery_stop_event, serial
                                )
                            except Exception as exc:
                                raise RuntimeError(
                                    f"Falha ao transmitir em {context}: "
                                    f"{type(exc).__name__}: {exc}"
                                ) from exc

                            if not sent or self.discovery_stop_event.is_set():
                                break

                            try:
                                result = read_discovery_response(
                                    ser, slave, fc, response_timeout_s,
                                    self.discovery_stop_event
                                )
                            except Exception as exc:
                                raise RuntimeError(
                                    f"Falha ao receber em {context}: "
                                    f"{type(exc).__name__}: {exc}"
                                ) from exc

                            if result is not None:
                                elapsed_ms = (
                                    time.perf_counter() - started_probe
                                ) * 1000.0
                                used_fc = fc
                                if char_gap_s > 0:
                                    self.discovery_stop_event.wait(
                                        min(char_gap_s, 0.05)
                                    )
                                break

                        if result is not None and used_fc is not None:
                            found_count += 1
                            if result["kind"] == "EXCEPTION":
                                code = result["exception_code"]
                                name = MODBUS_EXCEPTION_CODES.get(
                                    code, ("Unknown/Reserved Exception", "")
                                )[0]
                                result_text = f"Exception 0x{code:02X} — {name}"
                            else:
                                result_text = "Response"

                            self.event_queue.put((
                                "discovery_found",
                                {
                                    "slave": slave,
                                    "baud": baud,
                                    "config": config_label,
                                    "fc": f"{used_fc:02X}",
                                    "result": result_text,
                                    "response_ms": elapsed_ms,
                                    "raw": hex_bytes(result["frame"]),
                                }
                            ))

                        completed += 1
                        elapsed = time.perf_counter() - started
                        eta = (
                            max(
                                0.0,
                                (elapsed / completed) * (total_units - completed)
                            )
                            if completed > 0 else 0.0
                        )

                        self.event_queue.put((
                            "discovery_progress",
                            {
                                "completed": completed,
                                "total": total_units,
                                "baud": baud,
                                "config": config_label,
                                "slave": slave,
                                "elapsed": elapsed,
                                "eta": eta,
                                "found": found_count,
                            }
                        ))

                finally:
                    if ser is not None:
                        cancel_serial_io(ser)
                        try:
                            ser.close()
                        except Exception:
                            pass
                    self.discovery_serial = None

        except Exception as exc:
            if not self.discovery_stop_event.is_set():
                fatal_error = str(exc) or f"{context}: {type(exc).__name__}"

        elapsed = time.perf_counter() - started
        self.event_queue.put((
            "discovery_done",
            {
                "stopped": self.discovery_stop_event.is_set(),
                "error": fatal_error,
                "elapsed": elapsed,
                "completed": completed,
                "total": total_units,
                "found": found_count,
            }
        ))

    def apply_discovery_progress(self, payload):
        completed = int(payload["completed"])
        total = max(1, int(payload["total"]))
        self.discovery_progress_var.set(100.0 * completed / total)
        self.discovery_progress_text_var.set(
            f"{completed} / {payload['total']} — "
            f"{payload['baud']} / {payload['config']} / Slave {payload['slave']}"
        )
        self.discovery_found_var.set(f"Encontrados: {payload['found']}")
        self.discovery_status_var.set(
            f"Decorrido {format_duration(payload['elapsed'])} — "
            f"restante ~{format_duration(payload['eta'])}"
        )

    def add_discovery_result(self, payload):
        self.discovery_found_count += 1
        self.discovery_found_var.set(f"Encontrados: {self.discovery_found_count}")
        self.discovery_tree.insert(
            "", "end",
            values=(
                payload["slave"],
                payload["baud"],
                payload["config"],
                payload["fc"],
                payload["result"],
                f"{payload['response_ms']:.1f}" if payload.get("response_ms") is not None else "",
                payload["raw"],
            )
        )

    def finish_discovery_ui(self, payload):
        self.discovery_active = False
        self.busy = False
        self.discovery_stop_event.clear()
        self.discovery_serial = None
        self.discovery_thread = None

        self.discovery_stop_btn.configure(state="disabled")
        self.discovery_clear_btn.configure(state="normal")
        self.discovery_refresh_btn.configure(state="normal")
        self.discovery_port_combo.configure(state="readonly")

        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.restart_btn.configure(state="normal")
        self.set_sniffer_refresh_state("normal")
        self.set_simulation_button_state("normal")

        if payload.get("error"):
            self.discovery_status_var.set("Erro na pesquisa")
            messagebox.showerror("Erro na Bus Slave Finder", payload["error"])
        elif payload.get("stopped"):
            self.discovery_status_var.set(
                f"Pesquisa parada — {payload['found']} encontrados — "
                f"{format_duration(payload['elapsed'])}"
            )
        else:
            self.discovery_progress_var.set(100.0)
            self.discovery_status_var.set(
                f"Pesquisa concluída — {payload['found']} encontrados — "
                f"{format_duration(payload['elapsed'])}"
            )

        self.update_discovery_estimate()
        self.update_discovery_start_state()
        self.update_com_status()

