#!/usr/bin/env python3
"""Modbus TCP transport: MBAP framing, Server engine and Client engine.

This module has no widgets. Modbus TCP carries the same PDU as Modbus RTU
(function code + data) inside an MBAP header instead of Slave ID + CRC:

    Transaction ID (2) | Protocol ID = 0 (2) | Length (2) | Unit ID (1) | PDU

The Modbus logic is not repeated here: a TCP request is turned into the
equivalent RTU frame (Unit ID as Slave ID, CRC added) and served by
``mb_slave.handle_request()``; a Client request is built by ``mb_master`` and
its response is matched by ``find_master_response()``. Only the envelope,
the sockets and the per-connection bookkeeping are TCP-specific.
"""

import ipaddress
import json
import os
import random
import selectors
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

from mb_master import MasterEngine, PollDefinition, build_read_request, find_master_response
from mb_protocol import append_crc, hex_bytes
from mb_slave import FC_TABLES, handle_request

MBAP_LENGTH = 7
MODBUS_TCP_PORT = 502
# Largest Length field: Unit ID + a 253-byte PDU.
MBAP_MAX_LENGTH = 254
# Exception sent by the Server for a Unit ID it does not simulate.
EXCEPTION_GATEWAY_TARGET_FAILED = 0x0B
SERVER_MAX_CLIENTS = 16
# A Client does not retry a device that refused the connection for this long.
CLIENT_RETRY_SECONDS = 1.0


# ---------------------------------------------------------------------------
# MBAP framing
# ---------------------------------------------------------------------------

def build_adu(transaction, unit, pdu, protocol=0):
    """MBAP header + PDU."""
    pdu = bytes(pdu)
    return (transaction.to_bytes(2, "big") + protocol.to_bytes(2, "big")
            + (len(pdu) + 1).to_bytes(2, "big") + bytes((unit & 0xFF,)) + pdu)


def adu_length(buffer):
    """Total length of the ADU starting at buffer[0]; None if the header is incomplete.

    Raises ValueError when the Length field is impossible (the connection is
    then out of step and must be closed).
    """
    if len(buffer) < 6:
        return None
    length = (buffer[4] << 8) | buffer[5]
    if not 2 <= length <= MBAP_MAX_LENGTH:
        raise ValueError(f"MBAP Length {length}")
    return 6 + length


def parse_adu(adu):
    """(transaction, protocol, unit, pdu) of one complete ADU."""
    return ((adu[0] << 8) | adu[1], (adu[2] << 8) | adu[3], adu[6], bytes(adu[7:]))


def rtu_to_adu(rtu_frame, transaction):
    """ADU for an RTU frame: Slave ID becomes Unit ID, the CRC is dropped."""
    return build_adu(transaction, rtu_frame[0], rtu_frame[1:-2])


def adu_to_rtu(unit, pdu):
    """Equivalent RTU frame (Unit ID as Slave ID, valid CRC) of a TCP PDU."""
    return append_crc(bytes((unit & 0xFF,)) + bytes(pdu))


def validate_host(text):
    """Return a cleaned IP address or host name; raise ValueError (PT)."""
    host = str(text or "").strip()
    if not host or len(host) > 253 or any(ch.isspace() for ch in host):
        raise ValueError("Indica um endereço IP ou nome válido.")
    return host


