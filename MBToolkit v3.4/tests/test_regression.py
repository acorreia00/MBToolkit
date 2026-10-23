import json
import queue
import random
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path

import mb_config
import mb_slave_finder
from mb_capture import CaptureMixin
from mb_protocol import (
    SessionMetrics,
    append_crc,
    burst_may_continue,
    crc16_modbus,
    crc_ok,
    modbus_rtu_interframe_gap_seconds,
    parse_burst,
    read_bits_details,
    split_capture_buffer,
)
from mb_slave_finder import SlaveFinderMixin
from mb_view import ViewMixin
from mb_diagnostics import inspector_values
from mb_i18n import (
    LANGUAGE_ENGLISH,
    LANGUAGE_PORTUGUESE,
    english_help_blocks,
    normalize_language,
    translate_details,
    translate_runtime_text,
    translate_text,
)

from mb_slave_finder import (
    build_device_identification_probe,
    build_discovery_probe,
    device_identification_timeout_seconds,
    find_device_identification_response,
    find_discovery_response,
    format_device_identification,
    read_basic_device_identification,
)


def with_bad_crc(frame: bytes) -> bytes:
    damaged = bytearray(frame)
    damaged[-1] ^= 0xFF
    return bytes(damaged)


def device_id_response(
    slave=1,
    objects=None,
    *,
    more_follows=False,
    next_object_id=0,
    conformity=0x01,
):
    if objects is None:
        objects = {
            0x00: b"Schneider Electric",
            0x01: b"TEST-PRODUCT",
            0x02: b"1.2.3",
        }
    payload = bytearray((
        slave,
        0x2B,
        0x0E,
        0x01,
        conformity,
        0xFF if more_follows else 0x00,
        next_object_id,
        len(objects),
    ))
    for object_id, value in objects.items():
        value = bytes(value)
        payload.extend((int(object_id) & 0xFF, len(value)))
        payload.extend(value)
    return append_crc(bytes(payload))


class FakeSerial:
    """Minimal non-blocking serial fake for active Device ID regression tests."""

    def __init__(self, response_by_object):
        self.response_by_object = dict(response_by_object)
        self.rx = bytearray()
        self.writes = []

    @property
    def in_waiting(self):
        return len(self.rx)

    def reset_input_buffer(self):
        self.rx.clear()

    def reset_output_buffer(self):
        pass

    def write(self, data):
        data = bytes(data)
        self.writes.append(data)
        object_id = data[4] if len(data) >= 5 else 0
        response = self.response_by_object.get(object_id, b"")
        self.rx.extend(response)
        return len(data)

    def read(self, size):
        size = min(int(size), len(self.rx))
        chunk = bytes(self.rx[:size])
        del self.rx[:size]
        return chunk


class FakeSerialModule:
    class SerialTimeoutException(TimeoutError):
        pass

    class SerialException(OSError):
        pass


class StaticVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyCapture:
    calculated_gap_ms = CaptureMixin.calculated_gap_ms

    def __init__(self, *, mode="Auto", baud="9600", data="8", parity="None", stop="1", manual="2.0"):
        self.gap_mode_var = StaticVar(mode)
        self.baud_var = StaticVar(baud)
        self.data_var = StaticVar(data)
        self.parity_var = StaticVar(parity)
        self.stop_var = StaticVar(stop)
        self.gap_ms_var = StaticVar(manual)


class TimingRegressionTests(unittest.TestCase):
    def test_t35_uses_character_time_at_or_below_19200(self):
        self.assertAlmostEqual(
            modbus_rtu_interframe_gap_seconds(9600, 11),
            3.5 * 11 / 9600,
            places=9,
        )
        self.assertAlmostEqual(
            modbus_rtu_interframe_gap_seconds(19200, 11),
            3.5 * 11 / 19200,
            places=9,
        )

    def test_t35_is_fixed_above_19200(self):
        for baud in (38400, 57600, 115200):
            with self.subTest(baud=baud):
                self.assertAlmostEqual(
                    modbus_rtu_interframe_gap_seconds(baud, 10),
                    0.001750,
                    places=9,
                )

    def test_sniffer_auto_gap_uses_fixed_1750_us_above_19200(self):
        capture = DummyCapture(baud="115200", parity="None", stop="1")
        self.assertAlmostEqual(capture.calculated_gap_ms(), 1.750, places=6)

    def test_sniffer_manual_gap_is_unchanged(self):
        capture = DummyCapture(mode="Manual", manual="2,75")
        self.assertAlmostEqual(capture.calculated_gap_ms(), 2.75, places=6)

    def test_device_id_timeout_covers_a_full_rtu_frame(self):
        timeout = device_identification_timeout_seconds(9600, "None", "1", 40)
        self.assertGreaterEqual(timeout, 256 * 10 / 9600 + 0.001750)


