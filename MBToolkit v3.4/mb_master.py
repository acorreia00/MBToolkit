#!/usr/bin/env python3
"""Modbus RTU master (poll) engine: frames, data formats and scheduling.

This module has no widgets. ``MasterEngine`` owns one open serial port and
serves every poll window over it: Modbus RTU allows a single request on the
bus at a time, so windows are polled in turn according to their scan rate,
with queued writes and "read once" requests served first. Results are
posted to the application's ``event_queue`` like the other workers.
"""

import math
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass

from mb_config import (
    MASTER_RECONNECT_INTERVAL_SECONDS,
    MASTER_MAX_READ_BITS,
    MASTER_MAX_READ_REGISTERS,
    MASTER_MAX_WRITE_BITS,
    MASTER_MAX_WRITE_REGISTERS,
)
from mb_protocol import append_crc, crc_ok, hex_bytes, modbus_rtu_interframe_gap_seconds
from mb_slave_finder import (
    bus_activity_detected,
    cancel_serial_io,
    discovery_bits_per_char,
    write_discovery_request,
)

READ_FUNCTION_CODES = (1, 2, 3, 4)
BIT_FUNCTION_CODES = (1, 2)
WRITABLE_READ_FCS = {1: (5, 15), 3: (6, 16)}  # read window FC -> write FCs

# ---------------------------------------------------------------------------
# Data formats
# ---------------------------------------------------------------------------

BYTE_ORDERS = ("ABCD", "CDAB", "BADC", "DCBA")
# 64-bit orders, in the same sequence: big-endian, word swap (registers in
# reverse order), byte swap inside each register, little-endian.
BYTE_ORDERS_64 = ("ABCDEFGH", "GHEFCDAB", "BADCFEHG", "HGFEDCBA")
WIRE_LETTERS = "ABCDEFGH"

# (key, label, registers per value).  Labels are technical terms and are not
# translated.  Byte order letters follow the wire order of the registers:
# register n = A B, register n+1 = C D, ...; "ABCD" / "ABCDEFGH" is big-endian.
REGISTER_FORMATS = (
    ("int16", "Signed 16-bit", 1),
    ("uint16", "Unsigned 16-bit", 1),
    ("hex16", "Hex 16-bit", 1),
    ("bin16", "Binary 16-bit", 1),
) + tuple(
    (f"{kind}_{order}", f"{label} {order}", 2)
    for kind, label in (
        ("int32", "Signed 32-bit"),
        ("uint32", "Unsigned 32-bit"),
        ("float32", "Float 32-bit"),
    )
    for order in BYTE_ORDERS
) + tuple(
    (f"{kind}_{order}", f"{label} {order}", 4)
    for kind, label in (
        ("int64", "Signed 64-bit"),
        ("uint64", "Unsigned 64-bit"),
        ("float64", "Double 64-bit"),
    )
    for order in BYTE_ORDERS_64
)
FORMAT_LABELS = {key: label for key, label, _size in REGISTER_FORMATS}
FORMAT_KEYS_BY_LABEL = {label: key for key, label, _size in REGISTER_FORMATS}
FORMAT_SIZES = {key: size for key, _label, size in REGISTER_FORMATS}
DEFAULT_FORMAT = "int16"

_STRUCT_CODES = {"int32": ">i", "uint32": ">I", "float32": ">f",
                 "int64": ">q", "uint64": ">Q", "float64": ">d"}


def _value_bytes(registers, order):
    """Reorder the wire bytes of 2 or 4 registers into big-endian value bytes."""
    wire = b"".join(bytes(((r >> 8) & 0xFF, r & 0xFF)) for r in registers)
    return bytes(wire[WIRE_LETTERS.index(letter)] for letter in order)


def _registers_from_value_bytes(value, order):
    wire = bytearray(len(order))
    for index, letter in enumerate(order):
        wire[WIRE_LETTERS.index(letter)] = value[index]
    return [(wire[i] << 8) | wire[i + 1] for i in range(0, len(wire), 2)]


def format_float(value, digits=7):
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "-Inf" if value < 0 else "Inf"
    return f"{value:.{digits}g}"


