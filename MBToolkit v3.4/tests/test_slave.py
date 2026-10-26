import os
import queue
import random
import tempfile
import threading
import time
import unittest

from mb_master import (
    MasterEngine,
    PollDefinition,
    build_read_request,
    build_write_request,
    find_master_response,
)
from mb_protocol import append_crc, crc_ok
from mb_slave import (
    SlaveEngine,
    SlaveStore,
    corrupt_crc,
    fault_active,
    handle_request,
    request_length,
    validate_fault,
)
import mb_config
from mb_i18n import LANGUAGE_ENGLISH, translate_text
from mb_slave_ui import SlaveWindow, fault_parts, validate_area
from mb_table_ui import list_workspaces, workspace_path


class BusEnd:
    """One end of an in-memory serial link: what one end writes, the other reads.

    With *echo*, every byte written also comes back to the writer, like an
    RS485 adapter that hears its own transmission.
    """

    def __init__(self, echo=False):
        self.echo = echo
        self.peer = None
        self.rx = bytearray()
        self.written = []
        self._lock = threading.Lock()

    @staticmethod
    def pair(echo_a=False, echo_b=False):
        a, b = BusEnd(echo_a), BusEnd(echo_b)
        a.peer, b.peer = b, a
        return a, b

    @property
    def in_waiting(self):
        with self._lock:
            return len(self.rx)

    def read(self, size):
        with self._lock:
            data = bytes(self.rx[:size])
            del self.rx[:size]
            return data

    def write(self, data):
        data = bytes(data)
        self.written.append(data)
        if self.echo:
            self.inject(data)
        if self.peer is not None:
            self.peer.inject(data)
        return len(data)

    def inject(self, data):
        with self._lock:
            self.rx.extend(data)

    def reset_input_buffer(self):
        with self._lock:
            self.rx.clear()

    def reset_output_buffer(self):
        pass

    def cancel_read(self):
        pass

    def cancel_write(self):
        pass

    def close(self):
        pass


def make_store():
    store = SlaveStore()
    store.set_areas([(1, "holding", 0, 20), (1, "coils", 0, 16), (1, "input", 100, 4),
                     (1, "discrete", 0, 8), (2, "holding", 0, 10)])
    store.write(1, "holding", 0, [i * 10 for i in range(20)])
    store.write(1, "input", 100, [7, 8, 9, 10])
    store.write(1, "coils", 0, [1, 0, 1, 1])
    store.write(1, "discrete", 0, [0, 1])
    return store


