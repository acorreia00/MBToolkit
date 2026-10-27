# MBSniffer — Histórico de desenvolvimento (CHANGELOG)

Registo cronológico de todas as decisões e alterações, versão a versão.
As regras **em vigor** estão resumidas em `DEVELOPMENT_NOTES.md`; este ficheiro
guarda o detalhe e o porquê de cada decisão. Acrescentar sempre no fim; nunca
reescrever entradas antigas.

> Até à v3.0 este conteúdo era o próprio `DEVELOPMENT_NOTES.md`. Foi copiado
> sem alterações na v3.1, quando as notas foram divididas em regras em vigor
> (`DEVELOPMENT_NOTES.md`) e histórico (este ficheiro). Algumas regras antigas
> abaixo foram substituídas por decisões posteriores; em caso de conflito vale
> a entrada mais recente e o `DEVELOPMENT_NOTES.md`.

---

# (Histórico) MBSniffer — Development Notes até à v3.0

## Current version

**3.0**

This file is the development/architecture handoff. `README.txt` is intentionally
user-facing and must remain concise. Internal history and decisions belong here.

## Product intent

Windows GUI for Modbus RTU diagnostics. The Sniffer path is passive and must
remain read-only; Bus Slave Finder is the deliberately separate active path.

## Supported physical modes

- RS485 2-wire: one COM, both directions on the same bus.
- RS232 single RX: one COM, one observed direction.
- RS232 dual RX: two COM ports, one RX channel per direction.

For RS232 sniffing, sniffer TX lines must remain disconnected. RS232 and TTL/UART
must not be conflated in user guidance.

## Core Modbus behavior

- CRC16 Modbus validation.
- Parser recognizes common Modbus RTU read/write functions and exception frames.
- Request/response pairing is FIFO by `(Slave ID, Function Code)` because Modbus
  RTU has no transaction ID.
- Pending requests expire after a configurable timeout.
- Pending timeout UI range: 1–300 s, default 10 s.
- Exception display must remain short:
  `Exception 0x02 — Illegal Data Address`
  i.e. label + hexadecimal exception code + official exception name only.
- Simulation is GUI-only and must never create/write `.txt` logs.

## UI / performance decisions

- `self.busy` prevents capture/simulation re-entry.
- GUI queue processes at most 200 events per cycle.
- Busy queue interval 10 ms; idle interval 50 ms.
- Treeview keeps individual rows selectable.
- Visible GUI history is bounded:
  - MAX_UI_FRAMES = 20000
  - UI_PRUNE_CHUNK_FRAMES = 2000
  - MAX_RAW_TEXT_LINES = 20000
  - RAW_TEXT_PRUNE_CHUNK_LINES = 2000
- Treeview pruning uses a deque; do not revert to traversing the complete
  Treeview on every prune.
- Visual transaction separators are inserted only after a matched response or
  exception. They are GUI-only and are not written as artificial separator rows
  to disk logs.
- Reader threads are joined with a finite timeout during shutdown; never add an
  unbounded GUI-thread join.

## Logs

### v2.6 decision

Logs are no longer stored in Windows Documents.

They must always be placed in:

`<application directory>/MBSniffer Logs`

Application directory means:

- BAT/Python mode: directory containing `MBSniffer.py` (normally also
  `MBSniffer.bat`).
- PyInstaller mode: directory containing `MBSniffer.exe`.

Only real captures that actually receive traffic create logs. Simulation never creates a log.

Real log name:

`MBSniffer_YYYYMMDD_HHMMSS.txt`

The full disk log remains complete even when old GUI rows are pruned.

## COM port status — added in v2.6

The GUI has explicit COM status for A/B:

- `Aberta`: the selected port is currently open by MBSniffer.
- `Detetada`: Windows/pyserial reports the selected port, but MBSniffer does not
  currently own an open handle to it.
- `Não detetada`: the selected port is no longer reported by the OS.
- `Não selecionada`: no A port selected.
- COM B displays `—` outside RS232 dual-RX mode.

Status polling must not probe a port by opening it. It uses `list_ports.comports()`
and current MBSniffer serial handles, so status checking remains non-invasive.
The UI refreshes status approximately once per second.

Important: `Detetada` does **not** mean the COM is free. Another process may own it.
The authoritative availability check occurs when MBSniffer tries to open it.

## COM restart — added in v2.6

`Reiniciar COM` means close/reopen the MBSniffer serial handle(s). It does **not**
restart/reset the Windows USB serial driver or physically power-cycle the adapter.

Behavior:

- During a real capture: stop old reader generation, close COM handle(s), reopen
  with current serial settings, start new reader threads, and continue the same
  capture session. A `# COM restart:` comment is written to the real log if/when
  that capture receives traffic. Restarting COM alone must not create a log file.
- When not capturing: selected COM handle(s) are opened and closed once as a
  restart/open test, without creating a capture log.
- During Simulation the restart button is disabled.
- Reader control events carry a generation number. Events from a previous reader
  generation are ignored after a restart, preventing stale `reader_stopped` events
  from terminating the newly restarted capture.

## COM enumeration

Dropdown values come from `serial.tools.list_ports.comports()`. The application
shows ports reported by Windows; it does not guarantee that a listed port is free.

## BAT distribution

`MBSniffer.bat` is the normal no-build launcher.

It:

1. Finds Python 3.
2. If Python is absent, attempts Python 3.13 installation via WinGet.
3. Checks tkinter.
4. Installs pyserial with pip if missing.
5. Runs `MBSniffer.py`, preferring `pythonw.exe` where possible.

The user requested one normal BAT, not a separate setup BAT.

## EXE build

`build_exe.bat` is optional and creates a PyInstaller one-file/windowed EXE.
It includes `MBSniffer.ico` using both `--icon` and `--add-data`, allowing the icon
to be used by the executable and the Tk window.

The Python code also sets a Windows AppUserModelID and explicitly loads the icon
for the Tk window. Preserve both behaviors.

## Files expected in release ZIP

The project is modular from v2.6 onward. Keep these files together:

- `MBSniffer.py`
- `mb_config.py`
- `mb_protocol.py`
- `mb_slave_finder.py`
- `mb_capture.py`
- `mb_view.py`
- `mb_gui.py`
- `mb_widgets.py`
- `mb_theme.py`
- `MBSniffer.bat`
- `build_exe.bat`
- `MBSniffer.ico`
- `README.txt`
- `DEVELOPMENT_NOTES.md`

PyInstaller still produces a single `MBSniffer.exe`; local Python modules are
followed automatically from the imports.

## Version history / decisions retained from 2.4

- App renamed to MBSniffer.
- Three physical capture modes implemented.
- Help tab with wiring/diagnostic guidance.
- Delta-t and approximate response-time columns.
- Session statistics: Requests, Responses, Pending, Timeouts, CRC errors,
  Exceptions, RAW.
- Request detail includes PDU address, 1-based address and quantity where applicable.
- Response detail carries matched request context.
- Pending request expiry prevents stale pairing in long captures.
- Known Modbus exception codes are recognized.
- Exception UI text deliberately uses only code + official short name.
- Simulation does not write logs.
- UI history cap and chunked pruning implemented.
- Graceful finite-time reader-thread shutdown.
- Custom icon support for BAT/Python window and PyInstaller EXE.

## README policy

On every future release, generate a fresh concise `README.txt` containing only
information required by the end user. Do not append internal implementation
history to README. Update this `DEVELOPMENT_NOTES.md` cumulatively instead.

## Release discipline

- Use the latest release ZIP/source as source of truth.
- Do not silently remove existing features while implementing a new request.
- Keep version unchanged unless the user explicitly requests a version change.
- User explicitly requested version 2.6 for the changes documented above.
- Validate the exact saved Python modules and the contents of the final ZIP, not
  only in-memory edited source strings.


## Traffic-gated log creation — v2.6

User decision: a real capture with zero received traffic must not leave an empty
`.txt` file.

Implementation rules:

- `start_capture()` prepares the log filename/header only in memory.
- Do **not** open/create the real log at capture start.
- The first actual captured frame or RAW block triggers log creation.
- The log filename timestamp remains based on capture start time, not on the time
  of the first frame.
- If capture stops before any traffic is received, no `.txt` file is created.
- Simulation remains GUI-only and never creates a log.
- COM restart must not create a log by itself.
- If COM is restarted before the first frame, the restart note is queued in memory
  and written only if traffic later causes the log to be created.
- Once created, the real log remains complete for the rest of the capture session.
- A log creation error is reported only once per capture session to avoid repeated
  dialogs on a busy bus.

This behavior must be preserved in both BAT/Python and PyInstaller EXE modes.


## Slave filtering + time sorting — v2.6

User decision: keep version 2.6 and add a hybrid GUI view model:

- Slave selection is a **filter**, not a slave sort.
- Date/time is the **sort** dimension.
- Provide explicit `Todos` and `Nenhum` actions.
- Individual discovered slaves are selectable with checkboxes.
- Default state is `Todos`.
- If all currently known slaves are checked, the application stays in "All mode"
  and future newly discovered slaves are automatically selected.
- If the user selects a subset, future newly discovered slaves start unchecked.
- `Nenhum` hides all GUI traffic, including RAW/unparsed traffic without a usable
  slave ID.
- `Todos` shows every captured GUI record, including RAW/unparsed records.

Time ordering:

- Default: ascending, oldest → newest.
- Alternative: descending, newest → oldest.
- Clicking the `Hora` Treeview heading toggles the same setting.
- Both `Tráfego` and `Raw Hex / Log` follow the selected order.
- In descending view, visual transaction separator rows are intentionally omitted.
  Otherwise a separator after a RESPONSE would sit between that RESPONSE and the
  earlier REQUEST when frame order is reversed.

Architecture / invariants:

- Filtering and sorting are **display-only**.
- SessionMetrics always processes every captured frame.
- Real `.txt` logs always receive every real captured frame, regardless of the
  active slave filter or time order.
- Simulation remains no-log.
- `_frame_history` is the bounded source-of-truth for re-rendering the GUI.
- `_frame_history` uses a deque and is pruned by the existing hysteresis values:
  `MAX_UI_FRAMES` / `UI_PRUNE_CHUNK_FRAMES`.
- Filter/sort changes rebuild the GUI from `_frame_history`; live traffic is still
  inserted incrementally to avoid rebuilding 20k rows per frame.
- Raw Hex is rebuilt when its line-cap hysteresis is exceeded so the correct edge
  is retained for both ascending and descending order.
- `Limpar` clears GUI history, detected slave filters, and resets time order to
  ascending.
- Do not allow GUI filtering to alter pairing, statistics, timeout handling, disk
  logging, COM state/restart behavior, or passive/read-only capture semantics.


## Header-integrated filtering/sorting — v2.6

UI decision replacing the temporary separate `Visualização` section:

- Do not use a separate filter/sort toolbar.
- Time sorting is controlled only from the `Hora` Treeview header.
- `Hora ↑` means oldest → newest.
- `Hora ↓` means newest → oldest.
- Slave filtering is controlled only from the `Slave` Treeview header.
- Clicking the Slave header opens a popup menu at the pointer position.
- Popup contents:
  - `Todos`
  - `Nenhum`
  - one checkbutton per discovered Slave ID.
- Slave heading state:
  - `Slave ▾` = all
  - `Slave (Filtro) ▾` = subset
  - `Slave (Nenhum) ▾` = none
- The previous visible Menubutton, Todos/Nenhum toolbar buttons and Data/Hora
  combobox were intentionally removed.
- Filtering and sorting remain display-only; logs, statistics and pairing remain
  complete and unaffected.
- Both Treeview and Raw Hex follow the selected filter/order.


## Auto-fit centered Traffic columns — v2.6

User decision:

- Keep version 2.6.
- Every `Tráfego` Treeview column must be as compact as practical.
- Width is determined by the longest **currently visible** cell in that column
  OR the current heading text, whichever is wider.
- Add `tree_column_padding_px = 28` total horizontal padding so the longest text
  is not visually pressed against the column border.
- Both heading text and cell values are center-aligned.
- Columns use `stretch=False`; horizontal scrolling remains available when the
  total natural width exceeds the window.

Performance/behavior:

- Exact widths are measured in pixels with `tkinter.font.Font.measure`.
- Heading font and normal Treeview cell font are measured separately.
- New live visible records only **expand** a column incrementally when required;
  the entire history is not rescanned on every frame.
- User-driven filter/sort rebuilds and history-prune rebuilds perform a full
  auto-fit, allowing columns to shrink again when the longest visible value is
  no longer present.
- `Limpar` resets every column to the compact width required by its heading.
- Dynamic heading states (`Hora ↑/↓`, `Slave ▾`, `Slave (Filtro) ▾`,
  `Slave (Nenhum) ▾`) participate in width calculation.
- Decorative transaction separator rows are not used when calculating widths.
- Filtering, logging, pairing, statistics, lazy log creation, COM restart and
  passive capture semantics are unchanged.


## Wrapped left-aligned Details + request-only address context — v2.6

UI decision:

- Keep version 2.6.
- All Traffic headings/cells remain centered **except `Detalhes`**.
- `Detalhes` heading and cell content are left-aligned.
- Non-Details columns remain compact auto-fit columns.
- `Detalhes` consumes the remaining Treeview viewport width instead of expanding
  to the natural width of long messages.
- Details text is pixel-aware word-wrapped using the current Tk default font.
- Long individual tokens fall back to character-level wrapping.
- Treeview does not support per-row heights, so the dedicated
  `MBSniffer.Treeview` style uses one global row height calculated from the
  largest wrapped Details cell currently visible.
- Window/Treeview resize is debounced (120 ms) and triggers a reflow so Details
  wrap follows the new available width.
- If a compact non-Details column grows during live traffic, the visible table
  is rebuilt once for that batch so Details can be rewrapped to the reduced
  remaining width.
- Raw `.txt` log details remain unwrapped; wrapping is display-only.
- Raw Hex text behavior is unchanged.

Request/response context decision:

- Keep request pairing internally for response-time/statistics.
- Do not append `Req PDU`, `1-based`, or `Qty` to matched RESPONSE/EXCEPTION
  detail text.
- Address/PDU Address, 1-based and Qty remain shown on the REQUEST where they
  originate.
- FC03/FC04 RESPONSE details continue to show response-native information such as
  ByteCount and decoded Registers.
- This reduces duplicated information and especially reduces long RESPONSE rows.

Terminology:

- Modbus PDU = Protocol Data Unit: Function Code + function-specific data.
- In an RTU request, the address field displayed as `PDU Address` is the raw
  zero-based address value carried in the Modbus request data.
- `1-based` is a convenience display (`PDU Address + 1`) for manuals/tables that
  number entries from 1.
- `Qty` is the requested quantity.


## Random multi-slave simulation — v2.6

User decision: keep version 2.6 and make Simulation substantially richer.

Simulation generation:

- Every press of `Simulação` creates a fresh random plan.
- 4..7 unique Slave IDs are selected randomly from valid Modbus addresses 1..247.
- Default plan size: 30 transactions.
- Simulated Function Codes:
  - FC01 Read Coils
  - FC02 Read Discrete Inputs
  - FC03 Read Holding Registers
  - FC04 Read Input Registers
  - FC15 Write Multiple Coils
  - FC16 Write Multiple Registers
- Every selected slave appears at least once per simulation.
- Every supported simulated FC appears at least once per simulation.
- Remaining slave/FC choices are random.
- Start addresses are random.
- Quantities are random within small protocol-valid ranges:
  - FC01/02: 1..40 bits
  - FC03/04: 1..16 registers
  - FC15: 1..32 coils
  - FC16: 1..12 registers
- Payload values/data are random.
- Slave outcome distribution per transaction:
  - ~84% normal response
  - ~10% Modbus exception
  - ~6% CRC-corrupted response
- Requests themselves remain valid so pairing/stats can be exercised sensibly.

Physical-mode simulation semantics:

- RS485 2-wire: request and reply both shown on `BUS`.
- RS232 dual RX: request `A→B`, reply `B→A`.
- RS232 single RX: only request direction `A→B` is shown; replies are intentionally
  absent because one physical RX cannot observe the opposite TX direction.
- Random inter-request and request-to-response delays are used so Δt/Resp. timing
  fields vary realistically.
- Status line temporarily shows the randomly selected Slave IDs.
- Simulation remains GUI-only and never creates `.txt` logs.

Implementation:

- `build_simulation_transaction(slave, fc, rng)` constructs valid request/response
  pairs.
- `build_random_simulation_plan(...)` constructs the complete multi-slave plan.
- RNG can be injected for deterministic tests.
- `corrupt_crc()` is used only on simulated slave responses.
- Existing real-capture parser, filtering, sorting, wrapping, pairing and logging
  code paths are reused; Simulation does not use a separate display parser.


## Simplified 5-transaction simulation — v2.6

User decision:

- Keep version 2.6.
- Simulation generates exactly 5 transactions.
- One transaction for each FC:
  - FC01
  - FC02
  - FC03
  - FC04
  - FC07
- Use 5 unique random Slave IDs, one per transaction.
- FC01..04:
  - Address random 1..32
  - Qty random 1..32
- FC07 must remain protocol-valid:
  - request length = 4 RTU bytes: Slave + FC + CRC
  - no Address field
  - no Qty field
  - response = Slave + FC + one Exception Status byte + CRC
- All 5 simulated outcomes are normal responses.
- Remove random simulated Modbus exceptions and bad-CRC outcomes from the
  simplified simulation.
- Simulation remains GUI-only and creates no `.txt` log.

Parser extension:

- FC07 is now explicitly recognized by the real parser as well as Simulation.
- Candidate frame lengths:
  - REQUEST = 4 bytes
  - RESPONSE = 5 bytes
- FC07 REQUEST details: `Read Exception Status`
- FC07 RESPONSE details: `Status=0xXX`

Do not invent Address/Qty bytes for FC07 just to make its display match FC01..04.


## Simulation limited to FC01..FC04 — v2.6

User decision:

- Keep version 2.6.
- Remove FC07 from Simulation.
- Simulation now generates exactly 4 transactions:
  - FC01
  - FC02
  - FC03
  - FC04
- Use 4 unique random Slave IDs, one per transaction.
- Every transaction uses:
  - Address random 1..32
  - Qty random 1..32
- All simulated outcomes are normal responses.
- Simulation remains GUI-only and creates no `.txt` log.
- Existing real-parser FC07 support is intentionally left intact because it is
  useful for real captures; only Simulation was restricted.


## Source-level Simulation visibility switch — v2.6

User decision:

- Keep version 2.6.
- Add near the beginning of `MBSniffer.py`:

      debug_sim = 0

- Source comment documents:
  - `0 = simulação inativa`
  - `1 = simulação ativa`

Behavior:

- Default is `debug_sim = 0`.
- With `debug_sim == 0`:
  - the Simulation button is not instantiated;
  - it is not packed;
  - no GUI space is reserved for it;
  - Simulation-specific Help content is omitted;
  - `run_simulation()` returns immediately if called directly.
- With `debug_sim == 1`:
  - the Simulation button is created and packed normally;
  - Simulation Help is shown;
  - the current FC01..FC04 four-transaction simulation is available.
- `self.sim_btn` is always defined and is `None` when disabled.
- Button-state changes go through `set_simulation_button_state(state)`, which
  safely does nothing when Simulation is disabled.

Build behavior:

- BAT/Python mode uses the current value in `MBSniffer.py` on the next launch.
- PyInstaller EXE uses the value present at build time; change `debug_sim` and
  rebuild the EXE for the new setting.


## Compact separators preserved in both time orders — v2.6

User decision:

- Keep version 2.6.
- `Separar transações` must stay visible in both Hora ascending and descending.
- Reduce the large vertical gap produced by standalone separator rows after
  wrapped Details introduced a global multi-line Treeview row height.

Implementation:

- Remove standalone separator Treeview items.
- Draw the transaction rule inside the matched RESPONSE Details cell:
  - Hora ↑: rule below RESPONSE.
  - Hora ↓: rule above RESPONSE.
- This preserves REQUEST/RESPONSE grouping in both orders.
- Rule width follows the current Details column.
- Wrapped row vertical padding reduced from +8 px to +6 px.
- Raw Hex keeps separators in both orders using `RAW_TRANSACTION_SEPARATOR`:
  - Hora ↑: after matched RESPONSE.
  - Hora ↓: before matched RESPONSE.
- Raw Hex uses a visible compact rule instead of a blank separator line.
- `.txt` disk logs are unchanged; separators remain GUI-only.

Timing definitions:

- `Δt`: elapsed milliseconds between the current captured frame and the previous
  captured frame in the complete acquisition stream.
- `Resp.`: elapsed milliseconds from a pending REQUEST to its matched
  RESPONSE/EXCEPTION, using the existing `(Slave ID, Function Code)` FIFO
  pairing.
- Filtering/sorting does not recalculate these values.
- Timing is approximate because timestamps are generated through Windows/USB,
  not hardware timestamping.


## Compact per-line wrapping without global row expansion — v2.6

Correction after field/UI review:

The previous wrapped Details implementation placed newline text inside a single
ttk.Treeview item and increased the Treeview style rowheight to the largest
wrapped Details cell. ttk.Treeview has only one rowheight for the entire widget,
so one two-line/three-line RESPONSE made every REQUEST and RESPONSE equally tall.
This created excessive empty space between REQUEST and RESPONSE.

New implementation:

- Keep Treeview rowheight fixed and compact:
  - `max(20, font linespace + 5)`.
- A logical Modbus frame still has one main Treeview row.
- If Details wraps onto additional lines, create compact continuation Treeview
  rows directly below the main row.
- Continuation rows:
  - show only the Details continuation text;
  - retain the same Raw Hex mapping as the logical frame;
  - do not duplicate Hora/Δt/Resp./Canal/Tipo/Slave/FC/CRC.
- This provides full wrap without forcing all rows to the maximum wrapped height.

Transaction separators:

- Restore a standalone separator Treeview row at the transaction boundary.
- Hora ↑:
  - REQUEST
  - RESPONSE (+ continuation rows if needed)
  - separator
- Hora ↓:
  - separator
  - RESPONSE (+ continuation rows if needed)
  - REQUEST
- Because the global rowheight is now compact, the separator row no longer
  creates the large gap seen with the previous implementation.
- Raw Hex compact separator behavior from the previous change is preserved.

Important invariant:

- Continuation rows are display-only. They do not create extra Modbus frames,
  do not affect SessionMetrics, pairing, statistics, filtering source data, or
  `.txt` logging.


## Portuguese language review of Help / Ligações — v2.6

User decision:

- Keep version 2.6.
- Review the complete user-visible text in the `Ajuda / Ligações` tab.
- Correct European Portuguese spelling, accents, punctuation, agreement and
  awkward phrasing without changing the intended technical behavior.

Corrections include, among others:

- `não assumes` → `não assumas`;
- improved comma placement and sentence punctuation;
- `buses` → `barramentos`;
- `interface físico` → `interface física`;
- `checkbox` → `caixa de seleção`;
- `pairing` → `emparelhamento` in explanatory Portuguese text;
- clearer Portuguese around COM status, pending requests, log creation and
  RS232/RS485 wiring;
- consistent use of `Function Code`, `Slave ID`, `REQUEST`, `RESPONSE`,
  `EXCEPTION`, `PDU Address`, `Qty` and other UI/protocol terms where preserving
  the displayed terminology is useful.

The Help text was also reconciled with current v2.6 behavior where older wording
had become stale:

- transaction separators remain visible in both Hora ↑ and Hora ↓;
- Raw Hex uses a compact separator rather than a blank line;
- Details wraps through compact continuation rows rather than increasing every
  Treeview row to the largest wrapped height;
- response rows do not repeat PDU Address / 1-based / Qty;
- visible-history wording now uses Portuguese thousands formatting and
  `barramentos` instead of `buses`.

README remains user-facing only and was regenerated with reviewed Portuguese.


## Pair-boundary separators + Raw Hex alignment — v2.6

User decision:

- Keep version 2.6.
- A transaction separator must exist only BETWEEN complete visible
  REQUEST/RESPONSE pairs.
- Never leave a trailing separator after the final visible complete pair.
- In Traffic, the separator should span the full Details column.
- In Raw Hex / Log, the separator should span the full displayed/content line.
- Raw Hex timing fields with no value must show absolutely no timing text while
  preserving the same fixed horizontal width so all later fields stay aligned.

Pair identity / separator algorithm:

- `SessionMetrics` now stores the request `_view_seq` in each pending request.
- A matched RESPONSE/EXCEPTION record stores `request_seq`.
- `completed_pairs_for_records(records)` reconstructs exact visible pairs in the
  current Hora order.
- `separator_after_sequences(records)` returns the visually last record of every
  complete pair except the final complete pair.
- Therefore the separator is always *below the complete pair in the current
  display order*:
  - Hora ↑: normally after RESPONSE.
  - Hora ↓: normally after REQUEST.
- Filtering/sorting rebuilds these boundaries from the bounded source history.
- During live capture, Treeview boundaries are synchronized after a newly matched
  response without rebuilding normal traffic rows.

Treeview separator:

- Standalone separator rows are retained because rowheight is now compact.
- The line is deliberately slightly wider than Details and relies on Treeview
  clipping so it reaches the usable column boundary.
- Separator rows are tracked separately from logical frame rows.

Raw Hex separator:

- Separator width is recalculated as the maximum of:
  - the longest currently displayed Raw Hex line;
  - the current visible Raw Text widget width in Consolas character cells.
- Raw Text resize is debounced and re-renders separators when needed.
- No trailing Raw Hex separator is emitted after the final complete pair.

Raw Hex timing alignment:

- Existing timing field widths are preserved:
  - Δt field width: 13 characters.
  - Resp. field width: 15 characters.
- When a value exists, render the normal `dt=...ms` / `resp=...ms` field.
- When a value does not exist, render only spaces of the same width.
- Do not display `-`, `dt=`, `resp=` or `ms` for missing timing values.
- This keeps Canal, Tipo, Slave, FC, CRC, raw bytes and Details aligned.

Disk log:

- `raw_line_for_record()` is shared by Raw Hex and the text log, so the same
  blank-but-fixed-width timing presentation is preserved in saved logs.


## Simulation freeze after second transaction — bug fix — v2.6

Observed symptom:

- With Simulation enabled, only the first 2 of the 4 simulated transactions
  were displayed.
- The GUI then appeared to freeze and Simulation never reached the completed
  state.

Root cause:

- `details_horizontal_rule()` uses `math.ceil()` to size the Traffic separator
  across the Details column.
- The previous separator-boundary change introduced that call but did not add
  `import math`.
- The first separator is intentionally created only after a second complete
  REQUEST/RESPONSE pair exists.
- Therefore the missing import was not triggered during the first pair; it
  failed exactly when the second pair completed.
- Tk raised `NameError: name 'math' is not defined` inside `process_queue()`.
  Because the periodic queue callback terminated on that exception, the
  remaining simulated frames stayed queued and the GUI appeared blocked.

Fix:

- Add `import math` to the standard-library imports near the beginning of
  `MBSniffer.py`.
- No simulation, separator, filtering, pairing or logging behavior was otherwise
  changed.

Regression requirement:

- When `debug_sim = 1`, a complete RS485 simulation must reach:
  - Requests = 4
  - Responses = 4
  - Pending = 0
  - status = `Simulação concluída`
- The first transaction must not require a separator.
- The first separator appears only when a second complete pair exists.


## Wrapped Raw Hex / Log view — v2.6

User decision:

- Keep version 2.6.
- Raw Hex / Log must wrap long lines so the user does not need horizontal
  scrolling.

Implementation:

- Change the Raw Text widget from `wrap="none"` to `wrap="word"`.
- Remove the horizontal ttk.Scrollbar completely.
- Remove `xscrollcommand`; only the vertical scrollbar remains.
- This change is GUI-only. `raw_line_for_record()` and saved `.txt` log lines
  remain logically one line per captured frame.
- Existing fixed-width blank Δt/Resp. fields are preserved, so fields following
  them remain aligned at the start of each logical line.

Raw separator behavior with wrapping:

- A separator now spans the current visible Raw Text viewport width only.
- Do not size the separator to the longest unwrapped content line; doing that
  would make the separator itself wrap onto multiple visual lines.
- `raw_separator_width_chars()` uses the current Raw Text pixel width divided by
  the monospace separator-glyph width, with a small border reserve.
- Resizing the Raw Text widget continues to trigger a debounced separator reflow.
- The previous `raw_separator_width_grew` optimization was removed because raw
  content length no longer determines separator width.

Existing invariants preserved:

- No trailing separator after the final complete visible pair.
- Slave filtering and Hora sorting still affect Raw Hex / Log.
- Simulation behavior is unchanged and remains gated by `debug_sim`.
- Real `.txt` logging, pairing, statistics and lazy log creation are unchanged.


## Simulation Qty range reduced to 1..8 — v2.6

User decision:

- Keep version 2.6.
- Simulation remains exactly 4 transactions:
  - FC01
  - FC02
  - FC03
  - FC04
- Random Address range remains 1..32.
- Random Qty range changes from 1..32 to 1..8 for all four simulated
  transactions.
- Slave IDs remain random and unique.
- All other simulation, parser, GUI, filtering, sorting, separator, Raw Hex,
  logging and `debug_sim` behavior remains unchanged.


## Active Modbus RTU Slave Discovery — v2.6

User decision:

- Keep version 2.6.
- Add a completely separate top-level tab named `Bus Slave Finder`.
- The discovery workspace must occupy the full application page so it cannot be
  confused with passive sniffing.
