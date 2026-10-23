#!/usr/bin/env python3
"""Capture the Sniffer, Bus Slave Finder, Master and Slave UI figures for the PDF.

Launches SnifferApp from a package folder, shows each main tab and saves
``sniffer.png``, ``finder.png``, ``master.png`` and ``slave.png`` (client area
only, no title bar) into the output folder.  Windows only (uses PIL.ImageGrab).

The Master figure is taken while connected to the in-memory test slave from
``tests/test_master.py`` (FakeSlaveSerial), so it shows live values without
any hardware. For the Slave figure the Master is disconnected and the Slave
tab answers a MasterEngine over the in-memory link of ``tests/test_slave.py``.

The user's real settings are never read or written: APPDATA is redirected
to a temporary folder, so the screenshots always show the default (PT-PT,
Light mode) interface.  No __pycache__ is written into the package.

Usage:
    python tools/capture_ui_screenshots.py --app-dir "MBToolkit v3.1" --out tools/screenshots
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path


def prepare_master_demo(app, app_dir):
    """Connect the Master tab to the test suite's fake slave with demo windows."""
    sys.path.insert(0, str(app_dir / "tests"))
    from test_master import FakeSlaveSerial

    class FakeSerialModule:
        SerialTimeoutException = TimeoutError
        SerialException = OSError

    slave = FakeSlaveSerial(slave_id=1)
    slave.registers.update({0: 0x42F6, 1: 0xE979, 2: 0x4120, 3: 0x0000})
    app.get_serial_modules = lambda: (FakeSerialModule, None)
    app.open_discovery_serial_port = lambda *a, **k: slave
    for window_id in list(app.master_windows):
        app.master_close_window(window_id)
    first = app.master_add_window({"slave": 1, "fc": 3, "address": 0, "qty": 6,
                                   "scan_ms": 250, "fmt": "float32_ABCD",
                                   "names": {0: "Temperatura", 2: "Pressão"}})
    app.master_add_window({"slave": 1, "fc": 1, "address": 0, "qty": 8, "scan_ms": 500})
    app.master_add_window({"slave": 7, "fc": 3, "address": 100, "qty": 4, "scan_ms": 1000})
    app.master_port_var.set("COM3")
    app.master_timeout_var.set("100")
    app.master_safety_var.set(True)
    app.master_connect()
    return first


def prepare_slave_demo(app, app_dir):
    """Disconnect the Master and let a MasterEngine poll the Slave tab."""
    import queue

    sys.path.insert(0, str(app_dir / "tests"))
    from mb_master import MasterEngine, PollDefinition, build_write_request
    from mb_slave import validate_fault
    from test_slave import BusEnd

    import time

    app.master_disconnect()
    deadline = time.monotonic() + 3.0
    while app.master_active and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    master_end, slave_end = BusEnd.pair()
    app.open_discovery_serial_port = lambda *a, **k: slave_end
    for window_id in list(app.slave_windows):
        app.slave_close_window(window_id)
    holding = app.slave_add_window({"slave": 1, "table": "holding", "address": 0, "qty": 6,
                                    "formats": {0: "float32_ABCD"},
                                    "names": {0: "Temperatura", 2: "Setpoint"}})
    app.slave_add_window({"slave": 1, "table": "coils", "address": 0, "qty": 8})
    app.slave_add_window({"slave": 7, "table": "input", "address": 100, "qty": 4,
                          "title": "Inversor 7"})
    app.slave_set_value(holding, 0, "21.5")
    app.slave_set_value(holding, 2, "450")
    app.slave_set_fault(7, validate_fault({"no_response": True, "probability": 20}))
    app.slave_port_var.set("COM4")
    app.slave_safety_var.set(True)
    app.slave_connect()
    app.slave_engine.baud = 115200
    master = MasterEngine(master_end, queue.Queue(), baud=115200, parity="None",
                          stopbits="1", response_timeout_ms=100, delay_ms=5)
    master.start()
    master.set_poll(PollDefinition(1, 1, 3, 0, 6, 200))
    master.set_poll(PollDefinition(2, 7, 4, 100, 4, 300))
    master.queue_write(1, build_write_request(1, 15, 2, [1, 1, 0, 1]), "")
    master.queue_write(1, build_write_request(1, 16, 4, [1200, 34]), "")
    return master


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app-dir", required=True, help="Folder containing MBToolkit.py (e.g. 'MBToolkit v3.1')")
    parser.add_argument("--out", required=True, help="Output folder for the PNG figures")
    parser.add_argument("--geometry", default="1280x780", help="Window size used for the capture")
    parser.add_argument("--settle-ms", type=int, default=1500, help="Delay before each capture")
    args = parser.parse_args(argv)

    sys.dont_write_bytecode = True
    app_dir = Path(args.app_dir).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    settings_home = tempfile.mkdtemp(prefix="mbs_ui_")
    os.environ["APPDATA"] = settings_home

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    sys.path.insert(0, str(app_dir))
    import mb_config
    mb_config.debug_sim = 0
    from mb_gui import SnifferApp
    from PIL import ImageGrab

    app = SnifferApp()
    app.geometry(f"{args.geometry}+30+30")
    app.attributes("-topmost", True)
    app.lift()

    shots = [("sniffer", "sniffer_page"), ("finder", "discovery_page")]
    if hasattr(app, "master_page"):
        shots.append(("master", "master_page"))
        prepare_master_demo(app, app_dir)
    if hasattr(app, "slave_page"):
        shots.append(("slave", "slave_page"))
    demo = {}

    def grab(index=0):
        if index >= len(shots):
            if demo.get("master") is not None:
                demo["master"].stop()
            app.attributes("-topmost", False)
            app.on_close()
            return
        name, page_attr = shots[index]
        if name == "slave":
            demo["master"] = prepare_slave_demo(app, app_dir)
        app.main_notebook.select(getattr(app, page_attr))
        app.update_idletasks()
        app.update()

        def capture():
            app.update()
            x, y = app.winfo_rootx(), app.winfo_rooty()
            w, h = app.winfo_width(), app.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
            target = out_dir / f"{name}.png"
            image.save(target)
            print(f"saved {target} ({image.width}x{image.height})")
            grab(index + 1)

        # The Slave figure is taken while the last master write is still highlighted.
        settle = 900 if name == "slave" else args.settle_ms
        app.after(settle, capture)

    app.after(300, grab)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