class ParserRegressionTests(unittest.TestCase):
    def test_crc_known_request(self):
        frame = build_discovery_probe(1, 3)
        self.assertTrue(crc_ok(frame))
        self.assertEqual(frame[:6], bytes.fromhex("01 03 00 00 00 01"))

    def test_invalid_frame_before_valid_frame_stays_crc_error(self):
        first = with_bad_crc(build_discovery_probe(1, 3))
        second = build_discovery_probe(2, 4)
        parts = split_capture_buffer(first + second)
        self.assertEqual(parts[0], (first, "REQUEST", "ERROR"))
        self.assertEqual(parts[1], (second, "REQUEST", "OK"))

    def test_long_unsynchronised_noise_recovers_next_valid_frame(self):
        noise = bytes([0xFF]) * 4000
        frame = build_discovery_probe(7, 3)
        parts = split_capture_buffer(noise + frame)
        self.assertEqual(parts[-1], (frame, "REQUEST", "OK"))
        self.assertTrue(parts[0][1].startswith("RAW/"))
        self.assertEqual(sum(len(part[0]) for part in parts), len(noise) + len(frame))

    def test_supported_function_code_shapes(self):
        frames = {
            "fc01_req": append_crc(bytes.fromhex("01 01 00 00 00 08")),
            "fc01_resp": append_crc(bytes.fromhex("01 01 01 5A")),
            "fc02_req": append_crc(bytes.fromhex("01 02 00 00 00 08")),
            "fc02_resp": append_crc(bytes.fromhex("01 02 01 A5")),
            "fc03_req": append_crc(bytes.fromhex("01 03 00 00 00 01")),
            "fc03_resp": append_crc(bytes.fromhex("01 03 02 00 2A")),
            "fc04_req": append_crc(bytes.fromhex("01 04 00 00 00 01")),
            "fc04_resp": append_crc(bytes.fromhex("01 04 02 00 2A")),
            "fc05": append_crc(bytes.fromhex("01 05 00 01 FF 00")),
            "fc06": append_crc(bytes.fromhex("01 06 00 01 00 2A")),
            "fc07_req": append_crc(bytes.fromhex("01 07")),
            "fc07_resp": append_crc(bytes.fromhex("01 07 AA")),
            "fc08": append_crc(bytes.fromhex("01 08 00 00 12 34")),
            "fc15_req": append_crc(bytes.fromhex("01 0F 00 00 00 08 01 5A")),
            "fc15_resp": append_crc(bytes.fromhex("01 0F 00 00 00 08")),
            "fc16_req": append_crc(bytes.fromhex("01 10 00 00 00 01 02 00 2A")),
            "fc16_resp": append_crc(bytes.fromhex("01 10 00 00 00 01")),
            "fc22": append_crc(bytes.fromhex("01 16 00 01 FF 00 00 2A")),
            "fc23_req": append_crc(bytes.fromhex(
                "01 17 00 00 00 01 00 10 00 01 02 00 2A"
            )),
            "fc23_resp": append_crc(bytes.fromhex("01 17 02 00 2A")),
            "exception": append_crc(bytes.fromhex("01 83 02")),
        }
        for name, frame in frames.items():
            with self.subTest(name=name):
                parts = split_capture_buffer(frame)
                self.assertEqual(len(parts), 1)
                self.assertEqual(parts[0][0], frame)
                self.assertEqual(parts[0][2], "OK")
                self.assertFalse(parts[0][1].startswith("RAW"))

    def test_random_noise_never_crashes_and_preserves_all_bytes(self):
        rng = random.Random(20260910)
        for _ in range(250):
            length = rng.randint(1, 512)
            data = bytes(rng.randrange(256) for _ in range(length))
            parts = split_capture_buffer(data)
            self.assertEqual(sum(len(part[0]) for part in parts), len(data))
            self.assertTrue(all(len(part[0]) > 0 for part in parts))

    def test_request_response_pairing_and_response_time(self):
        req = parse_burst(
            append_crc(bytes.fromhex("01 03 00 00 00 01")),
            "12:00:00.000",
            "BUS",
            100.000,
        )[0]
        resp = parse_burst(
            append_crc(bytes.fromhex("01 03 02 00 2A")),
            "12:00:00.125",
            "BUS",
            100.125,
        )[0]
        req["_view_seq"] = 10
        resp["_view_seq"] = 11

        metrics = SessionMetrics(pending_timeout_seconds=1.0)
        first = metrics.process(req)
        second = metrics.process(resp)

        self.assertEqual(first["pending"], 1)
        self.assertEqual(second["pending"], 0)
        self.assertEqual(second["matched_request"]["seq"], 10)
        self.assertAlmostEqual(second["response_ms"], 125.0, places=6)

    def test_timeout_regression(self):
        req = parse_burst(
            append_crc(bytes.fromhex("05 04 00 00 00 01")),
            "12:00:00.000",
            "BUS",
            10.0,
        )[0]
        req["_view_seq"] = 77
        metrics = SessionMetrics(pending_timeout_seconds=1.0)
        metrics.process(req)
        self.assertEqual(metrics.expire_pending(11.1), 1)
        expired = metrics.pop_expired_requests()
        self.assertEqual(expired[0]["seq"], 77)
        self.assertEqual(metrics.timeouts, 1)