- Implement active discovery only; no passive discovery mode.
- The scanner must remain practical when many serial combinations are selected.

Top-level UI architecture:

- The application now has a top-level ttk.Notebook with:
  - `Sniffer`
  - `Bus Slave Finder`
- The existing Sniffer controls, statistics and inner tabs remain under the
  `Sniffer` page.
- The discovery page is independent and fills the window.

Safety model:

- Passive capture remains read-only and does not call `Serial.write()`.
- Active discovery intentionally acts as a temporary Modbus RTU master.
- Discovery transmits read-only FC03/FC04 probes.
- The UI requires the user to check:
  `Confirmo que não existe outro master ativo no barramento.`
  before the Start button can be enabled.
- Capture/simulation controls are disabled while discovery is running.
- The shared `busy` lock prevents simultaneous passive capture/simulation and
  active discovery.

Discovery serial combinations:

- Data bits are fixed at 8.
- Selectable baud rates:
  - 1200
  - 2400
  - 4800
  - 9600
  - 19200
  - 38400
  - 57600
  - 115200
- Selectable parity:
  - None
  - Even
  - Odd
- Selectable stop bits:
  - 1
  - 2
- Slave range is configurable from 1 to 247.
- Defaults are intentionally conservative/fast:
  - baud 9600 + 19200
  - parity None + Even
  - stop bit 1
  - slaves 1..247

Probe design:

- Primary probe is always:
  - FC03 Read Holding Registers
  - PDU Address 0
  - Qty 1
- Any CRC-valid normal response counts as a discovered slave.
- Any CRC-valid Modbus Exception from the requested Slave ID and FC also counts
  as a discovered slave.
- Optional `FC04 fallback` can be enabled. It is OFF by default because scanning
  a second function for every silent address can approximately double worst-case
  duration.
- FC04 fallback uses the same Address 0 / Qty 1 probe.
- No write functions are used by discovery.

Response recognition:

- `find_discovery_response()` scans received bytes for the requested Slave ID.
- It accepts:
  - normal FC03/FC04 register responses with positive even ByteCount and valid CRC;
  - exception FC (`requested FC | 0x80`) with valid CRC.
- Request echoes and unrelated traffic are ignored by the response matcher.

Adaptive timeout / speed:

- Timeout after request transmission is calculated from:
  - selected baud/parity/stop bits;
  - estimated 7-byte normal response transmission time;
  - Modbus serial/inter-frame margin;
  - user-selected minimum timeout.
- Default minimum timeout: 40 ms.
- Allowed minimum-timeout range: 10..2000 ms.
- This preserves a short timeout at fast baud rates while automatically allowing
  more time for low baud rates.
- The tab calculates a worst-case estimate before scanning.
- With all 48 serial configurations, Slave IDs 1..247, FC03 only and the default
  40 ms minimum, the current estimator is roughly 13 minutes rather than hours.
- Normal/default selections are much faster (roughly under a minute by the same
  worst-case estimator).
- A response advances immediately; the scanner never waits the full timeout after
  a valid frame has already arrived.

Worker/thread architecture:

- Active scanning runs in a daemon worker thread.
- Tk widgets are never mutated directly from the worker.
- Worker events are sent through the existing application `event_queue`:
  - `discovery_status`
  - `discovery_progress`
  - `discovery_found`
  - `discovery_done`
- The existing bounded `process_queue()` handles these events in the Tk thread.
- `Parar` sets a dedicated `discovery_stop_event`; response waits check it at
  millisecond-scale intervals so cancellation remains responsive.
- `on_close()` also stops discovery, closes the active discovery serial handle
  and gives the discovery thread a short opportunity to exit.

Results UI:

- Progress bar is based on serial-configuration × Slave-ID units.
- Status shows:
  - current baud/config/slave;
  - elapsed time;
  - estimated remaining time;
  - found count.
- Results show only discovered slaves with columns:
  - Slave
  - Baud
  - Config. (e.g. 8N1 / 8E1)
  - FC
  - Resultado
  - Resp. (ms)
  - Raw Hex
- Exception results use the standard existing exception-name mapping, e.g.
  `Exception 0x02 — Illegal Data Address`.
- Discovery does not create capture logs.

Port handling:

- `refresh_ports()` also populates the Discovery COM combobox.
- Discovery opens one serial configuration at a time and closes/reopens between
  configurations.
- `write_timeout` is 1 s; reads are non-blocking and governed by the adaptive
  discovery deadline.

Do not regress:

- Discovery is not controlled by `debug_sim`; it is a normal production feature.
- `debug_sim` continues to control only Simulation visibility.
- Passive capture remains strictly read-only.
- Simulation remains 4 transactions using FC01..04, Address 1..32, Qty 1..8.
- Existing filters, time sorting, compact wrapping, pair-boundary separators,
  Raw Hex wrapping and lazy capture logs remain unchanged.


## Larger Windows taskbar icon — v2.6

User decision:

- Keep version 2.6.
- Preserve the existing MBSniffer icon design.
- Make the visible artwork larger because the taskbar rendering was too small
  to read clearly.

Implementation:

- Start from the existing 256×256 RGBA icon artwork.
- Crop 24 px from each side and rescale to 256×256.
- This increases the visible logo occupancy by about 23% without changing the
  design.
- Rebuild `MBSniffer.ico` as a true multi-resolution Windows icon containing:
  - 16×16
  - 20×20
  - 24×24
  - 32×32
  - 40×40
  - 48×48
  - 64×64
  - 128×128
  - 256×256
- Native small icon frames improve Windows taskbar/window rendering compared
  with relying on one 256×256 frame to be downscaled at runtime.
- `build_exe.bat` continues to use the same `MBSniffer.ico`; no code behavior
  or application version change was required.


## Serial/discovery robustness pass — v2.6

Trigger:

- Active Slave Discovery could fail immediately with `Write timeout` at 0/247.
- The error occurred during TX, before waiting for any slave response.

Discovery TX changes:

- Keep version 2.6.
- Active discovery no longer forces `RTS=False` or `DTR=False`.
- Hardware flow control remains disabled (`xonxoff=False`, `rtscts=False`,
  `dsrdtr=False`).
- Discovery `write_timeout` is 1.5 s.
- Remove `ser.flush()` from the active scanner.
- Add `write_discovery_request()`:
  - verifies all request bytes are accepted;
  - retries one `SerialTimeoutException`;
  - calls `cancel_write()` when available;
  - clears input/output buffers after the timeout;
  - waits enough time for a possible partial request plus a Modbus RTU frame gap
    before retrying;
  - accounts for request on-wire time before starting the response deadline.
- Stop/close paths call best-effort `cancel_read()` / `cancel_write()` when the
  driver exposes those methods.

Discovery RX/error handling:

- Do not silently convert `in_waiting`/driver failures into ordinary slave
  no-response timeouts.
- Limit temporary discovery RX buffer to 1024 bytes.
- Serial open/TX/RX failures now include useful context:
  COM, baud/configuration, Slave ID and Function Code.
- A persistent write timeout terminates the scan cleanly through the normal
  `discovery_done` event instead of leaving the GUI busy.

General robustness changes:

- `process_queue()` is guarded so one unexpected GUI/event exception cannot
  permanently kill the periodic queue callback and make the program appear
  frozen.
- Only the first such internal queue-processing error opens a dialog; traceback
  is still printed when a console exists.
- Any passive-reader failure sets the shared stop event so dual-RX capture does
  not continue silently with only one direction alive.
- Simulation worker exceptions now emit `simulation_error` and restore the GUI
  instead of leaving `busy=True` indefinitely.
- Failure to start the discovery worker thread restores all GUI states.
- Shutdown uses an `_closing` guard, cancels serial I/O before joining workers,
  and avoids rescheduling periodic callbacks after close.
- `poll_com_status()` respects the `_closing` guard.

Regression tests performed:

- Python compilation / AST import.
- Discovery probe CRC and parser behavior retained.
- Fake serial adapter where first write raises `Write timeout` and second write
  succeeds: retry succeeds and scan continues.
- Persistent fake write timeout: scan terminates with detailed
  COM/config/slave/FC context.
- Fake discovery scan with normal response + Modbus Exception + no-response:
  correct found count and completion.
- GUI simulation under Xvfb: 4 Requests, 4 Responses, Pending 0.
- Synthetic exception inside GUI queue processing: callback recovers and
  continues processing subsequent events.
- GUI close path completes cleanly.


## Feature rename — Bus Slave Finder — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep application version `2.6`.
- Rename the active slave-discovery feature/tab to `Bus Slave Finder`.
- No functional behavior changed.


## Compact COM refresh control — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Replace the visible `Atualizar COM` text buttons with a compact circular-arrow
  button (`↻`) beside the COM selector.
- Apply the same visual convention to the Sniffer and Bus Slave Finder areas.
- The command remains `refresh_ports()`; behavior is unchanged.
- Internal widget names (`refresh_btn`, `discovery_refresh_btn`) remain unchanged
  so existing enable/disable logic is preserved.


## Modular Python architecture — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Refactor the application from one large Python source file into focused
  modules without changing user-visible behavior or existing features.
- Keep `debug_sim = 0/1` in `MBSniffer.py` so the existing simulation switch
  remains in the same user-facing location.

Current module responsibilities:

- `MBSniffer.py`
  - small launcher;
  - user-facing `debug_sim` switch;
  - Windows AppUserModelID initialization;
  - starts `SnifferApp`.
- `mb_config.py`
  - version/name;
  - application constants;
  - Modbus exception-code table;
  - application/resource/log path helpers.
- `mb_protocol.py`
  - Modbus CRC;
  - frame splitting/parsing/decoding;
  - request/response session metrics;
  - simulation frame generation.
- `mb_slave_finder.py`
  - Bus Slave Finder probe helpers;
  - adaptive discovery timing;
  - robust active serial TX/RX helpers;
  - Bus Slave Finder GUI/worker mixin.
- `mb_capture.py`
  - COM enumeration/configuration/restart;
  - passive serial-reader threads;
  - real capture lifecycle;
  - simulation worker;
  - GUI event-queue processing;
  - shutdown/cancellation handling.
- `mb_view.py`
  - traffic/Raw Hex rendering;
  - slave filter and time sorting;
  - compact Details wrapping;
  - transaction separators;
  - statistics;
  - bounded GUI history;
  - lazy disk logging.
- `mb_gui.py`
  - Tk root window;
  - overall widget layout;
  - composes the mixins into `SnifferApp`.

Architecture rules:

- Keep protocol logic independent from Tk where practical.
- Keep active Bus Slave Finder transmission logic separate from passive capture.
- Passive sniffer capture must remain read-only.
- Do not re-collapse the project into one monolithic Python file unless the user
  explicitly asks.
- Avoid excessive fragmentation: add a new module only when it has a clear,
  stable responsibility.
- `MBSniffer.bat` continues to launch `MBSniffer.py`.
- `build_exe.bat` continues to build from `MBSniffer.py`; PyInstaller follows
  local imports and bundles the modules into the one-file EXE.


## Bus Slave Finder UI cleanup — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Change only the Bus Slave Finder UI.
- Remove the `Todos` and `Nenhum` buttons from:
  - Baud rate;
  - Parity;
  - Stop bits.
- Keep individual checkboxes unchanged.
- Do not remove or change the Sniffer Slave-filter menu options `Todos` /
  `Nenhum`.
- Place the circular COM refresh button (`↻`) immediately beside the Bus Slave
  Finder COM dropdown, matching the compact Sniffer convention.
- Refresh behavior remains `refresh_ports()`; no serial behavior changed.

Implementation:

- COM label, combobox and refresh button are grouped in a non-expanding
  `port_controls` frame so weighted parent grid columns cannot push the refresh
  icon away from the dropdown.
- The now-unused `set_discovery_group()` helper was removed.


## UI alignment + extracted package layout — v2.6

User decisions:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Make both COM refresh controls visually identical:
  - circular arrow `↻`;
  - square button;
  - square height exactly tracks the adjacent COM combobox height;
  - arrow centered;
  - 4 px visual gap between combobox and refresh square.
- Improve menu organization/alignment without changing application behavior.

Sniffer UI changes:

- Configuration is organized into aligned horizontal rows:
  - physical mode + COM ports;
  - serial format;
  - frame timing/options;
  - COM state + pending timeout;
  - mode help.
- Existing widget variable names and callbacks remain unchanged.

Bus Slave Finder UI changes:

- COM selector/probe summary use one aligned top row.
- Baud checkboxes are distributed evenly.
- Parity, Stop bits and Slave IDs/velocity groups retain equal-width columns
  with consistent gaps.
- Existing discovery behavior remains unchanged.

Release ZIP layout:

- ZIP root contains only:
  - `README.txt`
  - `MBSniffer.bat`
  - `MBSniffer/` directory
- All other application files live inside `MBSniffer/`, including Python
  modules, icon, `build_exe.bat` and `DEVELOPMENT_NOTES.md`.
- Root `MBSniffer.bat` launches `MBSniffer\MBSniffer.py`.
- `build_exe.bat` remains inside the application folder and still builds from
  the local `MBSniffer.py`.
- Logs in BAT/Python mode therefore live under
  `MBSniffer\MBSniffer Logs`.


## Sniffer configuration grid + refresh icon/build output fixes — v2.6

User decisions:

- Keep name `MBSniffer`.
- Keep version `2.6`.
- Bus Slave Finder layout otherwise remains unchanged.
- Fix refresh control clipping in both tabs.
- Spread Sniffer configuration across explicit equal-width columns instead of
  packing controls against the left side.
- Build `MBSniffer.exe` directly into the extraction root beside
  `README.txt` and `MBSniffer.bat`.

Sniffer layout:

- Four equal-width configuration columns (`uniform="sniffer_cfg"`).
- Row 1:
  - Modo físico
  - COM A
  - COM B + refresh
  - Estado
- Row 2:
  - Baud
  - Data bits
  - Parity
  - Stop bits
- Row 3:
  - Frame gap
  - Gap manual (ms)
  - Visualização / Auto-scroll
  - Pending timeout
- COM A/B state and mode-help text remain below the grid.
- Existing variable/widget names required by capture logic are preserved.

Refresh controls:

- Replaced the Unicode text glyph with a 16×16 embedded PNG icon.
- This removes dependence on Segoe UI Symbol glyph metrics/fallback and avoids
  the curved arrow being vertically clipped.
- Both refresh buttons:
  - are hosted in a square frame;
  - dynamically track the adjacent COM combobox height;
  - use a 4 px gap from the combobox;
  - center the image through the ttk button layout;
  - retain existing enable/disable behavior and `refresh_ports()` callback.

EXE build:

- `MBSniffer\build_exe.bat` sets PyInstaller `--distpath` to the parent folder.
- Final EXE path is `<extraction root>\MBSniffer.exe`.
- PyInstaller work files remain under `MBSniffer\build`.
- No final `dist` directory is used.