def decode_value(registers, fmt):
    """Numeric value of one value (None for the Hex/Binary display formats)."""
    if fmt in ("hex16", "bin16"):
        return None
    if FORMAT_SIZES[fmt] == 1:
        value = registers[0] & 0xFFFF
        return value - 0x10000 if fmt == "int16" and value & 0x8000 else value
    kind, order = fmt.split("_")
    return struct.unpack(_STRUCT_CODES[kind], _value_bytes(registers, order))[0]


SCALE_MAX_DECIMALS = 6
SCALE_MAX_UNIT_LENGTH = 12


def validate_scale(raw_min, raw_max, eng_min, eng_max, decimals=1, unit=""):
    """Return a scale dict from user text/numbers; raise ValueError (PT text)."""
    try:
        values = [float(str(v).strip().replace(",", ".")) for v in
                  (raw_min, raw_max, eng_min, eng_max)]
        decimals = int(str(decimals).strip())
    except ValueError:
        raise ValueError("A escala tem de ter números válidos.") from None
    if any(math.isnan(v) or math.isinf(v) for v in values):
        raise ValueError("A escala tem de ter números válidos.")
    if values[0] == values[1]:
        raise ValueError("O bruto mínimo e o bruto máximo têm de ser diferentes.")
    if not 0 <= decimals <= SCALE_MAX_DECIMALS:
        raise ValueError("As casas decimais têm de estar entre 0 e 6.")
    unit = str(unit or "").strip()[:SCALE_MAX_UNIT_LENGTH]
    return {"raw": [values[0], values[1]], "eng": [values[2], values[3]],
            "decimals": decimals, "unit": unit}


def scale_value(number, scale):
    """Linear map from raw units to engineering units through two points."""
    (r1, r2), (e1, e2) = scale["raw"], scale["eng"]
    return e1 + (number - r1) * (e2 - e1) / (r2 - r1)


def unscale_value(value, scale):
    """Inverse of scale_value(): engineering units back to raw units."""
    (r1, r2), (e1, e2) = scale["raw"], scale["eng"]
    if e1 == e2:
        raise ValueError("Esta escala não permite escrever: os valores de engenharia são iguais.")
    return r1 + (value - e1) * (r2 - r1) / (e2 - e1)


def format_scaled(number, scale):
    text = f"{scale_value(number, scale):.{scale['decimals']}f}"
    return f"{text} {scale['unit']}" if scale.get("unit") else text


def format_value(registers, fmt):
    """Display text of one value occupying ``FORMAT_SIZES[fmt]`` registers."""
    if FORMAT_SIZES[fmt] == 1:
        value = registers[0] & 0xFFFF
        if fmt == "int16":
            return str(value - 0x10000 if value & 0x8000 else value)
        if fmt == "uint16":
            return str(value)
        if fmt == "hex16":
            return f"0x{value:04X}"
        return f"{value >> 8:08b} {value & 0xFF:08b}"

    kind, order = fmt.split("_")
    number = struct.unpack(_STRUCT_CODES[kind], _value_bytes(registers, order))[0]
    if kind == "float32":
        return format_float(number, 7)
    if kind == "float64":
        return format_float(number, 15)
    return str(number)


def register_groups(qty, start_address=0, default_fmt=DEFAULT_FORMAT, overrides=None):
    """Split a window's registers into values: [(offset, size, fmt or None)].

    *overrides* maps a PDU address to the format of the value starting there
    (per-address formats). Other registers use *default_fmt*. A value that
    would run past the window, or a default multi-register value cut by an
    override, becomes ``(offset, size, None)`` and is shown as "—".
    """
    overrides = overrides or {}
    default_fmt = default_fmt if default_fmt in FORMAT_SIZES else DEFAULT_FORMAT
    groups = []
    offset = 0
    while offset < qty:
        fmt = overrides.get(start_address + offset)
        if fmt not in FORMAT_SIZES:
            fmt = default_fmt
            size = FORMAT_SIZES[fmt]
            cut = next((j for j in range(offset + 1, min(offset + size, qty))
                        if start_address + j in overrides), None)
            if cut is not None:
                groups.append((offset, cut - offset, None))
                offset = cut
                continue
        size = FORMAT_SIZES[fmt]
        if offset + size > qty:
            groups.append((offset, qty - offset, None))
            break
        groups.append((offset, size, fmt))
        offset += size
    return groups