def drain(event_queue):
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
    return events


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class SlaveRequestTests(unittest.TestCase):
    def test_reads_answer_from_the_tables(self):
        store = make_store()
        reply = handle_request(store, build_read_request(1, 3, 2, 3))
        self.assertEqual(reply.status, "ok")
        found = find_master_response(reply.response, build_read_request(1, 3, 2, 3))
        self.assertEqual(found["values"], [20, 30, 40])
        found = find_master_response(handle_request(store, build_read_request(1, 1, 0, 4)).response,
                                     build_read_request(1, 1, 0, 4))
        self.assertEqual(found["values"], [1, 0, 1, 1])
        found = find_master_response(handle_request(store, build_read_request(1, 4, 100, 4)).response,
                                     build_read_request(1, 4, 100, 4))
        self.assertEqual(found["values"], [7, 8, 9, 10])
        found = find_master_response(handle_request(store, build_read_request(1, 2, 0, 2)).response,
                                     build_read_request(1, 2, 0, 2))
        self.assertEqual(found["values"], [0, 1])

    def test_writes_change_the_tables_and_answer_like_a_device(self):
        store = make_store()
        request = build_write_request(1, 6, 5, [1234])
        reply = handle_request(store, request)
        self.assertEqual(reply.response, request)
        self.assertEqual(reply.written, [(1, "holding", 5, 1)])
        self.assertEqual(store.read(1, "holding", 5, 1), [1234])

        request = build_write_request(1, 16, 10, [1, 2, 3])
        reply = handle_request(store, request)
        self.assertEqual(reply.response, append_crc(request[:6]))
        self.assertEqual(store.read(1, "holding", 10, 3), [1, 2, 3])

        handle_request(store, build_write_request(1, 5, 1, [1]))
        handle_request(store, build_write_request(1, 15, 8, [1, 1, 0, 1, 0, 0, 1]))
        self.assertEqual(store.read(1, "coils", 0, 2), [1, 1])
        self.assertEqual(store.read(1, "coils", 8, 7), [1, 1, 0, 1, 0, 0, 1])

    def test_exceptions_like_a_real_device(self):
        store = make_store()
        # Address outside the defined areas, also when only partly outside.
        for request in (build_read_request(1, 3, 20, 1), build_read_request(1, 3, 18, 4),
                        build_read_request(1, 4, 0, 1), build_write_request(1, 6, 50, [1])):
            reply = handle_request(store, request)
            self.assertEqual((reply.status, reply.exception_code), ("exception", 2))
            self.assertEqual(reply.response, append_crc(bytes((1, request[1] | 0x80, 2))))
        # Unsupported function.
        reply = handle_request(store, append_crc(bytes((1, 0x08, 0, 0, 0x12, 0x34))))
        self.assertEqual(reply.exception_code, 1)
        # Bad quantity and bad FC05 value.
        reply = handle_request(store, append_crc(bytes((1, 3, 0, 0, 0, 0))))
        self.assertEqual(reply.exception_code, 3)
        reply = handle_request(store, append_crc(bytes((1, 5, 0, 1, 0x12, 0x34))))
        self.assertEqual(reply.exception_code, 3)

    def test_other_slave_ids_are_ignored(self):
        reply = handle_request(make_store(), build_read_request(9, 3, 0, 1))
        self.assertEqual(reply.status, "ignored")
        self.assertIsNone(reply.response)

    def test_broadcast_writes_every_covering_slave_without_answering(self):
        store = make_store()
        reply = handle_request(store, build_write_request(0, 6, 3, [77]))
        self.assertEqual(reply.status, "broadcast")
        self.assertIsNone(reply.response)
        self.assertEqual(sorted(reply.written), [(1, "holding", 3, 1), (2, "holding", 3, 1)])
        self.assertEqual(store.read(2, "holding", 3, 1), [77])
        # Slave 2 does not cover address 15: only slave 1 is written.
        reply = handle_request(store, build_write_request(0, 6, 15, [5]))
        self.assertEqual(reply.written, [(1, "holding", 15, 1)])
        # Broadcast reads and errors are never answered.
        self.assertIsNone(handle_request(store, append_crc(bytes((0, 3, 0, 0, 0, 1)))).response)
        self.assertIsNone(handle_request(store, append_crc(bytes((0, 6, 0, 90, 0, 1)))).response)

    def test_request_length(self):
        self.assertIsNone(request_length(b"\x01"))
        self.assertEqual(request_length(build_read_request(1, 3, 0, 1)), 8)
        self.assertEqual(request_length(build_write_request(1, 16, 0, [1, 2])), 13)
        self.assertIsNone(request_length(b"\x01\x10\x00\x00\x00\x02"))
        self.assertIsNone(request_length(b"\x01\x2B\x0E\x01"))

    def test_window_areas_define_the_slave(self):
        window = SlaveWindow(1, 1, slave=4, table="input", address=10, qty=5)
        store = SlaveStore()
        store.set_areas([window.area()])
        self.assertEqual(store.slave_ids(), {4})
        self.assertTrue(store.covers(4, "input", 10, 5))
        self.assertFalse(store.covers(4, "input", 10, 6))


class SlaveFaultTests(unittest.TestCase):
    def test_fault_validation(self):
        self.assertFalse(fault_active(validate_fault({})))
        fault = validate_fault({"delay_ms": "250", "probability": "10", "exception": 6})
        self.assertTrue(fault_active(fault))
        self.assertEqual((fault["delay_ms"], fault["probability"], fault["exception"]),
                         (250, 10, 6))
        for bad in ({"delay_ms": -1}, {"delay_ms": 10001}, {"probability": 0},
                    {"probability": 101}, {"exception": 5}, {"delay_ms": "x"}):
            with self.assertRaises(ValueError):
                validate_fault(bad)

    def test_inactive_faults_are_not_stored(self):
        store = make_store()
        store.set_fault(1, validate_fault({"probability": 50}))
        self.assertIsNone(store.fault(1))
        store.set_fault(1, validate_fault({"bad_crc": True}))
        self.assertTrue(store.fault(1)["bad_crc"])
        store.set_fault(1, None)
        self.assertEqual(store.faults(), {})

    def test_corrupt_crc(self):
        frame = build_read_request(1, 3, 0, 1)
        self.assertFalse(crc_ok(corrupt_crc(frame)))


