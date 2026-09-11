#!/usr/bin/env python3
"""Runtime language support for MBSniffer.

Portuguese (Portugal) is the canonical UI language.  English translations are
kept here so switching language never mutates protocol data or application
logic.
"""

LANGUAGE_PORTUGUESE = "Português"
LANGUAGE_ENGLISH = "English"
LANGUAGE_CHOICES = (LANGUAGE_PORTUGUESE, LANGUAGE_ENGLISH)

# Static UI text. Technical terms that are already English are intentionally
# left out: translate_text() returns unknown strings unchanged.
PT_TO_EN = {
    "Linguagem": "Language",
    "Modo escuro": "Dark mode",
    "Configuração": "Configuration",
    "Modo físico": "Physical mode",
    "RS232 dual RX: COM A escuta uma direção; COM B escuta a direção oposta.": "RS232 dual RX: COM A monitors one direction; COM B monitors the opposite direction.",
    "RS232 single RX: uma COM escuta apenas uma direção da ligação RS232.": "RS232 single RX: one COM port monitors only one direction of the RS232 link.",
    "RS485 2-wire: uma COM consegue observar pedidos e respostas no mesmo par diferencial.": "RS485 2-wire: one COM port can monitor requests and responses on the same differential pair.",
    "Estado": "Status",
    "Visualização": "Display",
    "Gap manual (ms)": "Manual gap (ms)",
    "Estado COM": "COM status",
    "Controlos": "Controls",
    "Iniciar Captura": "Start Capture",
    "Parar": "Stop",
    "Reiniciar COM": "Restart COM",
    "Limpar": "Clear",
    "Abrir pasta de logs": "Open logs folder",
    "Simulação": "Simulation",
    "Separar transações": "Separate transactions",
    "Realçar resultados": "Highlight results",
    "Estatísticas da sessão": "Session statistics",
    "Tráfego": "Traffic",
    "Ajuda / Ligações": "Help / Connections",
    "Filtros": "Filters",
    "Todos": "All",
    "Pesquisa": "Search",
    "Limpar filtros": "Clear filters",
    "Exportar CSV": "Export CSV",
    "Hora ↑": "Time ↑",
    "Hora ↓": "Time ↓",
    "Tipo": "Type",
    "Detalhes": "Details",
    "Copiar Raw Hex": "Copy Raw Hex",
    "Copiar frame descodificado": "Copy decoded frame",
    "Filtrar por este Slave": "Filter by this Slave",
    "Filtrar por este FC": "Filter by this FC",
    "Mostrar apenas esta transação": "Show only this transaction",
    "Limpar filtro de transação": "Clear transaction filter",
    "Tempos de resposta": "Response times",
    "Qualidade": "Quality",
    "Pedidos": "Requests",
    "Pendentes": "Pending",
    "Slave (Filtro) ▾": "Slave (Filter) ▾",
    "Slave (Nenhum) ▾": "Slave (None) ▾",
    "✓ Sucesso": "✓ Success",
    "⚠ Resposta lenta": "⚠ Slow response",
    "● Parado": "● Stopped",
    "● A reiniciar COM": "● Restarting COM",
    "● A capturar": "● Capturing",
    "● A parar": "● Stopping",
    "● A simular": "● Simulating",
    "● Simulação concluída": "● Simulation complete",
    "● Erro na simulação": "● Simulation error",
    "Parado": "Stopped",
    "A iniciar pesquisa…": "Starting scan…",
    "A parar…": "Stopping…",
    "Erro ao iniciar pesquisa": "Error starting scan",
    "Respostas": "Responses",
    "Taxa de pedidos": "Request rate",
    "Slaves ativos": "Active Slaves",
    "Bytes observados": "Observed bytes",
    "Utilização do bus ~": "Bus utilization ~",
    "Média": "Average",
    "Mínimo": "Minimum",
    "Máximo": "Maximum",
    "Slave mais lento": "Slowest Slave",
    "Erros de CRC": "CRC errors",
    "Bytes não validados": "Unvalidated bytes",
    "Taxa de timeout": "Timeout rate",
    "Exceções": "Exceptions",
    "Exceções / Slave": "Exceptions / Slave",
    "Seleciona uma linha no Tráfego para ver a descodificação estruturada do frame.":
        "Select a row in Traffic to view the structured frame decoding.",
    "Recolher": "Collapse",
    "Expandir": "Expand",
    "Resultado": "Result",
    "Dados": "Data",
    "Sucesso": "Success",
    "Resposta lenta": "Slow response",
    "Pendente / sem resultado": "Pending / no result",
    "Sem classificação": "Unclassified",
    "Verde": "Green",
    "Amarelo": "Yellow",
    "Vermelho": "Red",
    "Laranja": "Orange",
    "Roxo": "Purple",
    "Neutro": "Neutral",
    "Desconhecida/outra": "Unknown/other",
    "Não Utilizada": "Not Used",
    "Não selecionada": "Not selected",
    "Aberta": "Open",
    "Detetada": "Detected",
    "Não detetada": "Not detected",
    "Configuração inválida": "Invalid configuration",
    "pyserial em falta": "pyserial missing",
    "Porta COM": "COM port",
    "A porta série não aceitou bytes para transmissão.": "The serial port did not accept bytes for transmission.",
    "Erro ao abrir porta": "Error opening port",
    "Erro de captura": "Capture error",
    "Erro na simulação": "Simulation error",
    "Erro interno": "Internal error",
    "Abrir pasta": "Open folder",
    "Pesquisa ativa — transmite no barramento": "Active scan — transmits on the bus",
    "Esta ferramenta atua temporariamente como master Modbus RTU e envia apenas pedidos de leitura. Não a utilizes com outro master ativo no mesmo barramento.": "This tool temporarily acts as a Modbus RTU master and sends read requests only. Do not use it while another master is active on the same bus.",
    "Confirmo que não existe outro master ativo no barramento.": "I confirm that no other master is active on the bus.",
    "FC03 é o modo rápido. Uma resposta normal OU uma Modbus Exception com CRC válido conta como slave encontrado. Ativa FC04 fallback apenas para dispositivos que possam ignorar FC03 sem devolver Exception. Device Identification envia FC43/14 apenas aos slaves encontrados e tenta ler VendorName, ProductCode e Revision.": "FC03 is the fast mode. A normal response OR a CRC-valid Modbus Exception counts as a found Slave. Enable FC04 fallback only for devices that may ignore FC03 without returning an Exception. Device Identification sends FC43/14 only to found Slaves and attempts to read VendorName, ProductCode and Revision.",
    "Configuração da pesquisa": "Scan configuration",
    "Porta COM": "COM port",
    "A porta série não aceitou bytes para transmissão.": "The serial port did not accept bytes for transmission.",
    "Data bits: 8 (fixo)": "Data bits: 8 (fixed)",
    "Slave IDs / velocidade": "Slave IDs / speed",
    "De": "From",
    "até": "to",
    "Timeout mín.": "Min. timeout",
    "Iniciar pesquisa": "Start scan",
    "Limpar resultados": "Clear results",
    "Slaves encontrados": "Slaves found",
    "Encontrados: 0": "Found: 0",
    "Resultado": "Result",
    "Pesquisa ativa": "Active scan",
    "Erro ao iniciar pesquisa": "Error starting scan",
    "Erro na Bus Slave Finder": "Bus Slave Finder error",
    "Erro na pesquisa": "Scan error",
    "Nenhum": "None",
    "Nenhum slave detetado": "No Slave detected",
    "Crescente — antigo → recente": "Ascending — oldest → newest",
    "Decrescente — recente → antigo": "Descending — newest → oldest",
    "Todos os ficheiros": "All files",
    "Exportar sessão para CSV": "Export session to CSV",
}

