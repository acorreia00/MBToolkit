# MBSniffer

[Português](README.md) | [English](README.en.md)

**MBSniffer** is a Windows application for diagnosing **Modbus RTU** communications over **RS485** and **RS232**. It can passively observe and analyse bus traffic and also includes an active tool for locating Modbus devices.

## Features

- passive Modbus RTU capture on RS485 2-wire and RS232;
- identification of requests, responses, exceptions, CRC errors and RAW data;
- Frame Inspector with addresses, quantities, data and CRC details;
- request/response pairing and response-time measurement;
- Bus Health metrics including response times, timeouts and the percentage of non-validated bytes;
- traffic filters, search, anomaly highlighting and CSV export;
- complete TXT logging for real capture sessions;
- **Bus Slave Finder** for active Slave ID discovery, with optional Device Identification (FC43/14) and a safety warning;
- Light and Dark modes with persistent preferences.

> **Warning:** the Sniffer is passive, but the **Bus Slave Finder transmits Modbus RTU requests**. Do not use it on a bus that already has another active master.

## Run

Requires **Windows 10/11 x64**. After extracting the package, run:

```text
MBSniffer.bat
```

The launcher checks Python and installs `pyserial` when required. To build the standalone executable, use `MBSniffer v2.9\build_exe.bat`.

Application preferences are stored in `%APPDATA%\MBSniffer\settings.json`. The selected COM port is not saved, so you must choose the port again each time you start the program.