def format_window_values(registers, start_address=0, default_fmt=DEFAULT_FORMAT,
                         overrides=None, scales=None):
    """Return one display string per register, honouring per-address formats.

    A multi-register value is shown on the row of its first register; the
    other rows of the group are empty. Incomplete groups show "—". *scales*
    maps the PDU address where a value starts to a scale (validate_scale());
    scaled values are shown in engineering units (Hex/Binary stay raw).
    """
    scales = scales or {}
    out = []
    for offset, size, fmt in register_groups(len(registers), start_address,
                                             default_fmt, overrides):
        if fmt is None:
            out.extend(["—"] + [""] * (size - 1))
            continue
        group = registers[offset:offset + size]
        scale = scales.get(start_address + offset)
        number = decode_value(group, fmt) if scale else None
        if scale and number is not None and not (isinstance(number, float)
                                                  and (math.isnan(number) or math.isinf(number))):
            out.append(format_scaled(number, scale))
        else:
            out.append(format_value(group, fmt))
        out.extend([""] * (size - 1))
    return out


def raw_text_for_scaled(value_text, scale, fmt):
    """Convert an engineering value typed by the user into raw text for *fmt*."""
    try:
        value = float(str(value_text).strip().replace(",", "."))
    except ValueError:
        raise ValueError("Valor fora do formato selecionado.") from None
    raw = unscale_value(value, scale)
    if fmt.split("_")[0].startswith("float"):
        return repr(raw)
    return str(int(round(raw)))


def format_register_values(registers, fmt):
    """Display strings for registers that all use one format."""
    return format_window_values(registers, 0, fmt, None)


def _parse_int(text):
    text = str(text).strip().replace(" ", "").replace("_", "")
    lowered = text.lower()
    if lowered.startswith(("0x", "-0x")):
        return int(text, 16)
    if lowered.startswith(("0b", "-0b")):
        return int(text, 2)
    return int(text, 10)


def encode_register_value(text, fmt):
    """Convert one user-entered value to the registers it occupies.

    Raises ValueError with a message key (PT canonical text) when the value
    does not fit the format.
    """
    fmt = fmt if fmt in FORMAT_SIZES else DEFAULT_FORMAT
    text = str(text).strip()
    if not text:
        raise ValueError("Valor vazio.")
    try:
        if fmt == "hex16":
            value = int(text[2:] if text.lower().startswith("0x") else text, 16)
            if not 0 <= value <= 0xFFFF:
                raise ValueError
            return [value]
        if fmt == "bin16":
            value = int(text.replace(" ", "")[2:] if text.lower().startswith("0b")
                        else text.replace(" ", ""), 2)
            if not 0 <= value <= 0xFFFF:
                raise ValueError
            return [value]
        if fmt == "int16":
            value = _parse_int(text)
            if not -0x8000 <= value <= 0x7FFF:
                raise ValueError
            return [value & 0xFFFF]
        if fmt == "uint16":
            value = _parse_int(text)
            if not 0 <= value <= 0xFFFF:
                raise ValueError
            return [value]

        kind, order = fmt.split("_")
        code = _STRUCT_CODES[kind]
        if kind.startswith("float"):
            number = float(text.replace(",", "."))
            raw = struct.pack(code, number)
            if math.isinf(struct.unpack(code, raw)[0]) and not math.isinf(number):
                raise ValueError
        else:
            raw = struct.pack(code, _parse_int(text))
        return _registers_from_value_bytes(raw, order)
    except (ValueError, OverflowError, struct.error):
        raise ValueError("Valor fora do formato selecionado.") from None


def encode_coil_value(text):
    value = str(text).strip().lower()
    if value in ("1", "on", "true"):
        return 1
    if value in ("0", "off", "false"):
        return 0
    raise ValueError("Uma coil só aceita 0 ou 1.")


# ---------------------------------------------------------------------------
# Request frames
# ---------------------------------------------------------------------------

def _u16(value):
    return bytes(((value >> 8) & 0xFF, value & 0xFF))


def read_limit(fc):
    return MASTER_MAX_READ_BITS if fc in BIT_FUNCTION_CODES else MASTER_MAX_READ_REGISTERS


