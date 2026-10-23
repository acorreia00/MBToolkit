#!/usr/bin/env python3
"""MBToolkit application configuration, constants and filesystem helpers."""

import ctypes
import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "MBToolkit"
# Product name up to v3.2. Its settings folder is migrated on first start.
LEGACY_APP_NAME = "MBSniffer"
APP_VERSION = "3.4"

# Simulação:
#   0 = simulação inativa (o botão não aparece no GUI)
#   1 = simulação ativa  (o botão aparece no GUI)
debug_sim = 0

# Active Modbus RTU slave discovery.
DISCOVERY_BAUD_RATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
DISCOVERY_PARITIES = ("None", "Even", "Odd")
DISCOVERY_STOP_BITS = ("1", "2")
DISCOVERY_DEFAULT_MIN_TIMEOUT_MS = 100
# v3.0 default; settings saved by v3.0 with this value migrate to the new default.
DISCOVERY_LEGACY_DEFAULT_MIN_TIMEOUT_MS = 40
DISCOVERY_MIN_TIMEOUT_MS = 10
DISCOVERY_MAX_TIMEOUT_MS = 2000
DISCOVERY_PROBE_ADDRESS = 0
DISCOVERY_PROBE_QTY = 1
DISCOVERY_WRITE_TIMEOUT_SECONDS = 1.5
DISCOVERY_WRITE_RETRIES = 1
DISCOVERY_RX_BUFFER_LIMIT = 1024
# Total probe attempts per FC when a Slave does not answer.
DISCOVERY_MIN_ATTEMPTS = 1
DISCOVERY_MAX_ATTEMPTS = 3
DISCOVERY_DEFAULT_ATTEMPTS = 1
# Passive listen before the first transmission; any byte aborts the scan.
DISCOVERY_IDLE_CHECK_SECONDS = 1.0

# GUI queue processing limits.
UI_QUEUE_BATCH_SIZE = 200
UI_QUEUE_IDLE_INTERVAL_MS = 50
UI_QUEUE_BUSY_INTERVAL_MS = 10

# Pending-request timeout.
MIN_PENDING_REQUEST_TIMEOUT_SECONDS = 1.0
DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS = 10.0
MAX_PENDING_REQUEST_TIMEOUT_SECONDS = 300.0
PENDING_REQUEST_TIMEOUT_SECONDS = DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS

# Master (poll) tab. Modbus limits per request; RTU response timeout and the
# silent gap between two requests are user settings.
MASTER_MAX_READ_BITS = 2000
MASTER_MAX_READ_REGISTERS = 125
MASTER_MAX_WRITE_BITS = 1968
MASTER_MAX_WRITE_REGISTERS = 123
MASTER_DEFAULT_RESPONSE_TIMEOUT_MS = 1000
MASTER_MIN_RESPONSE_TIMEOUT_MS = 10
MASTER_MAX_RESPONSE_TIMEOUT_MS = 10000
MASTER_DEFAULT_DELAY_MS = 20
MASTER_MIN_DELAY_MS = 0
MASTER_MAX_DELAY_MS = 10000
MASTER_DEFAULT_SCAN_MS = 1000
MASTER_MAX_SCAN_MS = 3600000
MASTER_MAX_WINDOWS = 32
# When the serial port fails (e.g. USB adapter unplugged), the Master keeps
# trying to reopen it at this interval until it succeeds or is disconnected.
MASTER_RECONNECT_INTERVAL_SECONDS = 2.0
MASTER_WORKSPACE_FORMAT = "MBToolkit Master workspace"
# Workspaces saved by MBSniffer v3.2 use this format name and still open.
MASTER_WORKSPACE_FORMATS = (MASTER_WORKSPACE_FORMAT, "MBSniffer Master workspace")
MASTER_WORKSPACE_VERSION = 1

# Slave (simulator) tab. Each window is one data table of one simulated Slave
# ID; requests are answered from those tables.
SLAVE_MAX_WINDOWS = 32
SLAVE_MAX_QTY = 2000
# A master write is shown highlighted in the table for this long.
SLAVE_HIGHLIGHT_SECONDS = 1.5
SLAVE_FAULT_MAX_DELAY_MS = 10000
# Bytes that do not form a request (other devices' responses, noise) are
# discarded once the bus has been silent this long. Long enough for the
# latency-timer chunks of USB-serial adapters (FTDI default 16 ms).
SLAVE_RESYNC_SILENCE_MS = 40.0
SLAVE_WORKSPACE_FORMAT = "MBToolkit Slave workspace"
SLAVE_WORKSPACE_VERSION = 1