EN_TO_PT = {english: portuguese for portuguese, english in PT_TO_EN.items()}
# "None" is also a canonical technical serial-parity value in the Portuguese UI.
# Do not reverse-translate it to "Nenhum" when restoring Portuguese; menu entries
# that need "Nenhum" are rendered from their Portuguese canonical source text.
EN_TO_PT.pop("None", None)

EXCEPTION_DESCRIPTION_EN = {
    0x01: "The requested Modbus function is not supported or permitted by the device.",
    0x02: "The requested address or address range is not valid for this device.",
    0x03: "A value, quantity or request field is invalid for this function.",
    0x04: "The device encountered an internal error while attempting to execute the request.",
    0x05: "The request was accepted but requires more time to be processed.",
    0x06: "The device is busy and cannot process the request at this time.",
    0x08: "A parity error was detected while accessing the device memory.",
    0x0A: "The gateway could not establish a path to the target device.",
    0x0B: "The gateway did not receive a response from the target device.",
}


def normalize_language(value):
    return value if value in LANGUAGE_CHOICES else LANGUAGE_PORTUGUESE


def canonical_ui_text(text):
    """Return the canonical PT-PT form of a known static UI string."""
    value = str(text)
    return EN_TO_PT.get(value, value)


def translate_text(text, language):
    """Translate a known static string; leave technical/unknown text intact."""
    canonical = canonical_ui_text(text)
    if normalize_language(language) == LANGUAGE_ENGLISH:
        return PT_TO_EN.get(canonical, canonical)
    return canonical


