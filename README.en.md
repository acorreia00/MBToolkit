# MBSniffer

[Português](README.md) | [English](README.en.md)

**MBSniffer** is a Windows application for diagnosing **Modbus RTU** communications over **RS485** and **RS232**. It can passively observe and analyse bus traffic, locate Modbus devices on the bus and read/write values as a Modbus RTU master.

## Features

- Passive Modbus RTU capture on RS485 2-wire and RS232;
- Identification of requests, responses, exceptions, CRC errors and RAW data;
- Frame Inspector with addresses, quantities, data and CRC details;
- Read responses showing the address of each register, coil or input;
- Request/response pairing and response-time measurement;
- Bus Health metrics including response times, timeouts and the percentage of non-validated bytes;
- Traffic filters, search, anomaly highlighting and CSV export;
- Complete TXT logging for real capture sessions;
- **Bus Slave Finder** for active Slave ID discovery, with configurable retries, optional Device Identification (FC43/14), a safety warning and an automatic idle-bus check;
- **Master** with several windows (one per Slave or data area): cyclic FC01–FC04 reads, FC05/06/15/16 writes, 16, 32 and 64-bit formats (including float and double, in the 4 byte orders), also per address, scaling to engineering units, per-window counters and errors, named pop-out windows workspaces saved in a menu, "Open in Master" from the Sniffer and the Finder and automatic port reconnection;
- Runtime **Português / English** interface selection;
- Light and Dark modes with persistent preferences.

> **Warning:** the Sniffer is passive, but the **Bus Slave Finder and the Master transmit Modbus RTU requests**. Do not use it on a bus that already has another active master.

## Run

Requires **Windows 10/11 x64**. After extracting the package, run:

```text
MBSniffer.bat
```

The package also contains the git history (`.git`), the documentation tools (`tools/`) and the technical PDF.

The launcher checks Python and installs `pyserial` when required. To build the standalone executable, use `MBSniffer v3.2\build_exe.bat`.

Language, Light/Dark mode and other application preferences are stored in `%APPDATA%\MBSniffer\settings.json`. The selected COM port is not saved, so you must choose the port again each time you start the program.