# Sniffer burst assembly: extra wait when a burst ends with the start of a
# recognised frame. USB-serial adapters deliver bytes in latency-timer
# chunks (FTDI default 16 ms), which can split one RTU frame in two.
SNIFFER_SPLIT_FRAME_HOLD_MS = 40.0

# Diagnostic thresholds.
SLOW_RESPONSE_THRESHOLD_MS = 500.0

# Standard Modbus exception response codes.
MODBUS_EXCEPTION_CODES = {
    0x01: (
        "Illegal Function",
        "A função Modbus pedida não é suportada/permitida pelo dispositivo."
    ),
    0x02: (
        "Illegal Data Address",
        "O endereço ou a gama de endereços pedida não é válida neste dispositivo."
    ),
    0x03: (
        "Illegal Data Value",
        "Um valor, quantidade ou campo do pedido é inválido para esta função."
    ),
    0x04: (
        "Server Device Failure",
        "O dispositivo encontrou um erro interno ao tentar executar o pedido."
    ),
    0x05: (
        "Acknowledge",
        "O pedido foi aceite, mas necessita de mais tempo para ser processado."
    ),
    0x06: (
        "Server Device Busy",
        "O dispositivo está ocupado e não consegue processar o pedido neste momento."
    ),
    0x08: (
        "Memory Parity Error",
        "Foi detetado um erro de paridade ao aceder à memória do dispositivo."
    ),
    0x0A: (
        "Gateway Path Unavailable",
        "O gateway não conseguiu estabelecer o caminho para o dispositivo de destino."
    ),
    0x0B: (
        "Gateway Target Device Failed to Respond",
        "O gateway não recebeu resposta do dispositivo de destino."
    ),
}

# Bounded GUI history. The disk log remains complete.
MAX_UI_FRAMES = 20000
MAX_RAW_TEXT_LINES = 20000
UI_PRUNE_CHUNK_FRAMES = 2000
RAW_TEXT_PRUNE_CHUNK_LINES = 2000
RAW_TRANSACTION_SEPARATOR = "─" * 72 + "\n"

SIMULATION_FUNCTION_CODES = (1, 2, 3, 4)
SIMULATION_EXCEPTION_CODES = (1, 2, 3, 4, 6)

def resource_path(filename):
    """Return a bundled/source resource path for normal Python or PyInstaller."""
    try:
        base = Path(sys._MEIPASS)
    except (AttributeError, TypeError):
        base = Path(__file__).resolve().parent
    return base / filename