def validate_tcp_port(text):
    try:
        port = int(str(text).strip())
    except ValueError:
        raise ValueError("A porta TCP tem de estar entre 1 e 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("A porta TCP tem de estar entre 1 e 65535.")
    return port


def list_ipv4_interfaces():
    """[(ip, interface name)] of this PC's IPv4 addresses, loopback excluded.

    On Windows the names come from Get-NetIPAddress (run hidden, 5 s limit);
    elsewhere, or if that fails, the addresses of the host name are used
    without names.
    """
    found = []
    if os.name == "nt":
        try:
            command = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                       "Get-NetIPAddress -AddressFamily IPv4 | "
                       "Select-Object IPAddress,InterfaceAlias | ConvertTo-Json -Compress")
            output = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.decode("utf-8", "replace").strip()
            data = json.loads(output) if output else []
            for item in data if isinstance(data, list) else [data]:
                found.append((str(item.get("IPAddress", "")), str(item.get("InterfaceAlias", ""))))
        except Exception:
            found = []
    if not found:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                found.append((info[4][0], ""))
        except OSError:
            pass
    result, seen = [], set()
    for ip, name in found:
        try:
            if ipaddress.ip_address(ip).is_loopback or ip in seen:
                continue
        except ValueError:
            continue
        seen.add(ip)
        result.append((ip, name))
    # Link-local addresses (169.254.x.x, adapters without DHCP) go last.
    return sorted(result, key=lambda item: (ipaddress.ip_address(item[0]).is_link_local,
                                            ipaddress.ip_address(item[0])))


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def _request_area(fc, pdu):
    """(table, address, qty) named by a request PDU, for the window counters."""
    if fc not in FC_TABLES or len(pdu) < 5:
        return None, None, None
    address = (pdu[1] << 8) | pdu[2]
    qty = 1 if fc in (5, 6) else (pdu[3] << 8) | pdu[4]
    return FC_TABLES[fc], address, qty