class SlaveEngineTests(unittest.TestCase):
    """The Master engine talking to the Slave engine over an in-memory bus."""

    def setUp(self):
        self.store = make_store()
        self.master_end, self.slave_end = BusEnd.pair()
        self.slave_events = queue.Queue()
        self.master_events = queue.Queue()
        self.slave = None
        self.master = None

    def tearDown(self):
        for engine in (self.master, self.slave):
            if engine is not None:
                engine.stop()

    def start_slave(self, **options):
        self.slave = SlaveEngine(self.slave_end, self.slave_events, self.store, baud=115200,
                                 parity="None", stopbits="1", **options)
        self.slave.start()

    def start_master(self, timeout_ms=200):
        self.master = MasterEngine(self.master_end, self.master_events, baud=115200,
                                   parity="None", stopbits="1",
                                   response_timeout_ms=timeout_ms, delay_ms=0)
        self.master.start()

    def master_results(self, count, timeout=3.0):
        results = []
        deadline = time.monotonic() + timeout
        while len(results) < count and time.monotonic() < deadline:
            try:
                event, payload = self.master_events.get(timeout=0.05)
            except queue.Empty:
                continue
            if event == "master_result":
                results.append(payload)
        return results

    def test_master_reads_and_writes_every_function(self):
        self.start_slave()
        self.start_master()
        for window_id, (fc, address, qty) in enumerate(
                ((3, 0, 5), (4, 100, 4), (1, 0, 4), (2, 0, 2)), start=1):
            self.master.set_poll(PollDefinition(window_id, 1, fc, address, qty, 10000))
        values = {r["window_id"]: r["values"] for r in self.master_results(4)}
        self.assertEqual(values, {1: [0, 10, 20, 30, 40], 2: [7, 8, 9, 10],
                                  3: [1, 0, 1, 1], 4: [0, 1]})

        for request in (build_write_request(1, 6, 0, [999]), build_write_request(1, 16, 1, [5, 6]),
                        build_write_request(1, 5, 1, [1]),
                        build_write_request(1, 15, 2, [0, 0])):
            self.master.queue_write(1, request, "w")
        statuses = [r["status"] for r in self.master_results(4) if r["kind"] == "write"]
        self.assertEqual(statuses, ["ok"] * 4)
        self.assertEqual(self.store.read(1, "holding", 0, 3), [999, 5, 6])
        self.assertEqual(self.store.read(1, "coils", 0, 4), [1, 1, 0, 0])
        written = [p["written"] for e, p in drain(self.slave_events)
                   if e == "slave_request" and p["written"]]
        self.assertIn([(1, "holding", 1, 2)], written)

    def test_exception_reaches_the_master(self):
        self.start_slave()
        self.start_master()
        self.master.set_poll(PollDefinition(1, 1, 3, 30, 2, 10000))
        result = self.master_results(1)[0]
        self.assertEqual((result["status"], result["exception_code"]), ("exception", 2))

    def test_adapter_echo_and_foreign_traffic_are_ignored(self):
        self.slave_end.echo = True
        self.start_slave()
        # A response of another slave on the bus before the request.
        self.slave_end.inject(append_crc(bytes((9, 3, 2, 0x12, 0x34))))
        self.start_master()
        self.master.set_poll(PollDefinition(1, 1, 3, 2, 2, 20))
        results = self.master_results(5)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r["status"] == "ok" and r["values"] == [20, 30] for r in results))
        answered = []

        def five_answered():
            answered.extend(p for e, p in drain(self.slave_events)
                            if e == "slave_request" and p["status"] == "ok")
            return len(answered) >= 5

        self.assertTrue(wait_for(five_answered))

    def test_split_request_is_assembled(self):
        self.start_slave()
        request = build_read_request(1, 3, 0, 2)
        self.slave_end.inject(request[:3])
        time.sleep(0.01)
        self.slave_end.inject(request[3:])
        self.assertTrue(wait_for(lambda: len(self.slave_end.written) == 1))
        found = find_master_response(self.slave_end.written[0], request)
        self.assertEqual(found["values"], [0, 10])

    def test_garbage_before_a_request_is_dropped(self):
        self.start_slave(silence_ms=20)
        request = build_read_request(1, 3, 0, 1)
        self.slave_end.inject(b"\x01\x10\xFF" + request)
        self.assertTrue(wait_for(lambda: len(self.slave_end.written) == 1))
        self.assertEqual(find_master_response(self.slave_end.written[0], request)["values"], [0])

    def test_unknown_function_gets_exception_01_after_silence(self):
        self.start_slave(silence_ms=10)
        self.slave_end.inject(append_crc(bytes((1, 0x2B, 0x0E, 0x01, 0x00))))
        self.assertTrue(wait_for(lambda: len(self.slave_end.written) == 1))
        self.assertEqual(self.slave_end.written[0], append_crc(bytes((1, 0xAB, 1))))

    def test_faults(self):
        self.start_slave(rng=random.Random(1))
        self.start_master(timeout_ms=100)
        self.master.set_poll(PollDefinition(1, 1, 3, 0, 1, 10000))

        self.store.set_fault(1, validate_fault({"no_response": True}))
        self.master.read_once(1)
        self.assertEqual(self.master_results(2)[-1]["status"], "timeout")

        self.store.set_fault(1, validate_fault({"exception": 6}))
        self.master.read_once(1)
        result = self.master_results(1)[0]
        self.assertEqual((result["status"], result["exception_code"]), ("exception", 6))

        self.store.set_fault(1, validate_fault({"bad_crc": True}))
        self.master.read_once(1)
        self.assertEqual(self.master_results(1)[0]["status"], "invalid")

        self.store.set_fault(1, validate_fault({"delay_ms": 300}))
        self.master.read_once(1)
        self.assertEqual(self.master_results(1)[0]["status"], "timeout")
        time.sleep(0.35)  # let the late response pass before the next request

        self.store.set_fault(1, None)
        self.master.read_once(1)
        self.assertEqual(self.master_results(1)[0]["status"], "ok")

    def test_fault_probability(self):
        store = make_store()
        store.set_fault(1, validate_fault({"no_response": True, "probability": 30}))
        engine = SlaveEngine(BusEnd(), queue.Queue(), store, baud=115200, parity="None",
                             stopbits="1", rng=random.Random(7))
        engine.gap_s = 0
        for _ in range(400):
            engine._answer(build_read_request(1, 3, 0, 1))
        statuses = [p["status"] for _e, p in drain(engine.event_queue)]
        silent = statuses.count("no_response")
        self.assertTrue(80 <= silent <= 160, silent)
        self.assertEqual(silent + statuses.count("ok"), 400)


