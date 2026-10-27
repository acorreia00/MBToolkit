#!/usr/bin/env python3
"""Modbus RTU slave (simulator) engine: data tables, replies and the serial loop.

This module has no widgets. ``SlaveStore`` holds the data tables of every
simulated Slave ID, the address areas the windows define and the fault
settings of each Slave ID. ``handle_request()`` executes one request frame
against the store and builds the reply, the way a real device would.
``SlaveEngine`` listens on one serial port, assembles the request frames,
answers them and posts what it did to the application's ``event_queue``.
"""

import math
import random
import threading
import time
from dataclasses import dataclass, field

from mb_config import (
    MASTER_MAX_READ_BITS,
    MASTER_MAX_READ_REGISTERS,
    MASTER_MAX_WRITE_BITS,
    MASTER_MAX_WRITE_REGISTERS,
    MASTER_RECONNECT_INTERVAL_SECONDS,
    SLAVE_FAULT_MAX_DELAY_MS,
    SLAVE_RESYNC_SILENCE_MS,
)
from mb_protocol import append_crc, crc_ok, modbus_rtu_interframe_gap_seconds
from mb_slave_finder import cancel_serial_io, discovery_bits_per_char, write_discovery_request

# Data tables of a Modbus device. Labels are technical terms (not translated).
TABLES = ("coils", "discrete", "holding", "input")
TABLE_LABELS = {
    "coils": "Coils",
    "discrete": "Discrete Inputs",
    "holding": "Holding Registers",
    "input": "Input Registers",
}
BIT_TABLES = ("coils", "discrete")
# Table read by FC01–FC04 and written by FC05/06/15/16.
FC_TABLES = {1: "coils", 2: "discrete", 3: "holding", 4: "input",
             5: "coils", 15: "coils", 6: "holding", 16: "holding"}
SUPPORTED_FUNCTION_CODES = (1, 2, 3, 4, 5, 6, 15, 16)
WRITE_FUNCTION_CODES = (5, 6, 15, 16)
# Exception codes offered by the fault simulation.
FAULT_EXCEPTION_CODES = (1, 2, 3, 4, 6)

EXCEPTION_ILLEGAL_FUNCTION = 0x01
EXCEPTION_ILLEGAL_ADDRESS = 0x02
EXCEPTION_ILLEGAL_VALUE = 0x03


# Function code that reads each table (shown with the table name).
TABLE_READ_FC = {"coils": 1, "discrete": 2, "holding": 3, "input": 4}


def table_label(table):
    return TABLE_LABELS.get(table, table)


def table_choice_label(table):
    """Table field text: read function code + name, e.g. "03 Holding Registers"."""
    return f"{TABLE_READ_FC[table]:02d} {TABLE_LABELS[table]}"


# ---------------------------------------------------------------------------
# Fault simulation
# ---------------------------------------------------------------------------

def default_fault():
    return {"delay_ms": 0, "no_response": False, "exception": 0, "bad_crc": False,
            "probability": 100}


def validate_fault(data):
    """Return a clean fault dict from user/workspace data; raise ValueError (PT)."""
    if not isinstance(data, dict):
        raise ValueError("Falha inválida.")
    try:
        delay_ms = int(str(data.get("delay_ms", 0)).strip() or 0)
        probability = int(str(data.get("probability", 100)).strip() or 0)
        exception = int(data.get("exception", 0) or 0)
    except ValueError:
        raise ValueError("A falha tem de ter números válidos.") from None
    if not 0 <= delay_ms <= SLAVE_FAULT_MAX_DELAY_MS:
        raise ValueError("O atraso tem de estar entre 0 e 10000 ms.")
    if not 1 <= probability <= 100:
        raise ValueError("A probabilidade tem de estar entre 1 e 100 %.")
    if exception and exception not in FAULT_EXCEPTION_CODES:
        raise ValueError("Código de exceção não suportado.")
    return {"delay_ms": delay_ms, "no_response": bool(data.get("no_response")),
            "exception": exception, "bad_crc": bool(data.get("bad_crc")),
            "probability": probability}


def fault_active(fault):
    """True when the fault settings change how the slave answers."""
    return bool(fault) and bool(fault.get("delay_ms") or fault.get("no_response")
                                or fault.get("exception") or fault.get("bad_crc"))


# ---------------------------------------------------------------------------
# Automatic values
# ---------------------------------------------------------------------------