class ServerEngine:
    """Modbus TCP server: answers several clients from one SlaveStore.

    One thread serves the listening socket and every client connection with
    ``selectors``. Each request is answered from the store like the RTU Slave
    (``handle_request``); a Unit ID that is not simulated gets Exception 0B
    (Gateway Target Device Failed to Respond). The fault simulation of the
    Unit ID applies: no response, a chosen Exception, a corrupted MBAP header
    (Protocol ID 1) and a delay, which is scheduled so other clients are not
    held up. Events: ``server_ready``, ``server_client``, ``server_request``
    and ``server_stopped``.
    """

    def __init__(self, event_queue, store, *, host, port, rng=None,
                 max_clients=SERVER_MAX_CLIENTS):
        self.event_queue = event_queue
        self.store = store
        self.host = host
        self.port = int(port)
        self.rng = rng or random.Random()
        self.max_clients = max_clients
        self.stop_event = threading.Event()
        self.thread = None
        self.bound_port = None
        self._clients = {}    # socket -> {"peer": "ip:port", "rx": bytearray}
        self._pending = []    # [(due, socket, data)] delayed responses

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self, join_timeout=1.0):
        self.stop_event.set()
        thread = self.thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

    def run(self):
        error = None
        listener = None
        selector = selectors.DefaultSelector()
        try:
            try:
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    # Windows: never share the port with another server.
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                listener.bind((self.host, self.port))
                listener.listen(self.max_clients)
                listener.setblocking(False)
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"
                return
            self.bound_port = listener.getsockname()[1]
            selector.register(listener, selectors.EVENT_READ, None)
            self.event_queue.put(("server_ready", {"host": self.host, "port": self.bound_port}))
            while not self.stop_event.is_set():
                timeout = 0.1
                if self._pending:
                    timeout = max(0.0, min(timeout, min(p[0] for p in self._pending)
                                           - time.perf_counter()))
                for key, _mask in selector.select(timeout):
                    if key.data is None:
                        self._accept(listener, selector)
                    else:
                        self._receive(key.fileobj, selector)
                self._send_due(selector)
        finally:
            for sock in list(self._clients):
                self._drop(sock, selector, notify=False)
            if listener is not None:
                try:
                    listener.close()
                except OSError:
                    pass
            selector.close()
            self.event_queue.put(("server_stopped", {"error": error}))

    # -- connections ---------------------------------------------------------
    def _accept(self, listener, selector):
        try:
            sock, address = listener.accept()
        except OSError:
            return
        if len(self._clients) >= self.max_clients:
            sock.close()
            return
        sock.setblocking(False)
        peer = f"{address[0]}:{address[1]}"
        self._clients[sock] = {"peer": peer, "rx": bytearray()}
        selector.register(sock, selectors.EVENT_READ, peer)
        self.event_queue.put(("server_client", {"peer": peer, "connected": True,
                                                "count": len(self._clients)}))

    def _drop(self, sock, selector, notify=True):
        client = self._clients.pop(sock, None)
        try:
            selector.unregister(sock)
        except (KeyError, ValueError, OSError):
            pass
        try:
            sock.close()
        except OSError:
            pass
        self._pending = [p for p in self._pending if p[1] is not sock]
        if notify and client is not None:
            self.event_queue.put(("server_client", {"peer": client["peer"], "connected": False,
                                                    "count": len(self._clients)}))

    def _receive(self, sock, selector):
        client = self._clients.get(sock)
        if client is None:
            return
        try:
            data = sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._drop(sock, selector)
            return
        buffer = client["rx"]
        buffer.extend(data)
        while True:
            try:
                length = adu_length(buffer)
            except ValueError:
                self._drop(sock, selector)  # out of step: close like a real server
                return
            if length is None or len(buffer) < length:
                return
            adu = bytes(buffer[:length])
            del buffer[:length]
            self._answer(sock, client["peer"], adu)

    def _send(self, sock, data):
        try:
            sock.sendall(data)
        except OSError:
            pass

    def _send_due(self, selector):
        if not self._pending:
            return
        now = time.perf_counter()
        due = [p for p in self._pending if p[0] <= now]
        self._pending = [p for p in self._pending if p[0] > now]
        for _due, sock, data in due:
            if sock in self._clients:
                self._send(sock, data)

    # -- requests ----------------------------------------------------------------
    def _answer(self, sock, peer, adu):
        transaction, protocol, unit, pdu = parse_adu(adu)
        if protocol != 0 or not pdu:
            return  # not Modbus: ignored, as a real server does
        fc = pdu[0] & 0x7F
        table, address, qty = _request_area(fc, pdu)
        info = {"slave": unit, "fc": fc, "table": table, "address": address, "qty": qty,
                "status": "ok", "exception_code": None, "written": [], "fault": False,
                "time": time.time(), "peer": peer}

        response_pdu = None
        fault = None
        if unit not in self.store.slave_ids():
            info.update(status="exception", exception_code=EXCEPTION_GATEWAY_TARGET_FAILED)
            response_pdu = bytes((fc | 0x80, EXCEPTION_GATEWAY_TARGET_FAILED))
        else:
            fault = self.store.fault(unit)
            if fault and self.rng.random() * 100.0 >= fault["probability"]:
                fault = None
            info["fault"] = bool(fault)
            if fault and fault["no_response"]:
                info["status"] = "no_response"
            elif fault and fault["exception"]:
                info.update(status="exception", exception_code=fault["exception"])
                response_pdu = bytes((fc | 0x80, fault["exception"]))
            else:
                reply = handle_request(self.store, adu_to_rtu(unit, pdu))
                info.update(status=reply.status, exception_code=reply.exception_code,
                            written=list(reply.written))
                if reply.table is not None:
                    info.update(table=reply.table, address=reply.address, qty=reply.qty)
                if reply.response is not None:
                    response_pdu = reply.response[1:-2]

        if response_pdu is not None:
            # A corrupted response carries Protocol ID 1 (clients reject it).
            protocol_out = 1 if fault and fault["bad_crc"] else 0
            data = build_adu(transaction, unit, response_pdu, protocol_out)
            delay_s = fault["delay_ms"] / 1000.0 if fault else 0.0
            if delay_s > 0:
                self._pending.append((time.perf_counter() + delay_s, sock, data))
            else:
                self._send(sock, data)
            info["response"] = len(data)
        self.event_queue.put(("server_request", info))


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@dataclass
class ClientPollDefinition(PollDefinition):
    """Poll window of the TCP Client: the device's address and Unit ID 0–255."""
    host: str = "127.0.0.1"
    port: int = MODBUS_TCP_PORT

    def request(self):
        # RTU form with the Unit ID in the Slave byte: mb_master validates
        # Slave IDs 1–247, Modbus TCP allows Unit IDs 0–255.
        frame = build_read_request(1, self.fc, self.address, self.qty)
        return append_crc(bytes((self.slave & 0xFF,)) + frame[1:-2])


