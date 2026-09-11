#!/usr/bin/env python3
"""Serial-port management, passive capture, simulation and event processing."""

import queue
import random
import threading
import time
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import messagebox

from mb_config import (
    APP_NAME,
    APP_VERSION,
    MIN_PENDING_REQUEST_TIMEOUT_SECONDS,
    MAX_PENDING_REQUEST_TIMEOUT_SECONDS,
    UI_QUEUE_BATCH_SIZE,
    UI_QUEUE_IDLE_INTERVAL_MS,
    UI_QUEUE_BUSY_INTERVAL_MS,
    debug_sim,
)
from mb_protocol import (
    parse_burst,
    build_anomaly_simulation_plan,
    modbus_rtu_interframe_gap_seconds,
)
from mb_slave_finder import cancel_serial_io

class CaptureMixin:
    """Methods for serial capture, COM management and simulation."""

    def set_sniffer_refresh_state(self, state):
        """Apply the same state to both Sniffer COM refresh buttons."""
        for name in ("refresh_a_btn", "refresh_b_btn"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def update_mode_ui(self):
        mode = self.mode_var.get()
        dual = mode == "RS232 dual RX"

        state = "readonly" if dual else "disabled"
        self.port_b_combo.configure(state=state)

        if dual:
            self.mode_help_var.set(
                self.tr("RS232 dual RX: COM A escuta uma direção; COM B escuta a direção oposta.")
            )
        elif mode == "RS232 single RX":
            self.mode_help_var.set(
                self.tr("RS232 single RX: uma COM escuta apenas uma direção da ligação RS232.")
            )
        else:
            self.mode_help_var.set(
                self.tr("RS485 2-wire: uma COM consegue observar pedidos e respostas no mesmo par diferencial.")
            )

        self.update_com_status()

    def update_gap_state(self):
        self.gap_entry.configure(
            state="normal" if self.gap_mode_var.get() == "Manual" else "disabled"
        )

    def get_serial_modules(self):
        try:
            import serial
            from serial.tools import list_ports
            return serial, list_ports
        except ImportError:
            return None, None

    def refresh_ports(self):
        _, list_ports = self.get_serial_modules()
        ports = [p.device for p in list_ports.comports()] if list_ports else []

        self.port_a_combo["values"] = ports
        self.port_b_combo["values"] = ports

        if ports:
            if self.port_a_var.get() not in ports:
                self.port_a_var.set(ports[0])
            if len(ports) > 1:
                if self.port_b_var.get() not in ports or self.port_b_var.get() == self.port_a_var.get():
                    self.port_b_var.set(ports[1])
            elif not self.port_b_var.get():
                self.port_b_var.set("")
        else:
            self.port_a_var.set("")
            self.port_b_var.set("")

        if hasattr(self, "discovery_port_combo"):
            self.discovery_port_combo["values"] = ports
            current_discovery = self.discovery_port_var.get().strip()
            if ports:
                if current_discovery not in ports:
                    self.discovery_port_var.set(ports[0])
            else:
                self.discovery_port_var.set("")
            self.update_discovery_start_state()

        self.update_com_status()

    def detected_ports(self):
        """Return the set of COM device names currently reported by Windows/pyserial."""
        _, list_ports = self.get_serial_modules()
        if list_ports is None:
            return set()
        try:
            return {p.device for p in list_ports.comports()}
        except Exception:
            return set()

    def port_status_text(self, label, port, enabled=True):
        if not enabled:
            return f"{label} - {self.tr('Não Utilizada')}"
        if not port:
            return f"{label} - {self.tr('Não selecionada')}"

        ser = self.serial_by_port.get(port)
        if ser is not None:
            try:
                if ser.is_open:
                    return f"{label} - {self.tr('Aberta')}"
            except Exception:
                pass

        if port in self.detected_ports():
            return f"{label} - {self.tr('Detetada')}"
        return f"{label} - {self.tr('Não detetada')}"

    def update_com_status(self):
        """
        Update COM status without opening/probing a port.

        Status means:
          - Aberta: currently opened by MBSniffer
          - Detetada: reported by Windows/pyserial, but not opened by MBSniffer
          - Não detetada: selected name is no longer reported by the OS
        """
        if not hasattr(self, "port_a_status_var"):
            return

        mode = self.mode_var.get() if hasattr(self, "mode_var") else "RS485 2-wire"
        dual = mode == "RS232 dual RX"
        self.port_a_status_var.set(
            self.port_status_text("COM A", self.port_a_var.get().strip(), True)
        )
        self.port_b_status_var.set(
            self.port_status_text("COM B", self.port_b_var.get().strip(), dual)
        )

    def poll_com_status(self):
        if self._closing:
            return
        try:
            self.update_com_status()
            if hasattr(self, "stat_requests_var"):
                self.update_stats_labels()
        finally:
            if not self._closing:
                try:
                    self.after(1000, self.poll_com_status)
                except tk.TclError:
                    pass

    def selected_port_plan(self):
        """Return [(channel, port), ...] for the currently selected physical mode."""
        mode = self.mode_var.get()
        port_a = self.port_a_var.get().strip()
        port_b = self.port_b_var.get().strip()

        if not port_a:
            raise ValueError("Select COM A." if self.current_language == "English" else "Seleciona a COM A.")

        plan = [("BUS" if mode == "RS485 2-wire" else "A→B", port_a)]

        if mode == "RS232 dual RX":
            if not port_b:
                raise ValueError("Select COM B as well." if self.current_language == "English" else "Seleciona também a COM B.")
            if port_a == port_b:
                raise ValueError("COM A and COM B must be different." if self.current_language == "English" else "COM A e COM B têm de ser diferentes.")
            plan.append(("B→A", port_b))

        return plan

    def open_selected_ports(self, serial, config):
        """Open the selected capture ports and return [(channel, serial_obj), ...]."""
        opened = []
        try:
            for channel, port in self.selected_port_plan():
                opened.append((channel, self.open_serial_port(serial, port, config)))
            return opened
        except Exception:
            for _, ser_obj in opened:
                try:
                    ser_obj.close()
                except Exception:
                    pass
            raise

    def install_opened_ports(self, opened):
        self.serial_objects = [ser_obj for _, ser_obj in opened]
        self.serial_by_port = {
            ser_obj.port: ser_obj for _, ser_obj in opened if getattr(ser_obj, "port", None)
        }
        self.update_com_status()

    def start_reader_threads(self, opened, gap_ms):
        self.reader_threads = []
        generation = self.reader_generation
        for channel, ser_obj in opened:
            t = threading.Thread(
                target=self.reader_loop,
                args=(ser_obj, gap_ms, channel, generation),
                daemon=True
            )
            self.reader_threads.append(t)
            t.start()

    def restart_com_port(self):
        """
        Close and reopen the selected COM port(s).

        During an active capture the capture continues in the same session/log.
        When stopped, the selected COM port(s) are opened and closed once as a
        restart/test of the application's serial handle.
        """
        if self.busy and not self.capture_active:
            return
        if self.restart_in_progress:
            return

        serial, _ = self.get_serial_modules()
        if serial is None:
            messagebox.showerror(self.tr("pyserial em falta"), "pyserial is not installed." if self.current_language == "English" else "pyserial não está instalado.")
            return

        try:
            config = self.serial_config(serial)
            gap_ms = self.calculated_gap_ms()
            self.selected_port_plan()
        except Exception as exc:
            messagebox.showerror(self.tr("Porta COM"), str(exc))
            return

        self.restart_in_progress = True
        self.restart_btn.configure(state="disabled")

        if not self.capture_active:
            opened = []
            try:
                opened = self.open_selected_ports(serial, config)
                self.install_opened_ports(opened)
                self.update_idletasks()
            except Exception as exc:
                messagebox.showerror(self.tr("Reiniciar COM"), (f"Could not restart the COM port:\n\n{exc}" if self.current_language == "English" else f"Não foi possível reiniciar a porta COM:\n\n{exc}"))
            finally:
                for _, ser_obj in opened:
                    try:
                        ser_obj.close()
                    except Exception:
                        pass
                self.serial_objects = []
                self.serial_by_port = {}
                self.restart_in_progress = False
                self.restart_btn.configure(state="normal")
                self.refresh_ports()
            return

        # Active capture: stop only the current serial-reader generation.
        self.status_var.set(self.tr("● A reiniciar COM"))
        self.reader_generation += 1
        self.stop_event.set()

        for thread in list(self.reader_threads):
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass

        for ser_obj in list(self.serial_objects):
            try:
                ser_obj.close()
            except Exception:
                pass

        self.reader_threads = []
        self.serial_objects = []
        self.serial_by_port = {}
        self.stop_event.clear()

        try:
            opened = self.open_selected_ports(serial, config)
        except Exception as exc:
            self.restart_in_progress = False
            self.capture_active = False
            self.busy = False
            self.stop_event.set()
            self.finish_capture_ui()
            self.update_com_status()
            messagebox.showerror(
                self.tr("Reiniciar COM"),
                (f"Could not reopen the COM port. Capture was stopped.\n\n{exc}" if self.current_language == "English" else f"Não foi possível reabrir a porta COM. A captura foi parada.\n\n{exc}")
            )
            return

        self.install_opened_ports(opened)
        self.stop_event.clear()
        self.start_reader_threads(opened, gap_ms)
        self.queue_log_note(
            f"# COM restart: {datetime.now().isoformat(timespec='milliseconds')}\n"
        )
        self.status_var.set(self.tr("● A capturar"))
        self.restart_in_progress = False
        self.restart_btn.configure(state="normal")
        self.update_com_status()

    def set_simulation_button_state(self, state):
        """Change Simulation button state only when the optional button exists."""
        if self.sim_btn is not None:
            self.sim_btn.configure(state=state)

    def selected_pending_timeout_seconds(self):
        try:
            value = float(self.pending_timeout_var.get().strip().replace(",", "."))
        except ValueError:
            raise ValueError("Invalid Pending timeout." if self.current_language == "English" else "Pending timeout inválido.")

        if not (
            MIN_PENDING_REQUEST_TIMEOUT_SECONDS
            <= value
            <= MAX_PENDING_REQUEST_TIMEOUT_SECONDS
        ):
            raise ValueError(
                (
                    f"Pending timeout must be between {MIN_PENDING_REQUEST_TIMEOUT_SECONDS:g} and {MAX_PENDING_REQUEST_TIMEOUT_SECONDS:g} seconds."
                    if self.current_language == "English"
                    else "Pending timeout deve estar entre "
                    f"{MIN_PENDING_REQUEST_TIMEOUT_SECONDS:g} e "
                    f"{MAX_PENDING_REQUEST_TIMEOUT_SECONDS:g} segundos."
                )
            )

        return value

    def calculated_gap_ms(self):
        if self.gap_mode_var.get() == "Manual":
            value = float(self.gap_ms_var.get().replace(",", "."))
            if value <= 0:
                raise ValueError("Invalid manual Frame gap." if self.current_language == "English" else "Frame gap manual inválido.")
            return value

        baud = int(self.baud_var.get())
        data_bits = int(self.data_var.get())
        parity_bits = 0 if self.parity_var.get() == "None" else 1
        stop_bits = float(self.stop_var.get())
        bits_per_char = 1 + data_bits + parity_bits + stop_bits
        return modbus_rtu_interframe_gap_seconds(baud, bits_per_char) * 1000.0

    def serial_config(self, serial):
        byte_map = {
            5: serial.FIVEBITS, 6: serial.SIXBITS,
            7: serial.SEVENBITS, 8: serial.EIGHTBITS,
        }
        parity_map = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
            "Mark": serial.PARITY_MARK,
            "Space": serial.PARITY_SPACE,
        }
        stop_map = {
            "1": serial.STOPBITS_ONE,
            "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            "2": serial.STOPBITS_TWO,
        }
        return {
            "baudrate": int(self.baud_var.get()),
            "bytesize": byte_map[int(self.data_var.get())],
            "parity": parity_map[self.parity_var.get()],
            "stopbits": stop_map[self.stop_var.get()],
        }

    def open_serial_port(self, serial, port, config):
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = config["baudrate"]
        ser.bytesize = config["bytesize"]
        ser.parity = config["parity"]
        ser.stopbits = config["stopbits"]
        ser.timeout = 0
        ser.write_timeout = 0
        ser.xonxoff = False
        ser.rtscts = False
        ser.dsrdtr = False

        try:
            ser.rts = False
            ser.dtr = False
        except Exception:
            pass

        ser.open()

        try:
            ser.rts = False
            ser.dtr = False
        except Exception:
            pass

        try:
            ser.reset_input_buffer()
        except Exception:
            pass

        return ser

    def start_capture(self):
        if self.busy:
            return

        serial, _ = self.get_serial_modules()
        if serial is None:
            messagebox.showerror(
                self.tr("pyserial em falta"),
                ("pyserial is not installed.\n\nbuild_exe.bat includes it automatically in the EXE." if self.current_language == "English" else "pyserial não está instalado.\n\nO build_exe.bat inclui-o automaticamente no EXE.")
            )
            return

        mode = self.mode_var.get()
        port_a = self.port_a_var.get().strip()
        port_b = self.port_b_var.get().strip()

        try:
            gap_ms = self.calculated_gap_ms()
            pending_timeout_s = self.selected_pending_timeout_seconds()
            config = self.serial_config(serial)
            opened = self.open_selected_ports(serial, config)
        except Exception as exc:
            messagebox.showerror(self.tr("Erro ao abrir porta"), str(exc))
            self.update_com_status()
            return

        self.reader_generation += 1
        self.install_opened_ports(opened)
        self.reader_threads = []
        self.stop_event.clear()
        self.busy = True
        self.capture_active = True
        self.metrics.pending_timeout_seconds = pending_timeout_s
        self.reset_session_metrics()

        capture_started = datetime.now()
        log_header = (
            f"# {APP_NAME} v{APP_VERSION}\n"
            f"# Start: {capture_started.isoformat(timespec='milliseconds')}\n"
            f"# Mode: {mode}\n"
            f"# COM A: {port_a}\n"
            + (f"# COM B: {port_b}\n" if mode == "RS232 dual RX" else "")
            + f"# Serial: baud={self.baud_var.get()} data={self.data_var.get()} "
              f"parity={self.parity_var.get()} stop={self.stop_var.get()} "
              f"frame_gap_ms={gap_ms:.3f}\n"
            + f"# Pending timeout: {pending_timeout_s:g} s\n"
            + "# Passive/read-only: no Serial.write() calls.\n#\n"
        )
        self.prepare_log_session("MBSniffer", capture_started, log_header)

        self.status_var.set(self.tr("● A capturar"))
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.restart_btn.configure(state="normal")
        self.set_simulation_button_state("disabled")
        self.set_sniffer_refresh_state("disabled")

        self.start_reader_threads(opened, gap_ms)
        self.update_com_status()

    def reader_loop(self, ser, gap_ms, channel, generation):
        gap_s = gap_ms / 1000.0
        poll_sleep = min(max(gap_s / 8.0, 0.0002), 0.001)

        buffer = bytearray()
        buffer_wall = None
        last_rx = None

        try:
            while not self.stop_event.is_set():
                waiting = ser.in_waiting

                if waiting:
                    chunk = ser.read(waiting)
                    if chunk:
                        if not buffer:
                            buffer_wall = datetime.now()
                        buffer.extend(chunk)
                        last_rx = time.perf_counter()

                elif buffer and last_rx is not None:
                    if (time.perf_counter() - last_rx) >= gap_s:
                        ts = (
                            buffer_wall.strftime("%H:%M:%S.%f")[:-3]
                            if buffer_wall else datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        )
                        event_epoch = (
                            buffer_wall.timestamp() if buffer_wall else time.time()
                        )
                        for row in parse_burst(bytes(buffer), ts, channel, event_epoch):
                            self.event_queue.put(("frame", row))
                        buffer.clear()
                        buffer_wall = None
                        last_rx = None

                time.sleep(poll_sleep)

        except Exception as exc:
            if not self.stop_event.is_set():
                self.event_queue.put(("error", (generation, channel, str(exc))))

        finally:
            if buffer:
                ts = (
                    buffer_wall.strftime("%H:%M:%S.%f")[:-3]
                    if buffer_wall else datetime.now().strftime("%H:%M:%S.%f")[:-3]
                )
                event_epoch = (
                    buffer_wall.timestamp() if buffer_wall else time.time()
                )
                for row in parse_burst(bytes(buffer), ts, channel, event_epoch):
                    self.event_queue.put(("frame", row))

            try:
                ser.close()
            except Exception:
                pass
            self.event_queue.put(("reader_stopped", (generation, channel)))

    def stop_capture(self):
        if self.capture_active:
            self.status_var.set(self.tr("● A parar"))
        self.stop_event.set()

    def run_simulation(self):
        if debug_sim != 1:
            return

        if self.busy:
            return

        try:
            pending_timeout_s = self.selected_pending_timeout_seconds()
        except Exception as exc:
            messagebox.showerror(self.tr("Configuração inválida"), str(exc))
            return

        self.busy = True
        self.metrics.pending_timeout_seconds = pending_timeout_s
        self.reset_session_metrics()

        # Simulation is GUI-only. Never create or write a .txt log.
        self.close_log()

        self.status_var.set(self.tr("● A simular"))
        self.start_btn.configure(state="disabled")
        self.restart_btn.configure(state="disabled")
        self.set_simulation_button_state("disabled")
        self.set_sniffer_refresh_state("disabled")

        def worker():
            try:
                # Simulation always exercises the complete diagnostic scenario.
                # "Realçar resultados" affects only Treeview row colouring; it
                # never changes which simulated frames are generated.
                rng = random.Random()
                plan = build_anomaly_simulation_plan(rng=rng)

                for tx in plan["transactions"]:
                    time.sleep(rng.uniform(0.025, 0.085))

                    request_now = datetime.now()
                    request_ts = request_now.strftime("%H:%M:%S.%f")[:-3]

                    request_channel = "SIM"

                    for row in parse_burst(
                        tx["request"], request_ts, request_channel,
                        request_now.timestamp()
                    ):
                        self.event_queue.put(("frame", row))

                    outcome = tx.get("outcome", "response")

                    if outcome == "timeout":
                        # Do not sleep for the user-configured Pending timeout.
                        # The queue event expires this exact pending request
                        # through SessionMetrics and marks the REQUEST row.
                        self.event_queue.put((
                            "simulation_force_timeout",
                            (tx["slave"], tx["fc"]),
                        ))
                        continue

                    if outcome == "slow":
                        time.sleep(plan.get("slow_delay_seconds", 0.65))
                    else:
                        time.sleep(rng.uniform(0.018, 0.095))

                    reply_now = datetime.now()
                    reply_ts = reply_now.strftime("%H:%M:%S.%f")[:-3]
                    reply_channel = "SIM"

                    reply = tx.get("reply")
                    if reply:
                        for row in parse_burst(
                            reply, reply_ts, reply_channel,
                            reply_now.timestamp()
                        ):
                            self.event_queue.put(("frame", row))

                # One RAW row completes the diagnostic scenario. With anomaly
                # highlighting OFF it remains a normal, uncoloured RAW row;
                # with highlighting ON the same row receives the RAW colour.
                raw_now = datetime.now()
                raw_ts = raw_now.strftime("%H:%M:%S.%f")[:-3]
                raw_channel = "SIM"
                for row in parse_burst(
                    plan["raw_noise"],
                    raw_ts,
                    raw_channel,
                    raw_now.timestamp(),
                ):
                    self.event_queue.put(("frame", row))

                self.event_queue.put(("simulation_done", None))

            except Exception as exc:
                # Never leave the GUI permanently busy if the simulation worker
                # fails unexpectedly.
                self.event_queue.put((
                    "simulation_error",
                    f"{type(exc).__name__}: {exc}"
                ))

        threading.Thread(target=worker, daemon=True).start()

    def process_queue(self):
        if self._closing:
            return

        delay = UI_QUEUE_IDLE_INTERVAL_MS
        try:
            events = []
            for _ in range(UI_QUEUE_BATCH_SIZE):
                try:
                    events.append(self.event_queue.get_nowait())
                except queue.Empty:
                    break

            frame_batch = []

            def flush_frames():
                nonlocal frame_batch
                if frame_batch:
                    self.add_frame_rows_batch(frame_batch)
                    frame_batch = []

            for event, payload in events:
                if event == "frame":
                    frame_batch.append(payload)
                    continue

                flush_frames()

                if event == "error":
                    generation, channel, error_text = payload
                    if generation != self.reader_generation:
                        continue
                    # Stop all readers in this capture generation after any
                    # reader failure; never leave a half-alive dual-RX capture.
                    self.stop_event.set()
                    self.update_com_status()
                    messagebox.showerror(
                        self.tr("Erro de captura"), f"{channel}: {error_text}"
                    )

                elif event == "reader_stopped":
                    generation, _channel = payload
                    if generation != self.reader_generation:
                        continue
                    if not any(t.is_alive() for t in self.reader_threads):
                        self.finish_capture_ui()

                elif event == "simulation_force_timeout":
                    slave, fc = payload
                    expired = self.metrics.force_timeout(slave, fc)
                    if expired:
                        self.mark_timed_out_records(expired, rerender=True)
                    self.update_stats_labels()

                elif event == "simulation_done":
                    self.busy = False
                    self.status_var.set(self.tr("● Simulação concluída"))
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.restart_btn.configure(state="normal")
                    self.set_simulation_button_state("normal")
                    self.set_sniffer_refresh_state("normal")
                    self.close_log()
                    self.update_com_status()

                elif event == "simulation_error":
                    self.busy = False
                    self.status_var.set(self.tr("● Erro na simulação"))
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.restart_btn.configure(state="normal")
                    self.set_simulation_button_state("normal")
                    self.set_sniffer_refresh_state("normal")
                    self.close_log()
                    self.update_com_status()
                    messagebox.showerror(self.tr("Erro na simulação"), str(payload))

                elif event == "discovery_status":
                    self.discovery_status_var.set(str(payload))

                elif event == "discovery_progress":
                    self.apply_discovery_progress(payload)

                elif event == "discovery_found":
                    self.add_discovery_result(payload)

                elif event == "discovery_done":
                    self.finish_discovery_ui(payload)

            flush_frames()

            if self.metrics.expire_pending(time.time()):
                expired = self.metrics.pop_expired_requests()
                if expired:
                    self.mark_timed_out_records(expired, rerender=True)
                self.update_stats_labels()

            if (
                self.capture_active
                and not self.restart_in_progress
                and self.stop_event.is_set()
                and self.reader_threads
                and not any(t.is_alive() for t in self.reader_threads)
                and self.stop_btn["state"] != "disabled"
            ):
                self.finish_capture_ui()

            delay = (
                UI_QUEUE_BUSY_INTERVAL_MS
                if len(events) >= UI_QUEUE_BATCH_SIZE
                else UI_QUEUE_IDLE_INTERVAL_MS
            )

        except tk.TclError:
            if self._closing:
                return
            traceback.print_exc()
            delay = UI_QUEUE_IDLE_INTERVAL_MS

        except Exception as exc:
            # One unexpected event/UI error must not permanently kill the
            # periodic queue callback and make the application appear frozen.
            traceback.print_exc()
            if not self._process_queue_error_shown and not self._closing:
                self._process_queue_error_shown = True
                try:
                    messagebox.showerror(
                        self.tr("Erro interno"),
                        (("An error occurred while processing interface events. Processing will continue.\n\n") if self.current_language == "English" else "Ocorreu um erro ao processar eventos da interface. O processamento continuará.\n\n")
                        + f"{type(exc).__name__}: {exc}"
                    )
                except Exception:
                    pass
            delay = UI_QUEUE_IDLE_INTERVAL_MS

        finally:
            if not self._closing:
                try:
                    self.after(delay, self.process_queue)
                except tk.TclError:
                    pass

    def on_close(self):
        if self._closing:
            return

        try:
            saver = getattr(self, "save_current_ui_settings", None)
            if callable(saver):
                saver()
        except Exception:
            pass

        self._closing = True
        self.busy = False
        self.capture_active = False
        self.stop_event.set()
        self.discovery_stop_event.set()

        # Cancel driver I/O before joining workers so shutdown is not held up
        # by a serial read/write timeout.
        cancel_serial_io(self.discovery_serial)

        if self.discovery_thread is not None:
            try:
                if self.discovery_thread.is_alive():
                    self.discovery_thread.join(timeout=0.8)
            except Exception:
                pass

        if self.discovery_serial is not None:
            try:
                self.discovery_serial.close()
            except Exception:
                pass
        self.discovery_serial = None

        for ser in list(self.serial_objects):
            cancel_serial_io(ser)

        for thread in list(self.reader_threads):
            try:
                if thread.is_alive():
                    thread.join(timeout=0.5)
            except Exception:
                pass

        for ser in list(self.serial_objects):
            try:
                ser.close()
            except Exception:
                pass

        self.close_log()
        try:
            self.destroy()
        except tk.TclError:
            pass