def set_windows_app_user_model_id():
    """
    Give Windows a stable application identity so the taskbar can associate
    the Tk window with MBToolkit instead of a generic Python process.
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{APP_NAME}.{APP_VERSION}"
        )
    except Exception:
        pass



def get_settings_file() -> Path:
    """
    Return the persistent per-user settings file.

    Windows:
        %APPDATA%\\MBToolkit\\settings.json

    Fallback:
        ~/.mbtoolkit/settings.json

    This location is independent from the EXE/BAT folder, so the selected
    Light/Dark mode survives application updates and also works when the
    application folder is read-only.
    """
    try:
        folder = _settings_folder(APP_NAME)
        if not folder.exists():
            _migrate_legacy_settings(folder)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "settings.json"
    except Exception:
        return Path.home() / ".mbtoolkit_settings.json"


def _settings_folder(app_name):
    if os.name == "nt":
        roaming_app_data = os.environ.get("APPDATA")
        if roaming_app_data:
            return Path(roaming_app_data) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    return Path.home() / f".{app_name.lower()}"


def _migrate_legacy_settings(folder):
    """Copy MBSniffer's settings and workspaces into the new MBToolkit folder.

    Runs once, when the MBToolkit folder does not exist yet. The old folder
    is left untouched. Failures are ignored: settings are convenience state.
    """
    legacy = _settings_folder(LEGACY_APP_NAME)
    if not legacy.is_dir():
        return
    try:
        shutil.copytree(legacy, folder)
    except Exception:
        pass


def _validated_choice(value, allowed, default):
    return value if value in allowed else default


def _validated_bool(value, default):
    return value if isinstance(value, bool) else default


def _validated_number_string(value, minimum, maximum, default):
    try:
        number = float(value)
        if minimum <= number <= maximum:
            return f"{number:g}"
    except (TypeError, ValueError):
        pass
    return str(default)


def _validated_int_string(value, minimum, maximum, default):
    try:
        number = int(value)
        if minimum <= number <= maximum:
            return str(number)
    except (TypeError, ValueError):
        pass
    return str(default)


def load_ui_settings() -> dict:
    """
    Load validated user preferences from the single Roaming settings file.

    Machine-specific state such as COM-port names and window geometry is
    deliberately excluded.
    """
    path = get_settings_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    result = {}

    if isinstance(data.get("dark_mode"), bool):
        result["dark_mode"] = data["dark_mode"]

    if data.get("language") in ("Português", "English"):
        result["language"] = data["language"]

    if data.get("last_main_tab") in ("Sniffer", "Bus Slave Finder", "Master", "Slave"):
        result["last_main_tab"] = data["last_main_tab"]

    sniffer_in = data.get("sniffer")
    if isinstance(sniffer_in, dict):
        # v2.9 migration: the UI option was renamed from "Realçar anomalias"
        # to "Realçar resultados". Accept the old key once so existing user
        # preferences are not lost, but expose/save only the new name.
        highlight_results_value = sniffer_in.get(
            "highlight_results",
            sniffer_in.get("highlight_anomalies"),
        )

        result["sniffer"] = {
            "physical_mode": _validated_choice(
                sniffer_in.get("physical_mode"),
                ("RS485 2-wire", "RS232 single RX", "RS232 dual RX"),
                "RS485 2-wire",
            ),
            "baud": _validated_choice(
                str(sniffer_in.get("baud", "")),
                tuple(str(v) for v in DISCOVERY_BAUD_RATES),
                "9600",
            ),
            "data_bits": _validated_choice(
                str(sniffer_in.get("data_bits", "")),
                ("5", "6", "7", "8"),
                "8",
            ),
            "parity": _validated_choice(
                sniffer_in.get("parity"),
                ("None", "Even", "Odd", "Mark", "Space"),
                "None",
            ),
            "stop_bits": _validated_choice(
                str(sniffer_in.get("stop_bits", "")),
                ("1", "1.5", "2"),
                "1",
            ),
            "frame_gap_mode": _validated_choice(
                sniffer_in.get("frame_gap_mode"),
                ("Auto", "Manual"),
                "Auto",
            ),
            "frame_gap_ms": str(sniffer_in.get("frame_gap_ms", "")),
            "pending_timeout_s": _validated_number_string(
                sniffer_in.get("pending_timeout_s"),
                MIN_PENDING_REQUEST_TIMEOUT_SECONDS,
                MAX_PENDING_REQUEST_TIMEOUT_SECONDS,
                DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS,
            ),
            "auto_scroll": _validated_bool(
                sniffer_in.get("auto_scroll"),
                True,
            ),
            "separate_transactions": _validated_bool(
                sniffer_in.get("separate_transactions"),
                True,
            ),
            "highlight_results": _validated_bool(
                highlight_results_value,
                False,
            ),
        }

    finder_in = data.get("bus_slave_finder")
    if isinstance(finder_in, dict):
        saved_bauds = finder_in.get("baud_rates")
        if isinstance(saved_bauds, list):
            baud_rates = [
                int(v) for v in saved_bauds
                if isinstance(v, (int, float, str))
                and str(v).isdigit()
                and int(v) in DISCOVERY_BAUD_RATES
            ]
        else:
            baud_rates = [9600, 19200]

        saved_parities = finder_in.get("parities")
        if isinstance(saved_parities, list):
            parities = [
                v for v in saved_parities
                if v in DISCOVERY_PARITIES
            ]
        else:
            parities = ["None", "Even"]

        saved_stops = finder_in.get("stop_bits")
        if isinstance(saved_stops, list):
            stop_bits = [
                str(v) for v in saved_stops
                if str(v) in DISCOVERY_STOP_BITS
            ]
        else:
            stop_bits = ["1"]

        min_timeout_ms = _validated_int_string(
            finder_in.get("min_timeout_ms"),
            DISCOVERY_MIN_TIMEOUT_MS,
            DISCOVERY_MAX_TIMEOUT_MS,
            DISCOVERY_DEFAULT_MIN_TIMEOUT_MS,
        )
        # Settings written before v3.1 have no "attempts" key. Their 40 ms
        # value is the old automatic default, not a user choice.
        if (
            "attempts" not in finder_in
            and min_timeout_ms == str(DISCOVERY_LEGACY_DEFAULT_MIN_TIMEOUT_MS)
        ):
            min_timeout_ms = str(DISCOVERY_DEFAULT_MIN_TIMEOUT_MS)

        result["bus_slave_finder"] = {
            "baud_rates": baud_rates,
            "parities": parities,
            "stop_bits": stop_bits,
            "slave_start": _validated_int_string(
                finder_in.get("slave_start"),
                1,
                247,
                1,
            ),
            "slave_end": _validated_int_string(
                finder_in.get("slave_end"),
                1,
                247,
                247,
            ),
            "min_timeout_ms": min_timeout_ms,
            "attempts": _validated_int_string(
                finder_in.get("attempts"),
                DISCOVERY_MIN_ATTEMPTS,
                DISCOVERY_MAX_ATTEMPTS,
                DISCOVERY_DEFAULT_ATTEMPTS,
            ),
            "fc04_fallback": _validated_bool(
                finder_in.get("fc04_fallback"),
                False,
            ),
            "device_identification": _validated_bool(
                finder_in.get("device_identification"),
                False,
            ),
        }

    master_in = data.get("master")
    if isinstance(master_in, dict):
        result["master"] = {
            "baud": _validated_choice(
                str(master_in.get("baud", "")),
                tuple(str(v) for v in DISCOVERY_BAUD_RATES),
                "9600",
            ),
            "parity": _validated_choice(
                master_in.get("parity"), ("None", "Even", "Odd"), "None"
            ),
            "stop_bits": _validated_choice(
                str(master_in.get("stop_bits", "")), ("1", "2"), "1"
            ),
            "response_timeout_ms": _validated_int_string(
                master_in.get("response_timeout_ms"),
                MASTER_MIN_RESPONSE_TIMEOUT_MS,
                MASTER_MAX_RESPONSE_TIMEOUT_MS,
                MASTER_DEFAULT_RESPONSE_TIMEOUT_MS,
            ),
            "delay_ms": _validated_int_string(
                master_in.get("delay_ms"),
                MASTER_MIN_DELAY_MS,
                MASTER_MAX_DELAY_MS,
                MASTER_DEFAULT_DELAY_MS,
            ),
            # Workspace reopened at start-up (name of a file in Workspaces).
            "last_workspace": _validated_workspace_name(master_in.get("last_workspace")),
        }

    slave_in = data.get("slave")
    if isinstance(slave_in, dict):
        result["slave"] = {
            "baud": _validated_choice(
                str(slave_in.get("baud", "")),
                tuple(str(v) for v in DISCOVERY_BAUD_RATES),
                "9600",
            ),
            "parity": _validated_choice(
                slave_in.get("parity"), ("None", "Even", "Odd"), "None"
            ),
            "stop_bits": _validated_choice(
                str(slave_in.get("stop_bits", "")), ("1", "2"), "1"
            ),
            "last_workspace": _validated_workspace_name(slave_in.get("last_workspace")),
        }

    return result


def _validated_workspace_name(value):
    """Workspace name remembered in settings.json, or "" when unusable."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not 0 < len(value) <= 60 or any(ch in '<>:"/\\|?*' for ch in value):
        return ""
    return value


