import os
import queue
import random
import socket
import tempfile
import time
import unittest

import mb_config

from mb_master import build_write_request
from mb_protocol import append_crc, crc_ok
from mb_slave import SlaveStore, validate_fault
from mb_tcp import (
    ClientEngine,
    ClientPollDefinition,
    ServerEngine,
    adu_length,
    adu_to_rtu,
    build_adu,
    parse_adu,
    rtu_to_adu,
    validate_host,
    validate_tcp_port,
)
from mb_tcp_ui import ClientTab, ClientWindow, ServerTab


def make_store():
    store = SlaveStore()
    store.set_areas([(1, "holding", 0, 10), (1, "coils", 0, 8), (2, "input", 100, 4)])
    store.write(1, "holding", 0, [i * 10 for i in range(10)])
    store.write(1, "coils", 0, [1, 0, 1])
    store.write(2, "input", 100, [7, 8, 9, 10])
    return store


def wait_event(event_queue, name, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event, payload = event_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        if event == name:
            return payload
    raise AssertionError(f"no {name} event")


class MbapFramingTests(unittest.TestCase):
    def test_adu_round_trip(self):
        request = build_write_request(17, 16, 0x6B, [0x0102, 0x0304])
        adu = rtu_to_adu(request, 0x1234)
        self.assertEqual(adu[:7], bytes.fromhex("1234 0000 000B 11"))
        self.assertEqual(adu_length(adu), len(adu))
        transaction, protocol, unit, pdu = parse_adu(adu)
        self.assertEqual((transaction, protocol, unit), (0x1234, 0, 17))
        self.assertEqual(adu_to_rtu(unit, pdu), request)
        self.assertTrue(crc_ok(adu_to_rtu(unit, pdu)))

    def test_incomplete_and_impossible_headers(self):
        self.assertIsNone(adu_length(b"\x00\x01\x00\x00\x00"))
        with self.assertRaises(ValueError):
            adu_length(bytes.fromhex("0001 0000 0001"))
        with self.assertRaises(ValueError):
            adu_length(bytes.fromhex("0001 0000 0100"))

    def test_host_and_port_validation(self):
        self.assertEqual(validate_host(" 192.168.1.10 "), "192.168.1.10")
        self.assertEqual(validate_tcp_port("502"), 502)
        for bad in ("", "a b", "x" * 254):
            with self.assertRaises(ValueError):
                validate_host(bad)
        for bad in ("0", "65536", "porta"):
            with self.assertRaises(ValueError):
                validate_tcp_port(bad)


class ServerClientTests(unittest.TestCase):
    """The Client engine talking to the Server engine over 127.0.0.1."""

    def setUp(self):
        self.store = make_store()
        self.server_events = queue.Queue()
        self.server = ServerEngine(self.server_events, self.store, host="127.0.0.1", port=0,
                                   rng=random.Random(1))
        self.server.start()
        self.port = wait_event(self.server_events, "server_ready")["port"]
        self.client_events = queue.Queue()
        self.client = None

    def tearDown(self):
        if self.client is not None:
            self.client.stop()
        self.server.stop()

    def start_client(self, timeout_ms=300):
        self.client = ClientEngine(self.client_events, response_timeout_ms=timeout_ms,
                                   delay_ms=0)
        self.client.start()

    def poll(self, window_id, unit, fc, address, qty, port=None):
        self.client.set_poll(ClientPollDefinition(window_id, unit, fc, address, qty, 10000,
                                                  host="127.0.0.1", port=port or self.port))

    def results(self, count, timeout=3.0):
        found = []
        deadline = time.monotonic() + timeout
        while len(found) < count and time.monotonic() < deadline:
            try:
                event, payload = self.client_events.get(timeout=0.05)
            except queue.Empty:
                continue
            if event == "client_result":
                found.append(payload)
        return found

    def test_reads_writes_and_exceptions(self):
        self.start_client()
        self.poll(1, 1, 3, 0, 4)
        self.poll(2, 2, 4, 100, 4)
        self.poll(3, 1, 1, 0, 3)
        values = {r["window_id"]: r["values"] for r in self.results(3)}
        self.assertEqual(values, {1: [0, 10, 20, 30], 2: [7, 8, 9, 10], 3: [1, 0, 1]})

        self.client.queue_write(1, build_write_request(1, 16, 2, [222, 333]), "w")
        self.client.queue_write(3, build_write_request(1, 5, 7, [1]), "w")
        writes = [r for r in self.results(2) if r["kind"] == "write"]
        self.assertEqual([r["status"] for r in writes], ["ok", "ok"])
        self.assertEqual(self.store.read(1, "holding", 2, 2), [222, 333])
        self.assertEqual(self.store.read(1, "coils", 7, 1), [1])

        self.poll(4, 1, 3, 50, 1)       # outside the windows -> Exception 02
        self.poll(5, 9, 3, 0, 1)        # Unit ID not simulated -> Exception 0B
        codes = {r["window_id"]: (r["status"], r["exception_code"]) for r in self.results(2)}
        self.assertEqual(codes, {4: ("exception", 2), 5: ("exception", 0x0B)})

    def test_server_events(self):
        self.start_client()
        self.poll(1, 1, 3, 0, 1)
        self.results(1)
        client = wait_event(self.server_events, "server_client")
        self.assertTrue(client["connected"])
        request = wait_event(self.server_events, "server_request")
        self.assertEqual((request["slave"], request["table"], request["address"], request["qty"],
                          request["status"]), (1, "holding", 0, 1, "ok"))

    def test_faults(self):
        self.start_client(timeout_ms=150)
        self.poll(1, 1, 3, 0, 1)
        self.results(1)
        self.store.set_fault(1, validate_fault({"exception": 6}))
        self.client.read_once(1)
        self.assertEqual(self.results(1)[0]["exception_code"], 6)
        self.store.set_fault(1, validate_fault({"bad_crc": True}))
        self.client.read_once(1)
        self.assertEqual(self.results(1)[0]["status"], "invalid")
        self.store.set_fault(1, validate_fault({"no_response": True}))
        self.client.read_once(1)
        self.assertEqual(self.results(1)[0]["status"], "timeout")
        self.store.set_fault(1, validate_fault({"delay_ms": 300}))
        self.client.read_once(1)
        self.assertEqual(self.results(1)[0]["status"], "timeout")
        time.sleep(0.35)  # the late answer arrives and is skipped by Transaction ID
        self.store.set_fault(1, None)
        self.client.read_once(1)
        self.assertEqual(self.results(1)[0]["status"], "ok")

    def test_several_clients_at_once(self):
        sockets = [socket.create_connection(("127.0.0.1", self.port), timeout=1)
                   for _ in range(3)]
        try:
            for index, sock in enumerate(sockets):
                sock.sendall(build_adu(index, 1, bytes.fromhex("03 0000 0002")))
            for index, sock in enumerate(sockets):
                answer = sock.recv(64)
                self.assertEqual(parse_adu(answer)[0], index)
                self.assertEqual(parse_adu(answer)[3], bytes.fromhex("03 04 0000 000A"))
        finally:
            for sock in sockets:
                sock.close()

    def test_unreachable_device_and_reconnection(self):
        self.start_client(timeout_ms=200)
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        dead_port = free.getsockname()[1]
        free.close()
        self.poll(1, 1, 3, 0, 1, port=dead_port)
        result = self.results(1)[0]
        self.assertEqual(result["status"], "no_connection")
        self.assertTrue(result["error"])
        # The same window pointed at the live server works again.
        self.poll(1, 1, 3, 0, 1)
        self.client.read_once(1)
        self.assertTrue(any(r["status"] == "ok" for r in self.results(3)))

    def test_port_in_use_is_reported(self):
        events = queue.Queue()
        second = ServerEngine(events, self.store, host="127.0.0.1", port=self.port)
        second.start()
        stopped = wait_event(events, "server_stopped")
        self.assertIn("Error", stopped["error"])

    def test_unit_ids_above_247(self):
        definition = ClientPollDefinition(1, 255, 3, 0, 1, 1000)
        self.assertEqual(definition.request()[0], 255)
        self.assertTrue(crc_ok(append_crc(definition.request()[:-2])))


class ClientWindowTests(unittest.TestCase):
    def test_workspace_entry_round_trip_and_validation(self):
        window = ClientWindow(1, 1, slave=255, fc=4, address=10, qty=5,
                              host="192.168.1.50", port=1502, names={10: "P"})
        data = ClientWindow.validated_kwargs(window.to_json())
        self.assertEqual((data["slave"], data["host"], data["port"], data["fc"], data["names"]),
                         (255, "192.168.1.50", 1502, 4, {10: "P"}))
        definition = ClientWindow(2, 2, **data).definition()
        self.assertEqual((definition.host, definition.port, definition.request()[0]),
                         ("192.168.1.50", 1502, 255))
        for bad in ({"slave": 256}, {"host": ""}, {"port": 0}, {"fc": 5}):
            with self.assertRaises(ValueError):
                ClientWindow.validated_kwargs(dict(window.to_json(), **bad))

    def test_write_uses_the_unit_id(self):
        window = ClientWindow(1, 1, slave=1, fc=3, address=0, qty=4)
        tab = ClientTab(object())  # no widgets needed to build a request
        request, _ = tab.master_build_write(window, "250", "2", "7", 6)
        self.assertEqual(request[:6], bytes((250, 6, 0, 2, 0, 7)))
        with self.assertRaises(ValueError):
            tab.master_build_write(window, "256", "2", "7", 6)

    def test_tabs_keep_their_own_settings_and_folders(self):
        self.assertEqual(ClientTab._master_settings_key, "client")
        self.assertEqual(ServerTab._slave_settings_key, "server")
        self.assertEqual(ClientTab._master_ws_folder().name, "Client")
        self.assertEqual(ServerTab._slave_ws_folder().name, "Server")


class TcpSettingsTests(unittest.TestCase):
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

    def test_client_and_server_settings_are_validated(self):
        mb_config.save_ui_settings(settings={
            "client": {"response_timeout_ms": "500", "delay_ms": "5", "last_workspace": "Obra"},
            "server": {"bind": "192.168.1.20", "port": "1502", "last_workspace": "Sim"},
            "last_main_tab": "Server"})
        loaded = mb_config.load_ui_settings()
        self.assertEqual(loaded["client"], {"response_timeout_ms": "500", "delay_ms": "5",
                                            "last_workspace": "Obra"})
        self.assertEqual(loaded["server"], {"bind": "192.168.1.20", "port": "1502",
                                            "last_workspace": "Sim"})
        self.assertEqual(loaded["last_main_tab"], "Server")
        mb_config.save_ui_settings(settings={"server": {"bind": "x", "port": "70000"}})
        self.assertEqual(mb_config.load_ui_settings()["server"],
                         {"bind": "127.0.0.1", "port": "502", "last_workspace": ""})


if __name__ == "__main__":
    unittest.main()