def validate_read_definition(slave, fc, address, qty):
    """Raise ValueError (PT canonical message) for an invalid poll definition."""
    if not 1 <= int(slave) <= 247:
        raise ValueError("O Slave ID de leitura tem de estar entre 1 e 247.")
    if int(fc) not in READ_FUNCTION_CODES:
        raise ValueError("Função de leitura não suportada.")
    if not 0 <= int(address) <= 0xFFFF:
        raise ValueError("O endereço tem de estar entre 0 e 65535.")
    if not 1 <= int(qty) <= read_limit(int(fc)):
        raise ValueError("Quantidade fora do limite desta função.")
    if int(address) + int(qty) > 0x10000:
        raise ValueError("O intervalo de endereços ultrapassa 65535.")


def build_read_request(slave, fc, address, qty):
    validate_read_definition(slave, fc, address, qty)
    return append_crc(bytes((int(slave), int(fc))) + _u16(int(address)) + _u16(int(qty)))


def build_write_request(slave, fc, address, values):
    """Build an FC05/06/15/16 request. *values* are 0/1 bits or 16-bit registers."""
    slave, fc, address = int(slave), int(fc), int(address)
    values = [int(v) for v in values]
    if not 0 <= slave <= 247:
        raise ValueError("O Slave ID de escrita tem de estar entre 0 (broadcast) e 247.")
    if not 0 <= address <= 0xFFFF or address + max(1, len(values)) > 0x10000:
        raise ValueError("O endereço tem de estar entre 0 e 65535.")
    if fc == 5:
        if len(values) != 1:
            raise ValueError("FC05 escreve exatamente uma coil.")
        payload = _u16(address) + (b"\xFF\x00" if values[0] else b"\x00\x00")
    elif fc == 6:
        if len(values) != 1:
            raise ValueError("FC06 escreve exatamente um registo.")
        payload = _u16(address) + _u16(values[0] & 0xFFFF)
    elif fc == 15:
        if not 1 <= len(values) <= MASTER_MAX_WRITE_BITS:
            raise ValueError("Quantidade fora do limite desta função.")
        data = bytearray((len(values) + 7) // 8)
        for index, bit in enumerate(values):
            if bit:
                data[index // 8] |= 1 << (index % 8)
        payload = _u16(address) + _u16(len(values)) + bytes((len(data),)) + bytes(data)
    elif fc == 16:
        if not 1 <= len(values) <= MASTER_MAX_WRITE_REGISTERS:
            raise ValueError("Quantidade fora do limite desta função.")
        data = b"".join(_u16(v & 0xFFFF) for v in values)
        payload = _u16(address) + _u16(len(values)) + bytes((len(data),)) + data
    else:
        raise ValueError("Função de escrita não suportada.")
    return append_crc(bytes((slave, fc)) + payload)


def expected_response_length(request):
    fc = request[1]
    if fc in BIT_FUNCTION_CODES:
        qty = (request[4] << 8) | request[5]
        return 5 + (qty + 7) // 8
    if fc in (3, 4):
        qty = (request[4] << 8) | request[5]
        return 5 + 2 * qty
    return 8  # FC05/06/15/16


# ---------------------------------------------------------------------------
# Response matching
# ---------------------------------------------------------------------------

def find_master_response(buffer, request):
    """Find the response to *request* in the received bytes.

    Returns a dict with ``kind`` RESPONSE or EXCEPTION, the ``frame`` and,
    for reads, the decoded ``values`` (bits or registers); None when no
    complete, CRC-valid, matching frame is present yet. A request echoed by
    an RS485 adapter is skipped for reads because its length and CRC do not
    fit the expected response. For FC05/06 a slave reply is itself an exact
    echo, so an adapter echo cannot be distinguished from it.
    """
    data = bytes(buffer)
    slave, fc = request[0], request[1]
    length = expected_response_length(request)

    for offset in range(len(data)):
        if data[offset] != slave or offset + 2 > len(data):
            continue
        response_fc = data[offset + 1]

        if response_fc == (fc | 0x80) and offset + 5 <= len(data):
            frame = data[offset:offset + 5]
            if crc_ok(frame):
                return {"kind": "EXCEPTION", "frame": frame, "exception_code": frame[2],
                        "values": None}

        if response_fc != fc or offset + length > len(data):
            continue
        frame = data[offset:offset + length]
        if not crc_ok(frame):
            continue

        if fc in READ_FUNCTION_CODES:
            if frame[2] != length - 5:
                continue
            payload = frame[3:-2]
            qty = (request[4] << 8) | request[5]
            if fc in BIT_FUNCTION_CODES:
                values = [(payload[i // 8] >> (i % 8)) & 1 for i in range(qty)]
            else:
                values = [(payload[i] << 8) | payload[i + 1] for i in range(0, len(payload), 2)]
            return {"kind": "RESPONSE", "frame": frame, "exception_code": None, "values": values}

        if fc in (5, 6) and frame != request:
            continue
        if fc in (15, 16) and frame[2:6] != request[2:6]:
            continue
        return {"kind": "RESPONSE", "frame": frame, "exception_code": None, "values": None}

    return None


# ---------------------------------------------------------------------------
# Poll definitions and engine
# ---------------------------------------------------------------------------

@dataclass
class PollDefinition:
    window_id: int
    slave: int
    fc: int
    address: int
    qty: int
    scan_ms: int
    enabled: bool = True

    def request(self):
        return build_read_request(self.slave, self.fc, self.address, self.qty)


class MasterEngine:
    """Serve all poll windows over one serial port, one transaction at a time.

    Order of service: queued writes, then "read once" requests, then the
    enabled poll whose next due time is earliest. A poll becomes due again
    ``scan_ms`` after its previous transaction started (0 = continuously).
    After every transaction the bus is left silent for at least the
    configured delay between polls, and never less than Modbus t3.5.

    With *reopen* (a callable returning a new open serial object), a serial or
    driver failure does not end the session: the engine closes the port, posts
    ``master_reconnecting`` and retries every MASTER_RECONNECT_INTERVAL_SECONDS
    until the port opens again (``master_reconnected``) or the engine stops.
    """

    def __init__(self, ser, event_queue, *, baud, parity, stopbits,
                 response_timeout_ms, delay_ms, serial_module=None,
                 idle_check_seconds=0.0, reopen=None,
                 reconnect_interval_s=MASTER_RECONNECT_INTERVAL_SECONDS):
        self.ser = ser
        self.reopen = reopen
        self.reconnect_interval_s = float(reconnect_interval_s)
        self.event_queue = event_queue
        self.baud = int(baud)
        self.parity = parity
        self.stopbits = stopbits
        self.response_timeout_s = max(0.001, float(response_timeout_ms) / 1000.0)
        gap_s = modbus_rtu_interframe_gap_seconds(
            self.baud, discovery_bits_per_char(parity, stopbits)
        )
        self.delay_s = max(gap_s, float(delay_ms) / 1000.0)
        self.serial_module = serial_module
        self.idle_check_seconds = float(idle_check_seconds)

        self._lock = threading.Lock()
        self._polls = {}           # window_id -> [PollDefinition, next_due]
        self._writes = deque()     # (window_id, request, description)
        self._once = deque()       # window_id
        self._wake = threading.Event()
        self.stop_event = threading.Event()
        self.thread = None

    # -- control (any thread) ----------------------------------------------
    def set_poll(self, definition):
        with self._lock:
            self._polls[definition.window_id] = [definition, 0.0]
        self._wake.set()

    def remove_poll(self, window_id):
        with self._lock:
            self._polls.pop(window_id, None)
            self._once = deque(w for w in self._once if w != window_id)

    def read_once(self, window_id):
        with self._lock:
            if window_id in self._polls and window_id not in self._once:
                self._once.append(window_id)
        self._wake.set()

    def queue_write(self, window_id, request, description=""):
        with self._lock:
            self._writes.append((window_id, bytes(request), description))
        self._wake.set()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self, join_timeout=1.0):
        self.stop_event.set()
        self._wake.set()
        cancel_serial_io(self.ser)
        thread = self.thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

    # -- scheduling ----------------------------------------------------------
    def next_job(self, now=None):
        """Return ('write', item), ('read', definition, once) or ('wait', seconds)."""
        now = time.perf_counter() if now is None else now
        with self._lock:
            if self._writes:
                return ("write", self._writes.popleft())
            while self._once:
                window_id = self._once.popleft()
                entry = self._polls.get(window_id)
                if entry is not None:
                    return ("read", entry[0], True)
            due = [
                (entry[1], window_id)
                for window_id, entry in self._polls.items()
                if entry[0].enabled
            ]
            if not due:
                return ("wait", 0.5)
            next_due, window_id = min(due)
            if next_due > now:
                return ("wait", min(0.5, next_due - now))
            entry = self._polls[window_id]
            entry[1] = now + max(0, entry[0].scan_ms) / 1000.0
            return ("read", entry[0], False)

    # -- worker --------------------------------------------------------------
    def run(self):
        error = None
        try:
            if self.idle_check_seconds > 0:
                traffic = bus_activity_detected(
                    self.ser, self.idle_check_seconds, self.stop_event
                )
                if traffic:
                    error = ("traffic", hex_bytes(traffic[:16]), len(traffic))
                    return
            self.event_queue.put(("master_ready", None))

            while not self.stop_event.is_set():
                try:
                    self._serve_jobs()
                except Exception as exc:  # serial/driver failure
                    if self.stop_event.is_set():
                        break
                    detail = f"{type(exc).__name__}: {exc}"
                    if self.reopen is None:
                        error = ("serial", detail, 0)
                        break
                    if not self._reconnect(detail):
                        break
        except Exception as exc:  # failure during the idle check
            if not self.stop_event.is_set():
                error = ("serial", f"{type(exc).__name__}: {exc}", 0)
        finally:
            self.event_queue.put(("master_stopped", {"error": error}))

    def _serve_jobs(self):
        """Serve writes / reads until stopped; serial errors propagate."""
        while not self.stop_event.is_set():
            job = self.next_job()
            if job[0] == "wait":
                self._wake.wait(job[1])
                self._wake.clear()
                continue

            if job[0] == "write":
                window_id, request, description = job[1]
                result = self.transact(request)
                result.update(kind="write", window_id=window_id, description=description)
            else:
                definition, once = job[1], job[2]
                result = self.transact(definition.request())
                result.update(kind="read", window_id=definition.window_id, once=once,
                              fc=definition.fc, address=definition.address)
            if self.stop_event.is_set():
                return
            self.event_queue.put(("master_result", result))
            if self.stop_event.wait(self.delay_s):
                return

    def _reconnect(self, detail):
        """Close the failed port and reopen it; False when stopped meanwhile."""
        try:
            self.ser.close()
        except Exception:
            pass
        self.event_queue.put(("master_reconnecting", {"error": detail}))
        while not self.stop_event.wait(self.reconnect_interval_s):
            try:
                ser = self.reopen()
            except Exception:
                continue
            self.ser = ser
            self.event_queue.put(("master_reconnected", None))
            return True
        return False

    def transact(self, request):
        """Send one request and wait for its response (no wait for broadcast)."""
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        sent = write_discovery_request(
            self.ser, request, self.baud, self.parity, self.stopbits,
            self.stop_event, self.serial_module,
        )
        # write_discovery_request() returns once the request has left the
        # wire, so response time and timeout count from the end of the request.
        started = time.perf_counter()
        result = {"tx": hex_bytes(request), "rx": "", "status": "stopped",
                  "values": None, "exception_code": None, "response_ms": None}
        if not sent:
            return result
        if request[0] == 0:
            result["status"] = "broadcast"
            return result

        deadline = time.perf_counter() + self.response_timeout_s
        buffer = bytearray()
        while time.perf_counter() < deadline and not self.stop_event.is_set():
            waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
            if waiting:
                buffer.extend(self.ser.read(waiting) or b"")
                found = find_master_response(buffer, request)
                if found is not None:
                    result.update(
                        status="exception" if found["kind"] == "EXCEPTION" else "ok",
                        values=found["values"],
                        exception_code=found["exception_code"],
                        rx=hex_bytes(found["frame"]),
                        response_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    return result
            elif self.stop_event.wait(0.001):
                break

        if self.stop_event.is_set():
            return result
        result["rx"] = hex_bytes(buffer)
        result["status"] = "invalid" if buffer else "timeout"
        return result