def save_ui_settings(settings=None, **updates) -> None:
    """
    Persist UI preferences atomically in the single Roaming settings file.

    Partial updates merge with the existing file. This lets the Dark-mode
    toggle update immediately without discarding the other remembered options.
    """
    path = get_settings_file()

    current = load_ui_settings()
    if isinstance(settings, dict):
        current.update(settings)
    current.update(updates)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(current, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception:
        # Remembered UI state must never break application use.
        pass


def get_application_directory() -> Path:
    """
    Return the user-facing application directory.

    - PyInstaller EXE: directory containing MBToolkit.exe.
    - Packaged Python/BAT mode: directory containing the root MBToolkit.bat.
      The Python sources live inside the versioned child folder, e.g. ``MBToolkit v3.4``.
    - Development Python mode: directory containing this module.
    """
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent

        source_dir = Path(__file__).resolve().parent
        launcher_dir = source_dir.parent

        if (launcher_dir / "MBToolkit.bat").is_file():
            return launcher_dir

        return source_dir
    except Exception:
        return Path.cwd()

def get_workspaces_folder() -> Path:
    """
    Return/create the Master workspace folder beside settings.json:

        %APPDATA%\\MBToolkit\\Workspaces
    """
    folder = get_settings_file().parent / "Workspaces"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_slave_workspaces_folder() -> Path:
    """
    Return/create the Slave workspace folder inside the workspace folder:

        %APPDATA%\\MBToolkit\\Workspaces\\Slave
    """
    folder = get_workspaces_folder() / "Slave"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_logs_folder() -> Path:
    """
    Return/create the log directory beside MBToolkit.bat or MBToolkit.exe:

        <launcher/exe directory>/MBToolkit Logs
    """
    folder = get_application_directory() / "MBToolkit Logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