class SlaveWindowTests(unittest.TestCase):
    def test_workspace_entry_round_trip_and_validation(self):
        window = SlaveWindow(1, 1, slave=3, table="coils", address=5, qty=16, base=1,
                             title=" Saídas ", names={5: "Bomba"})
        data = SlaveWindow.validated_kwargs(window.to_json())
        self.assertEqual((data["title"], data["slave"], data["table"], data["address"],
                          data["qty"], data["base"], data["names"]),
                         ("Saídas", 3, "coils", 5, 16, 1, {5: "Bomba"}))
        for bad in ({"slave": 0}, {"slave": 248}, {"table": "x"}, {"qty": 0},
                    {"qty": 2001}, {"address": 65530, "qty": 10}):
            with self.assertRaises(ValueError):
                SlaveWindow.validated_kwargs(bad)
        validate_area(1, "input", 65535, 1)

    def test_table_field_shows_the_read_function_code(self):
        from mb_slave import table_choice_label
        from mb_slave_ui import TABLE_CHOICES, TABLE_KEYS_BY_LABEL
        self.assertEqual(TABLE_CHOICES, ("01 Coils", "02 Discrete Inputs",
                                         "03 Holding Registers", "04 Input Registers"))
        for table in ("coils", "discrete", "holding", "input"):
            self.assertEqual(TABLE_KEYS_BY_LABEL[table_choice_label(table)], table)

    def test_window_overlap(self):
        window = SlaveWindow(1, 1, address=10, qty=5)
        self.assertEqual(window.overlap(0, 12), (0, 2))
        self.assertEqual(window.overlap(12, 100), (2, 5))
        self.assertIsNone(window.overlap(15, 3))
        self.assertIsNone(window.overlap(0, 10))

    def test_fault_description_translates(self):
        fault = validate_fault({"no_response": True, "delay_ms": 50, "exception": 4})
        parts = [translate_text(template, LANGUAGE_ENGLISH).format(**values)
                 for template, values in fault_parts(fault)]
        self.assertEqual(parts, ["no response", "Exception 04", "delay 50 ms"])
        self.assertEqual(translate_text("Falhas…", LANGUAGE_ENGLISH), "Faults…")


class SlaveSettingsTests(unittest.TestCase):
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

    def test_slave_workspaces_have_their_own_folder(self):
        folder = mb_config.get_slave_workspaces_folder()
        self.assertEqual(folder.parent, mb_config.get_workspaces_folder())
        workspace_path("Banco", folder).write_text("{}", encoding="utf-8")
        self.assertEqual(list_workspaces(folder), ["Banco"])
        # Not listed with the Master ones.
        self.assertEqual(list_workspaces(mb_config.get_master_workspaces_folder()), [])

    def test_slave_settings_are_validated(self):
        mb_config.save_ui_settings(settings={
            "slave": {"baud": "19200", "parity": "Even", "stop_bits": "2",
                      "last_workspace": "Banco"},
            "last_main_tab": "Slave"})
        loaded = mb_config.load_ui_settings()
        self.assertEqual(loaded["slave"], {"baud": "19200", "parity": "Even",
                                           "stop_bits": "2", "last_workspace": "Banco"})
        self.assertEqual(loaded["last_main_tab"], "Slave")
        mb_config.save_ui_settings(settings={
            "slave": {"baud": "1", "parity": "x", "stop_bits": "3", "last_workspace": "a/b"}})
        self.assertEqual(mb_config.load_ui_settings()["slave"],
                         {"baud": "9600", "parity": "None", "stop_bits": "1",
                          "last_workspace": ""})


if __name__ == "__main__":
    unittest.main()