# Register values: counter, ramp (sawtooth), sine and random. Bits (Coils /
# Discrete Inputs): toggle and random 0/1.
REGISTER_GENERATORS = ("counter", "ramp", "sine", "random")
BIT_GENERATORS = ("toggle", "random")
GENERATOR_MIN_PERIOD_S = 0.1
GENERATOR_MAX_PERIOD_S = 3600.0


def _number(value, message):
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError:
        raise ValueError(message) from None
    if math.isnan(number) or math.isinf(number):
        raise ValueError(message)
    return number


def validate_generator(data, bits=False):
    """Return a clean automatic-value dict; raise ValueError (PT canonical text).

    ``period_s`` is the full cycle of a ramp / sine and the update interval of
    a counter, random value or toggle. Registers use ``min`` / ``max`` (and
    ``step`` for a counter) in the units shown in the window.
    """
    if not isinstance(data, dict):
        raise ValueError("Valor automático inválido.")
    kind = data.get("kind")
    if kind not in (BIT_GENERATORS if bits else REGISTER_GENERATORS):
        raise ValueError("Tipo de valor automático inválido.")
    period_s = _number(data.get("period_s", 1), "O período tem de ser um número.")
    if not GENERATOR_MIN_PERIOD_S <= period_s <= GENERATOR_MAX_PERIOD_S:
        raise ValueError("O período tem de estar entre 0,1 e 3600 s.")
    result = {"kind": kind, "period_s": period_s}
    if bits:
        return result
    low = _number(data.get("min", 0), "O mínimo e o máximo têm de ser números.")
    high = _number(data.get("max", 100), "O mínimo e o máximo têm de ser números.")
    if low >= high:
        raise ValueError("O mínimo tem de ser menor que o máximo.")
    result.update(min=low, max=high)
    if kind == "counter":
        step = _number(data.get("step", 1), "O passo tem de ser um número.")
        if step <= 0:
            raise ValueError("O passo tem de ser maior que 0.")
        result["step"] = step
    return result


class ValueGenerator:
    """Value of one automatic address as a function of the elapsed time.

    Counter, ramp, sine and toggle are deterministic: ``value(t)`` depends only
    on the seconds since the generator started. A random value changes once
    per period. Wrapping: a counter returns to ``min`` after ``max``; a ramp
    rises from ``min`` to ``max`` in one period and starts again.
    """

    def __init__(self, config, rng=None):
        self.config = dict(config)
        self.rng = rng or random.Random()
        self._random_index = None
        self._random_value = None

    def value(self, elapsed_s):
        c = self.config
        period = c["period_s"]
        cycles = max(0.0, elapsed_s) / period
        kind = c["kind"]
        if kind == "toggle":
            return int(cycles) % 2
        if kind == "random":
            index = int(cycles)
            if index != self._random_index:
                self._random_index = index
                if "min" in c:
                    self._random_value = self.rng.uniform(c["min"], c["max"])
                else:
                    self._random_value = self.rng.randint(0, 1)
            return self._random_value
        low, high = c["min"], c["max"]
        if kind == "ramp":
            return low + (high - low) * (cycles - math.floor(cycles))
        if kind == "sine":
            middle, amplitude = (low + high) / 2.0, (high - low) / 2.0
            return middle + amplitude * math.sin(2.0 * math.pi * cycles)
        # counter
        count = int(math.floor((high - low) / c["step"] + 1e-9)) + 1
        return low + (int(cycles) % count) * c["step"]


# ---------------------------------------------------------------------------
# Data store
# ---------------------------------------------------------------------------