def translate_details(text, language):
    """Translate only human-readable fragments embedded in protocol details."""
    value = str(text or "")
    if normalize_language(language) == LANGUAGE_ENGLISH:
        value = value.replace("Registos=", "Registers=")
    else:
        value = value.replace("Registers=", "Registos=")
    return value


def exception_description(code, portuguese_text, language):
    if normalize_language(language) == LANGUAGE_ENGLISH:
        return EXCEPTION_DESCRIPTION_EN.get(code, portuguese_text)
    return portuguese_text


# English Help content. Tags match the tags configured by mb_gui.py.
def english_help_blocks(max_ui_frames_text, max_raw_lines_text,
                        min_pending, max_pending, debug_sim=False):
    blocks = [
        ("title", "MBSniffer — Help and connections\n"),
        (None, "MBSniffer is designed for Modbus RTU communications diagnostics. The Sniffer tab is passive: it opens the COM port(s) for reception and does not transmit requests. Bus Slave Finder is an active scan tool and must only be used when no other master is active on the same bus.\n"),
        ("heading", "Quick start — Sniffer\n"),
        ("bullet", "1. Select the correct physical mode: RS485 2-wire, RS232 single RX or RS232 dual RX.\n"),
        ("bullet", "2. Select the COM port(s) and serial parameters used by the communication being observed.\n"),
        ("bullet", "3. Keep Frame gap set to Auto unless you have a specific reason to change it.\n"),
        ("bullet", "4. Click “Start Capture” and confirm activity through BUS ● RX.\n"),
        ("bullet", "5. Use Traffic for quick diagnostics and Raw Hex / Log to confirm the actual bytes.\n"),
        ("bullet", "6. Select a frame to inspect its detailed analysis in Frame Inspector.\n"),

        ("heading", "1. RS485 2-wire\n"),
        (None, "In this mode, one COM port observes requests and responses on the same differential pair. The sniffer adapter must be connected in parallel and must not act as a master.\n"),
        ("subheading", "Typical connection:\n"),
        ("mono", "        Device A              Device B\n             D+ --------------- D+\n             D- --------------- D-\n               \\               /\n                \\             /\n                 D+           D-\n                  USB-RS485 sniffer\n\n"),
        ("bullet", "• Connect sniffer D+ in parallel with bus D+.\n"),
        ("bullet", "• Connect sniffer D− in parallel with bus D−.\n"),
        ("bullet", "• If a C/COM/0 V reference is available, connect it only when you know it is the correct RS485 interface reference.\n"),
        ("warning", "• Do not add a third 120 Ω termination resistor if the bus is already terminated at both ends.\n"),
        ("bullet", "• If the USB-RS485 adapter has selectable termination or bias, leave them disabled during passive capture unless they are intentionally required by the installation.\n"),
        ("bullet", "• A/B naming is not universal: different manufacturers may use opposite polarities. Prefer D+/D− and the equipment documentation.\n"),

        ("heading", "2. RS232 single RX\n"),
        (None, "Observes only one RS232 direction. RS232 is full-duplex: each direction uses an independent TX line, so one RX input cannot observe both directions simultaneously.\n"),
        ("mono", "        Device A                       Device B\n             TX ----------------------------> RX\n              \\\n               \\----> USB-RS232 sniffer RX (COM A)\n\n             GND --------------------------- GND\n               \\--------------------------> sniffer GND\n\n        Sniffer TX: DO NOT CONNECT\n\n"),
        ("bullet", "• Connect sniffer RX to the TX line you want to observe.\n"),
        ("bullet", "• Connect the common GND as well.\n"),
        ("warning", "• Leave the TX pin of the adapter used as a sniffer physically disconnected.\n"),

        ("heading", "3. RS232 dual RX\n"),
        (None, "Allows both RS232 directions to be observed at the same time. Two independent RX channels are required, normally two USB-RS232 adapters.\n"),
        ("mono", "        Device A                       Device B\n             TX ----------------------------> RX\n              \\----> sniffer RX COM A   (A → B)\n\n             RX <----------------------------- TX\n                                      \\----> sniffer RX COM B   (B → A)\n\n             GND ---------------------------- GND\n               \\---------------------------- COM A GND\n                \\--------------------------- COM B GND\n\n        TX on both sniffers: DO NOT CONNECT\n\n"),
        ("bullet", "• COM A is shown as A→B and COM B as B→A.\n"),
        ("bullet", "• Both COM ports must use the same serial parameters as the observed link.\n"),

        ("heading", "RS232 is not TTL\n"),
        ("warning", "Do not connect RS232 signals directly to 3.3 V or 5 V USB-TTL/UART interfaces. Use a USB-RS232 adapter with a transceiver suitable for RS232 voltage levels.\n"),

        ("heading", "Serial communication parameters\n"),
        (None, "Baud rate, Data bits, Parity and Stop bits must match the actual communication. Incorrect parameters may produce apparently random bytes, frames with invalid CRC, or no recognizable frames at all.\n"),
        ("bullet", "• Baud rate — speed in bit/s, for example 9600 or 19200.\n"),
        ("bullet", "• Data bits — normally 8 for Modbus RTU.\n"),
        ("bullet", "• Parity — None, Even, Odd, Mark or Space, according to the installation.\n"),
        ("bullet", "• Stop bits — 1, 1.5 or 2, according to the observed configuration.\n"),

        ("heading", "Frame gap\n"),
        (None, "In Auto mode, MBSniffer uses 3.5 character times up to and including 19200 bit/s. Above 19200 bit/s it uses the fixed 1.750 ms t3.5 recommended for Modbus RTU. Manual mode allows another millisecond value to be used when diagnosing equipment or drivers with particular behavior.\n"),
        (None, "USB adapters and Windows may group bytes and introduce latency. MBSniffer timestamps are therefore useful for sequence diagnostics and relative timing, but they do not replace a logic analyzer when high-precision timing measurements are required.\n"),

        ("heading", "Pending timeout\n"),
        (None, "Defines how long a CRC-valid REQUEST may remain waiting for a matchable RESPONSE/EXCEPTION. When it expires, the original REQUEST is marked as timeout and the Timeout/Timeout rate counters increase.\n"),
        (None, f"Allowed range: {min_pending:g} to {max_pending:g} s. The value should be greater than the normal maximum response time of the installation to avoid false timeouts.\n"),

        ("heading", "How to read the Traffic table\n"),
        ("bullet", "• REQUEST — Modbus RTU request recognized by the parser.\n"),
        ("bullet", "• RESPONSE — recognized Modbus RTU response that is not an EXCEPTION.\n"),
        ("bullet", "• EXCEPTION — Modbus response with an exception Function Code (bit 7 set). Details shows the code and normalized description.\n"),
        ("bullet", "• CRC OK — received CRC matches the calculated CRC.\n"),
        ("bullet", "• CRC ERROR — the structure resembles a supported frame, but the received CRC does not match the calculated CRC.\n"),
        ("bullet", "• RAW/UNSYNC — bytes discarded during resynchronization before a structurally recognized, CRC-valid frame is found later in the same burst.\n"),
        ("bullet", "• RAW/UNPARSED — remaining bytes that could not be interpreted or resynchronized as a valid Modbus frame. This is the state normally shown for a noise block with no later valid frame in the same burst.\n"),
        (None, "RAW/UNSYNC and RAW/UNPARSED are different conditions and both may appear in the Type column. Neither represents a valid Modbus response.\n"),

        ("heading", "Traffic table columns\n"),
        ("bullet", "• Time — timestamp for the start of the processed burst/frame.\n"),
        ("bullet", "• Δt — interval since the previous observed frame.\n"),
        ("bullet", "• Resp. — time between a REQUEST and its matched RESPONSE/EXCEPTION. Blank when no valid pair exists.\n"),
        ("bullet", "• COM — capture channel: BUS in RS485, A→B/B→A in RS232 dual RX and SIM in development mode. It does not necessarily represent the Windows COM number.\n"),
        ("bullet", "• Type — REQUEST, RESPONSE, EXCEPTION or a RAW state.\n"),
        ("bullet", "• Slave — Modbus Unit/Slave ID when identifiable.\n"),
        ("bullet", "• FC — hexadecimal Function Code observed in the frame.\n"),
        ("bullet", "• Details — address, quantity, data or operation description.\n"),
        ("bullet", "• CRC — OK, ERROR or ? when a complete Modbus frame is not available.\n"),

        ("heading", "REQUEST/RESPONSE pairing\n"),
        (None, "Modbus RTU has no Transaction ID. MBSniffer pairs frames by (Slave ID, Function Code) in FIFO order. This is appropriate for normal RTU traffic, but can become ambiguous when requests using the same Slave and FC overlap before their corresponding responses arrive.\n"),
        (None, "An EXCEPTION uses its base Function Code for pairing. For example, response 0x83 is associated with a pending FC03 REQUEST when a compatible request exists.\n"),

        ("heading", "PDU Address, 1-based and Qty\n"),
        (None, "PDU Address is the address encoded in the Modbus request. 1-based is simply PDU Address + 1 and helps compare with manuals that number the first register/coil as 1. Qty is the requested quantity.\n"),
        (None, "These fields belong to the REQUEST. A RESPONSE does not automatically repeat Address or Qty in the protocol, so MBSniffer does not invent those fields on the response row.\n"),

        ("heading", "Modbus exception codes\n"),
        ("bullet", "• 0x01 — Illegal Function: function not supported or not permitted.\n"),
        ("bullet", "• 0x02 — Illegal Data Address: invalid address/address range.\n"),
        ("bullet", "• 0x03 — Illegal Data Value: invalid value, quantity or field.\n"),
        ("bullet", "• 0x04 — Server Device Failure: device-side execution failure.\n"),
        ("bullet", "• 0x05 — Acknowledge.\n"),
        ("bullet", "• 0x06 — Server Device Busy.\n"),
        ("bullet", "• 0x08 — Memory Parity Error.\n"),
        ("bullet", "• 0x0A — Gateway Path Unavailable.\n"),
        ("bullet", "• 0x0B — Gateway Target Device Failed to Respond.\n"),

        ("heading", "Advanced filters\n"),
        (None, "The bar at the top of Traffic can combine several filters without changing the original session data:\n"),
        ("bullet", "• Type — All, Requests, Responses, Exceptions, CRC errors, Timeouts or RAW.\n"),
        ("bullet", "• FC (hex) — Function Code, with or without the 0x prefix.\n"),
        ("bullet", "• Resp. > — only completed responses above the specified time in ms.\n"),
        ("bullet", "• Search — searches Details, Raw Hex, Slave, FC, Type and COM/channel.\n"),
        (None, "The Slave filter remains available in the column header and combines with the advanced filters. “Clear filters” resets all display filters. Filters do not change statistics or the capture log.\n"),

        ("heading", "Highlight results\n"),
        (None, "This option is disabled by default to keep the table neutral. When enabled, results are differentiated by color: a completed normal transaction with a CRC-valid RESPONSE is green; CRC error, timeout, Exception, RAW and slow response retain their respective diagnostic colors.\n"),
        (None, "In a successfully completed normal transaction, both the REQUEST and its RESPONSE are green. A still-pending REQUEST remains neutral. A slow response keeps the slow-response color even if valid so that the timing result is not hidden.\n"),

        ("heading", "Frame Inspector\n"),
        (None, "Select a Traffic row to analyze the frame without manually interpreting every byte. Frame Inspector shows Slave, Type, Function, response time, Result, PDU Address, 1-based address, Qty, ByteCount, CRC, decoded Data and Raw Hex.\n"),
        (None, "The CRC field shows both received and calculated values for a complete frame. Result uses the same diagnostic classification as Traffic, independently of whether Highlight results is enabled.\n"),

        ("heading", "Traffic context menu\n"),
        (None, "Right-click a Traffic row to:\n"),
        ("bullet", "• Copy Raw Hex.\n"),
        ("bullet", "• Copy the decoded frame.\n"),
        ("bullet", "• Filter by that frame's Slave.\n"),
        ("bullet", "• Filter by that frame's Function Code.\n"),
        ("bullet", "• Show only the matching REQUEST/RESPONSE transaction.\n"),
        ("bullet", "• Clear the temporary transaction filter.\n"),

        ("heading", "Bus Health\n"),
        (None, "Bus Health summarizes session quality and performance without replacing the frame table.\n"),
        ("bullet", "• Requests / Responses — session counters.\n"),
        ("bullet", "• Request rate — average number of observed requests per second.\n"),
        ("bullet", "• Active Slaves — valid Modbus IDs observed in the session.\n"),
        ("bullet", "• Observed bytes — sum of bytes delivered to the parser.\n"),
        ("bullet", "• Bus utilization ~ — estimate based on observed bytes, baud rate, data bits, parity and stop bits. It is approximate and depends on the capture point.\n"),
        ("bullet", "• Average / Minimum / Maximum — paired response times.\n"),
        ("bullet", "• P95 — 95% of measured responses were at or below this value.\n"),
        ("bullet", "• Slowest Slave — Slave with the highest average response time among observed samples.\n"),
        ("bullet", "• Unvalidated bytes — percentage of observed bytes belonging to invalid-CRC frames or RAW blocks. By itself this does not prove electrical noise; incorrect serial parameters, incomplete capture or parser-unsupported functions can also produce RAW.\n"),
        ("bullet", "• Timeout rate — percentage of REQUESTs that expired without a matched response.\n"),
        ("bullet", "• Exceptions / Slave — distribution of Exception responses by Slave ID.\n"),

        ("heading", "BUS RX indicator\n"),
        (None, "BUS ● RX pulses briefly when a batch of frames reaches the interface. At rest, BUS ○ is displayed. It is only a visual confirmation of received activity; it does not indicate electrical quality or guarantee that frames are valid.\n"),

        ("heading", "Raw Hex / Log\n"),
        (None, "Shows captured bytes in hexadecimal with context information. Long lines wrap to the available width. The view follows the same display filters used in Traffic; the on-disk TXT file, when present, keeps the complete capture and is not truncated by filters.\n"),

        ("heading", "Export CSV\n"),
        (None, "Export CSV saves the frames currently retained in the UI history using Excel-compatible UTF-8. It includes Time, Δt, Response time, Channel, Type, Slave, FC, Details, CRC, Raw, PDU Address, 1-based, Qty, ByteCount, Timeout and anomaly class.\n"),
        (None, f"The interface retains approximately the latest {max_ui_frames_text} frames. In longer sessions, the CSV therefore represents the history still retained by the GUI, while the TXT file from a real capture remains the complete on-disk record.\n"),

        ("heading", "Capture logs\n"),
        (None, "The TXT log is created only after real traffic arrives. Starting and stopping without receiving frames does not create an empty file.\n"),
        (None, "Logs folder:\n"),
        ("mono", "        <application folder>\\MBSniffer Logs\n"),
        (None, "Filters, sorting, Highlight results and Frame Inspector are display-only features and do not change frames written to the log.\n"),

        ("heading", "Visible history limits\n"),
        (None, f"To keep the application responsive, the interface retains approximately {max_ui_frames_text} frames and {max_raw_lines_text} Raw Hex lines. Pruning is performed in blocks. The capture TXT log, when active, is independent of this limit.\n"),

        ("heading", "COM status and ports\n"),
        (None, "COM status distinguishes a port opened by MBSniffer, a port merely detected by Windows and a port that is no longer detected. Status is refreshed periodically.\n"),
        (None, "Restart COM closes and reopens the port(s) used by Sniffer. This restarts the serial-port handle inside MBSniffer; it does not restart the Windows USB/COM driver.\n"),
        (None, "The ↻ buttons beside the COM selectors refresh the available port enumeration in Sniffer and Bus Slave Finder.\n"),

        ("heading", "Bus Slave Finder — active scan\n"),
        (None, "Bus Slave Finder transmits Modbus RTU requests, so it is not passive. Before starting, confirm that no other master is active on the same bus.\n"),
        (None, "Select COM, baud rates, parities, stop bits and the Slave ID range. Data bits is fixed at 8. The scan tries FC03 Address 0 Qty 1; either a normal response or a CRC-valid Modbus Exception confirms that the Slave exists.\n"),
        (None, "FC04 fallback is optional and increases the maximum number of attempts. The minimum timeout is adapted to baud rate. A write timeout means transmission through the port/driver failed and must not be interpreted simply as “slave did not respond”.\n"),
        (None, "Device Identification (FC43/14) is optional. When enabled, it is sent only after a Slave has been found and attempts to read Basic Device Identification: VendorName, ProductCode and MajorMinorRevision. An Exception or no response to FC43/14 does not invalidate Slave discovery.\n"),
        (None, "Finder and Sniffer share the global activity lock so the same application cannot actively scan and capture at the same time.\n"),

        ("heading", "Saved preferences\n"),
        (None, "User preferences are stored in %APPDATA%\\MBSniffer\\settings.json. They include Light/Dark, Language, last tab, serial parameters, Frame gap, Pending timeout, Auto-scroll, Separate transactions, Highlight results and Bus Slave Finder options.\n"),
        (None, "COM ports are not saved because they are specific to each computer. The Bus Slave Finder safety confirmation is not saved either.\n"),

        ("heading", "Diagnostic best practices\n"),
        ("bullet", "• Confirm wiring, polarity and serial parameters first.\n"),
        ("bullet", "• On RS485, keep the sniffer stub short and avoid changing the existing termination.\n"),
        ("bullet", "• Make sure no other program has the same COM port open.\n"),
        ("bullet", "• Treat CRC ERROR and RAW as indicators of framing, noise, incorrect parameters or incomplete capture.\n"),
        ("bullet", "• Treat Exceptions as valid protocol responses: they are not equivalent to CRC errors.\n"),
        ("bullet", "• Compare response times with normal equipment behavior, not only with a generic threshold.\n"),
        ("bullet", "• Keep the TXT log when you need later analysis of the complete capture.\n"),
    ]
    if debug_sim:
        blocks.extend([
            ("heading", "Simulation mode\n"),
            (None, "This development mode appears only when debug_sim = 1 in MBSniffer.py. It does not open serial ports and never creates TXT logs.\n"),
            (None, "Each run uses the same diagnostic scenario types: one normal response, one slow response, one Modbus Exception, one CRC error, one timeout and one RAW/UNPARSED block. This makes it possible to compare the same information directly with and without visual highlighting.\n"),
            (None, "Highlight results does not change Simulation data. When disabled, all rows use normal table colors; when enabled, the completed normal transaction is green and Exception, CRC error, timeout, slow response and RAW rows use their respective diagnostic colors.\n"),
            (None, "Frames in this scenario use the SIM channel so they are not confused with real physical capture.\n"),
        ])
    blocks.extend([
        ("heading", "Important limitation\n"),
        (None, "MBSniffer interprets bytes, CRC, Function Code, addresses, quantities, pairing and timing observed by the operating system. It does not directly measure electrical levels, ringing, reflections, bias, common-mode, rise/fall times or analog signal integrity. Those problems still require an oscilloscope or an analyzer suitable for the physical interface.\n"),
    ])
    return blocks