Validation for this UI revision:

- All Python modules compile.
- Tk GUI smoke-tested under Xvfb.
- Sniffer refresh host: 24×24 px with adjacent combobox height 24 px.
- Bus Slave Finder refresh host: 24×24 px with adjacent combobox height 24 px.
- Measured dropdown→refresh visual gap: exactly 4 px in both tabs.
- Sniffer configuration grid measured four equal columns (301 px each at the
  default test geometry).


Validation for this UI revision:

- All Python modules compile.
- Tk GUI smoke-tested under Xvfb.
- Both COM comboboxes measured 24 px high in the test environment.
- Both refresh hosts measured 24×24 px.
- Dropdown-to-refresh gap measured exactly 4 px in both tabs.
- Sniffer configuration grid measured four equal-width columns.
- Existing simulation completed with 4 requests, 4 responses and 0 pending.


## PyInstaller path quoting fix — v2.6

Trigger:

- `build_exe.bat` failed on Windows with a PyInstaller error where several
  arguments were concatenated into an invalid script path.
- The problematic argument was `--specpath "%~dp0"`. `%~dp0` ends with a
  backslash, and a quoted Windows command-line argument ending in `\` can be
  misparsed by the Python/Windows argv rules, especially when the parent path
  contains spaces.

Fix:

- Keep version `2.6`.
- Normalize the application directory with:
  `for %%I in ("%~dp0.") do set "APPDIR=%%~fI"`
  so `APPDIR` has no trailing backslash.
- Derive `DISTDIR`, `SCRIPT`, `ICON`, `WORKDIR` and `SPECFILE` from normalized
  absolute paths.
- Remove the unnecessary `--specpath "%~dp0"` argument.
- Keep `--distpath "%DISTDIR%"` so the final EXE is created directly in the
  extraction root beside `README.txt` and `MBSniffer.bat`.
- Keep `--workpath "%WORKDIR%"` so build intermediates stay inside the
  `MBSniffer` folder.
- After PyInstaller returns success, explicitly verify that
  `%DISTDIR%\MBSniffer.exe` exists; otherwise report a build error.
- This is a build-script-only fix; application/runtime behavior is unchanged.


## Fixed-width Sniffer dropdowns + optical refresh centering — v2.6

User decisions:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Do not enlarge Sniffer dropdowns to fill the equal-width configuration
  columns.
- All Sniffer comboboxes use `width=13`, matching the Bus Slave Finder COM
  combobox.
- Controls are left-aligned within four equal layout columns; unused column
  width remains intentionally blank to provide spacing/alignment.
- COM B keeps the 4 px dropdown-to-refresh gap.
- Compact manual-gap and pending-timeout controls remain fixed-width rather
  than stretching across their columns.

Refresh icon correction:

- Re-rasterized `↻` into a 16×16 transparent PNG with a 2 px visual margin.
- The glyph is optically centered inside the image instead of touching the
  image edges.
- `Refresh.TButton` explicitly uses `anchor="center"`.
- The same image is used by Sniffer and Bus Slave Finder.
- Existing square-host sizing and COM-combobox height synchronization remain
  unchanged.


## Root-level log folder — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Create `MBSniffer Logs` in the same directory as the root `MBSniffer.bat`.
- Store all real capture `.txt` logs inside that folder.
- In EXE mode, create the same folder beside `MBSniffer.exe`.

Implementation:

- `get_application_directory()` now resolves the package root in BAT/Python
  mode by detecting `MBSniffer.bat` one directory above the source modules.
- Frozen/PyInstaller mode continues to use the EXE directory.
- Development mode falls back to the Python source directory when no root
  launcher BAT is present.
- `get_logs_folder()` remains the only log-directory creation point.


## Deterministic refresh centering + stacked COM status — v2.6

User priority:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Refresh arrow centering is the priority. Previous ttk text/image approaches
  still rendered visibly off-center on Windows.
- COM B status should appear directly below COM A status.

Refresh implementation:

- Added `mb_widgets.py` with `RefreshButton`, a `tk.Canvas` subclass.
- No ttk text/image layout is used for the refresh glyph.
- The circular arc and arrowhead are drawn with explicit Canvas coordinates.
- After drawing, `bbox("glyph")` is measured and the entire glyph is moved so
  its bounding-box center exactly matches the button center.
- This makes centering deterministic at runtime and independent of Windows ttk
  theme padding, font metrics or image layout.
- The Canvas itself remains square and dynamically follows the adjacent COM
  combobox height.
- Both Sniffer and Bus Slave Finder use the exact same widget and 4 px gap.
- `RefreshButton.configure(state="disabled"/"normal")` remains compatible with
  the existing capture/discovery state-management calls.

COM status layout:

- Display now uses:
  `Estado COM    COM A - <estado>`
  followed by:
  `              COM B - <estado>`
- Status separator changed from `:` to ` - ` for COM A/B.


Validation for deterministic refresh centering:

- Both refresh controls were instantiated as `RefreshButton`.
- Adjacent COM combobox height measured 24 px in the GUI test.
- Both refresh controls measured 24×24 px.
- Both dropdown-to-refresh gaps measured exactly 4 px.
- Actual Canvas glyph bbox for both buttons measured `(5, 3, 19, 21)`.
- That bbox center is exactly `(12, 12)`, matching the center of the 24×24
  button in both X and Y.
- State transitions `normal -> disabled -> normal` preserve centered drawing.
- Existing 4-request/4-response simulation regression still passes.


## COM B unused-state wording — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- When the selected physical mode does not use COM B, show:
  `COM B - Não Utilizada`
  instead of `COM B - —`.
- No serial behavior changed.


## Two Sniffer COM refresh buttons — v2.6

User decision:

- Keep application name `MBSniffer`.
- Keep version `2.6`.
- Sniffer now has one refresh button immediately after COM A and a second
  refresh button immediately after COM B.
- Both buttons intentionally call the same global `refresh_ports()` function,
  so either button refreshes:
  - Sniffer COM A list;
  - Sniffer COM B list;
  - Bus Slave Finder COM list.
- Both Sniffer refresh buttons use the same `RefreshButton` implementation,
  4 px dropdown gap and dynamic square sizing.
- Added `set_sniffer_refresh_state(state)` so capture/simulation/Bus Slave
  Finder lifecycle code enables/disables both Sniffer refresh buttons together.


## v2.7 — GUI modernization with ttkbootstrap

Primary goal:

- graphical/interface refresh while preserving Modbus functionality as the
  highest priority.

Toolkit decision:

- Use `ttkbootstrap` as the normal runtime theme layer rather than rewriting
  protocol/capture widgets around a separate widget model.
- Keep standard Tk/ttk-compatible widgets and all existing variable/state APIs,
  which minimizes regression risk in capture, filtering, Treeview, Raw Hex,
  Bus Slave Finder and logging code.
- `mb_theme.py` applies ttkbootstrap theme `bootstrap-light` when installed and retains
  a native ttk fallback for direct-development execution.
- Root `MBSniffer.bat` treats `pyserial` as mandatory and `ttkbootstrap` as optional: it attempts to install the theme but falls back to native ttk if installation is blocked.
- PyInstaller build uses `--collect-all ttkbootstrap` and keeps the one-file EXE
  output in the extraction root.

Sniffer layout revision:

- Top area is split horizontally:
  - left: compact Configuração card;
  - right: Controlos + Estatísticas da sessão.
- The old separate action row and statistics row were removed.
- Traffic notebook moved from Sniffer row 3 to row 1 and remains the expanding
  row, increasing vertical space available for live traffic.
- Frame selecionado moved to row 2.
- Configuration remains four columns but inside a narrower card, with smaller
  inter-column spacing and fixed-size controls; this reduces visual whitespace
  without enlarging dropdowns.
- Control buttons use a compact two-column grid:
  Iniciar/Parar, Reiniciar/Limpar, Abrir pasta de logs, optional Simulação and
  Separar transações.
- Session statistics use a compact two-column grid in the right panel.

Preserved behavior:

- passive Sniffer path remains read-only;
- Bus Slave Finder behavior unchanged;
- COM refresh behavior unchanged;
- COM B unused wording remains `Não Utilizada`;
- simulation FC01..04 / Qty 1..8 unchanged;
- filtering, sorting, separators, Raw Hex, lazy logging, log location and
  robust serial handling unchanged.

Validation for v2.7 GUI refactor:

- All 9 Python modules compile.
- Native ttk fallback GUI smoke-tested under Xvfb.
- Simulated ttkbootstrap-available code path smoke-tested with an API-compatible Style stub.
- Existing simulation regression passes: 4 requests, 4 responses, 0 pending.
- Bus Slave Finder probe CRC generation still passes.
- Default 1280×780 test geometry moved the traffic Treeview top to ~414 px and increased visible Treeview height to ~265 px, versus ~165 px in the previous v2.6 layout test.
- COM B unused wording remains `COM B - Não Utilizada`.


## v2.7 visual refinement — traffic headers / scroll / refresh / brightness

User decisions:

- Keep application name `MBSniffer`.
- Keep version `2.7`.
- Restore visible divisions between Traffic table headers.
- Remove the Traffic horizontal scrollbar.
- Retry the refresh control with Unicode now that the v2.7 buttons are larger.
- Make the light interface slightly darker/softer to reduce eye strain.

Implementation:

- Theme default changed to ttkbootstrap `flatly` when available.
- Added a soft neutral palette:
  - application background `#e7eaed`;
  - content background `#f5f6f7`;
  - traffic header background `#dde2e6`;
  - explicit neutral borders.
- Native fallback prefers `clam` because it respects custom border/background
  styling reliably.
- `MBSniffer.Treeview.Heading` now has explicit 1 px solid borders, restoring
  visual separation between every Traffic header.
- Traffic horizontal scrollbar and `xscrollcommand` were removed. Existing
  Details-column sizing/wrap logic remains responsible for fitting the viewport.
- Raw Hex and Help text surfaces use the softer content background rather than
  pure white.
- `RefreshButton` is again a Unicode `↻` rendered by a native `ttk.Button`,
  inside a square pixel-sized wrapper. The larger v2.7 control gives the glyph
  more room and leaves centering to the native themed button layout.
- Existing `configure(state=...)`, square-size synchronization and refresh
  callbacks remain compatible.


## v2.7 native colour rollback + static simulation status

User decisions:

- Keep application name `MBSniffer`.
- Keep version `2.7`.
- Keep the v2.7 compact/reorganised layout.
- Return to the native pre-v2.7 Windows/Tk colour appearance.
- Keep Traffic header divisions and no horizontal Traffic scrollbar.
- Refresh arrows remain Unicode `↻`, with another centering attempt.
- During simulation, do not display generated Slave IDs in the Configuration
  `Estado` field because that text changes the layout geometry.

Implementation:

- Removed the custom grey palette and ttkbootstrap runtime/build dependency.
- Native ttk theme order: Vista -> xpnative -> winnative -> clam fallback.
- Raw Hex and Help return to native Tk text colours.
- `RefreshButton` now draws the real Unicode `↻` on Canvas and iteratively
  centers the actual rendered text bbox on the square centre.
- The simulation no longer emits the `simulation_status` event containing the
  random slave list.
- Simulation status is the short fixed text `● A simular`; completion remains
  `● Simulação concluída`.
- The Configuration status label has fixed `width=22`, so status strings cannot
  resize the four-column configuration grid.


## v2.7 refresh optical centering

User decision:

- Keep version `2.7`.
- Prefer visual/optical centering over equal geometric margins.
- Keep the real Unicode `↻`.

Implementation:

- Keep the existing rendered-bbox centering as the baseline.
- Apply a deliberate optical correction after bbox centering:
  - X: `-1 px` (left)
  - Y: `+1 px` (down)
- Rationale: the arrowhead adds visual weight to the upper-right of the glyph,
  so pure geometric centering looks high/right even when its bbox is centered.
- The same correction applies to COM A, COM B and Bus Slave Finder refresh
  buttons because all three use the same `RefreshButton`.


## v2.7 refresh optical Y adjustment

User visual adjustment:

- Keep version `2.7`.
- Keep Unicode `↻`.
- Move all refresh glyphs 5 px upward relative to the previous build.
- Keep the existing 1 px left optical correction.

Implementation:

- `OPTICAL_OFFSET_X = -1`
- `OPTICAL_OFFSET_Y = -4`

The previous Y offset was `+1`; changing it to `-4` is a net 5 px upward move.


## v2.8 — Light/Dark mode switch

User decision:

- Bump application version from `2.7` to `2.8`.
- Preserve all existing Modbus/capture/discovery functionality.
- Add an explicit ON/OFF switch for Dark mode.
- Light mode must retain the native pre-dark-mode appearance preferred in v2.7.

UI placement:

- The switch is placed in the existing bottom options row of the Sniffer
  `Controlos` card, to the right of `Separar transações`.
- No new vertical row is added, so Traffic keeps the same usable height.
- Label: `Dark mode`.
- Default on every launch: OFF / Light mode.

Theme architecture:

- `mb_theme.py` now exposes:
  - `apply_light_theme()`
  - `apply_dark_theme()`
  - `apply_theme()`
  - `theme_colors()`
- Light mode prefers native Windows ttk themes in this order:
  `vista -> xpnative -> winnative`, with `clam` fallback.
- Dark mode deliberately uses `clam`, because native Windows ttk themes do not
  reliably honour full dark palettes for every widget.
- No new external GUI/theme dependency is required.

Dark coverage:

- root/window background;
- frames and LabelFrames;
- Notebook/tabs;
- buttons;
- entries, comboboxes and spinboxes;
- checkbuttons;
- scrollbars;
- Sniffer Traffic Treeview + headers;
- Bus Slave Finder Treeview + headers;
- Raw Hex / Log;
- Help / Ligações;
- Slave filter popup menu;
- COM refresh buttons;
- custom Dark mode switch itself.

Functionality guarantees:

- Theme switching is visual only.
- It must not open/close/restart serial ports.
- It must not reset session metrics.
- It must not clear captured traffic.
- It must not start/stop capture or Bus Slave Finder.
- Treeview compact row height is re-applied after ttk theme-engine changes.
- Existing v2.7 no-horizontal-scroll Traffic behavior remains unchanged.
- Existing v2.7 static simulation status behavior remains unchanged.



## v2.8 — Restore original appearance; fix only Dark-mode transition/toggle

User correction:

- Do not redesign/retheme the application.
- Restore the original v2.8 appearance:
  - Light mode uses the native Windows ttk theme exactly as before.
  - Dark mode keeps the already approved dark palette.
- Keep the Dark-mode control global in the top-right corner, outside both tabs.
- Do not change any other layout/functionality.
- The toggle must render at its normal size immediately on application startup.
- Clicking the toggle must not show a white focus rectangle.

Implementation:

- Reverted the single-engine Light/Dark experiment.
- Light again prefers `vista -> xpnative -> winnative`, with `clam` fallback.
- Dark still uses `clam` with the existing v2.8 dark colours.
- Removed the custom overlay ttk styles; the global top-right frame/label use
  normal ttk styling so Light mode keeps the previous native appearance.
- On Windows, `toggle_dark_mode()` temporarily suspends top-level redraw with
  `WM_SETREDRAW`, performs the theme/layout update, then repaints once. This
  hides intermediate ttk metric/layout passes without changing the final look.
- On non-Windows platforms the normal event-loop repaint path is used.
- `ToggleSwitch` keeps `takefocus=0`, `bd=0`, `highlightthickness=0`.
- `ToggleSwitch` now redraws on `<Configure>` and performs a delayed final
  redraw after startup/theme changes, fixing the small-until-hover problem.


## v2.8 — Dark checkbox tick preservation

User request:

- Do not change any other UI element or layout.
- In Dark mode, checkboxes must keep the same square/check visual language as
  Light mode instead of clam's selected-state X.
- The selected mark should be white, matching Dark-mode text.

Implementation:

- Light-mode checkbox behavior remains untouched/native.
- Dark mode replaces only the `TCheckbutton` indicator element.
- Custom indicator footprint is `15x15`, matching clam's native checkbox size,
  so checkbox geometry remains unchanged.
- Unchecked: dark square with neutral border.
- Checked: same square with a white tick.
- Disabled selected state uses the existing disabled grey.
- On Light fallback using clam, the original clam TCheckbutton layout is
  restored.


## v2.8 — Light/Dark structural geometry parity

User requirement:

- Do not redesign the application.
- Keep the approved native Light appearance.
- Keep the approved Dark colour palette.
- Light and Dark must use the same visual structure; only colours should differ.
- In particular:
  - LabelFrame rectangular borders must have the same geometry.
  - LabelFrame title text must sit on the border in the same position.
  - Notebook tabs/separators must use the same spacing and dimensions.
  - Buttons, inputs, checkboxes, Treeviews and scrollbars must retain the same
    geometry where the active ttk theme exposes equivalent elements.

Implementation:

- While Light mode is active, MBSniffer captures only geometry-related ttk
  information:
  - style layouts;
  - padding;
  - border widths;
  - relief;
  - LabelFrame label margins/outside placement;
  - Notebook tab margins/padding;
  - indicator/arrow sizes and margins;
  - fonts/row heights where relevant.
- No Light colour values are copied.
- When Dark mode activates, it keeps the existing Dark palette but replays the
  captured Light structural profile on clam.
- Layout replay is guarded: native-only elements are skipped if unavailable in
  clam, while compatible geometry options are still applied.
- Dark checkbox square/white-tick artwork is re-applied after geometry replay so
  the checkbox visual fix remains intact.
- Existing WM_SETREDRAW transition smoothing remains unchanged.
- No Modbus, capture, discovery, logging or layout-grid code was changed.


## v2.8 — Targeted Light/Dark visual parity from Windows screenshots

User-provided Windows screenshots identified four remaining visual differences.
This change is deliberately limited to those points; no Modbus/capture logic or
unrelated layout is changed.

1. LabelFrame titles
- Desired reference is the Dark-mode title position: title above the rectangle,
  not overlapping its top border.
- Force `labeloutside=True` and clam-compatible `labelmargins=(0,0,0,4)` in
  both Light and Dark.

2. Sniffer top workspace alignment
- `Controlos` begins at the same vertical coordinate as `Configuração`.
- The right-side stack fills the same overall height as `Configuração`.
- `Estatísticas da sessão` receives the flexible row and expands vertically so
  its lower border always aligns dynamically with the lower border of
  `Configuração`.

3. Notebook/tab tops
- Desired reference is Light/Vista geometry.
- Both modes now use Vista top-tab geometry:
  - `tabmargins=(2,2,2,0)`
  - selected `expand=(2,2,2,2)`
  - fixed tab padding in selected and unselected states.
- This specifically removes clam's selected-state padding shift in Dark mode.

4. Sniffer Traffic table header
- Desired reference is the Light/Vista table style.
- Dark `MBSniffer.Treeview.Heading` is forced flat with 1 px separators and no
  raised/3D header-cell appearance.
- Dark colours remain unchanged; only structural styling is aligned.

Existing v2.8 behavior retained:
- global top-right Dark-mode switch;
- Windows redraw suspension during theme transition;
- full-size toggle at startup;
- no toggle focus rectangle;
- square Dark checkboxes with white tick;
- Bus Slave Finder and Sniffer functionality unchanged;
- discovery write timeout remains 1.5 s.


## v2.8 — Dark Traffic header column separators

Targeted visual correction only:

- Light Traffic headers show a thin vertical divider between every column.
- Dark Traffic headers now render the existing 1 px heading border with
  `relief="solid"` instead of `flat`.
- Border colour remains the current Dark palette border colour.
- Active/pressed header states also remain `solid`, so separators do not
  disappear on hover/click.
- No table dimensions, column widths, row heights, sorting, filtering or
  Modbus functionality changed.


## v2.8 — Immutable Light/Dark construction + persistent preference

Windows screenshots showed that switching between native Vista Light and clam
Dark could never be structurally identical: the two ttk engines render tabs,
headers, borders and control metrics differently. Capturing/replaying metrics
reduced the differences but did not eliminate them.

Final architecture:

- MBSniffer now selects `clam` once before UI construction.
- It never changes ttk theme engine again during the process lifetime.
- All geometry/state construction is defined once in
  `_configure_fixed_geometry()`.
- Runtime Light/Dark switching calls `_apply_palette()` only.
- `_apply_palette()` is restricted to colour-related options and checkbox image
  pixels. It does not change layout, padding, border width, relief, margins,
  fonts, row heights or dimensions.
- Therefore the Dark-mode toggle changes colour, not page construction.

Light appearance:

- Neutral Windows-like palette.
- LabelFrame titles remain above the rectangular border.
- Vista-like fixed Notebook tab geometry.
- Flat Windows-like buttons/inputs.
- Square checkboxes with a black check.

Dark appearance:

- Existing approved v2.8 Dark palette retained.
- Same LabelFrame/tab/button/input/check geometry as Light.
- Checkbox image dimensions remain 15x15; selected check is white.

Traffic header:

- Shared geometry in both modes.
- `Treeview.Heading` border width is asymmetric:
  `(0, 0, 1, 1)`.
- This draws only the right-side column separator plus the bottom line, matching
  the Light screenshot instead of producing independent boxed header cells.
- Same geometry is used by `MBSniffer.Treeview.Heading`.

Persistent UI preference:

- `mb_config.py` adds `load_ui_settings()` / `save_ui_settings()`.
- Windows path:
  `%APPDATA%\MBSniffer\settings.json`
- Fallback:
  `~/.mbsniffer/settings.json`
- Stored field:
  `dark_mode: true/false`
- Loaded before ttk widgets are built, avoiding a Light flash when the saved
  preference is Dark.
- Works in BAT/Python and PyInstaller EXE mode.
- Settings failures are non-fatal.

Existing functionality retained:

- global top-right Dark-mode switch;
- switch remains full-size from startup and has no focus rectangle;
- dynamic Configuração / Controlos / Estatísticas alignment;
- no Traffic horizontal scrollbar;
- discovery write timeout remains 1.5 s;
- no capture/discovery/logging/Modbus logic changed.


## v2.8 — Dark-mode preference moved to Roaming AppData

User decision:

- Keep version `2.8`.
- Store the persisted Light/Dark preference in Roaming AppData rather than
  Local AppData.

Windows path:

- `%APPDATA%\MBSniffer\settings.json`
- Fallback: `C:\Users\<user>\AppData\Roaming\MBSniffer\settings.json`

Rationale:

- `dark_mode` is a user preference rather than machine-specific state.
- In Windows environments with roaming profiles, the preference can therefore
  follow the user between computers.

No UI, theme, Modbus, capture, discovery or logging behavior changed.


## v2.8 — Roaming preference expansion + restrained modern UI polish

User preference persistence:

- Keep one file only:
  `%APPDATA%\MBSniffer\settings.json`.
- Remember:
  - Dark mode;
  - last main tab (`Sniffer` / `Bus Slave Finder`);
  - Sniffer physical mode;
  - Sniffer Baud/Data bits/Parity/Stop bits;
  - Frame gap mode + manual value;
  - Pending timeout;
  - Auto-scroll;
  - Separate transactions;
  - Bus Slave Finder selected Baud rates;
  - Finder selected Parities;
  - Finder selected Stop bits;
  - Finder Slave start/end;
  - Finder minimum timeout;
  - Finder FC04 fallback.
- Deliberately do NOT persist:
  - any COM-port name;
  - finder safety confirmation;
  - window geometry;
  - traffic/session results.
- Variables are persisted with a 300 ms debounce.
- A final synchronous preference save occurs during normal application close.
- `save_ui_settings()` supports partial merges so one update cannot erase the
  remaining settings.

Visual direction:

- Keep the existing compact layout and immutable Light/Dark geometry.
- No theme-engine swap on toggle.
- Light/Dark continue to differ only by palette.
- Improve neutral button contrast, especially in Light.
- `MBS.Primary.TButton` uses the existing restrained blue accent so
  `Iniciar Captura` is visually identifiable as the primary action.
- Neutral buttons use a visible 1 px solid border.
- Scrollbars are reduced to a 9 px track/thumb and their arrow buttons are
  removed from the ttk layout.
- Spinbox arrowsize reduced from 10 to 7.
- Combobox arrowsize reduced from 12 to 10.
- Finder progressbar thickness fixed to 8 px.
- All these geometry rules are configured once at startup, therefore the
  Light/Dark toggle cannot move the interface.

Version remains `2.8`.


## v2.8 — Pending timeout direct entry + refresh glyph recenter

Targeted visual changes only.

Pending timeout:
- Replace only the Sniffer Pending timeout `ttk.Spinbox` with a `ttk.Entry`.
- Keep the same `pending_timeout_var`.
- Keep width `13`.
- Keep the existing min/default/max explanatory text.
- Keep existing runtime range validation in `get_pending_timeout_seconds()`.
- Keep Roaming persistence of `pending_timeout_s`.
- Purpose: remove the very small increment/decrement arrows after the modern
  spinbox arrow-size reduction.

Refresh buttons:
- Keep the existing custom `RefreshButton`, size and Unicode `↻` glyph.
- Keep the same button geometry/palette/behavior.
- Historical optical offsets `X=-1`, `Y=-4` are removed.
- New offsets are `X=0`, `Y=0`.
- The glyph is positioned solely by the existing rendered-Tk-bbox centering
  algorithm.
- This is now reliable because Light and Dark use the same fixed clam
  construction and refresh-control dimensions.
- Applies identically to COM A, COM B and Bus Slave Finder refresh buttons.

No other graphics, theme palette, layout, persistence or Modbus logic changed.
Version remains `2.8`.


## v2.8 — Full-buffer RTU resynchronization fix

Bug:
- `split_capture_buffer()` limited out-of-sync CRC resynchronization to the next
  32 bytes.
- With 33+ bytes of corruption/noise, a valid Modbus RTU frame later in the
  same captured burst could be swallowed into one final `RAW/UNPARSED` blob.

Fix:
- Replace:
  `min(max(len(buf) - 4, 0), 32)`
  with:
  `max(len(buf) - 4, 0)`.
- The existing `candidate_prefixes()` / `find_valid_prefix()` logic is unchanged.
- When a valid prefix is found at a later offset, the preceding unsynchronized
  bytes are emitted and the existing `continue` resumes parsing from that
  valid frame.
- The additional search cost occurs only while already out of sync.

No UI, theme, persistence, capture, logging or discovery behavior changed.
Version remains `2.8`.


## v2.9 — Diagnostic workspace expansion

User scope:
- Bump version from `2.8` to `2.9`.
- Implement every previously proposed diagnostic/UI feature except Named
  Profiles.
- Do not change the existing Light/Dark application theme.
- `Realçar anomalias` must be optional/off by default.
- When debug simulation is enabled and anomaly highlighting is selected,
  simulation must demonstrate every anomaly colour.

Theme guarantee:
- `mb_theme.py` is intentionally unchanged from the final v2.8 package.
- v2.9 adds controls/views/tags but does not alter the application theme,
  Light/Dark palette, ttk construction or global Dark-mode behavior.

### Frame Inspector
- Replaces the old one-line `Frame selecionado` field.
- Panel is collapsible via `Recolher` / `Expandir`.
- Displays:
  - Slave;
  - type;
  - Function Code and normalized function name;
  - PDU Address;
  - 1-based address;
  - Qty;
  - ByteCount where present;
  - response time;
  - received/calculated CRC;
  - decoded register/data/Exception information;
  - Raw Hex.
- Tree continuation rows map to the same logical source record.
- New module `mb_diagnostics.py` centralizes function names, CRC inspection,
  payload decoding and anomaly classification.

### Bus Health
- New `Bus Health` inner tab.
- SessionMetrics now tracks:
  - first/last event time;
  - total observed bytes;
  - active Slave IDs;
  - response-time samples;
  - response-time samples per Slave;
  - Exceptions per Slave.
- Metrics exposed:
  - Requests/Responses;
  - requests per second;
  - response average/min/max/P95;
  - CRC error rate;
  - timeout rate;
  - active Slaves;
  - approximate bus utilization;
  - slowest Slave by average response time;
  - Exception counts per Slave.
- Approximate bus utilization uses:
  observed bytes × serial bits-per-character / (baud × elapsed time).
- Health statistics are refreshed from the existing 1-second COM-status timer.
- Once capture/simulation is stopped, rate/load values freeze at the last frame
  instead of decaying forever.

### Advanced Traffic filters
- Compact toolbar above the Traffic Treeview.
- Filters:
  - Type: Todos/Requests/Responses/Exceptions/CRC errors/Timeouts/RAW;
  - FC hexadecimal;
  - response time > X ms;
  - free text over Details/Raw/Slave/FC/Type/Channel.
- Existing Slave-heading filter is preserved and combines with advanced filters.
- `Limpar filtros` also resets the existing Slave filter.
- Filters affect display only; session metrics/logging remain complete.
- Exception FC filtering accepts the base function as well: e.g. filter `03`
  also includes exception frame `83`.

### Timeout visualization
- SessionMetrics retains descriptors for requests that expire from Pending.
- The GUI marks the original REQUEST record with `timed_out=True`.
- This enables:
  - `Timeouts` filter;
  - timeout highlighting;
  - Frame Inspector timeout indication;
  - CSV timeout field.
- `force_timeout()` exists only to exercise the same mechanism quickly in
  debug simulation.

### Optional anomaly highlighting
- New `Realçar anomalias` checkbox in Sniffer Controlos.
- Default: OFF.
- Preference is persisted in the existing Roaming settings file.
- When OFF, normal Treeview colours are used for all rows.
- When ON, only anomaly rows receive tags:
  - `anomaly_crc`;
  - `anomaly_timeout`;
  - `anomaly_exception`;
  - `anomaly_slow`;
  - `anomaly_raw`.