class SlaveStore:
    """Data tables, defined areas and faults of every simulated Slave ID.

    Values live per (Slave ID, table) and address and start at 0. A request
    is valid only for addresses inside an area defined by a window; windows
    over the same addresses share the values. Thread-safe: the engine thread
    reads and writes while the GUI edits.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._values = {}    # (slave, table) -> {address: value}
        self._defined = {}   # (slave, table) -> set of addresses
        self._faults = {}    # slave -> fault dict

    def set_areas(self, areas):
        """Replace the defined areas: iterable of (slave, table, address, qty)."""
        defined = {}
        for slave, table, address, qty in areas:
            defined.setdefault((int(slave), table), set()).update(
                range(int(address), int(address) + int(qty)))
        with self._lock:
            self._defined = defined

    def slave_ids(self):
        with self._lock:
            return {slave for slave, _table in self._defined}

    def covers(self, slave, table, address, qty):
        with self._lock:
            defined = self._defined.get((slave, table))
            return bool(defined) and all(a in defined for a in range(address, address + qty))

    def read(self, slave, table, address, qty):
        with self._lock:
            values = self._values.get((slave, table), {})
            return [values.get(a, 0) for a in range(address, address + qty)]

    def write(self, slave, table, address, values):
        mask = 1 if table in BIT_TABLES else 0xFFFF
        with self._lock:
            target = self._values.setdefault((slave, table), {})
            for offset, value in enumerate(values):
                target[address + offset] = int(value) & mask

    def clear_values(self):
        with self._lock:
            self._values = {}

    def set_fault(self, slave, fault):
        with self._lock:
            if fault_active(fault):
                self._faults[int(slave)] = dict(fault)
            else:
                self._faults.pop(int(slave), None)

    def fault(self, slave):
        with self._lock:
            fault = self._faults.get(slave)
            return dict(fault) if fault else None

    def faults(self):
        with self._lock:
            return {slave: dict(fault) for slave, fault in self._faults.items()}

    def clear_faults(self):
        with self._lock:
            self._faults = {}


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

def request_length(buffer):
    """Length of the request frame starting at buffer[0]; None if not known yet.

    FC01–FC06 requests are 8 bytes; FC15/FC16 carry a byte count in byte 6.
    Unknown function codes have no known length (None).
    """
    if len(buffer) < 2:
        return None
    fc = buffer[1]
    if fc in (1, 2, 3, 4, 5, 6):
        return 8
    if fc in (15, 16):
        return 9 + buffer[6] if len(buffer) >= 7 else None
    return None


def exception_frame(slave, fc, code):
    return append_crc(bytes((slave, fc | 0x80, code)))


@dataclass
class SlaveReply:
    """Outcome of one request: what to send back and what it touched."""
    slave: int
    fc: int
    status: str                 # ok, exception, broadcast, ignored
    table: str = None
    address: int = None
    qty: int = None
    exception_code: int = None
    response: bytes = None
    written: list = field(default_factory=list)   # [(slave, table, address, qty)]


def _u16(data, index):
    return (data[index] << 8) | data[index + 1]


def _parse_request(frame):
    """Return (table, address, qty, values or None) or raise _ExceptionReply."""
    fc = frame[1]
    if fc not in SUPPORTED_FUNCTION_CODES:
        raise _ExceptionReply(EXCEPTION_ILLEGAL_FUNCTION)
    table = FC_TABLES[fc]
    if fc in (15, 16):
        if len(frame) < 9 or len(frame) != 9 + frame[6]:
            raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
    elif len(frame) != 8:
        raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
    address = _u16(frame, 2)

    if fc in (1, 2, 3, 4):
        qty = _u16(frame, 4)
        limit = MASTER_MAX_READ_BITS if fc in (1, 2) else MASTER_MAX_READ_REGISTERS
        if not 1 <= qty <= limit:
            raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
        return table, address, qty, None
    if fc == 5:
        raw = _u16(frame, 4)
        if raw not in (0xFF00, 0x0000):
            raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
        return table, address, 1, [1 if raw else 0]
    if fc == 6:
        return table, address, 1, [_u16(frame, 4)]

    qty, byte_count = _u16(frame, 4), frame[6]
    data = frame[7:-2]
    if fc == 15:
        if not 1 <= qty <= MASTER_MAX_WRITE_BITS or byte_count != (qty + 7) // 8:
            raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
        return table, address, qty, [(data[i // 8] >> (i % 8)) & 1 for i in range(qty)]
    if not 1 <= qty <= MASTER_MAX_WRITE_REGISTERS or byte_count != 2 * qty:
        raise _ExceptionReply(EXCEPTION_ILLEGAL_VALUE)
    return table, address, qty, [_u16(data, 2 * i) for i in range(qty)]


class _ExceptionReply(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def handle_request(store, frame):
    """Execute one CRC-valid request frame and return a SlaveReply.

    Requests for Slave IDs that are not simulated are ``ignored``. Broadcast
    (Slave 0) writes are executed on every simulated Slave ID whose areas
    cover the addresses, and never answered. Errors answer like a real
    device: Exception 01 (function), 02 (address outside the defined areas)
    or 03 (quantity / value / byte count).
    """
    slave, fc = frame[0], frame[1] & 0x7F
    reply = SlaveReply(slave=slave, fc=fc, status="ignored")
    if slave != 0 and slave not in store.slave_ids():
        return reply

    try:
        table, address, qty, values = _parse_request(frame)
        reply.table, reply.address, reply.qty = table, address, qty
        if address + qty > 0x10000:
            raise _ExceptionReply(EXCEPTION_ILLEGAL_ADDRESS)
    except _ExceptionReply as exc:
        if slave == 0:
            reply.status = "broadcast"
            return reply
        reply.status = "exception"
        reply.exception_code = exc.code
        reply.response = exception_frame(slave, fc, exc.code)
        return reply

    if slave == 0:
        reply.status = "broadcast"
        if values is not None:
            for target in sorted(store.slave_ids()):
                if store.covers(target, table, address, qty):
                    store.write(target, table, address, values)
                    reply.written.append((target, table, address, qty))
        return reply

    if not store.covers(slave, table, address, qty):
        reply.status = "exception"
        reply.exception_code = EXCEPTION_ILLEGAL_ADDRESS
        reply.response = exception_frame(slave, fc, EXCEPTION_ILLEGAL_ADDRESS)
        return reply

    reply.status = "ok"
    if values is not None:
        store.write(slave, table, address, values)
        reply.written.append((slave, table, address, qty))
        reply.response = bytes(frame) if fc in (5, 6) else append_crc(bytes(frame[:6]))
        return reply

    current = store.read(slave, table, address, qty)
    if fc in (1, 2):
        data = bytearray((qty + 7) // 8)
        for index, bit in enumerate(current):
            if bit:
                data[index // 8] |= 1 << (index % 8)
    else:
        data = b"".join(bytes(((v >> 8) & 0xFF, v & 0xFF)) for v in current)
    reply.response = append_crc(bytes((slave, fc, len(data))) + bytes(data))
    return reply


def corrupt_crc(frame):
    """Same frame with a wrong CRC (fault simulation)."""
    frame = bytearray(frame)
    frame[-1] ^= 0xFF
    return bytes(frame)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SlaveEngine:
    """Answer the requests of a real master on one serial port.

    Request frames are taken from the received bytes by their length (FC01–06
    and FC15/16 have a known size), so a request is answered as soon as it is
    complete. Bytes that do not form a CRC-valid request (other devices'
    responses, noise, unknown function codes) are discarded one at a time
    until a request lines up, at the latest after SLAVE_RESYNC_SILENCE_MS of
    silence. The echo of our own response from an RS485 adapter is removed.

    Before answering, the engine waits the Modbus t3.5 gap, and the fault
    simulation of the Slave ID (if any) may delay, drop, replace by an
    exception or corrupt the response.

    With *reopen*, a serial failure does not end the session: the engine posts
    ``slave_reconnecting`` and reopens the port like the Master does.
    """

    def __init__(self, ser, event_queue, store, *, baud, parity, stopbits,
                 serial_module=None, reopen=None,
                 reconnect_interval_s=MASTER_RECONNECT_INTERVAL_SECONDS,
                 silence_ms=SLAVE_RESYNC_SILENCE_MS, rng=None):
        self.ser = ser
        self.event_queue = event_queue
        self.store = store
        self.baud = int(baud)
        self.parity = parity
        self.stopbits = stopbits
        self.serial_module = serial_module
        self.reopen = reopen
        self.reconnect_interval_s = float(reconnect_interval_s)
        bits_per_char = discovery_bits_per_char(parity, stopbits)
        self.char_s = bits_per_char / float(max(1, self.baud))
        self.gap_s = modbus_rtu_interframe_gap_seconds(self.baud, bits_per_char)
        self.silence_s = max(self.gap_s, float(silence_ms) / 1000.0)
        self.rng = rng or random.Random()
        self.stop_event = threading.Event()
        self.thread = None
        self._buffer = bytearray()
        self._echo = b""
        self._echo_deadline = 0.0

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self, join_timeout=1.0):
        self.stop_event.set()
        cancel_serial_io(self.ser)
        thread = self.thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

    # -- worker --------------------------------------------------------------
    def run(self):
        error = None
        try:
            self.event_queue.put(("slave_ready", None))
            while not self.stop_event.is_set():
                try:
                    self._listen()
                except Exception as exc:  # serial/driver failure
                    if self.stop_event.is_set():
                        break
                    detail = f"{type(exc).__name__}: {exc}"
                    if self.reopen is None:
                        error = detail
                        break
                    if not self._reconnect(detail):
                        break
        finally:
            self.event_queue.put(("slave_stopped", {"error": error}))

    def _reconnect(self, detail):
        try:
            self.ser.close()
        except Exception:
            pass
        self._buffer.clear()
        self.event_queue.put(("slave_reconnecting", {"error": detail}))
        while not self.stop_event.wait(self.reconnect_interval_s):
            try:
                ser = self.reopen()
            except Exception:
                continue
            self.ser = ser
            self.event_queue.put(("slave_reconnected", None))
            return True
        return False

    def _listen(self):
        """Read and answer until stopped; serial errors propagate."""
        last_rx = time.perf_counter()
        while not self.stop_event.is_set():
            waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
            if waiting:
                data = self._strip_echo(self.ser.read(waiting) or b"")
                last_rx = time.perf_counter()
                if data:
                    self._buffer.extend(data)
                    self.process(final=False)
                continue
            if self._buffer and time.perf_counter() - last_rx >= self.silence_s:
                self.process(final=True)
            if self.stop_event.wait(0.001):
                return

    def process(self, final):
        """Answer every complete request in the buffer.

        *final* (the bus went silent) also resolves what is left: a frame of
        unknown length is answered if the whole rest is CRC-valid, anything
        else is dropped byte by byte.
        """
        buffer = self._buffer
        while buffer and not self.stop_event.is_set():
            length = request_length(buffer)
            if length is None or len(buffer) < length:
                if not final:
                    return
                if length is None and len(buffer) >= 4 and crc_ok(bytes(buffer)):
                    frame = bytes(buffer)
                    buffer.clear()
                    self._answer(frame)
                    return
                del buffer[0]
                continue
            frame = bytes(buffer[:length])
            if crc_ok(frame):
                del buffer[:length]
                self._answer(frame)
            else:
                del buffer[0]

    def _strip_echo(self, data):
        """Remove the RS485 adapter echo of our last response from *data*."""
        if not self._echo:
            return data
        if time.perf_counter() > self._echo_deadline:
            self._echo = b""
            return data
        matched = 0
        while (matched < len(data) and matched < len(self._echo)
               and data[matched] == self._echo[matched]):
            matched += 1
        if matched == len(data) or matched == len(self._echo):
            self._echo = self._echo[matched:]
            return data[matched:]
        self._echo = b""
        return data

    def _answer(self, frame):
        slave = frame[0]
        fault = None
        if slave != 0 and slave in self.store.slave_ids():
            fault = self.store.fault(slave)
            if fault and self.rng.random() * 100.0 >= fault["probability"]:
                fault = None

        if fault and fault["no_response"]:
            reply = SlaveReply(slave=slave, fc=frame[1] & 0x7F, status="no_response")
        elif fault and fault["exception"]:
            code = fault["exception"]
            reply = SlaveReply(slave=slave, fc=frame[1] & 0x7F, status="exception",
                               exception_code=code,
                               response=exception_frame(slave, frame[1] & 0x7F, code))
        else:
            reply = handle_request(self.store, frame)
        if reply.table is None and reply.fc in FC_TABLES and len(frame) >= 6:
            # Fault replies and ignored requests still name the addresses, so
            # the windows over them can count the request.
            reply.table, reply.address = FC_TABLES[reply.fc], _u16(frame, 2)
            reply.qty = 1 if reply.fc in (5, 6) else _u16(frame, 4)

        response = reply.response
        if response is not None and fault and fault["bad_crc"]:
            response = corrupt_crc(response)
        info = {
            "slave": reply.slave, "fc": reply.fc, "table": reply.table,
            "address": reply.address, "qty": reply.qty, "status": reply.status,
            "exception_code": reply.exception_code, "written": list(reply.written),
            "fault": bool(fault), "time": time.time(),
        }
        if response is not None:
            delay_s = self.gap_s + (fault["delay_ms"] / 1000.0 if fault else 0.0)
            if self.stop_event.wait(delay_s):
                return
            # A request that arrived meanwhile belongs to another exchange; a
            # real slave would not answer over it, but answering late is the
            # best a PC can do. Anything received before our reply is dropped.
            self._buffer.clear()
            sent = write_discovery_request(
                self.ser, response, self.baud, self.parity, self.stopbits,
                self.stop_event, self.serial_module,
            )
            if not sent:
                return
            self._echo = bytes(response)
            self._echo_deadline = time.perf_counter() + len(response) * self.char_s + 0.2
            info["response"] = len(response)
        self.event_queue.put(("slave_request", info))
