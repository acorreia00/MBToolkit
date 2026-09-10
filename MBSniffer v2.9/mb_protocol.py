#!/usr/bin/env python3
"""Modbus RTU parsing, CRC, transaction metrics and simulation helpers."""

import math
import random
import time
from collections import defaultdict, deque

from mb_config import (
    MODBUS_EXCEPTION_CODES,
    PENDING_REQUEST_TIMEOUT_SECONDS,
    SIMULATION_FUNCTION_CODES,
    SIMULATION_EXCEPTION_CODES,
    SLOW_RESPONSE_THRESHOLD_MS,
)

def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

def crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    expected = crc16_modbus(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    return expected == received

def append_crc(payload: bytes) -> bytes:
    crc = crc16_modbus(payload)
    return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))

def hex_bytes(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

def plausible_request_qty(fc: int, qty: int) -> bool:
    if fc in (1, 2):
        return 1 <= qty <= 2000
    if fc in (3, 4):
        return 1 <= qty <= 125
    return True

def _plausible_unit_id(value: int) -> bool:
    """Return True for Modbus RTU unit addresses that can appear on the wire."""
    try:
        return 0 <= int(value) <= 247
    except (TypeError, ValueError):
        return False


def _candidate_prefixes_at(buf, start=0):
    """Return structurally plausible known-frame lengths at *start*."""
    remaining = len(buf) - int(start)
    if remaining < 2:
        return []

    unit = buf[start]
    if not _plausible_unit_id(unit):
        return []

    fc = buf[start + 1]
    out = []

    if fc & 0x80:
        # Exception responses use FC | 0x80 and have a fixed five-byte length.
        base_fc = fc & 0x7F
        if base_fc in (1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 22, 23):
            out.append((5, "EXCEPTION"))
        return out

    if fc in (1, 2, 3, 4):
        if remaining >= 6:
            qty = (buf[start + 4] << 8) | buf[start + 5]
            if plausible_request_qty(fc, qty):
                out.append((8, "REQUEST"))

        if remaining >= 3:
            byte_count = buf[start + 2]
            resp_len = 5 + byte_count
            if fc in (3, 4):
                if byte_count > 0 and byte_count % 2 == 0:
                    out.append((resp_len, "RESPONSE"))
            elif byte_count > 0:
                out.append((resp_len, "RESPONSE"))

    elif fc in (5, 6, 8):
        out.append((8, "REQ/RESP"))

    elif fc == 7:
        # FC07 request: Slave + FC + CRC = 4 bytes.
        # FC07 response: Slave + FC + Status + CRC = 5 bytes.
        if remaining >= 5:
            out.append((5, "RESPONSE"))
        out.append((4, "REQUEST"))

    elif fc in (15, 16):
        out.append((8, "RESPONSE"))
        if remaining >= 7:
            byte_count = buf[start + 6]
            if byte_count > 0:
                out.append((9 + byte_count, "REQUEST"))

    elif fc == 22:
        out.append((10, "REQ/RESP"))

    elif fc == 23:
        if remaining >= 3:
            bc = buf[start + 2]
            if bc > 0 and bc % 2 == 0:
                out.append((5 + bc, "RESPONSE"))
        if remaining >= 11:
            bc = buf[start + 10]
            if bc > 0:
                out.append((13 + bc, "REQUEST"))

    cleaned = []
    seen = set()
    for length, kind in out:
        if 4 <= length <= 260 and (length, kind) not in seen:
            seen.add((length, kind))
            cleaned.append((length, kind))
    return cleaned


def candidate_prefixes(buf: bytes):
    """Compatibility wrapper for callers/tests that inspect offset zero."""
    return _candidate_prefixes_at(buf, 0)


def _crc_ok_at(buf, start: int, length: int) -> bool:
    """CRC check without copying the whole remaining capture buffer."""
    if length < 4 or start < 0 or start + length > len(buf):
        return False
    end = start + length
    expected = crc16_modbus(memoryview(buf)[start:end - 2])
    received = buf[end - 2] | (buf[end - 1] << 8)
    return expected == received


def find_valid_prefix(buf: bytes, start=0):
    """Find a CRC-valid, structurally recognised Modbus frame at *start*."""
    for length, kind in _candidate_prefixes_at(buf, start):
        if start + length <= len(buf) and _crc_ok_at(buf, start, length):
            return length, kind
    return None


def guess_invalid_whole_frame(buf: bytes):
    """Classify a complete known-shape frame whose CRC is invalid."""
    if len(buf) < 4 or not _plausible_unit_id(buf[0]):
        return None
    for length, kind in _candidate_prefixes_at(buf, 0):
        if len(buf) == length:
            return kind
    return None


def _unknown_whole_frame_is_valid(buf: bytes) -> bool:
    """Conservative fallback for one unsupported FC occupying the whole burst.

    Unknown frames cannot be length-validated from their FC, so CRC-only
    recognition is deliberately restricted to the complete remaining burst.
    It is never used while scanning arbitrary offsets for resynchronisation.
    """
    if not 4 <= len(buf) <= 260:
        return False
    if not _plausible_unit_id(buf[0]):
        return False
    if _candidate_prefixes_at(buf, 0):
        return False
    return crc_ok(buf)


def split_capture_buffer(data: bytes):
    results = []
    buf = bytearray(data)

    while buf:
        match = find_valid_prefix(buf, 0)
        if match:
            length, kind = match
            results.append((bytes(buf[:length]), kind, "OK"))
            del buf[:length]
            continue

        # Search the full remaining burst, but only for structurally recognised
        # Modbus frames. The former generic CRC scan tried up to 256 candidate
        # lengths at every offset and became very slow on long noise bursts.
        # Restricting resynchronisation to known frame shapes makes the scan
        # effectively linear in the burst size and strongly reduces accidental
        # CRC-only "phantom" frames in random noise.
        found_offset = None
        search_limit = max(len(buf) - 4, 0)
        for offset in range(1, search_limit + 1):
            if find_valid_prefix(buf, offset):
                found_offset = offset
                break

        if found_offset is not None:
            prefix = bytes(buf[:found_offset])

            # If the bytes immediately before the recovered frame are exactly a
            # recognised Modbus frame shape, preserve the useful CRC diagnosis
            # instead of hiding it as RAW/UNSYNC. Otherwise they are genuinely
            # unsynchronised bytes and remain RAW.
            guessed = guess_invalid_whole_frame(prefix)
            if guessed:
                results.append((prefix, guessed, "ERROR"))
            else:
                results.append((prefix, "RAW/UNSYNC", "UNKNOWN"))
            del buf[:found_offset]
            continue

        guessed = guess_invalid_whole_frame(bytes(buf))
        if guessed:
            results.append((bytes(buf), guessed, "ERROR"))
        elif _unknown_whole_frame_is_valid(bytes(buf)):
            results.append((bytes(buf), "UNKNOWN", "OK"))
        else:
            results.append((bytes(buf), "RAW/UNPARSED", "UNKNOWN"))
        break

    return results

def decode_frame(frame: bytes, kind_hint: str):
    info = {
        "kind": kind_hint,
        "slave": "",
        "fc": "",
        "details": "",
        "pdu_address": None,
        "one_based": None,
        "qty": None,
    }

    if str(kind_hint).startswith("RAW"):
        info["details"] = f"{len(frame)} raw bytes"
        return info

    if len(frame) < 2:
        info["details"] = "Raw bytes"
        return info

    slave = frame[0]
    fc = frame[1]
    info["slave"] = str(slave)
    info["fc"] = f"{fc:02X}"

    if fc & 0x80:
        info["kind"] = "EXCEPTION"
        code = frame[2] if len(frame) >= 3 else None

        if code is None:
            info["details"] = "Exception"
            return info

        exception_info = MODBUS_EXCEPTION_CODES.get(code)
        if exception_info is not None:
            name, _description = exception_info
            info["details"] = f"Exception 0x{code:02X} — {name}"
        else:
            info["details"] = f"Exception 0x{code:02X} — Unknown/Reserved Exception"
        return info

    if fc in (1, 2, 3, 4):
        if kind_hint == "REQUEST" and len(frame) >= 8:
            start_addr = (frame[2] << 8) | frame[3]
            qty = (frame[4] << 8) | frame[5]
            info["pdu_address"] = start_addr
            info["one_based"] = start_addr + 1
            info["qty"] = qty
            info["details"] = (
                f"PDU Address={start_addr}  1-based={start_addr + 1}  Qty={qty}"
            )
            return info

        if kind_hint == "RESPONSE" and len(frame) >= 5:
            bc = frame[2]
            details = f"ByteCount={bc}"
            if fc in (3, 4) and bc % 2 == 0 and len(frame) >= 5 + bc:
                data = frame[3:3+bc]
                regs = [(data[i] << 8) | data[i+1] for i in range(0, len(data), 2)]
                details += f"  Registos={regs}"
            info["details"] = details
            return info

    if fc in (5, 6, 8) and len(frame) >= 8:
        addr = (frame[2] << 8) | frame[3]
        value = (frame[4] << 8) | frame[5]
        info["pdu_address"] = addr
        info["one_based"] = addr + 1
        info["details"] = (
            f"PDU Address={addr}  1-based={addr + 1}  Value=0x{value:04X}"
        )
        return info

    if fc == 7:
        if kind_hint == "REQUEST":
            info["details"] = "Read Exception Status"
        elif kind_hint == "RESPONSE" and len(frame) >= 5:
            info["details"] = f"Status=0x{frame[2]:02X}"
        else:
            info["details"] = "Read Exception Status"
        return info

    if fc in (15, 16):
        if kind_hint == "REQUEST" and len(frame) >= 9:
            start_addr = (frame[2] << 8) | frame[3]
            qty = (frame[4] << 8) | frame[5]
            bc = frame[6]
            info["pdu_address"] = start_addr
            info["one_based"] = start_addr + 1
            info["qty"] = qty
            info["details"] = (
                f"PDU Address={start_addr}  1-based={start_addr + 1}  "
                f"Qty={qty}  ByteCount={bc}"
            )
            return info
        if len(frame) >= 8:
            start_addr = (frame[2] << 8) | frame[3]
            qty = (frame[4] << 8) | frame[5]
            info["pdu_address"] = start_addr
            info["one_based"] = start_addr + 1
            info["qty"] = qty
            info["details"] = (
                f"PDU Address={start_addr}  1-based={start_addr + 1}  Qty={qty}"
            )
            return info

    info["details"] = f"{len(frame)} bytes"
    return info

def parse_burst(data: bytes, timestamp: str, channel: str = "", event_time=None):
    rows = []
    if event_time is None:
        event_time = time.time()

    for frame, kind, state in split_capture_buffer(data):
        info = decode_frame(frame, kind)
        crc_status = "OK" if state == "OK" else ("ERROR" if state == "ERROR" else "?")
        rows.append({
            "time": timestamp,
            "channel": channel,
            "type": info["kind"],
            "slave": info["slave"],
            "fc": info["fc"],
            "details": info["details"],
            "crc": crc_status,
            "raw": hex_bytes(frame),
            "pdu_address": info["pdu_address"],
            "one_based": info["one_based"],
            "qty": info["qty"],
            "_frame_len": len(frame),
            "_epoch": float(event_time),
        })
    return rows

class SessionMetrics:
    """Tracks pairing, counters and bus-health diagnostics for one session."""

    def __init__(self, pending_timeout_seconds=PENDING_REQUEST_TIMEOUT_SECONDS):
        self.pending_timeout_seconds = float(pending_timeout_seconds)
        self.reset()

    def reset(self):
        self.first_event_time = None
        self.last_event_time = None
        self.pending = {}
        self.requests = 0
        self.responses = 0
        self.timeouts = 0
        self.crc_errors = 0
        self.exceptions = 0
        self.raw = 0

        # Bus Health.
        self.total_bytes = 0
        self.nonvalidated_bytes = 0
        self.active_slaves = set()
        self.exception_by_slave = defaultdict(int)
        self.response_times_ms = deque(maxlen=10000)
        self.response_times_by_slave = defaultdict(lambda: deque(maxlen=2000))

        # Timeout events are exposed to the view so the original request row can
        # be marked/highlighted without inventing a fake serial frame.
        self._expired_requests = []

    def _key(self, row):
        try:
            slave = int(row.get("slave", ""))
            fc = int(row.get("fc", ""), 16)
        except (ValueError, TypeError):
            return None

        if row.get("type") == "EXCEPTION":
            fc &= 0x7F

        return (slave, fc)

    def pending_count(self):
        return sum(len(v) for v in self.pending.values())

    def pop_expired_requests(self):
        items = self._expired_requests
        self._expired_requests = []
        return items

    def expire_pending(self, now=None):
        """
        Expire stale requests and retain their sequence IDs for the GUI.

        Returns the number of newly expired requests, preserving the original
        public behavior used by CaptureMixin.
        """
        if now is None:
            now = time.time()
        now = float(now)

        expired = 0
        cutoff = now - self.pending_timeout_seconds

        for key in list(self.pending.keys()):
            pending_list = self.pending[key]

            keep_from = 0
            for item in pending_list:
                if item["time"] <= cutoff:
                    expired += 1
                    keep_from += 1
                    event = dict(item)
                    event["slave"] = key[0]
                    event["fc"] = key[1]
                    self._expired_requests.append(event)
                else:
                    break

            if keep_from:
                del pending_list[:keep_from]

            if not pending_list:
                self.pending.pop(key, None)

        if expired:
            self.timeouts += expired

        return expired

    def force_timeout(self, slave, fc):
        """
        Debug/simulation helper: expire the oldest pending request for one key.

        It uses the same pending bookkeeping and returns the expired request
        descriptor so the GUI marks the real REQUEST row as timed out.
        """
        try:
            key = (int(slave), int(fc))
        except (TypeError, ValueError):
            return []

        pending_list = self.pending.get(key, [])
        if not pending_list:
            return []

        item = pending_list.pop(0)
        if not pending_list:
            self.pending.pop(key, None)

        event = dict(item)
        event["slave"] = key[0]
        event["fc"] = key[1]
        self.timeouts += 1
        return [event]

    def _record_response_time(self, row, response_ms):
        if response_ms is None or row.get("crc") != "OK":
            return

        response_ms = float(response_ms)
        self.response_times_ms.append(response_ms)

        try:
            slave = int(row.get("slave", ""))
        except (TypeError, ValueError):
            return
        self.response_times_by_slave[slave].append(response_ms)

    def process(self, row):
        event_time = float(row.get("_epoch", time.time()))

        # Expire stale requests BEFORE pairing the current frame.
        self.expire_pending(event_time)
        expired_requests = self.pop_expired_requests()

        if self.first_event_time is None:
            self.first_event_time = event_time

        delta_ms = None
        if self.last_event_time is not None and event_time >= self.last_event_time:
            delta_ms = (event_time - self.last_event_time) * 1000.0
        if self.last_event_time is None or event_time >= self.last_event_time:
            self.last_event_time = event_time

        row_type = row.get("type", "")
        crc = row.get("crc", "")

        try:
            frame_len = max(0, int(row.get("_frame_len", 0)))
        except (TypeError, ValueError):
            frame_len = 0
        self.total_bytes += frame_len

        try:
            slave_num = int(row.get("slave", ""))
            if 1 <= slave_num <= 247 and not str(row_type).startswith("RAW"):
                self.active_slaves.add(slave_num)
        except (TypeError, ValueError):
            slave_num = None

        if crc == "ERROR":
            self.crc_errors += 1

        # RAW bytes cannot honestly be called CRC errors: there may be no
        # complete frame on which to validate a CRC. For Bus Health we track
        # them together with explicit CRC failures as traffic that could not be
        # validated as a correct Modbus RTU frame.
        if crc == "ERROR" or str(row_type).startswith("RAW"):
            self.nonvalidated_bytes += frame_len

        if row_type == "REQUEST":
            self.requests += 1
            key = self._key(row)
            if key is not None and crc == "OK":
                self.pending.setdefault(key, []).append({
                    "time": event_time,
                    "seq": row.get("_view_seq"),
                    "pdu_address": row.get("pdu_address"),
                    "one_based": row.get("one_based"),
                    "qty": row.get("qty"),
                })

        elif row_type == "RESPONSE":
            self.responses += 1

        elif row_type == "EXCEPTION":
            self.responses += 1
            self.exceptions += 1
            if slave_num is not None:
                self.exception_by_slave[slave_num] += 1

        elif str(row_type).startswith("RAW"):
            self.raw += 1

        response_ms = None
        matched_request = None

        if row_type in ("RESPONSE", "EXCEPTION"):
            key = self._key(row)
            if key is not None:
                pending_list = self.pending.get(key, [])
                if pending_list:
                    matched_request = pending_list.pop(0)
                    if not pending_list:
                        self.pending.pop(key, None)

                    if event_time >= matched_request["time"]:
                        response_ms = (
                            event_time - matched_request["time"]
                        ) * 1000.0

        self._record_response_time(row, response_ms)

        return {
            "delta_ms": delta_ms,
            "response_ms": response_ms,
            "matched_request": matched_request,
            "expired_requests": expired_requests,
            "pending": self.pending_count(),
            "timeouts": self.timeouts,
        }

    @staticmethod
    def _p95(values):
        if not values:
            return None
        ordered = sorted(float(v) for v in values)
        index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
        return ordered[index]

    def health_summary(
        self,
        *,
        baud=9600,
        data_bits=8,
        parity="None",
        stop_bits=1,
        now=None,
    ):
        """Return compact diagnostic metrics for the Bus Health view."""
        if now is None:
            now = time.time()

        if self.first_event_time is None:
            elapsed = 0.0
        else:
            end = max(
                float(now),
                float(self.last_event_time or self.first_event_time),
            )
            elapsed = max(0.0, end - float(self.first_event_time))

        responses = list(self.response_times_ms)
        response_avg = (
            sum(responses) / len(responses)
            if responses else None
        )
        response_min = min(responses) if responses else None
        response_max = max(responses) if responses else None
        response_p95 = self._p95(responses)

        slowest_slave = None
        slowest_avg = None
        for slave, samples in self.response_times_by_slave.items():
            if not samples:
                continue
            avg = sum(samples) / len(samples)
            if slowest_avg is None or avg > slowest_avg:
                slowest_slave = slave
                slowest_avg = avg

        request_rate = (
            self.requests / elapsed
            if elapsed > 0.0 else 0.0
        )

        nonvalidated_rate = (
            100.0 * self.nonvalidated_bytes / self.total_bytes
            if self.total_bytes else 0.0
        )
        timeout_rate = (
            100.0 * self.timeouts / self.requests
            if self.requests else 0.0
        )

        try:
            baud = max(1.0, float(baud))
        except (TypeError, ValueError):
            baud = 9600.0
        try:
            data_bits = float(data_bits)
        except (TypeError, ValueError):
            data_bits = 8.0
        try:
            stop_bits = float(stop_bits)
        except (TypeError, ValueError):
            stop_bits = 1.0

        parity_bits = 0.0 if str(parity) == "None" else 1.0
        bits_per_char = 1.0 + data_bits + parity_bits + stop_bits
        bus_load = (
            100.0 * (self.total_bytes * bits_per_char) / (baud * elapsed)
            if elapsed > 0.0 else 0.0
        )

        exception_summary = ", ".join(
            f"S{slave}:{count}"
            for slave, count in sorted(self.exception_by_slave.items())
        ) or "—"

        return {
            "elapsed_s": elapsed,
            "request_rate": request_rate,
            "response_avg_ms": response_avg,
            "response_min_ms": response_min,
            "response_max_ms": response_max,
            "response_p95_ms": response_p95,
            "nonvalidated_rate_pct": nonvalidated_rate,
            "timeout_rate_pct": timeout_rate,
            "active_slaves": len(self.active_slaves),
            "bus_load_pct": bus_load,
            "slowest_slave": slowest_slave,
            "slowest_avg_ms": slowest_avg,
            "exception_summary": exception_summary,
            "total_bytes": self.total_bytes,
            "nonvalidated_bytes": self.nonvalidated_bytes,
        }

def u16_bytes(value):
    value = int(value) & 0xFFFF
    return bytes(((value >> 8) & 0xFF, value & 0xFF))

def corrupt_crc(frame):
    damaged = bytearray(frame)
    if len(damaged) >= 2:
        damaged[-1] ^= 0xFF
    return bytes(damaged)

def build_simulation_transaction(slave, fc, rng):
    """
    Build one syntactically valid Modbus request/response pair.

    Simulation rules:
    - FC01..FC04 only.
    - Address random 1..32.
    - Qty random 1..8.
    """
    slave = int(slave)
    fc = int(fc)
    start_addr = rng.randint(1, 32)
    qty = rng.randint(1, 8)

    if fc in (1, 2):
        request = append_crc(
            bytes((slave, fc)) + u16_bytes(start_addr) + u16_bytes(qty)
        )

        byte_count = (qty + 7) // 8
        data = bytes(rng.randrange(256) for _ in range(byte_count))
        response = append_crc(bytes((slave, fc, byte_count)) + data)

    elif fc in (3, 4):
        request = append_crc(
            bytes((slave, fc)) + u16_bytes(start_addr) + u16_bytes(qty)
        )

        values = [rng.randint(0, 65535) for _ in range(qty)]
        payload = b"".join(u16_bytes(value) for value in values)
        response = append_crc(
            bytes((slave, fc, len(payload))) + payload
        )

    else:
        raise ValueError(f"Unsupported simulation FC: {fc}")

    return {
        "slave": slave,
        "fc": fc,
        "address": start_addr,
        "qty": qty,
        "request": request,
        "response": response,
    }

def build_random_simulation_plan(rng=None):
    """
    Build exactly four simulation transactions:
    FC01, FC02, FC03 and FC04, one each.

    Four unique random Slave IDs are used, one per transaction.
    """
    if rng is None:
        rng = random.Random()

    slaves = rng.sample(range(1, 248), 4)

    plan = []
    for slave, fc in zip(slaves, SIMULATION_FUNCTION_CODES):
        tx = build_simulation_transaction(slave, fc, rng)
        tx["outcome"] = "response"
        tx["reply"] = tx["response"]
        plan.append(tx)

    return {
        "slaves": slaves,
        "transactions": plan,
    }



def build_anomaly_simulation_plan(rng=None):
    """
    Build a deterministic set of anomaly categories for UI colour preview.

    Used whenever debug simulation is executed. "Realçar resultados" controls
    only whether these rows receive colours; it does not change the generated
    scenario.

    It demonstrates:
      - normal response
      - slow response
      - Modbus exception
      - CRC error
      - timeout
      - RAW/UNPARSED bytes
    """
    if rng is None:
        rng = random.Random()

    slaves = rng.sample(range(1, 248), 5)

    normal = build_simulation_transaction(slaves[0], 1, rng)
    normal["outcome"] = "response"
    normal["reply"] = normal["response"]

    slow = build_simulation_transaction(slaves[1], 2, rng)
    slow["outcome"] = "slow"
    slow["reply"] = slow["response"]

    exception = build_simulation_transaction(slaves[2], 3, rng)
    exception["outcome"] = "exception"
    exception["reply"] = append_crc(
        bytes((slaves[2], 0x83, 0x02))
    )

    crc_error = build_simulation_transaction(slaves[3], 4, rng)
    crc_error["outcome"] = "crc"
    crc_error["reply"] = corrupt_crc(crc_error["response"])

    timeout = build_simulation_transaction(slaves[4], 3, rng)
    timeout["outcome"] = "timeout"
    timeout["reply"] = None

    return {
        "slaves": slaves,
        "transactions": [normal, slow, exception, crc_error, timeout],
        # Four bytes are deliberately too short to be accepted as the FC=0xFF
        # exception frame candidate, producing a visible RAW/UNPARSED row.
        "raw_noise": bytes((0x00, 0x00, 0x00, 0x00)),
        "slow_delay_seconds": (SLOW_RESPONSE_THRESHOLD_MS / 1000.0) + 0.15,
    }