- Priority: CRC > Timeout > Exception > RAW > Slow.
- Slow-response threshold: `500 ms`.
- Separate palettes are used for Light/Dark row tags, without changing the
  application theme itself.

### Simulation anomaly demonstration
- Normal simulation remains four valid FC01/02/03/04 transactions when
  `Realçar anomalias` is OFF.
- With highlighting ON, simulation creates:
  - one normal response;
  - one response >500 ms;
  - one valid Modbus Exception;
  - one plausible response with invalid CRC;
  - one request forced through the real timeout bookkeeping;
  - one RAW/UNPARSED block.
- Demonstration rows use channel `SIM` so this visual mode is explicit and works
  regardless of selected physical mode.
- Simulation remains GUI-only and never creates capture logs.

### Traffic context menu
Right-click on a real frame row:
- Copy Raw Hex;
- Copy decoded frame;
- Filter by this Slave;
- Filter by this FC;
- Show only this transaction;
- Clear transaction filter.
Visual transaction-separator rows do not open the frame context menu.

### Bus activity
- Compact `BUS ○` indicator added to the existing Sniffer Controls options row.
- Changes briefly to `BUS ● RX` for 180 ms whenever a frame batch is received.
- Uses existing ttk styling; no theme change.

### CSV export
- `Exportar CSV` button in Traffic filter toolbar.
- Exports retained `_frame_history` with UTF-8 BOM for Excel compatibility.
- Fields:
  Time, Delta ms, Response ms, Channel, Type, Slave, FC, Details, CRC, Raw,
  PDU Address, 1-based Address, Qty, Byte Count, Timed out, Anomaly.
- Export intentionally follows the bounded GUI history (max 20,000 frames);
  the real capture TXT log remains the complete disk record.
- Export accepts an explicit path for automated testing without opening dialogs.

### Parser RAW semantics
- `decode_frame()` now preserves `RAW/*` as RAW and does not infer fake
  Slave/Function values from arbitrary unsynchronized bytes.

### Existing v2.8 parser resync fix retained
- Full-buffer resynchronization remains:
  `search_limit = max(len(buf) - 4, 0)`.
- The former fixed 32-byte search cap is not reintroduced.

### Small UI refinements
- The existing theme is unchanged.
- Diagnostic additions use the same ttk widgets/styles already present.
- Primary/secondary visual hierarchy from v2.8 is preserved.
- Frame Inspector collapse, compact filter toolbar, BUS status indicator and
  context actions improve information density without decorative redesign.

### Files
New:
- `mb_diagnostics.py`

Modified:
- `MBSniffer.py`
- `mb_config.py`
- `mb_protocol.py`
- `mb_capture.py`
- `mb_view.py`
- `mb_gui.py`
- `README.txt`
- `DEVELOPMENT_NOTES.md`
- BAT/build version labels.

Unchanged intentionally:
- `mb_theme.py`
- `mb_widgets.py`
- serial/discovery protocol behavior except use of existing GUI integration.


## v2.9 — Ajuda/Ligações aligned with current parser and feature set

Targeted documentation/UI-help correction; version remains `2.9`.

RAW terminology:
- The Traffic table can legitimately show both `RAW/UNSYNC` and
  `RAW/UNPARSED`; they are not aliases.
- `RAW/UNSYNC`: unsynchronized bytes emitted before a later CRC-valid frame
  where full-buffer resynchronization succeeds.
- `RAW/UNPARSED`: remaining bytes when no valid Modbus frame can be recovered
  from that remainder.
- The Help text now explains both states explicitly instead of mentioning only
  `RAW/UNSYNC`, which was inconsistent with the anomaly demonstration screenshot.

Ajuda / Ligações refresh:
- Rewritten as a current v2.9 operational reference rather than a collection of
  legacy notes.
- Covers:
  - quick-start workflow;
  - RS485 2-wire / RS232 single RX / RS232 dual RX wiring;
  - serial parameters and Frame gap;
  - Pending timeout;
  - Traffic columns and REQUEST/RESPONSE pairing;
  - PDU Address / 1-based / Qty;
  - Modbus Exception codes;
  - advanced filters;
  - Realçar anomalias;
  - Frame Inspector;
  - Traffic context menu;
  - Bus Health metrics;
  - BUS RX indicator;
  - Raw Hex / Log;
  - CSV export;
  - log/history limits;
  - COM state/restart;
  - Bus Slave Finder;
  - Roaming preferences;
  - field-diagnostic good practices and physical-layer limitations.

Simulation visibility:
- Every user-facing reference to Simulation inside `Ajuda / Ligações` is now
  inside `if debug_sim == 1`.
- With `debug_sim == 0`, the Help text contains no Simulation heading,
  explanation, anomaly-demo reference or other simulation wording.
- With `debug_sim == 1`, a dedicated Simulation chapter explains both normal
  and anomaly-preview behavior.

No theme, layout, parser, capture, Finder or Modbus behavior changed.


## v2.9 — Simulation always generates anomaly scenario

Targeted simulation behavior change; version remains `2.9`.

Previous behavior:
- With `Realçar anomalias` OFF, simulation generated only four normal
  FC01/02/03/04 transactions.
- With `Realçar anomalias` ON, simulation generated the diagnostic anomaly
  demonstration.

New behavior:
- Every simulation run always generates the diagnostic demonstration:
  - one normal response;
  - one response slower than the configured anomaly threshold;
  - one valid Modbus Exception;
  - one response with invalid CRC;
  - one request that becomes a timeout;
  - one `RAW/UNPARSED` row.
- All simulation traffic uses channel `SIM`, independently of the selected
  physical mode.
- `Realçar anomalias` is now strictly a presentation option:
  - OFF: anomaly rows remain visible but use the normal neutral Treeview style;
  - ON: the exact same anomaly rows receive their diagnostic colour tags.
- This permits direct visual comparison without changing the simulated dataset.
- Simulation remains available only when `debug_sim == 1`, stays GUI-only and
  never creates capture logs.
- The Help chapter remains entirely hidden when `debug_sim == 0`.

No theme, parser, capture-from-COM, Bus Slave Finder, logging or Modbus
interpretation behavior changed.


## v2.9 — Traffic COM header + "Realçar resultados" + success green

Targeted v2.9 UI/result-display refinement; version remains `2.9`.

Traffic header:
- User-facing heading `Canal` renamed to `COM`.
- Internal record field remains `channel` because values can still be `BUS`,
  `A→B`, `B→A` or `SIM`; no capture semantics changed.
- Help clarifies that the `COM` column identifies the capture channel/direction
  and is not necessarily a literal Windows COM-port number.

Highlight option:
- User-facing `Realçar anomalias` renamed to `Realçar resultados`.
- Existing anomaly colours remain unchanged.
- Normal successfully completed transactions are now green when highlighting
  is enabled.
- A success is defined as:
  - normal `RESPONSE`;
  - CRC `OK`;
  - matched to a pending REQUEST;
  - not classified as slow/CRC/timeout/Exception/RAW.
- Both the successful RESPONSE and its matching REQUEST are highlighted green.
- Pending/unmatched REQUEST rows remain neutral.
- Slow but otherwise valid responses keep the existing slow-result colour,
  rather than being overridden by green.

Persistence migration:
- New settings key: `sniffer.highlight_results`.
- Existing `sniffer.highlight_anomalies` is accepted as a backward-compatible
  read fallback so current users keep their preference.
- Subsequent saves write the new `highlight_results` key.

Simulation:
- Simulation data is unchanged: it always generates the same diagnostic
  scenario.
- With `Realçar resultados` OFF all rows remain neutral.
- With it ON, successful transactions are green and diagnostic outcomes use
  their respective existing colours.

No theme palette/layout, Modbus parser, serial capture, Bus Slave Finder or
logging behavior changed.


## v2.9 — Result classification in Inspector + colour legend

Targeted documentation/Inspector addition; version remains `2.9`.

Frame Inspector:
- Adds a dedicated `Resultado` line.
- Semantic examples:
  - `Resultado: ✓ Sucesso — Verde`
  - `Resultado: ⚠ Resposta lenta — Amarelo`
  - `Resultado: ✕ CRC Error — Vermelho`
  - `Resultado: Exception — Vermelho`
  - `Resultado: ⚠ Timeout — Laranja`
  - `Resultado: RAW/UNSYNC — Roxo`
  - `Resultado: RAW/UNPARSED — Roxo`
- Pending REQUESTs report `Pendente / sem resultado — Neutro`.
- Successful REQUEST rows use the existing successful-request pairing set so
  the Inspector agrees with the green Traffic row.
- Copy-decoded-frame output now includes the same Result line.

Colour behavior:
- With `Realçar resultados` OFF, the Inspector still reports the semantic
  result and colour name in text, but the Result label itself remains neutral.
- With it ON, the Result label foreground uses the same result/anomaly colour
  as the Traffic Treeview.
- Result-specific ttk label styles configure colours only; no geometry, font,
  padding or theme-engine changes are made.
- `mb_theme.py` remains unchanged.

Ajuda / Ligações:
- Adds an explicit `Código de cores dos resultados` section:
  Green=success, Yellow=slow response, Red=CRC/Exception, Orange=Timeout,
  Purple=RAW.
- Frame Inspector documentation now explicitly includes Result/colour meaning.

No parser, serial capture, Bus Slave Finder, logging, theme palette/layout or
version changes.


## v2.9 — Inspector result text simplified

Targeted presentation adjustment; version remains `2.9`.

- Keep the `Resultado` line in Frame Inspector.
- Keep the existing symbols/semantic labels:
  - `Resultado: ✓ Sucesso`
  - `Resultado: ⚠ Resposta lenta`
  - `Resultado: ✕ CRC Error`
  - `Resultado: Exception`
  - `Resultado: ⚠ Timeout`
  - `Resultado: RAW/UNSYNC` / `RAW/UNPARSED`
- Remove the written colour suffix from Inspector text.
- The Inspector still uses the matching colour visually when
  `Realçar resultados` is enabled.
- Ajuda / Ligações remains the only place where colour names are written out
  explicitly: Verde, Amarelo, Vermelho, Laranja and Roxo.
- Copy-decoded-frame output follows the Inspector and therefore also omits the
  written colour name.

No theme, geometry, parser, capture, Finder, persistence or result-colour
mapping changed.


## v2.9 — Adaptive Bus Health vertical layout

Targeted Windows layout correction; version remains `2.9`.

- With Frame Inspector expanded, Bus Health could be allocated less vertical
  height than its six-row metric cards requested.
- Bottom rows could therefore cross the LabelFrame lower border.
- Bus Health now measures the natural full card height from the real widgets.
- If available height is insufficient, each card automatically reflows to two
  metric/value pairs per row.
- Odd final metrics span the remaining row.
- When sufficient height returns, the original one-metric-per-row layout is
  restored automatically.
- Reflow reacts to Bus Health resize, notebook-tab changes and Frame Inspector
  expand/collapse.
- A small hysteresis prevents repeated layout flipping near the threshold.
- No hard-coded window height is used.

No theme, colours, parser, capture, Finder, persistence or Modbus behavior
changed. Version remains `2.9`.


## v2.9 — Cleaner slimmer scrollbars

Targeted visual refinement; version remains `2.9`.

- Scrollbar construction remains deliberately minimal:
  - trough;
  - thumb;
  - no arrow buttons;
  - no extra controls.
- Vertical and horizontal scrollbar width reduced from `9 px` to `6 px`.
- Removed the unused `arrowsize` configuration because arrow elements are not
  present in the custom scrollbar layout.
- Light/Dark palettes and all non-scrollbar widgets remain unchanged.


## v2.9 — Floating-thumb scrollbars + mouse-wheel guard

Targeted visual/input refinement; version remains `2.9`.

Scrollbar visuals:
- Existing minimal ttk construction is retained: trough + thumb only.
- No arrows or additional controls are added.
- Width remains `6 px`.
- The trough is now painted with the same `input` background as the adjacent
  Tree/Text content, so it is visually invisible.
- Only the movable thumb remains apparent.
- Thumb colours were softened for both Light and Dark mode, with a slightly
  stronger hover/pressed state.
- Progressbar colours are unaffected because its trough still uses the
  dedicated `scroll_trough` palette value.

Mouse wheel:
- Added an application bindtag before normal widget/class bindings.
- Wheel input is allowed only when the event target is a ttk/Tk Scrollbar.
- Wheel input over Treeview, Text, notebook tabs/pages, frames, labels and other
  non-scrollbar widgets is consumed with `break`.
- This prevents Windows ttk Notebook tabs from cycling when the user wheels
  outside a scrollbar.
- Dragging/clicking scrollbars remains unchanged, and wheel-over-scrollbar keeps
  ttk's native scrollbar behavior.
- Keyboard notebook navigation is unchanged.

No parser, capture, Bus Health calculations, Finder, logging, result colouring,
persistence or version changes.


## v2.9 — GitHub repository README

Packaging/documentation update; version remains `2.9`.

- Added root-level `README.md` intended for GitHub repository rendering.
- `README.md` describes:
  - project purpose;
  - passive Sniffer modes;
  - decoded Traffic/Frame Inspector;
  - result highlighting and colour semantics;
  - Bus Health;
  - advanced filters;
  - context menu;
  - logging/CSV;
  - Bus Slave Finder;
  - Light/Dark mode;
  - development simulation;
  - execution/build instructions;
  - repository structure;
  - concise version history.
- Future release ZIPs should include this root-level `README.md` and update its
  version-history section whenever application behavior changes.
- Existing end-user `README.txt` remains in the package.

No application behavior, theme, parser, serial capture, Finder or version
change.


## v2.9 — Parser resynchronisation, Bus Health and documentation fixes

Corrective update; application version remains `2.9`.

- Package source folder renamed from `MBSniffer v2.9` to `MBSniffer` so the root
  `MBSniffer.bat` launcher and documented build path resolve correctly.
- Reworked RTU resynchronisation to scan the full remaining burst using only
  structurally recognised Modbus frame candidates.
- Removed the generic CRC brute-force length scan from each resynchronisation
  offset. This prevents multi-second parser stalls on long noise buffers.
- Unsupported/unknown Function Codes may only be accepted by CRC when they
  occupy the complete remaining burst; CRC-only candidates are never used while
  scanning arbitrary offsets. This strongly reduces accidental phantom frames
  in random noise.
- If the bytes immediately before a recovered valid frame exactly match a known
  frame shape but have an invalid CRC, that segment is now emitted as `CRC ERROR`
  instead of `RAW/UNSYNC`.
- Kept the explicit CRC-error counter, but replaced the misleading Bus Health
  `CRC error rate` with `Tráfego não validado`: percentage of captured bytes that
  belong to CRC-invalid frames or RAW blocks.