def translate_runtime_text(text, language):
    """Translate status strings that contain live values."""
    import re

    value = str(text or "")
    target_en = normalize_language(language) == LANGUAGE_ENGLISH

    # Normalize either language to canonical PT where practical, then render.
    patterns = [
        (r"^Encontrados: (\d+)$", r"Found: \1", target_en),
        (r"^Found: (\d+)$", r"Encontrados: \1", not target_en),
        (r"^Decorrido (.+) — restante ~(.+)$", r"Elapsed \1 — remaining ~\2", target_en),
        (r"^Elapsed (.+) — remaining ~(.+)$", r"Decorrido \1 — restante ~\2", not target_en),
        (r"^A configurar (.+)…$", r"Configuring \1…", target_en),
        (r"^Configuring (.+)…$", r"A configurar \1…", not target_en),
        (r"^Pesquisa parada — (\d+) encontrados — (.+)$", r"Scan stopped — \1 found — \2", target_en),
        (r"^Scan stopped — (\d+) found — (.+)$", r"Pesquisa parada — \1 encontrados — \2", not target_en),
        (r"^Pesquisa concluída — (\d+) encontrados — (.+)$", r"Scan complete — \1 found — \2", target_en),
        (r"^Scan complete — (\d+) found — (.+)$", r"Pesquisa concluída — \1 encontrados — \2", not target_en),
        (r"^(\d+) config\. × (\d+) slaves — máx\. estimado: (.+)$", r"\1 config. × \2 slaves — estimated max.: \3", target_en),
        (r"^(\d+) config\. × (\d+) slaves — estimated max\.: (.+)$", r"\1 config. × \2 slaves — máx. estimado: \3", not target_en),
    ]
    for pattern, replacement, enabled in patterns:
        if enabled and re.match(pattern, value):
            return re.sub(pattern, replacement, value)

    return translate_text(value, language)