class ClientEngine(MasterEngine):
    """Modbus TCP client: the Master scheduler over one connection per device.

    Windows are served one request at a time, exactly like the Master (writes,
    then "read once", then the earliest due poll). Each window names its
    device (host:port); connections are opened on first use, kept open and
    reopened after a failure, at most once per CLIENT_RETRY_SECONDS. A device
    that cannot be reached gives the status ``no_connection``. Events are
    ``client_ready``, ``client_result`` and ``client_stopped``.
    """

    def __init__(self, event_queue, *, response_timeout_ms, delay_ms):
        super().__init__(None, event_queue, baud=115200, parity="None", stopbits="1",
                         response_timeout_ms=response_timeout_ms, delay_ms=delay_ms,
                         event_prefix="client")
        self.delay_s = max(0.0, float(delay_ms) / 1000.0)
        self._sockets = {}      # (host, port) -> socket
        self._failed = {}       # (host, port) -> (time, error text)
        self._transaction = 0

    def run(self):
        try:
            super().run()
        finally:
            for sock in self._sockets.values():
                try:
                    sock.close()
                except OSError:
                    pass
            self._sockets = {}

    def _connection(self, target):
        sock = self._sockets.get(target)
        if sock is not None:
            return sock
        failed = self._failed.get(target)
        if failed and time.monotonic() - failed[0] < CLIENT_RETRY_SECONDS:
            raise ConnectionError(failed[1])
        try:
            sock = socket.create_connection(target, timeout=self.response_timeout_s)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as exc:
            text = f"{type(exc).__name__}: {exc}"
            self._failed[target] = (time.monotonic(), text)
            raise ConnectionError(text) from None
        self._failed.pop(target, None)
        self._sockets[target] = sock
        return sock

    def _close(self, target):
        sock = self._sockets.pop(target, None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def transact_for(self, window_id, request):
        with self._lock:
            entry = self._polls.get(window_id)
        result = {"tx": "", "rx": "", "status": "stopped", "values": None,
                  "exception_code": None, "response_ms": None}
        if entry is None or self.stop_event.is_set():
            return result
        definition = entry[0]
        target = (definition.host, int(definition.port))
        request = append_crc(bytes(request[:-2]))  # valid CRC for the Unit ID byte
        self._transaction = (self._transaction + 1) & 0xFFFF
        transaction = self._transaction
        adu = rtu_to_adu(request, transaction)
        result["tx"] = hex_bytes(adu)
        try:
            sock = self._connection(target)
            sock.sendall(adu)
        except (OSError, ConnectionError) as exc:
            self._close(target)
            result.update(status="no_connection", error=str(exc))
            return result

        started = time.perf_counter()
        deadline = started + self.response_timeout_s
        buffer = bytearray()
        while not self.stop_event.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                result["status"] = "timeout"
                result["rx"] = hex_bytes(buffer)
                return result
            try:
                sock.settimeout(min(remaining, 0.1))
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                self._close(target)
                result.update(status="no_connection", error=f"{type(exc).__name__}: {exc}")
                return result
            if not data:
                self._close(target)
                result.update(status="no_connection", error="ligação fechada pelo equipamento")
                return result
            buffer.extend(data)
            while True:
                try:
                    length = adu_length(buffer)
                except ValueError:
                    self._close(target)
                    result.update(status="invalid", rx=hex_bytes(buffer))
                    return result
                if length is None or len(buffer) < length:
                    break
                answer = bytes(buffer[:length])
                del buffer[:length]
                got_transaction, protocol, _unit, pdu = parse_adu(answer)
                if got_transaction != transaction:
                    continue  # late answer to an earlier request
                result["rx"] = hex_bytes(answer)
                result["response_ms"] = (time.perf_counter() - started) * 1000.0
                found = None if protocol != 0 else find_master_response(
                    adu_to_rtu(request[0], pdu), request)
                if found is None:
                    result["status"] = "invalid"
                else:
                    result.update(status="exception" if found["kind"] == "EXCEPTION" else "ok",
                                  values=found["values"],
                                  exception_code=found["exception_code"])
                return result
        return result