- Revised end-user Portuguese for Portugal (`descodificar`, `descodificação`,
  etc.) and adjusted several visible labels.
- Replaced the long GitHub README with a concise Portuguese README and added
  `README.en.md`, linked by a language selector at the top of both files.
- Removed version history from the GitHub README.



## v2.9 — Versioned source-folder packaging convention

Packaging convention update; application version remains `2.9`.

- The source folder that contains the Python files is now named exactly `MBSniffer v2.9`.
- Future packages must use the same convention: `MBSniffer vX.Y`, with no additional suffix or descriptive text in that folder name.
- Root `MBSniffer.bat` now resolves `MBSniffer v2.9\MBSniffer.py`.
- GitHub/end-user build instructions now point to `MBSniffer v2.9\build_exe.bat`.
- The `%APPDATA%\MBSniffer\settings.json` application-data directory is unchanged; this naming rule applies only to the packaged source folder.


## v2.9 — README wording clarification

- Reworded the README explanation of COM-port handling so it states plainly that the selected COM port is not saved between application sessions.
- Applied the same clarification to the English README.
- Updated an internal packaging docstring to reflect the versioned source-folder naming convention (`MBSniffer vX.Y`).


## v2.9 — RTU frame-gap compliance, regression tests and Device Identification

Corrective/feature update; application version remains `2.9`.

- Sniffer serial label changed from `Baud` to `Baud rate`; existing English technical terminology elsewhere was intentionally preserved.
- Added a shared Modbus RTU t3.5 helper:
  - baud rates <= 19200 bit/s use 3.5 character times;
  - baud rates > 19200 bit/s use the fixed 1.750 ms inter-frame delay recommended by Modbus Serial Line V1.02.
- The same t3.5 helper is also used by Bus Slave Finder timing/retry logic so active queries do not retain a shorter high-baud gap.
- Added optional Bus Slave Finder `Device Identification (FC43/14)`.
  - Disabled by default.
  - Sent only after the Slave has already been found by FC03/FC04.
  - Uses MEI type 0x0E / Basic Device Identification (Read Device ID code 0x01).
  - Parses `VendorName`, `ProductCode` and `MajorMinorRevision`.
  - Supports `More Follows` pagination with a bounded page count.
  - A Device Identification exception or no response does not invalidate the already discovered Slave.
  - Result table now includes a `Device Identification` column and a horizontal scrollbar.
- Added standard-library `unittest` regression suite under `tests/`.
- Added `run_tests.bat` for manual regression execution.
- `build_exe.bat` now runs the regression suite before PyInstaller and cancels the build if any test fails.
- Regression coverage includes:
  - CRC and supported parser frame shapes;
  - CRC-invalid frame followed by a valid frame;
  - long-noise resynchronisation;
  - deterministic random-noise robustness;
  - request/response pairing and timeouts;
  - automatic/manual frame-gap behaviour;
  - Slave Finder normal/exception responses;
  - FC43/14 request/response, CRC rejection, request echo handling and `More Follows`.

No Portuguese technical terminology was broadly rewritten in this update; the previous PT-PT/English terminology mix is intentionally retained.
- UI: moved `Device Identification (FC43/14)` beside `FC04 fallback` in the Bus Slave Finder options row; no functional behaviour changed.

## v2.9 — Bus Slave Finder results table without horizontal scrolling

UI refinement; application version remains `2.9`.

- Removed the horizontal scrollbar and `xscrollcommand` from the `Slaves encontrados` Treeview.
- The short columns (`Slave`, `Baud`, `Config.`, `FC`, `Resp. (ms)`) keep compact fixed widths.
- `Resultado`, `Device Identification` and `Raw Hex` dynamically share the remaining viewport width.
- Column widths are recalculated on Treeview resize so the complete results table remains visible without horizontal scrolling, matching the Traffic table behaviour.

## v2.9 — Table mouse-wheel scrolling + Bus Health spacing

Targeted UI/input correction; version remains `2.9`.

### Mouse wheel
- Corrected the application-level mouse-wheel guard in `mb_gui.py`.
- Vertical wheel scrolling is now allowed over:
  - Traffic `Treeview`;
  - Bus Slave Finder `Slaves encontrados` `Treeview`;
  - `Raw Hex / Log` and Help `Text` widgets;
  - scrollbar widgets.
- Wheel events over `ttk.Notebook`, notebook tabs/pages and other non-scrollable
  UI areas are still consumed before ttk class bindings run.
- This preserves normal table/text scrolling without allowing the mouse wheel to
  cycle between `Tráfego`, `Raw Hex / Log`, `Bus Health` or other tabs.

### Bus Health
- Compact Bus Health rows now share the available card height equally instead of
  accumulating at the top of each rectangle.
- Removed the rigid percentage split previously imposed on the four compact
  metric columns.
- Label columns now absorb spare width while value columns keep their natural
  width, preventing long metrics from being clipped by a neighbouring column.
- At narrower card widths, labels may wrap instead of crossing or overlapping
  another metric/value pair.
- Full mode also distributes its rows evenly over the available height.
- Light/Dark colour behavior and Bus Health calculations are unchanged.

### Validation
- Existing 20 automated regression tests pass.
- GUI smoke test under Xvfb confirmed wheel scrolling changes the vertical
  viewport in both Traffic and Slave Finder Treeviews.
- The same input guard returns `break` for Notebook wheel events, preserving the
  selected tab.
- Representative Bus Health values were geometry-checked at 1280x780: all
  labels/values remained within their LabelFrame bounds with no overlap.

## v3.0 — Interface bilingue PT-PT / English

- `APP_VERSION` aumentado para `3.0`.
- Pasta de código da release: `MBSniffer v3.0`.
- Pacote da release: `MBSniffer_v3.0_Package.zip`.
- Adicionado seletor global `Linguagem` ao lado do controlo de Dark Mode, com `Português` e `English`.
- O idioma é aplicado em runtime sem reiniciar a aplicação e é persistido em `%APPDATA%\MBSniffer\settings.json`.
- Português continua a ser a língua canónica e mantém os textos PT-PT da v2.9. Termos técnicos já existentes em inglês não foram traduzidos artificialmente.
- Adicionado `mb_i18n.py`, isolando traduções da lógica Modbus.
- Traduzidos para English os menus, separadores, labels, estados, mensagens/diálogos, tabelas, Bus Health, Frame Inspector, Bus Slave Finder e todo o conteúdo de Ajuda / Ligações.
- Dados de protocolo continuam canónicos; fragmentos human-readable como `Registos=` são apresentados como `Registers=` em English.
- A Help PT-PT original é preservada e restaurada exatamente quando se regressa a Português.
- Suite de regressão ampliada de 20 para 26 testes com cobertura de internacionalização.


## v3.0 — README bullet capitalisation

- Capitalised the first letter of every feature bullet in both `README.md` and `README.en.md`.
- No application behaviour or translation strings were changed.

## v3.0 — Language switch geometry lock

- Language changes are now text-only: switching `Português` / `English` must not move or resize the main UI panels.
- The Sniffer top workspace uses a fixed 3:2 grid ratio independent of translated child requested widths.
- The Dark Mode / Language overlay keeps the canonical Portuguese grid-cell widths, preventing the controls from sliding horizontally.
- The Bus Slave Finder reserves the canonical Portuguese configuration-row height so wrapped English/PT explanatory text cannot move the Controls and Results panels vertically.
- Traffic and Slave Finder table column widths are preserved during a language switch; normal resizing and traffic-driven autofit behaviour remain available outside the language-change event.
- Validation compares `TLabelframe` geometry before/after PT→EN at 1050×650, 1280×780 and 1600×900; all main rectangles remain identical.

### v3.0 — layout centring pass
- Centred the eight session-statistics counters inside their fixed 4 × 2 cells.
- Centred Bus Slave Finder Baud rate, Parity and Stop bits options inside their LabelFrames.
- Added an inset content frame to `Slave IDs / velocidade` so `Device Identification (FC43/14)` stays fully inside the rectangle and remains on the same row as `FC04 fallback`.
- These changes affect internal alignment only; outer panel geometry remains fixed when switching language.

## v3.0 — Compact Slave IDs / speed layout

- Moved `Timeout mín.` / `Min. timeout` onto the same centred row as the Slave ID range (`De` / `From` ... `até` / `to`).
- Kept `FC04 fallback` and `Device Identification (FC43/14)` together on the second centred row.
- Reduced the requested height of the `Slave IDs / velocidade` / `Slave IDs / speed` LabelFrame so the three serial-configuration rectangles remain compact and visually balanced.
- The outer three-column geometry and PT-PT / English language-switch positions remain unchanged.
- GUI validation at 1280×780 confirmed the first row fits fully inside the rectangle in both languages.

- UI refinement: added a small 3 px vertical gap between the Slave range/timeout row and the FC04 fallback / Device Identification row, keeping the panel compact.


---

# v3.1 — Correções de diagnóstico, Bus Slave Finder e organização

Versão aumentada de `3.0` para `3.1` a pedido do utilizador. Pasta de código
`MBSniffer v3.1`; pacote `MBSniffer_v3.1_Package.zip`. Implementa as 15 melhorias
identificadas na revisão da v3.0. Testes: 26 → 45, todos a passar.

## Erros corrigidos

1. **Broadcast (Slave 0) contava como timeout.** Pedidos para o endereço 0 já
   não ficam pendentes. `SessionMetrics.broadcast_requests` conta-os à parte e
   são excluídos do denominador da Timeout rate.
2. **FC05/FC06/FC08/FC22 fora das estatísticas.** O parser continua a devolver
   `REQ/RESP` (o formato não distingue as duas direções), mas
   `SessionMetrics._resolve_echo_direction()` classifica agora cada trama:
   - é `RESPONSE` se existir um pedido pendente com a mesma chave (Slave, FC);
   - em FC05/06/22 (eco exato) os bytes têm também de ser iguais;
   - em RS232 dual RX a resposta tem de vir do canal oposto ao do pedido;
   - caso contrário é `REQUEST`; broadcast é sempre `REQUEST`.
   O tipo resolvido substitui `REQ/RESP` no registo, por isso a tabela, os
   filtros, a pairing, o tempo de resposta e os timeouts passam a funcionar.
   Limitação conhecida: em RS485 (um só canal), se o master repetir a mesma
   escrita a um slave que não responde, a repetição é tomada como resposta.
3. **Tramas partidas pelo adaptador USB apareciam como RAW.** Acima de
   19200 bit/s o gap Auto é 1,75 ms, menor que a latência USB (FTDI: 16 ms).
   - `burst_may_continue()` deteta quando o burst acaba no início de uma trama
     conhecida ainda incompleta;
   - nesse caso o `reader_loop` espera até `SNIFFER_SPLIT_FRAME_HOLD_MS`
     (40 ms) antes de fechar o burst; o parse só é refeito quando chegam bytes;
   - aumentar o gap não era solução: pedido e resposta ficariam no mesmo burst
     com a mesma hora (tempo de resposta 0 ms).
   - `parse_burst()` aceita `chunk_times` (offset, hora de cada leitura): frames
     juntos num burst ficam com a hora do seu próprio bloco de bytes.
4. **Cada timeout reconstruía a tabela inteira** (até 20 000 linhas, ~0,4 s
   no thread da interface). `mark_timed_out_records()` usa agora
   `refresh_record_tags()` para mudar só a tag das linhas visíveis desse pedido.
   Só reconstrói tudo com o filtro `Timeouts` ativo (a linha passa a ser visível).
   - Corrigido no mesmo sítio: `render_raw_text_only()` contava `"\\n"` literal
     em vez de quebras de linha, pelo que o limite do Raw Hex nunca disparava
     depois de uma reconstrução.

## Melhorias funcionais

5. **Tentativas no Bus Slave Finder** (1 a 3, por defeito 1): cada pedido sem
   resposta é repetido antes de passar ao Slave seguinte. Persistido em
   `settings.json` (`bus_slave_finder.attempts`). A estimativa de duração
   multiplica o pior caso pelas tentativas.
6. **Timeout mínimo por defeito 40 → 100 ms.** Migração: ficheiros de
   definições sem a chave `attempts` (escritos até à v3.0) e com 40 ms passam a
   100 ms, porque os 40 ms eram o valor automático antigo e não uma escolha.
7. **Verificação de barramento livre:** antes da primeira transmissão o Finder
   escuta `DISCOVERY_IDLE_CHECK_SECONDS` (1 s). Qualquer byte recebido aborta a
   pesquisa sem transmitir, com mensagem a indicar a porta e os primeiros bytes.
   Complementa (não substitui) a caixa de confirmação de segurança.
8. **Endereço de cada valor nas respostas de leitura:** o registo guarda
   `request_pdu_address`/`request_qty` do pedido emparelhado e o Frame Inspector
   mostra `Registos (PDU Address=valor): 100=42, 101=43`. Os Detalhes da
   RESPONSE continuam sem repetir o endereço (decisão v2.6 mantida).
9. **Bits FC01/FC02 descodificados:** Detalhes mostra `Bits=10110011 10` (ordem
   de endereço, agrupado por byte, cortado à Qty do pedido, no máximo 32 bits
   visíveis + `…(+N)`); o Inspector lista todos com o endereço.
10. **CRC por tabela** (`_CRC16_TABLE`): mesmo resultado, ~5–10× mais rápido;
    ajuda sobretudo a ressincronização com ruído.

## Organização

11. `.gitignore` na raiz do repositório (`__pycache__/`, `*.pyc`, build do
    PyInstaller, `MBSniffer.exe`, `MBSniffer Logs/`); `__pycache__` retirado do git.
12. Todas as traduções inline (`... if self.current_language == "English" else ...`,
    40 ocorrências) passaram para `mb_i18n.PT_TO_EN` como modelos usados com
    `self.trf()`. Um teste falha se voltar a aparecer uma ramificação inline.
13. Lista de ficheiros do pacote atualizada em `DEVELOPMENT_NOTES.md`.
14. Notas divididas: `DEVELOPMENT_NOTES.md` (regras em vigor) + este `CHANGELOG.md`.
15. Regra do PDF técnico: é gerado de novo em cada release, sempre sobre a
    versão mais recente, com `tools/build_technical_pdf.py`; fica na raiz do
    repositório e não entra no ZIP (o PDF documenta o hash do ZIP).

## Ajuda e README

- Ajuda PT/EN: broadcast, classificação FC05/06/08/22, bits e endereços no
  Inspector, espera por tramas partidas, Tentativas e verificação de
  barramento livre.
- README.md / README.en.md: novas funcionalidades e caminho `MBSniffer v3.1`.
- README.txt regenerado para a v3.1.

## Validação

- 45 testes de regressão a passar (19 novos: CRC vs referência bit a bit,
  broadcast, FC05/06 com e sem resposta, escritas diferentes, dual RX, burst
  incompleto, tempos por bloco, bits com Qty, retag sem reconstrução, filtro
  Timeouts, Inspector com endereços de registos e bits, Finder com tentativas,
  bloqueio por tráfego, migração do timeout, ausência de traduções inline,
  modelos traduzidos, reconstrução de trama partida no reader).