class SlaveFinderRegressionTests(unittest.TestCase):
    def test_normal_discovery_response(self):
        response = append_crc(bytes.fromhex("04 03 02 12 34"))
        found = find_discovery_response(response, 4, 3)
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"], "RESPONSE")

    def test_discovery_exception_counts_as_response(self):
        response = append_crc(bytes.fromhex("04 83 02"))
        found = find_discovery_response(response, 4, 3)
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"], "EXCEPTION")
        self.assertEqual(found["exception_code"], 2)

    def test_device_identification_request(self):
        request = build_device_identification_probe(4)
        self.assertEqual(request[:5], bytes.fromhex("04 2B 0E 01 00"))
        self.assertEqual(len(request), 7)
        self.assertTrue(crc_ok(request))

    def test_device_identification_response_parser(self):
        response = device_id_response(slave=4)
        found = find_device_identification_response(response, 4)
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"], "DEVICE_ID")
        self.assertEqual(found["objects"][0x00], "Schneider Electric")
        self.assertEqual(found["objects"][0x01], "TEST-PRODUCT")
        self.assertEqual(found["objects"][0x02], "1.2.3")
        self.assertEqual(
            format_device_identification(found),
            "Schneider Electric | TEST-PRODUCT | 1.2.3",
        )

    def test_device_identification_parser_ignores_request_echo(self):
        request = build_device_identification_probe(4)
        response = device_id_response(slave=4)
        found = find_device_identification_response(request + response, 4)
        self.assertIsNotNone(found)
        self.assertEqual(found["objects"][0x01], "TEST-PRODUCT")

    def test_device_identification_exception(self):
        response = append_crc(bytes.fromhex("04 AB 01"))
        found = find_device_identification_response(response, 4)
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"], "EXCEPTION")
        self.assertEqual(found["exception_code"], 1)
        self.assertIn("Illegal Function", format_device_identification(found))

    def test_device_identification_rejects_bad_crc(self):
        response = with_bad_crc(device_id_response(slave=4))
        self.assertIsNone(find_device_identification_response(response, 4))

    def test_device_identification_follows_more_follows(self):
        page0 = device_id_response(
            slave=4,
            objects={0x00: b"Vendor"},
            more_follows=True,
            next_object_id=0x01,
        )
        page1 = device_id_response(
            slave=4,
            objects={0x01: b"Product", 0x02: b"2.0"},
            more_follows=False,
            next_object_id=0x00,
        )
        serial = FakeSerial({0x00: page0, 0x01: page1})
        result = read_basic_device_identification(
            serial,
            4,
            115200,
            "None",
            "1",
            10,
            threading.Event(),
            FakeSerialModule,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["objects"][0x00], "Vendor")
        self.assertEqual(result["objects"][0x01], "Product")
        self.assertEqual(result["objects"][0x02], "2.0")
        self.assertEqual(len(serial.writes), 2)
        self.assertEqual(serial.writes[0][4], 0x00)
        self.assertEqual(serial.writes[1][4], 0x01)


