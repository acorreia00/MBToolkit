import json
import os
import queue
import struct
import tempfile
import time
import unittest
from pathlib import Path

import mb_config
import mb_master_ui
from mb_master import (
    BYTE_ORDERS,
    BYTE_ORDERS_64,
    format_value,
    format_window_values,
    raw_text_for_scaled,
    register_groups,
    validate_scale,
    MasterEngine,
    PollDefinition,
    build_read_request,
    build_write_request,
    encode_coil_value,
    encode_register_value,
    find_master_response,
    format_register_values,
)
from mb_master_ui import MasterMixin, MasterWindow, apply_format_to_rows
from mb_protocol import append_crc, crc_ok


class FakeSlaveSerial:
    """In-memory Modbus RTU slave behind a fake serial port.

    Answers FC01/03 reads and FC05/06/15/16 writes for ``slave_id`` from its
    coil/register banks, can echo every request like some RS485 adapters, and
    can hold bytes that are already on the bus before the master transmits.
    """

    def __init__(self, slave_id=1, *, echo=False, bus_traffic=b"", exception_for=None):
        self.slave_id = slave_id
        self.echo = echo
        self.exception_for = exception_for or {}
        self.registers = {i: i * 10 for i in range(200)}
        self.coils = {i: i % 2 for i in range(200)}
        self.rx = bytearray(bus_traffic)
        self.requests = []

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, size):
        data = bytes(self.rx[:size])
        del self.rx[:size]
        return data

    def reset_input_buffer(self):
        self.rx.clear()

    def reset_output_buffer(self):
        pass

    def cancel_read(self):
        pass

    def cancel_write(self):
        pass

    def close(self):
        pass

    def write(self, data):
        data = bytes(data)
        self.requests.append(data)
        if self.echo:
            self.rx.extend(data)
        if crc_ok(data) and data[0] == self.slave_id:
            self.rx.extend(self._answer(data))
        elif crc_ok(data) and data[0] == 0:
            self._answer(data)  # broadcast: execute, never answer
        return len(data)

    def _answer(self, req):
        fc = req[1]
        if fc in self.exception_for:
            return append_crc(bytes((req[0], fc | 0x80, self.exception_for[fc])))
        address = (req[2] << 8) | req[3]
        qty = (req[4] << 8) | req[5]
        if fc == 3:
            payload = b"".join(struct.pack(">H", self.registers.get(address + i, 0))
                               for i in range(qty))
            return append_crc(bytes((req[0], 3, len(payload))) + payload)
        if fc == 1:
            data = bytearray((qty + 7) // 8)
            for i in range(qty):
                if self.coils.get(address + i):
                    data[i // 8] |= 1 << (i % 8)
            return append_crc(bytes((req[0], 1, len(data))) + bytes(data))
        if fc == 6:
            self.registers[address] = qty
            return req
        if fc == 5:
            self.coils[address] = 1 if qty == 0xFF00 else 0
            return req
        if fc == 16:
            for i in range(qty):
                self.registers[address + i] = (req[7 + 2 * i] << 8) | req[8 + 2 * i]
            return append_crc(req[:6])
        if fc == 15:
            for i in range(qty):
                self.coils[address + i] = (req[7 + i // 8] >> (i % 8)) & 1
            return append_crc(req[:6])
        return append_crc(bytes((req[0], fc | 0x80, 1)))


def drain(event_queue):
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
    return events


def make_engine(serial, **overrides):
    options = dict(baud=115200, parity="None", stopbits="1",
                   response_timeout_ms=30, delay_ms=0)
    options.update(overrides)
    return MasterEngine(serial, queue.Queue(), **options)


class MasterFormatTests(unittest.TestCase):
    def test_32_bit_formats_round_trip_in_every_byte_order(self):
        for order in BYTE_ORDERS:
            for kind, text in (("int32", "-123456"), ("uint32", "4000000000"),
                               ("float32", "123.456")):
                fmt = f"{kind}_{order}"
                registers = encode_register_value(text, fmt)
                self.assertEqual(len(registers), 2)
                self.assertEqual(format_register_values(registers, fmt)[0], text)

    def test_float_byte_orders_match_wire_layout(self):
        big_endian = struct.pack(">f", 1.5)  # 3F C0 00 00 = A B C D
        self.assertEqual(encode_register_value("1.5", "float32_ABCD"), [0x3FC0, 0x0000])
        self.assertEqual(encode_register_value("1.5", "float32_CDAB"), [0x0000, 0x3FC0])
        self.assertEqual(encode_register_value("1.5", "float32_BADC"), [0xC03F, 0x0000])
        self.assertEqual(encode_register_value("1.5", "float32_DCBA"), [0x0000, 0xC03F])
        self.assertEqual(big_endian, bytes.fromhex("3FC00000"))

    def test_16_bit_formats(self):
        self.assertEqual(format_register_values([0xFFFE], "int16"), ["-2"])
        self.assertEqual(format_register_values([0xFFFE], "uint16"), ["65534"])
        self.assertEqual(format_register_values([0x00AB], "hex16"), ["0x00AB"])
        self.assertEqual(format_register_values([0x0105], "bin16"), ["00000001 00000101"])
        self.assertEqual(encode_register_value("-2", "int16"), [0xFFFE])
        self.assertEqual(encode_register_value("0x1A2B", "hex16"), [0x1A2B])
        self.assertEqual(encode_register_value("0000 0001 0000 0101", "bin16"), [0x0105])

    def test_values_outside_the_format_are_rejected(self):
        for text, fmt in (("40000", "int16"), ("-1", "uint16"), ("abc", "float32_ABCD"),
                          ("1e40", "float32_ABCD"), ("", "int16")):
            with self.assertRaises(ValueError):
                encode_register_value(text, fmt)
        with self.assertRaises(ValueError):
            encode_coil_value("2")

    def test_unpaired_register_in_32_bit_format(self):
        self.assertEqual(format_register_values([1, 2, 3], "uint32_ABCD"), ["65538", "", "—"])


class MasterFrameTests(unittest.TestCase):
    def test_write_frames_match_modbus_specification_examples(self):
        # Modbus Application Protocol V1.1b3 examples (CRC appended for RTU).
        self.assertEqual(build_write_request(0x11, 16, 1, [0x000A, 0x0102])[:-2],
                         bytes.fromhex("11 10 0001 0002 04 000A 0102"))
        coils = [1, 0, 1, 1, 0, 0, 1, 1, 1, 0]
        self.assertEqual(build_write_request(0x11, 15, 0x13, coils)[:-2],
                         bytes.fromhex("11 0F 0013 000A 02 CD 01"))
        self.assertEqual(build_write_request(0x11, 5, 0xAC, [1])[:-2],
                         bytes.fromhex("11 05 00AC FF00"))
        self.assertEqual(build_write_request(0x11, 6, 1, [3])[:-2],
                         bytes.fromhex("11 06 0001 0003"))

    def test_invalid_definitions_are_rejected(self):
        for args in ((0, 3, 0, 1), (1, 7, 0, 1), (1, 3, 0, 126), (1, 1, 0, 2001),
                     (1, 3, 65535, 2)):
            with self.assertRaises(ValueError):
                build_read_request(*args)
        with self.assertRaises(ValueError):
            build_write_request(1, 6, 0, [1, 2])

    def test_read_response_found_after_adapter_echo(self):
        request = build_read_request(1, 3, 0, 2)
        response = append_crc(bytes.fromhex("01 03 04 0001 0002"))
        found = find_master_response(request + response, request)
        self.assertEqual(found["kind"], "RESPONSE")
        self.assertEqual(found["values"], [1, 2])

    def test_coil_response_is_trimmed_to_quantity(self):
        request = build_read_request(1, 1, 0, 3)
        found = find_master_response(append_crc(bytes.fromhex("01 01 01 FD")), request)
        self.assertEqual(found["values"], [1, 0, 1])

    def test_exception_and_bad_crc(self):
        request = build_read_request(1, 3, 0, 1)
        exception = append_crc(bytes.fromhex("01 83 02"))
        self.assertEqual(find_master_response(exception, request)["exception_code"], 2)
        damaged = bytearray(append_crc(bytes.fromhex("01 03 02 0001")))
        damaged[-1] ^= 0xFF
        self.assertIsNone(find_master_response(bytes(damaged), request))

    def test_write_response_must_match_request(self):
        request = build_write_request(1, 16, 5, [1, 2])
        self.assertIsNotNone(find_master_response(append_crc(request[:6]), request))
        other = append_crc(bytes.fromhex("01 10 0006 0002"))
        self.assertIsNone(find_master_response(other, request))


class MasterEngineTests(unittest.TestCase):
    def run_engine(self, engine, seconds):
        engine.start()
        time.sleep(seconds)
        engine.stop()
        return drain(engine.event_queue)

    def test_scheduler_serves_writes_then_read_once_then_due_polls(self):
        engine = make_engine(FakeSlaveSerial())
        engine.set_poll(PollDefinition(1, 1, 3, 0, 1, 1000))
        engine.set_poll(PollDefinition(2, 1, 3, 0, 1, 1000))
        engine.read_once(2)
        engine.queue_write(1, build_write_request(1, 6, 0, [5]))
        self.assertEqual(engine.next_job(now=10.0)[0], "write")
        self.assertEqual(engine.next_job(now=10.0)[1:], (engine._polls[2][0], True))
        first = engine.next_job(now=10.0)
        second = engine.next_job(now=10.0)
        self.assertEqual({first[1].window_id, second[1].window_id}, {1, 2})
        self.assertEqual(engine.next_job(now=10.5)[0], "wait")
        self.assertEqual(engine.next_job(now=11.01)[0], "read")

    def test_fast_and_slow_windows_share_one_bus(self):
        serial = FakeSlaveSerial()
        engine = make_engine(serial)
        engine.set_poll(PollDefinition(1, 1, 3, 0, 4, 0))
        engine.set_poll(PollDefinition(2, 1, 1, 0, 8, 10000))
        events = self.run_engine(engine, 0.4)
        results = [p for name, p in events if name == "master_result"]
        fast = [r for r in results if r["window_id"] == 1]
        slow = [r for r in results if r["window_id"] == 2]
        self.assertGreater(len(fast), 3)
        self.assertEqual(len(slow), 1)
        self.assertEqual(fast[0]["values"], [0, 10, 20, 30])
        self.assertEqual(slow[0]["values"], [0, 1, 0, 1, 0, 1, 0, 1])
        self.assertEqual(events[0][0], "master_ready")
        self.assertEqual(events[-1], ("master_stopped", {"error": None}))

    def test_write_is_executed_and_reported(self):
        serial = FakeSlaveSerial(echo=True)
        engine = make_engine(serial)
        engine.queue_write(1, build_write_request(1, 16, 10, [0xABCD, 0x1234]), "FC16")
        results = [p for n, p in self.run_engine(engine, 0.15) if n == "master_result"]
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual((serial.registers[10], serial.registers[11]), (0xABCD, 0x1234))

    def test_broadcast_write_does_not_wait_for_a_response(self):
        serial = FakeSlaveSerial()
        engine = make_engine(serial, response_timeout_ms=5000)
        engine.queue_write(1, build_write_request(0, 6, 3, [77]))
        started = time.perf_counter()
        result = engine.transact(engine._writes.popleft()[1])
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(result["status"], "broadcast")
        self.assertEqual(serial.registers[3], 77)

    def test_timeout_exception_and_invalid_results(self):
        engine = make_engine(FakeSlaveSerial(slave_id=9))
        self.assertEqual(engine.transact(build_read_request(1, 3, 0, 1))["status"], "timeout")
        engine = make_engine(FakeSlaveSerial(exception_for={3: 2}))
        result = engine.transact(build_read_request(1, 3, 0, 1))
        self.assertEqual((result["status"], result["exception_code"]), ("exception", 2))

    def test_traffic_on_the_bus_blocks_the_master(self):
        serial = FakeSlaveSerial(bus_traffic=b"\x01\x03\x00")
        engine = make_engine(serial, idle_check_seconds=0.05)
        engine.set_poll(PollDefinition(1, 1, 3, 0, 1, 0))
        events = self.run_engine(engine, 0.2)
        self.assertEqual(serial.requests, [])
        self.assertEqual(events[-1][0], "master_stopped")
        self.assertEqual(events[-1][1]["error"][0], "traffic")


class MasterWindowTests(unittest.TestCase):
    def test_workspace_entry_round_trip_and_validation(self):
        window = MasterWindow(1, 1, slave=5, fc=3, address=100, qty=4, scan_ms=250, base=1,
                              fmt="float32_CDAB", names={100: "Temperatura"})
        data = MasterWindow.validated_kwargs(window.to_json())
        self.assertEqual(data["names"], {100: "Temperatura"})
        self.assertEqual((data["slave"], data["fmt"], data["base"]), (5, "float32_CDAB", 1))
        for bad in ({"slave": 0}, {"fc": 6}, {"qty": 200}, {"scan_ms": -1}, "x"):
            with self.assertRaises((ValueError, TypeError)):
                MasterWindow.validated_kwargs(bad)

    def test_write_dialog_builds_fc16_for_float_values(self):
        window = MasterWindow(1, 1, slave=2, fc=3, address=0, qty=10, base=1,
                              fmt="float32_ABCD")
        request, _ = MasterMixin.master_build_write(None, window, "2", "11", "1.5;2", 16)
        self.assertEqual(request[:-2], bytes.fromhex("02 10 000A 0004 08 3FC0 0000 4000 0000"))
        with self.assertRaises(ValueError):
            MasterMixin.master_build_write(None, window, "2", "11", "1.5", 6)


class MasterWorkspaceFolderTests(unittest.TestCase):
    def setUp(self):
        self._appdata = os.environ.get("APPDATA")
        self._folder = tempfile.TemporaryDirectory()
        os.environ["APPDATA"] = self._folder.name

    def tearDown(self):
        if self._appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._appdata
        self._folder.cleanup()

    def test_workspaces_live_beside_the_settings(self):
        folder = mb_config.get_workspaces_folder()
        self.assertEqual(folder.name, "Workspaces")
        self.assertEqual(folder.parent, mb_config.get_settings_file().parent)
        self.assertTrue(folder.is_dir())
        master = mb_config.get_master_workspaces_folder()
        self.assertEqual((master.name, master.parent), ("Master", folder))
        self.assertEqual(mb_master_ui.workspace_path("Linha 1").parent, master)

    def test_loose_master_workspaces_move_into_the_master_folder(self):
        root = mb_config.get_workspaces_folder()
        (root / "Linha 1.mbsw").write_text('{"windows": []}', encoding="utf-8")
        (root / "notas.txt").write_text("x", encoding="utf-8")
        self.assertEqual(mb_master_ui.list_workspaces(), ["Linha 1"])
        master = mb_config.get_master_workspaces_folder()
        self.assertTrue((master / "Linha 1.mbsw").is_file())
        self.assertFalse((root / "Linha 1.mbsw").exists())
        self.assertTrue((root / "notas.txt").exists())
        # Only the first time: a file put in Workspaces later stays there.
        (root / "Outro.mbsw").write_text("{}", encoding="utf-8")
        self.assertEqual(mb_master_ui.list_workspaces(), ["Linha 1"])

    def test_saved_workspaces_are_listed_by_name(self):
        for name in ("Subestação B", "armazém", "Linha 1"):
            mb_master_ui.workspace_path(name).write_text("{}", encoding="utf-8")
        (mb_config.get_master_workspaces_folder() / "notas.txt").write_text("x", encoding="utf-8")
        self.assertEqual(mb_master_ui.list_workspaces(),
                         ["armazém", "Linha 1", "Subestação B"])

    def test_workspace_names_must_be_valid_file_names(self):
        self.assertEqual(mb_master_ui.validate_workspace_name("  Linha 1. "), "Linha 1")
        for bad in ("", "   ", "a/b", "x:y", "CON", "com3", "a" * 61, 'q"'):
            with self.assertRaises(ValueError):
                mb_master_ui.validate_workspace_name(bad)

    def test_mbsniffer_settings_and_workspaces_are_migrated_once(self):
        legacy = Path(self._folder.name) / "MBSniffer"
        (legacy / "Workspaces").mkdir(parents=True)
        (legacy / "settings.json").write_text('{"language": "English"}', encoding="utf-8")
        (legacy / "Workspaces" / "Linha 1.mbsw").write_text(
            '{"format": "MBSniffer Master workspace", "windows": []}', encoding="utf-8")

        settings = mb_config.get_settings_file()
        self.assertEqual(settings.parent.name, "MBToolkit")
        self.assertEqual(mb_config.load_ui_settings()["language"], "English")
        self.assertEqual(mb_master_ui.list_workspaces(), ["Linha 1"])
        self.assertTrue((legacy / "settings.json").exists())  # old folder kept

        # Later changes in the old folder are not copied again.
        (legacy / "Workspaces" / "Outro.mbsw").write_text("{}", encoding="utf-8")
        mb_config.get_settings_file()
        self.assertEqual(mb_master_ui.list_workspaces(), ["Linha 1"])

    def test_legacy_workspace_format_is_accepted(self):
        self.assertIn("MBSniffer Master workspace", mb_config.MASTER_WORKSPACE_FORMATS)
        self.assertEqual(mb_config.MASTER_WORKSPACE_FORMAT, "MBToolkit Master workspace")

    def test_window_title_is_saved_in_the_workspace(self):
        window = MasterWindow(1, 2, title="  Inversor 3  ")
        self.assertEqual(window.title, "Inversor 3")
        self.assertEqual(MasterWindow.validated_kwargs(window.to_json())["title"], "Inversor 3")
        self.assertEqual(MasterWindow.validated_kwargs({"slave": 1})["title"], "")


class MasterPerAddressFormatTests(unittest.TestCase):
    def test_64_bit_formats_round_trip_in_every_byte_order(self):
        for order in BYTE_ORDERS_64:
            for kind, text in (("int64", "-1234567890123"), ("uint64", "18000000000000000000"),
                               ("float64", "123456.789012345")):
                fmt = f"{kind}_{order}"
                registers = encode_register_value(text, fmt)
                self.assertEqual(len(registers), 4)
                self.assertEqual(format_value(registers, fmt), text)

    def test_double_byte_orders_match_wire_layout(self):
        # 1.0 = 3FF0 0000 0000 0000 in IEEE 754 big-endian.
        self.assertEqual(encode_register_value("1", "float64_ABCDEFGH"), [0x3FF0, 0, 0, 0])
        self.assertEqual(encode_register_value("1", "float64_GHEFCDAB"), [0, 0, 0, 0x3FF0])
        self.assertEqual(encode_register_value("1", "float64_BADCFEHG"), [0xF03F, 0, 0, 0])
        self.assertEqual(encode_register_value("1", "float64_HGFEDCBA"), [0, 0, 0, 0xF03F])

    def test_per_address_formats_override_the_window_format(self):
        registers = [0x42F6, 0xE979, 0xFFFF, 0x0001, 0x0002, 7]
        texts = format_window_values(registers, 100, "int16", {100: "float32_ABCD"})
        self.assertEqual(texts, ["123.456", "", "-1", "1", "2", "7"])
        self.assertEqual(register_groups(6, 100, "int16", {102: "int64_ABCDEFGH"}),
                         [(0, 1, "int16"), (1, 1, "int16"), (2, 4, "int64_ABCDEFGH")])

    def test_default_multi_register_values_cut_by_an_override_show_a_dash(self):
        texts = format_window_values([1, 2, 3, 4, 5], 0, "uint32_ABCD", {1: "int16"})
        self.assertEqual(texts, ["—", "2", "196612", "", "—"])

    def test_selection_rules_for_multi_register_formats(self):
        window = MasterWindow(1, 1, address=100, qty=10)
        apply_format_to_rows(window, [2, 3, 4, 5], "float32_CDAB")
        self.assertEqual(window.formats, {102: "float32_CDAB", 104: "float32_CDAB"})
        apply_format_to_rows(window, [4, 5, 6, 7], "float64_ABCDEFGH")
        self.assertEqual(window.formats, {102: "float32_CDAB", 104: "float64_ABCDEFGH"})
        apply_format_to_rows(window, [0, 1], "hex16")
        self.assertEqual(window.formats[100], "hex16")
        self.assertEqual(window.formats[101], "hex16")
        apply_format_to_rows(window, [4], None)
        self.assertNotIn(104, window.formats)
        for rows, fmt in (([1], "float32_ABCD"), ([1, 3], "float32_ABCD"),
                          ([0, 1, 2], "float32_ABCD"), ([0, 1], "int64_ABCDEFGH"),
                          ([8, 9, 10, 11], "int64_ABCDEFGH"), ([], "int16")):
            with self.assertRaises(ValueError):
                apply_format_to_rows(window, rows, fmt)

    def test_formats_are_saved_and_invalid_ones_dropped(self):
        window = MasterWindow(1, 1, address=0, qty=4, formats={0: "float32_ABCD"})
        data = MasterWindow.validated_kwargs(window.to_json())
        self.assertEqual(data["formats"], {0: "float32_ABCD"})
        data = MasterWindow.validated_kwargs(
            {"formats": {"0": "nonsense", "x": "int16", "70000": "int16", "2": "hex16"}})
        self.assertEqual(data["formats"], {2: "hex16"})

    def test_write_uses_the_format_of_the_clicked_value(self):
        window = MasterWindow(1, 1, slave=3, address=0, qty=8, fmt="int16")
        request, _ = MasterMixin.master_build_write(None, window, "3", "4", "1", 16,
                                                    "float64_ABCDEFGH")
        self.assertEqual(request[:-2], bytes.fromhex("03 10 0004 0004 08 3FF0 0000 0000 0000"))


class MasterScaleTests(unittest.TestCase):
    SCALE = validate_scale("2000", "10000", "-180", "180", 1, "°")

    def test_scaled_values_are_shown_in_engineering_units(self):
        texts = format_window_values([2000, 6000, 10000, 0x00AB], 0, "int16", {3: "hex16"},
                                     {0: self.SCALE, 1: self.SCALE, 2: self.SCALE,
                                      3: self.SCALE})
        self.assertEqual(texts, ["-180.0 °", "0.0 °", "180.0 °", "0x00AB"])

    def test_scale_applies_to_multi_register_values(self):
        registers = encode_register_value("50", "float32_ABCD")
        scale = validate_scale(0, 100, 0, 10, 2, "bar")
        self.assertEqual(format_window_values(registers, 7, "float32_ABCD", None, {7: scale}),
                         ["5.00 bar", ""])

    def test_written_engineering_values_are_converted_to_raw(self):
        self.assertEqual(raw_text_for_scaled("90", self.SCALE, "int16"), "8000")
        self.assertEqual(raw_text_for_scaled("-180", self.SCALE, "uint16"), "2000")
        window = MasterWindow(1, 1, slave=1, address=0, qty=4,
                              scales={0: self.SCALE})
        request, _ = MasterMixin.master_build_write(None, window, "1", "0", "45", 6,
                                                    "int16", self.SCALE)
        self.assertEqual(request[:-2], bytes.fromhex("01 06 0000 1B58"))  # 7000

    def test_invalid_scales_are_rejected(self):
        for args in (("1", "1", "0", "10"), ("a", "1", "0", "1"), ("0", "1", "0", "1", "9"),
                     ("0", "nan", "0", "1")):
            with self.assertRaises(ValueError):
                validate_scale(*args)
        with self.assertRaises(ValueError):
            raw_text_for_scaled("5", validate_scale(0, 10, 3, 3), "int16")

    def test_scales_are_saved_and_invalid_ones_dropped(self):
        window = MasterWindow(1, 1, scales={4: self.SCALE})
        data = MasterWindow.validated_kwargs(window.to_json())
        self.assertEqual(data["scales"], {4: self.SCALE})
        data = MasterWindow.validated_kwargs({"scales": {
            "1": {"raw": [0, 0], "eng": [0, 1]}, "x": self.SCALE, "2": "bad",
            "3": {"raw": [0, 10], "eng": [0, 1], "decimals": 2, "unit": "A"}}})
        self.assertEqual(list(data["scales"]), [3])


class MasterOpenFromTrafficTests(unittest.TestCase):
    def definition(self, record):
        return MasterMixin.master_definition_from_record(None, record)

    def test_request_and_matched_response_give_the_read_definition(self):
        request = {"type": "REQUEST", "slave": "5", "fc": "03", "pdu_address": 100, "qty": 4}
        self.assertEqual(self.definition(request),
                         {"slave": 5, "fc": 3, "address": 100, "qty": 4})
        response = {"type": "RESPONSE", "slave": "5", "fc": "04",
                    "request_pdu_address": 7, "request_qty": 2}
        self.assertEqual(self.definition(response)["address"], 7)
        exception = {"type": "EXCEPTION", "slave": "5", "fc": "83",
                     "request_pdu_address": 1, "request_qty": 1}
        self.assertEqual(self.definition(exception)["fc"], 3)

    def test_frames_without_a_read_definition_are_refused(self):
        for record in (
            {"type": "REQUEST", "slave": "5", "fc": "06", "pdu_address": 1, "qty": None},
            {"type": "RESPONSE", "slave": "5", "fc": "03"},
            {"type": "RAW/UNPARSED", "slave": "", "fc": ""},
            {"type": "REQUEST", "slave": "0", "fc": "03", "pdu_address": 1, "qty": 1},
        ):
            self.assertIsNone(self.definition(record))


class FlakySlaveSerial(FakeSlaveSerial):
    """Fake slave whose port fails (like an unplugged USB adapter)."""

    def __init__(self, failures, **kwargs):
        super().__init__(**kwargs)
        self.failures = failures
        self.closed = False

    def write(self, data):
        if self.failures:
            self.failures -= 1
            raise OSError("device disconnected")
        return super().write(data)

    def close(self):
        self.closed = True


class MasterReconnectTests(unittest.TestCase):
    def test_engine_reopens_the_port_after_a_failure(self):
        broken = FlakySlaveSerial(failures=1)
        fresh = FakeSlaveSerial()
        reopen_calls = []
        engine = make_engine(broken, reconnect_interval_s=0.05,
                             reopen=lambda: reopen_calls.append(1) or fresh)
        engine.set_poll(PollDefinition(1, 1, 3, 0, 2, 0))
        engine.start()
        time.sleep(0.4)
        engine.stop()
        events = drain(engine.event_queue)
        names = [name for name, _payload in events]
        self.assertIn("master_reconnecting", names)
        self.assertIn("master_reconnected", names)
        self.assertTrue(broken.closed)
        self.assertIs(engine.ser, fresh)
        after = names[names.index("master_reconnected"):]
        self.assertIn("master_result", after)
        self.assertEqual(events[-1], ("master_stopped", {"error": None}))

    def test_engine_keeps_retrying_until_stopped(self):
        attempts = []

        def reopen():
            attempts.append(1)
            raise OSError("still unplugged")

        engine = make_engine(FlakySlaveSerial(failures=5), reconnect_interval_s=0.02,
                             reopen=reopen)
        engine.set_poll(PollDefinition(1, 1, 3, 0, 1, 0))
        engine.start()
        time.sleep(0.3)
        engine.stop()
        events = drain(engine.event_queue)
        self.assertGreater(len(attempts), 3)
        self.assertNotIn("master_reconnected", [n for n, _p in events])
        self.assertEqual(events[-1][0], "master_stopped")

    def test_without_reopen_a_failure_ends_the_session(self):
        engine = make_engine(FlakySlaveSerial(failures=1))
        engine.set_poll(PollDefinition(1, 1, 3, 0, 1, 0))
        engine.start()
        time.sleep(0.2)
        engine.stop()
        stopped = drain(engine.event_queue)[-1]
        self.assertEqual(stopped[0], "master_stopped")
        self.assertEqual(stopped[1]["error"][0], "serial")


class MasterSettingsTests(unittest.TestCase):
    def test_last_workspace_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            original = mb_config.get_settings_file
            mb_config.get_settings_file = lambda: path
            try:
                for value, expected in (("Linha 1", "Linha 1"), ("a/b", ""), (5, ""),
                                        ("x" * 61, ""), ("  Subestação  ", "Subestação")):
                    path.write_text(json.dumps({"master": {"last_workspace": value}}),
                                    encoding="utf-8")
                    self.assertEqual(
                        mb_config.load_ui_settings()["master"]["last_workspace"], expected)
            finally:
                mb_config.get_settings_file = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