- O teste da trama partida falha com a lógica antiga e passa com a nova.
- Teste da interface a 1280×780 com tráfego injetado: tipos corretos,
  1 timeout, 1 broadcast, Inspector com endereços em PT e EN; geometria do
  Bus Slave Finder igual em PT e EN com o novo campo Tentativas.


---

# v3.2 — Separador Master (Fase 1) e pacote completo

Versão aumentada de `3.1` para `3.2` a pedido do utilizador. Pasta de código
`MBSniffer v3.2`; pacote `MBSniffer_v3.2_Package.zip`. Testes: 45 → 64.

## Pedido do utilizador

Incorporar no MBSniffer uma ferramenta do género do Modbus Poll, sobretudo a
possibilidade de abrir várias janelas, uma por slave. As funcionalidades foram
recolhidas da documentação pública do Modbus Poll (modbustools.com); a cópia
crackeada do programa que estava na pasta não foi aberta nem analisada. O
Modbus Slave fica para mais tarde.

## Separador Master (Fase 1)

- Novo `mb_master.py` (sem widgets): tramas FC01–04 e FC05/06/15/16,
  `find_master_response()`, formatos de dados e `MasterEngine`, que serve todas
  as janelas numa só porta série, um pedido de cada vez (escritas → "Ler 1x" →
  janela com o prazo mais antigo), com atraso entre pedidos ≥ t3.5.
- Novo `mb_master_ui.py` (`MasterMixin`): ligação (porta, baud, parity, stop
  bits, timeout de resposta, atraso entre pedidos), confirmação de segurança,
  verificação de barramento livre, janelas em grelha (colunas conforme a
  largura) com Slave, FC, endereço, quantidade, scan rate, base 0/1 e formato,
  botões Aplicar / Pausar / Ler 1x / Duplicar / Destacar / Fechar, contadores
  Tx/Err/Timeouts, tempo de resposta e último erro por janela.
- Formatos: 16 bits com/sem sinal, hex, binário; 32 bits com/sem sinal e float
  nas ordens ABCD, CDAB, BADC e DCBA.
- Escrita por duplo clique (FC05/FC15 em janelas FC01, FC06/FC16 em FC03),
  vários valores com ";", broadcast com Slave 0, releitura após escrita aceite.
- Nomes por endereço (duplo clique na coluna Nome).
- Destacar uma janela abre-a num `Toplevel`; ancorar ou fechar devolve-a.
- Workspace `.mbsw` (JSON) com a ligação, janelas, formatos e nomes.
- Enquanto ligado, Sniffer, Simulação e Bus Slave Finder ficam bloqueados.
- `settings.json` guarda os parâmetros de ligação do Master (sem a porta) e
  aceita `Master` como último separador.
- Ajuda PT/EN, README e traduções (66 textos novos) atualizados.

## Pacote completo

- Por pedido do utilizador, o ZIP passa a levar o repositório inteiro: `.git`,
  `.gitignore`, `tools/` e o PDF técnico, além do código e dos README.
- Novo `tools/build_package.py` cria o ZIP a partir da pasta de trabalho e
  calcula o "Source snapshot SHA-256". Regra do utilizador: o processo de
  release nunca faz commit nem push; os commits são feitos pelo utilizador.
- `tools/build_technical_pdf.py`: como o PDF vai dentro do ZIP, a capa passa a
  citar o "Source snapshot SHA-256" (hash dos ficheiros documentados) em vez do
  hash do ZIP; `.git`, `tools/`, `.gitignore` e o PDF aparecem na árvore do
  pacote mas não são documentados como código. Gera-se a partir da pasta do
  repositório (`--source-dir .`).

## Validação

- 64 testes a passar (19 novos em `tests/test_master.py`, com um slave Modbus
  simulado: formatos nas 4 ordens, exemplos de tramas da especificação Modbus,
  eco do adaptador, exceção, CRC errado, escalonamento, janelas rápidas e lentas
  na mesma porta, escrita, broadcast, timeout, bloqueio por tráfego, workspace e
  escrita FC16 de floats).
- Teste da interface com o slave simulado: 3 janelas (FC03 float, FC01 coils,
  slave inexistente com Timeout), escrita FC16 de -7.25 relida, janela
  destacada, PT/EN e modo escuro, desligar e reabrir workspace.

## GitHub só com o código (pedido do utilizador)

- O GitHub passa a receber apenas o código necessário para correr a aplicação
  (`MBSniffer.bat`, módulos `.py`, ícone) e `README.md` / `README.en.md`.
- Regra em `.git/info/exclude` (lista branca local, nunca enviada); o
  `.gitignore` foi removido.
- `git rm --cached` de `README.txt`, `DEVELOPMENT_NOTES.md`, `CHANGELOG.md`,
  `tests/`, `build_exe.bat`, `run_tests.bat` e `tools/`: os ficheiros continuam
  no disco e no ZIP, mas o próximo commit do utilizador retira-os do GitHub.

## Histórico só com a versão atual dos documentos (pedido do utilizador)

- `README.txt`, o PDF, `DEVELOPMENT_NOTES.md` e `CHANGELOG.md` voltam a ir para o
  GitHub, mas só na versão atual; testes, `.bat` de build/testes e `tools/`
  continuam fora (lista branca em `.git/info/exclude`).
- `tools/build_package.py` passa a pôr no ZIP uma cópia reescrita do `.git`:
  os commits antigos ficam só com código e `README.md` / `README.en.md`
  (sem PDFs, notas, `__pycache__`, `tools/`, etc.), as refs `origin/*` saem e os
  objetos antigos são apagados. O `.git` empacotado passou de 52 MB para
  ~0,3 MB e o ZIP de 77,6 MB para ~24 MB. O repositório no disco não é alterado.
- Fluxo do utilizador: apagar a pasta do git, extrair o ZIP, commit e
  `git push --force origin main`.

## Pacote só com os ficheiros da aplicação (pedido do utilizador)

- O utilizador gere o git e o GitHub sozinho. O ZIP deixa de levar o `.git` e
  deixa de haver limpeza/reescrita de histórico ou regras de GitHub no processo
  de release (substitui as duas entradas anteriores sobre GitHub e histórico).
- O ZIP leva: `MBSniffer.bat`, `README.txt`, `README.md`, `README.en.md`, o PDF,
  a pasta `MBSniffer vX.Y` (código, ícone, testes, `.bat`, notas, CHANGELOG) e
  `tools/`.

## Janelas do Master e workspaces (versão mantém-se 3.2)

- Cada janela tem cabeçalho com o nome, o resumo (Slave/FC/endereço/quantidade)
  e os botões "Renomear", "Destacar" e "✕". O utilizador não encontrava o
  "Fechar": estava no fim da fila de botões e ficava cortado com a escala do
  Windows acima de 100%.
- Janelas com nome próprio (`title`), guardado no workspace; vazio = "Janela N".
- A grelha passa a calcular as colunas pela largura real das janelas.
- Workspaces: menu "Workspace" com Guardar workspace…, Abrir workspace ▸ e
  Apagar workspace ▸ (lista dos guardados) e Abrir pasta dos workspaces. Os
  ficheiros ficam em `%APPDATA%\MBSniffer\Workspaces`, junto do `settings.json`.
  Deixa de haver janelas de "Abrir/Guardar ficheiro".
- Testes: 64 → 68 (pasta dos workspaces, lista ordenada, nomes válidos, nome da
  janela no workspace).

## Formatos por endereço, 64 bits e workspaces (versão mantém-se 3.2)

Pedido do utilizador, registado em 9 pontos e aplicado de uma vez:

1. Etiqueta do workspace: "(alterado)" quando há alterações por guardar; some
   quando se fecham todas as janelas.
2. Formato por endereço com clique direito e seleção múltipla (Ctrl/Shift).
   32 bits exigem 2 registos seguidos; seleções maiores aplicam-se em pares.
   "Repor formato da janela". Guardado no workspace (`formats`).
3. Formatos de 64 bits: Signed, Unsigned e Double nas ordens ABCDEFGH,
   GHEFCDAB, BADCFEHG e HGFEDCBA (4 registos; seleções maiores em grupos de 4;
   escrita com FC16). `format_value()`, `register_groups()` e
   `format_window_values()` em `mb_master.py`.
4. Último workspace guardado em `settings.json` e reaberto ao arrancar (sem
   ligar). Ao fechar com o workspace alterado: Guardar? Sim/Não/Cancelar; sem
   workspace não pergunta.
5. "Aplicar" destacado enquanto há campos por aplicar.
6. Valores a cinzento quando a última leitura falha e ao desligar.
7. Altura da tabela = quantidade (3 a 15 linhas).
8. Copiar (menu e Ctrl+C) endereços, nomes e valores, separados por tabs.
9. Base de endereços passa para o menu de clique direito.

- A janela de escrita usa o formato do valor clicado.
- Testes: 68 → 76.

## Escala, Abrir no Master e religação automática (versão mantém-se 3.2)

- Escala por endereço no clique direito ("Escala…", "Remover escala"): bruto →
  unidades de engenharia por dois pontos, casas decimais e unidade; guardada no
  workspace; a escrita aceita unidades e converte para bruto.
- "Abrir no Master" no menu de contexto do Tráfego (pedido FC01–FC04 ou a sua
  resposta) e nos resultados do Bus Slave Finder (clique direito / duplo
  clique); copia os parâmetros série para o Master quando este está desligado.
- O Master volta a abrir a porta sozinho (a cada 2 s) quando ela falha, por
  exemplo com o adaptador USB desligado, e retoma as leituras.
- Testes: 76 → 86.

## Seleção por arrasto (versão mantém-se 3.2)

- Nas tabelas do Master, carregar e arrastar seleciona todas as linhas entre a
  linha inicial e a do rato, para cima ou para baixo, com scroll automático ao
  sair da tabela. Ctrl+arrastar junta o bloco à seleção anterior. Clique,
  Ctrl/Shift+clique e duplo clique ficam iguais.

## Tabelas do Master com linhas alternadas e moldura (versão mantém-se 3.2)

- Linhas alternadas com um fundo ligeiramente mais escuro e moldura de 1 px à
  volta de cada tabela, nas cores da paleta clara/escura. Não ocupa espaço.


---

# v3.3 — MBSniffer passa a chamar-se MBToolkit

Versão aumentada de `3.2` para `3.3` a pedido do utilizador; só a mudança de
nome (o Slave fica para a v3.4, para cada versão ser testada à parte).

- Nome do produto MBSniffer → MBToolkit em toda a aplicação, ficheiros e
  documentação: `MBToolkit.bat`, pasta `MBToolkit v3.3`, `MBToolkit.py`,
  `MBToolkit.ico`, `MBToolkit.exe`, `MBToolkit_v3.3_Package.zip`,
  `MBToolkit_v3.3_Technical_Code_Documentation.pdf`, título da janela, Ajuda
  PT/EN, README, notas, estilos/etiquetas internas. O separador "Sniffer"
  mantém o nome.
- Ícone novo no mesmo estilo, desenhado de raiz por `tools/make_icon.py` em
  alta resolução (16–256 px no .ico, PNG de 1024 px para documentos). Até
  32 px mostra só o símbolo, para ser legível na barra de tarefas.
- Migração automática, uma vez, de `%APPDATA%\MBSniffer` (settings.json e
  Workspaces) para `%APPDATA%\MBToolkit`; a pasta antiga não é apagada.
- Workspaces guardados como "MBSniffer Master workspace" continuam a abrir.
- Logs novos em `MBToolkit Logs` com o prefixo `MBToolkit_`.
- Testes: 86 → 88 (migração e formato antigo de workspace).


---

# v3.4 — Separador Slave (simulador)

Versão aumentada de `3.3` para `3.4` a pedido do utilizador (Fase 1 do Slave).
Decisões do utilizador: Master e Slave nunca ao mesmo tempo; o workspace
guarda só a configuração; a simulação de falhas entra já na Fase 1, por Slave ID.

- Novo separador **Slave**: janelas = tabelas de Slaves simulados (Coils,
  Discrete Inputs, Holding, Input Registers), vários Slave IDs.
- `mb_slave.py`: `SlaveStore`, `handle_request()` (FC01–06/15/16, Exceptions
  01/02/03, broadcast, IDs alheios ignorados) e `SlaveEngine` (montagem dos
  pedidos por comprimento, ressincronização por silêncio, espera t3.5, remoção
  do eco RS485, religação da porta).
- Simulação de falhas por Slave ID: atraso, não responder, Exception à escolha,
  CRC errado, probabilidade; aviso a vermelho no cabeçalho das janelas.
- Valores editados por duplo clique; escritas do master destacadas a amarelo.
- Contadores globais (pedidos, respostas, exceções, broadcast, outros IDs) e
  por janela (pedidos, exceções, último pedido).
- Workspace do Slave em `Workspaces\Slave` (só configuração); último workspace
  reaberto ao arrancar; pergunta ao fechar com alterações.
- Novo `mb_table_ui.py` (`TableUiMixin`): o código das janelas do Master
  (cabeçalho, tabela, arrasto, linhas alternadas, menu, escala, grelha, menu
  Workspace) passou para lá e serve os dois separadores. Comportamento do
  Master inalterado.
- Bloqueio global alargado: Sniffer, Finder, Master e Slave nunca ao mesmo
  tempo; mensagem do Master atualizada.
- Ajuda PT/EN com a secção do Slave; README; PDF com capítulo "Slave
  (simulator) tab", diagrama do motor e captura.
- Workspaces do Master em `Workspaces\Master` (simétrico com o Slave);
  `get_master_workspaces_folder()` move uma vez os `.mbsw` soltos em
  `Workspaces`. `workspace_path()` / `list_workspaces()` de `mb_table_ui.py`
  recebem sempre a pasta; `mb_master_ui.py` tem as versões do Master.
- Campo Tabela do Slave com o código e o nome ("03 Holding Registers"), como o
  campo FC do Master; o cabeçalho das janelas do Master e do Slave mostra o
  código e o nome (`FC03 Read Holding Registers` / `FC03 Holding Registers`).
- Fase 2 do Slave (parte): valores automáticos por endereço (contador, rampa,
  senoide, aleatório; alternar/aleatório nos bits), a azul e guardados no
  workspace; "Abrir no Slave" a partir do Tráfego do Sniffer e do clique
  direito numa janela do Master.
- Código dos workspaces juntado em `mb_table_ui.TableWorkspace` (guardar,
  abrir, apagar, menu, "(alterado)", pergunta ao fechar) para o Master e o
  Slave; comportamento igual.
- Testes: 88 → 118 (`tests/test_slave.py`, migração da pasta do Master, campo
  Tabela, valores automáticos e "Abrir no Slave").