class InternationalizationRegressionTests(unittest.TestCase):
    def test_language_normalization_defaults_to_portuguese(self):
        self.assertEqual(normalize_language("invalid"), LANGUAGE_PORTUGUESE)
        self.assertEqual(normalize_language(LANGUAGE_ENGLISH), LANGUAGE_ENGLISH)

    def test_static_ui_translation_is_reversible(self):
        self.assertEqual(translate_text("Configuração", LANGUAGE_ENGLISH), "Configuration")
        self.assertEqual(translate_text("Configuration", LANGUAGE_PORTUGUESE), "Configuração")
        self.assertEqual(translate_text("Frame gap", LANGUAGE_ENGLISH), "Frame gap")
        # "None" is a technical parity value and must remain English in the PT UI.
        self.assertEqual(translate_text("None", LANGUAGE_PORTUGUESE), "None")
        self.assertEqual(translate_text("Nenhum", LANGUAGE_ENGLISH), "None")

    def test_dynamic_status_translation_is_reversible(self):
        pt = "Pesquisa concluída — 7 encontrados — 00:12"
        en = "Scan complete — 7 found — 00:12"
        self.assertEqual(translate_runtime_text(pt, LANGUAGE_ENGLISH), en)
        self.assertEqual(translate_runtime_text(en, LANGUAGE_PORTUGUESE), pt)

    def test_register_details_follow_language(self):
        self.assertEqual(
            translate_details("ByteCount=2  Registos=[42]", LANGUAGE_ENGLISH),
            "ByteCount=2  Registers=[42]",
        )
        self.assertEqual(
            translate_details("ByteCount=2  Registers=[42]", LANGUAGE_PORTUGUESE),
            "ByteCount=2  Registos=[42]",
        )

    def test_inspector_english_labels_and_crc(self):
        frame = append_crc(bytes.fromhex("01 03 02 00 2A"))
        row = parse_burst(frame, "12:00:00.000", "BUS", 1.0)[0]
        row.update({"response_text": "12.3", "matched": True})
        values = inspector_values(row, language=LANGUAGE_ENGLISH)
        self.assertTrue(values["type"].startswith("Type:"))
        self.assertTrue(values["result"].startswith("Result:"))
        self.assertTrue(values["data"].startswith("Data:"))
        self.assertIn("Registers=[42]", values["data"])
        self.assertIn("received", values["crc"])
        self.assertIn("calculated", values["crc"])

    def test_english_help_contains_no_portuguese_diacritics(self):
        text = "".join(
            block for _tag, block in english_help_blocks(
                "20 000", "20 000", 1.0, 300.0, debug_sim=True
            )
        )
        for character in "ãõçáéíóúâê":
            self.assertNotIn(character, text.casefold())
        self.assertIn("Bus Slave Finder — active scan", text)
        self.assertIn("Device Identification (FC43/14)", text)


def bitwise_crc16(data: bytes) -> int:
    """Reference CRC used up to v3.0, kept to verify the table-driven CRC."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def process_frames(metrics, frames):
    """Run (bytes, channel, epoch) frames through SessionMetrics."""
    out = []
    for index, (frame, channel, epoch) in enumerate(frames):
        for row in parse_burst(frame, "12:00:00.000", channel, epoch):
            row["_view_seq"] = index
            out.append((row, metrics.process(row)))
    return out


class ProtocolV31RegressionTests(unittest.TestCase):
    def test_crc_table_matches_bitwise_reference(self):
        rng = random.Random(31)
        for length in (0, 1, 2, 7, 64, 256):
            data = bytes(rng.randrange(256) for _ in range(length))
            self.assertEqual(crc16_modbus(data), bitwise_crc16(data))

    def test_broadcast_request_never_times_out(self):
        request = append_crc(bytes.fromhex("00 10 00 00 00 01 02 00 05"))
        metrics = SessionMetrics(pending_timeout_seconds=1.0)
        process_frames(metrics, [(request, "BUS", 10.0)])
        self.assertEqual(metrics.requests, 1)
        self.assertEqual(metrics.broadcast_requests, 1)
        self.assertEqual(metrics.pending_count(), 0)
        metrics.expire_pending(20.0)
        self.assertEqual(metrics.timeouts, 0)
        self.assertEqual(metrics.health_summary(now=20.0)["timeout_rate_pct"], 0.0)

    def test_fc06_echo_pair_is_request_then_response(self):
        write = append_crc(bytes.fromhex("01 06 00 01 00 09"))
        metrics = SessionMetrics(pending_timeout_seconds=1.0)
        results = process_frames(
            metrics, [(write, "BUS", 100.0), (write, "BUS", 100.040)]
        )
        self.assertEqual(
            [row["type"] for row, _timing in results], ["REQUEST", "RESPONSE"]
        )
        self.assertEqual((metrics.requests, metrics.responses), (1, 1))
        self.assertAlmostEqual(results[1][1]["response_ms"], 40.0, places=6)

    def test_unanswered_fc05_write_times_out(self):
        write = append_crc(bytes.fromhex("02 05 00 10 FF 00"))
        metrics = SessionMetrics(pending_timeout_seconds=1.0)
        results = process_frames(metrics, [(write, "BUS", 5.0)])
        self.assertEqual(results[0][0]["type"], "REQUEST")
        self.assertEqual(metrics.expire_pending(6.5), 1)

    def test_different_fc06_writes_are_both_requests(self):
        first = append_crc(bytes.fromhex("01 06 00 01 00 09"))
        second = append_crc(bytes.fromhex("01 06 00 02 00 0A"))
        metrics = SessionMetrics()
        results = process_frames(
            metrics, [(first, "BUS", 1.0), (second, "BUS", 1.1)]
        )
        self.assertEqual(
            [row["type"] for row, _timing in results], ["REQUEST", "REQUEST"]
        )

    def test_dual_rx_echo_must_come_from_opposite_channel(self):
        write = append_crc(bytes.fromhex("01 06 00 01 00 09"))
        metrics = SessionMetrics()
        results = process_frames(metrics, [
            (write, "A→B", 1.0),
            (write, "A→B", 1.5),
            (write, "B→A", 1.52),
        ])
        self.assertEqual(
            [row["type"] for row, _timing in results],
            ["REQUEST", "REQUEST", "RESPONSE"],
        )

    def test_split_frame_is_held_until_complete(self):
        response = append_crc(bytes.fromhex("01 03 08") + bytes(8))
        self.assertTrue(burst_may_continue(response[:7]))
        self.assertTrue(burst_may_continue(response[:1]))
        self.assertFalse(burst_may_continue(response))
        self.assertFalse(burst_may_continue(bytes((0xFF,) * 6)))

    def test_merged_frames_keep_their_chunk_arrival_times(self):
        request = append_crc(bytes.fromhex("01 03 00 00 00 01"))
        response = append_crc(bytes.fromhex("01 03 02 00 2A"))
        rows = parse_burst(
            request + response,
            "12:00:00.000",
            "BUS",
            100.0,
            chunk_times=[(0, 100.0), (len(request), 100.030)],
        )
        self.assertEqual([row["type"] for row in rows], ["REQUEST", "RESPONSE"])
        self.assertAlmostEqual(rows[1]["_epoch"], 100.030, places=6)
        metrics = SessionMetrics()
        metrics.process(rows[0])
        self.assertAlmostEqual(metrics.process(rows[1])["response_ms"], 30.0, places=6)

    def test_read_bits_details_use_request_qty(self):
        response = append_crc(bytes.fromhex("01 01 02 CD 01"))
        self.assertEqual(
            read_bits_details(response),
            "ByteCount=2  Bits=10110011 10000000",
        )
        self.assertEqual(
            read_bits_details(response, qty=10),
            "ByteCount=2  Bits=10110011 10",
        )


class _ChunkedSerial:
    """Delivers byte chunks at fixed delays, like a USB latency timer."""

    def __init__(self, chunks, stop_event):
        self.started = time.perf_counter()
        self.chunks = list(chunks)  # [(delay_s, bytes)]
        self.stop_event = stop_event

    def _due(self):
        elapsed = time.perf_counter() - self.started
        if self.chunks and elapsed >= self.chunks[0][0]:
            return self.chunks[0][1]
        if not self.chunks and elapsed > 0.3:
            self.stop_event.set()
        return b""

    @property
    def in_waiting(self):
        return len(self._due())

    def read(self, size):
        data = self._due()
        if data:
            self.chunks.pop(0)
        return data

    def close(self):
        pass


class _ReaderStub(CaptureMixin):
    def __init__(self):
        self.stop_event = threading.Event()
        self.event_queue = queue.Queue()


class ReaderV31RegressionTests(unittest.TestCase):
    def test_frame_split_by_usb_latency_is_reassembled(self):
        response = append_crc(bytes.fromhex("01 03 08") + bytes(8))
        reader = _ReaderStub()
        serial = _ChunkedSerial(
            [(0.0, response[:7]), (0.016, response[7:])], reader.stop_event
        )
        # 115200 bit/s: Auto t3.5 is 1.75 ms, far shorter than the 16 ms split.
        reader.reader_loop(serial, 1.75, "BUS", 1)
        rows = []
        while not reader.event_queue.empty():
            name, payload = reader.event_queue.get()
            if name == "frame":
                rows.append(payload)
        self.assertEqual([(row["type"], row["crc"]) for row in rows], [("RESPONSE", "OK")])


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeTree:
    def __init__(self):
        self.tags = {}

    def item(self, iid, tags=()):
        self.tags[iid] = tags


class _TimeoutView(ViewMixin):
    def __init__(self, type_filter):
        self.tree = _FakeTree()
        self.advanced_filter_type_var = _FakeVar(type_filter)
        self.highlight_anomalies_var = _FakeVar(True)
        self._successful_request_seqs = set()
        self._frame_history = deque([{
            "seq": 5, "type": "REQUEST", "crc": "OK", "timed_out": False,
            "response_text": "",
        }])
        self._tree_iids_by_seq = {5: ["I001", "I002"]}
        self.full_renders = 0

    def render_filtered_view(self):
        self.full_renders += 1

    def selected_record(self):
        return None


class ViewV31RegressionTests(unittest.TestCase):
    def test_timeout_retags_rows_without_full_rebuild(self):
        view = _TimeoutView("Todos")
        self.assertEqual(view.mark_timed_out_records([{"seq": 5}]), 1)
        self.assertEqual(view.full_renders, 0)
        self.assertEqual(view.tree.tags["I001"], ("anomaly_timeout",))
        self.assertEqual(view.tree.tags["I002"], ("anomaly_timeout",))

    def test_timeouts_filter_still_rebuilds_view(self):
        view = _TimeoutView("Timeouts")
        view.mark_timed_out_records([{"seq": 5}])
        self.assertEqual(view.full_renders, 1)

    def test_inspector_shows_address_of_each_register(self):
        frame = append_crc(bytes.fromhex("01 03 04 00 2A 00 2B"))
        row = parse_burst(frame, "12:00:00.000", "BUS", 1.0)[0]
        row["request_pdu_address"] = 100
        pt = inspector_values(row, language=LANGUAGE_PORTUGUESE)
        en = inspector_values(row, language=LANGUAGE_ENGLISH)
        self.assertIn("Registos (PDU Address=valor): 100=42, 101=43", pt["data"])
        self.assertIn("Registers (PDU Address=value): 100=42, 101=43", en["data"])

    def test_inspector_shows_address_of_each_bit(self):
        frame = append_crc(bytes.fromhex("01 02 01 05"))
        row = parse_burst(frame, "12:00:00.000", "BUS", 1.0)[0]
        row.update({"request_pdu_address": 8, "request_qty": 3})
        values = inspector_values(row, language=LANGUAGE_PORTUGUESE)
        self.assertIn("Bits (PDU Address=valor): 8=1, 9=0, 10=1", values["data"])


class _FakeFinderSerial:
    def __init__(self, incoming=b""):
        self.incoming = bytearray(incoming)
        self.writes = []

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, size):
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def close(self):
        pass


class _FinderStub(SlaveFinderMixin):
    current_language = LANGUAGE_PORTUGUESE

    def __init__(self, fake_serial):
        self.fake_serial = fake_serial
        self.event_queue = queue.Queue()
        self.discovery_stop_event = threading.Event()
        self.discovery_serial = None

    def tr(self, text):
        return translate_text(text, self.current_language)

    def trf(self, text, **values):
        return self.tr(text).format(**values)

    def open_discovery_serial_port(self, serial, port, baud, parity, stopbits):
        return self.fake_serial

    def run_worker(self, slaves, attempts):
        self.discovery_worker(
            None, "COM9", [(115200, "None", "1")], slaves, 10, False, False,
            attempts,
        )
        events = []
        while not self.event_queue.empty():
            events.append(self.event_queue.get())
        return events


class FinderV31RegressionTests(unittest.TestCase):
    def setUp(self):
        self._idle_check = mb_slave_finder.DISCOVERY_IDLE_CHECK_SECONDS
        mb_slave_finder.DISCOVERY_IDLE_CHECK_SECONDS = 0.05

    def tearDown(self):
        mb_slave_finder.DISCOVERY_IDLE_CHECK_SECONDS = self._idle_check

    def test_each_silent_slave_gets_all_attempts(self):
        stub = _FinderStub(_FakeFinderSerial())
        events = stub.run_worker([1, 2], attempts=3)
        done = [payload for name, payload in events if name == "discovery_done"][0]
        self.assertIsNone(done["error"])
        self.assertEqual(len(stub.fake_serial.writes), 6)

    def test_traffic_before_scan_blocks_transmission(self):
        stub = _FinderStub(_FakeFinderSerial(b"\x01\x03\x00"))
        events = stub.run_worker([1], attempts=1)
        done = [payload for name, payload in events if name == "discovery_done"][0]
        self.assertIn("Foi detetado tráfego em COM9", done["error"])
        self.assertEqual(stub.fake_serial.writes, [])

    def test_legacy_default_timeout_migrates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            original = mb_config.get_settings_file
            mb_config.get_settings_file = lambda: path
            try:
                path.write_text(
                    json.dumps({"bus_slave_finder": {"min_timeout_ms": 40}}),
                    encoding="utf-8",
                )
                finder = mb_config.load_ui_settings()["bus_slave_finder"]
                self.assertEqual(finder["min_timeout_ms"], "100")
                self.assertEqual(finder["attempts"], "1")

                path.write_text(
                    json.dumps({"bus_slave_finder": {
                        "min_timeout_ms": 40, "attempts": 2,
                    }}),
                    encoding="utf-8",
                )
                finder = mb_config.load_ui_settings()["bus_slave_finder"]
                self.assertEqual(finder["min_timeout_ms"], "40")
                self.assertEqual(finder["attempts"], "2")
            finally:
                mb_config.get_settings_file = original


class SourceHygieneV31Tests(unittest.TestCase):
    def test_no_inline_language_branches(self):
        package = Path(__file__).resolve().parents[1]
        for source in package.glob("*.py"):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn(
                'current_language == "English"', text, source.name
            )

    def test_message_templates_translate(self):
        self.assertEqual(
            translate_text("Encontrados: {count}", LANGUAGE_ENGLISH).format(count=3),
            "Found: 3",
        )
        self.assertEqual(
            translate_text("A verificar se o barramento está livre…", LANGUAGE_ENGLISH),
            "Checking that the bus is idle…",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
