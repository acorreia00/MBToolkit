"""Hand-written content for the MBToolkit Technical Code Documentation PDF.

``build_technical_pdf.py`` combines this file with facts it derives itself
from the documented package (file lists, line counts, SHA-256 hashes,
callables, constants, imports, regression tests and source screenshots).

Edit this file whenever the behaviour of a new version changes:

* ``VERSION_HISTORY`` / ``VERSION_CHANGES`` - chapter "Version history and
  changes in this version" (one entry per release, newest last).
* ``CHAPTERS`` - explanatory chapters.  ``{version}`` is replaced by the
  documented version.  ``{{diagram:NAME}}`` inserts a diagram from
  ``DIAGRAMS``; ``{{figure:sniffer}}`` / ``{{figure:finder}}`` insert the UI
  screenshots captured by ``capture_ui_screenshots.py``.
* ``MODULE_INTROS`` / ``KEY_PATH_DETAILS`` / ``DESIGN_NOTES`` - module
  chapters.  The first sentence of a key-path detail is reused as the
  "Responsibility" cell of the callable table; callables without a detail
  use their docstring, or a readable form of their name.
* ``TEST_CLASS_DESCRIPTIONS`` / ``BAT_DESCRIPTIONS`` - test and build
  chapters.

All text is HTML.  Use ``<code>`` for identifiers and ``<b>`` for emphasis.
"""

# Order used for the package tree, the source inventory, the module
# reference, the integrity table and Appendix A.  Files that are not listed
# are appended alphabetically, so new modules are never silently omitted.
FILE_ORDER = [
    "MBToolkit.py",
    "mb_config.py",
    "mb_protocol.py",
    "mb_capture.py",
    "mb_diagnostics.py",
    "mb_view.py",
    "mb_slave_finder.py",
    "mb_master.py",
    "mb_master_ui.py",
    "mb_slave.py",
    "mb_slave_ui.py",
    "mb_table_ui.py",
    "mb_i18n.py",
    "mb_theme.py",
    "mb_widgets.py",
    "mb_gui.py",
    "tests/test_regression.py",
    "tests/test_master.py",
    "tests/test_slave.py",
    "run_tests.bat",
    "build_exe.bat",
    "MBToolkit.ico",
    "DEVELOPMENT_NOTES.md",
    "CHANGELOG.md",
]
# Order of the batch files in the integrity table, build chapter and Appendix A.
BAT_ORDER = ["MBToolkit.bat", "build_exe.bat", "run_tests.bat"]
ROOT_FILE_ORDER = ["MBToolkit.bat", "README.md", "README.en.md", "README.txt"]

COVER_SUBTITLE = (
    "Architecture, runtime flows, every callable, regression tests, build "
    "automation, and complete source-code screenshots"
)

COVER_NOTES = [
    "This document describes the exact source snapshot above. It does not document "
    "proposed future features, such as Modbus TCP, that are not present in this package.",
    "The final appendix reproduces every Python and Windows batch source line as code "
    "screenshots. The explanatory chapters refer to the same line numbers.",
]

# ---------------------------------------------------------------------------
# Version history.  Each entry: (version, date, one-line summary).
# VERSION_CHANGES[version] is the detailed HTML for that version; the chapter
# shows the history table plus the details of the documented version.
# ---------------------------------------------------------------------------
VERSION_HISTORY = [
    ("3.0", "21 September 2026",
     "Bilingual PT-PT / English interface, FC43/14 Device Identification, "
     "regression suite and first Technical Code Documentation."),
    ("3.1", "23 October 2026",
     "Broadcast/echo-write pairing fixes, USB split-frame reassembly, in-place timeout "
     "marking, Finder attempts and idle-bus check, address-mapped read data, "
     "table-driven CRC and centralised translations."),
    ("3.2", "23 October 2026",
     "Master (poll) tab with one window per Slave / data area, cyclic reads, writes, "
     "16/32-bit data formats and per-window counters; the release ZIP now also "
     "carries this PDF and the documentation tools."),
    ("3.3", "23 October 2026",
     "Renamed from MBSniffer to MBToolkit, with a new high-resolution icon and automatic "
     "migration of preferences and workspaces."),
    ("3.4", "23 October 2026",
     "Slave (simulator) tab: several simulated Slave IDs and data tables answering a real "
     "master, with fault simulation per Slave ID; window grid code shared with the Master."),
]

VERSION_CHANGES = {
    "3.4": """
<p>v3.4 adds the <b>Slave</b> tab: the application answers a real master (PLC, SCADA or
another Modbus Poll) as one or more Modbus RTU devices. See chapter "Slave (simulator)
tab".</p>
<ul>
<li><b>New modules:</b> <code>mb_slave.py</code> (<code>SlaveStore</code>,
<code>handle_request()</code>, <code>SlaveEngine</code>; no widgets),
<code>mb_slave_ui.py</code> (<code>SlaveMixin</code>, <code>SlaveWindow</code>) and
<code>mb_table_ui.py</code> (<code>TableUiMixin</code>: the window header, value table,
drag selection, zebra rows, row menu, scale dialog, grid reflow and Workspace menu shared
by Master and Slave, plus the workspace-file helpers).</li>
<li><b>Master refactor:</b> <code>MasterMixin</code> now uses <code>TableUiMixin</code>;
its behaviour is unchanged. <code>apply_format_to_rows()</code>,
<code>validate_workspace_name()</code>, <code>workspace_path()</code> and
<code>list_workspaces()</code> moved to <code>mb_table_ui.py</code> (which takes the folder);
<code>mb_master_ui.py</code> keeps Master versions bound to the Master folder.</li>
<li><b>Workspace folders:</b> Master workspaces now live in
<code>Workspaces\\Master</code> and Slave workspaces in <code>Workspaces\\Slave</code>;
Master files left directly in <code>Workspaces</code> are moved once.</li>
<li><b>Requests answered:</b> FC01&ndash;06, FC15 and FC16; Exception 01 (function), 02
(address outside the windows) and 03 (quantity / value / byte count); broadcast writes
executed on every covering Slave ID without a response; requests for other IDs
ignored; the RS485 adapter echo removed.</li>
<li><b>Fault simulation per Slave ID:</b> response delay, no response, a chosen
Exception, wrong CRC and a probability per request; an active fault is shown in red in
the header of that Slave's windows.</li>
<li><b>Global busy lock:</b> Sniffer, Finder, Master and Slave never run at the same
time.</li>
<li><b>Workspaces:</b> the Slave has its own Workspace menu (configuration only, values
restart at 0) in <code>%APPDATA%\\MBToolkit\\Workspaces\\Slave</code>;
<code>settings.json</code> gains a validated <code>slave</code> section and the "Slave"
last tab.</li>
<li>The regression suite grew to {tests} tests, including the Master engine talking to the
Slave engine over an in-memory serial link.</li>
</ul>
""",
    "3.3": """
<p>v3.3 renames the product from <b>MBSniffer</b> to <b>MBToolkit</b>: with the Master tab
it is no longer only a sniffer. The application behaves exactly as v3.2; every other
chapter is regenerated from the v3.3 source.</p>
<ul>
<li><b>Name:</b> <code>APP_NAME = "MBToolkit"</code>; launcher <code>MBToolkit.bat</code>,
folder <code>MBToolkit vX.Y</code>, <code>MBToolkit.py</code>, <code>MBToolkit.ico</code>,
<code>MBToolkit.exe</code>, package and PDF names, window title, Help and internal style
names. The "Sniffer" tab keeps its name.</li>
<li><b>Icon:</b> redrawn from shapes by <code>tools/make_icon.py</code>, rendered at 4&times;
and downsampled for every size (16&ndash;256 px); up to 32 px the icon shows the symbol
only so it stays readable on the taskbar.</li>
<li><b>Migration:</b> when <code>%APPDATA%\\MBToolkit</code> does not exist yet,
<code>get_settings_file()</code> copies <code>%APPDATA%\\MBSniffer</code> (settings and
workspaces) once and leaves the old folder untouched. Workspaces saved as
"MBSniffer Master workspace" still open (<code>MASTER_WORKSPACE_FORMATS</code>).</li>
<li><b>Logs:</b> new captures go to "MBToolkit Logs"; older logs stay in
"MBSniffer Logs".</li>
<li>The regression suite grew to {tests} tests (migration and legacy workspace
format).</li>
</ul>
""",
    "3.2": """
<p>v3.2 adds the first phase of a Modbus RTU master in the style of Modbus Poll: a
<b>Master</b> tab with several poll windows, one per Slave or data area. The feature
list was taken from the public Modbus Poll documentation. Every other chapter of this
document is regenerated from the v3.2 source, so the module reference, line numbers,
hashes, tests and Appendix A describe v3.2.</p>
<h2>Master tab (phase 1)</h2>
<ul>
<li><b>New modules:</b> <code>mb_master.py</code> (frames, data formats and
<code>MasterEngine</code>, no widgets) and <code>mb_master_ui.py</code>
(<code>MasterMixin</code>, the tab and its windows). See chapter "Master (poll) tab".</li>
<li><b>Windows:</b> Slave ID, FC01&ndash;FC04, address, quantity, scan rate and default
data format, with Apply (highlighted while fields are not applied), Pause, Read once and
Duplicate; up to 32 windows arranged in a responsive grid or popped out to their own
top-level window. Tables are 3&ndash;15 rows high, with alternating row shading and a thin
1 px frame, and values turn grey while the last read failed.</li>
<li><b>One bus, one request at a time:</b> all windows share one serial port; writes and
"Read once" are served first, then the window whose scan time is due earliest, with the
configured delay between polls (at least t3.5).</li>
<li><b>Data formats:</b> signed/unsigned 16-bit, hex, binary, signed/unsigned/float
32-bit in byte orders ABCD, CDAB, BADC and DCBA, and signed/unsigned/double 64-bit in
ABCDEFGH, GHEFCDAB, BADCFEHG and HGFEDCBA, per window and per address (right-click
menu, with scaling to engineering units, Copy and the address base).</li>
<li><b>Open in Master</b> from the Sniffer Traffic table and the Bus Slave Finder
results, and <b>automatic reconnection</b> when the serial port fails.</li>
<li><b>Writes:</b> FC05/FC15 from coil windows and FC06/FC16 from holding-register
windows, several values separated by ";", broadcast with Slave 0, automatic re-read
after an accepted write.</li>
<li><b>Diagnostics:</b> Tx, error and timeout counters, last response time and last
error (Timeout, Exception, invalid response) per window.</li>
<li><b>Safety:</b> the same confirmation and idle-bus check as Bus Slave Finder; while
connected, Sniffer, Simulation and Finder are locked through the global busy flag.</li>
<li><b>Window header:</b> each window has its own name (Rename), Pop out and a ✕
close button.</li>
<li><b>Workspaces:</b> a Workspace menu saves the connection, windows, formats and
per-address names under a chosen name in <code>%APPDATA%\\MBToolkit\\Workspaces</code>
and lists the saved workspaces to open or delete. The last workspace reopens at
start-up; closing with unsaved changes asks whether to save.</li>
</ul>
<h2>Packaging and documentation</h2>
<ul>
<li>The release ZIP holds the application files, the README files, this PDF and
<code>tools/</code>, and nothing related to git or GitHub, which the user manages.
<code>tools/build_package.py</code> builds it from the working folder.</li>
<li>Because this PDF travels inside the ZIP, the cover quotes a <b>Source snapshot
SHA-256</b> (one hash over every documented file) instead of the ZIP hash.</li>
<li>The regression suite grew from 45 to {tests} tests, including an in-memory Modbus
slave used to test the Master engine.</li>
</ul>
""",
    "3.0": """
<p>First edition of this Technical Code Documentation. It documents the v3.0 package
as released: runtime PT-PT / English language switching, the optional FC43/14 Device
Identification in Bus Slave Finder, the shared Modbus RTU t3.5 helper and the
regression-test suite executed by <code>run_tests.bat</code> and
<code>build_exe.bat</code>.</p>
""",
    "3.1": """
<p>v3.1 implements the fifteen improvements identified in the review of v3.0. Every other
chapter of this document is regenerated from the v3.1 package, so the module reference,
line numbers, hashes, tests and Appendix A describe v3.1.</p>
<h2>Corrections</h2>
<table class="grid">
<colgroup><col style="width:24%"><col style="width:38%"><col></colgroup>
<thead><tr><th>Problem in v3.0</th><th>Effect</th><th>v3.1 behaviour</th></tr></thead>
<tbody>
<tr><td>Broadcast requests (Slave 0) were kept pending.</td><td>Every broadcast write was
later counted as a timeout and inflated the Bus Health timeout rate.</td><td>Slave 0
requests are never pending. <code>SessionMetrics.broadcast_requests</code> counts them and
they are excluded from the timeout-rate denominator.</td></tr>
<tr><td>FC05/06/08/22 frames were typed <code>REQ/RESP</code>.</td><td>Single writes and
diagnostics never counted as requests or responses, had no response time and never timed
out.</td><td><code>SessionMetrics._resolve_echo_direction()</code> makes the frame a
RESPONSE when an older pending request with the same (Slave, FC) exists, the bytes are
identical for exact-echo FCs (05/06/22) and, in RS232 dual RX, the frame arrived on the
opposite channel. Otherwise it is a REQUEST.</td></tr>
<tr><td>Bursts were closed after t3.5 of silence only.</td><td>Above 19200 bit/s
(t3.5 = 1.75 ms) a USB adapter latency timer (FTDI default 16 ms) could split one frame
into two RAW rows.</td><td><code>burst_may_continue()</code> detects a burst ending with
the start of an unfinished known frame; <code>reader_loop()</code> then waits up to
<code>SNIFFER_SPLIT_FRAME_HOLD_MS</code> (40 ms). Frames merged into one burst get the
arrival time of their own read through <code>parse_burst(..., chunk_times)</code>.</td></tr>
<tr><td>Each expired request rebuilt the whole Traffic table.</td><td>Up to 20&nbsp;000
rows (~0.4&nbsp;s on the Tk thread) per timeout; a cyclically polled offline Slave could
freeze the UI.</td><td><code>mark_timed_out_records()</code> retags only the affected
rows through <code>refresh_record_tags()</code>; a full rebuild happens only while the
<code>Timeouts</code> filter is active. The Raw Hex line counter, which counted a literal
backslash-n, now counts real line breaks.</td></tr>
</tbody>
</table>
<h2>New behaviour</h2>
<ul>
<li><b>Bus Slave Finder attempts:</b> 1&ndash;3 attempts per unanswered probe (default 1),
persisted as <code>bus_slave_finder.attempts</code> and included in the duration
estimate.</li>
<li><b>Default minimum timeout 100 ms</b> (was 40 ms). Settings written before v3.1 with the
old automatic 40 ms value migrate to 100 ms.</li>
<li><b>Idle-bus check:</b> before the first transmission the Finder listens for
<code>DISCOVERY_IDLE_CHECK_SECONDS</code> (1 s); any received byte aborts the scan
without transmitting.</li>
<li><b>Address-mapped read data:</b> matched read responses carry
<code>request_pdu_address</code>/<code>request_qty</code>; the Frame Inspector lists
<code>PDU Address=value</code> for every register, coil or input. Traffic Details stay
response-native.</li>
<li><b>FC01/FC02 bits:</b> Details show the bits in address order, grouped per byte and
trimmed to the request quantity.</li>
<li><b>Table-driven CRC:</b> <code>_CRC16_TABLE</code> gives the same CRC 5&ndash;10&times;
faster, which speeds up resynchronisation on noisy buses.</li>
</ul>
<h2>Code organisation and documentation</h2>
<ul>
<li>All inline PT/EN branches were moved into <code>mb_i18n.PT_TO_EN</code> templates used
with <code>SnifferApp.trf()</code>; a regression test rejects new inline branches.</li>
<li>A <code>.gitignore</code> excludes bytecode caches, build output and logs.</li>
<li><code>DEVELOPMENT_NOTES.md</code> now holds only the rules in force; the complete
history moved to <code>CHANGELOG.md</code>.</li>
<li>This PDF is regenerated for every release by <code>tools/build_technical_pdf.py</code>
and always documents the most recent version.</li>
<li>The regression suite grew from 26 to {tests} tests.</li>
</ul>
""",
}

# ---------------------------------------------------------------------------
# Explanatory chapters, in order.  Each entry: (title, html).
# ---------------------------------------------------------------------------
CHAPTERS = [
    ("Architecture", """
<p>MBToolkit uses one Tkinter root object with five behavior mixins. Protocol parsing
and metrics are separated from the GUI, while the active Finder, Master and Slave have
their own worker logic. This is a pragmatic modular architecture rather than a strict MVC/MVVM
framework.</p>
{{diagram:architecture}}
<h2>Composition of SnifferApp</h2>
<p><code>SnifferApp(MasterMixin, SlaveMixin, SlaveFinderMixin, CaptureMixin, ViewMixin,
tk.Tk)</code> composes the application. <code>mb_gui.py</code> constructs and coordinates
the UI; the five mixins supply the Master tab, the Slave tab, active discovery, passive
capture, and presentation/logging behavior. <code>MasterMixin</code> and
<code>SlaveMixin</code> both inherit <code>TableUiMixin</code> from
<code>mb_table_ui.py</code>, which holds their common window-grid widgets.</p>
<h2>Important architectural boundaries</h2>
<ul>
<li><b>Protocol vs UI:</b> CRC, frame recognition, parsing and SessionMetrics are in
<code>mb_protocol.py</code> and have no Tkinter dependency.</li>
<li><b>Workers vs Tk:</b> serial reader/discovery threads communicate through
<code>event_queue</code>; Tk widgets are updated from the main thread.</li>
<li><b>Source history vs presentation:</b> filters and sorting rebuild the view from
<code>_frame_history</code>; they do not modify the raw session record or statistics.</li>
<li><b>Passive vs active:</b> the Sniffer only reads. Bus Slave Finder intentionally
transmits requests and is protected by a safety confirmation/global busy state. The
Master and the Slave transmit too and share the same busy state: only one of Sniffer,
Finder, Master and Slave runs at a time.</li>
<li><b>Appearance vs geometry:</b> Light/Dark changes colors; language changes text; both
are designed not to rebuild widget geometry.</li>
</ul>
{{figure:sniffer}}
"""),
    ("Passive capture pipeline", """
{{diagram:pipeline}}
<ol>
<li><b>Port selection.</b> <code>selected_port_plan()</code> maps RS485/RS232 mode to one or
two receive channels.</li>
<li><b>Serial configuration.</b> <code>serial_config()</code> translates Baud/Data
bits/Parity/Stop bits into pyserial constants.</li>
<li><b>Gap calculation.</b> Automatic mode uses the shared Modbus t3.5 helper; manual mode
validates the user-entered millisecond value.</li>
<li><b>Reader workers.</b> One daemon thread per active receive channel reads bytes,
records the arrival time of every read and closes a burst after the configured silence.
If the burst ends with the start of an unfinished known frame, the reader waits up to
<code>SNIFFER_SPLIT_FRAME_HOLD_MS</code> for the rest (USB latency-timer splits).</li>
<li><b>Parsing.</b> Each burst is split/resynchronised and decoded by
<code>parse_burst()</code>; each frame keeps the arrival time of the read holding its
first byte.</li>
<li><b>Thread boundary.</b> Parsed rows are placed in <code>event_queue</code>.</li>
<li><b>Main-thread processing.</b> <code>process_queue()</code> drains events in batches and
passes frame batches to <code>add_frame_rows_batch()</code>.</li>
<li><b>Metrics/view/log.</b> The view runs SessionMetrics, updates
Traffic/Raw/Inspector/Bus Health and writes complete real traffic to the lazy TXT
log.</li>
</ol>
<div class="callout info"><b>Threading rule.</b> The serial threads do not call Tkinter
methods. The queue is the explicit synchronization boundary between workers and the GUI
thread.</div>
"""),
    ("Frame model and parser behavior", """
<h2>RTU CRC and frame timing</h2>
<p><code>crc16_modbus()</code> implements the Modbus CRC-16 algorithm with a 256-entry
lookup table (<code>_CRC16_TABLE</code>).
<code>append_crc()</code> appends low byte then high byte.
<code>modbus_rtu_interframe_gap_seconds()</code> provides the common t3.5 timing used by
Sniffer and Finder.</p>
<h2>Recognised frame shapes</h2>
<p><code>_candidate_prefixes_at()</code> recognises structural lengths for FC01/02/03/04,
FC05/06/08, FC07, FC15/16, FC22, FC23 and standard Exception frames. Unknown Function
Codes are deliberately handled conservatively.</p>
<h2>Resynchronisation</h2>
<p>The parser first tries a recognised, CRC-valid frame at offset zero. If that fails, it
searches later offsets but only using recognised frame shapes. This is the performance
and false-positive safeguard introduced after the earlier brute-force CRC scan.</p>
<ul>
<li>Known-shape prefix before a recovered valid frame + bad CRC &rarr; <code>CRC ERROR</code>.</li>
<li>Unstructured bytes before a recovered frame &rarr; <code>RAW/UNSYNC</code>.</li>
<li>Known-shape complete remainder + bad CRC &rarr; <code>CRC ERROR</code>.</li>
<li>Unsupported-FC complete remainder with valid CRC &rarr; <code>UNKNOWN / OK</code>.</li>
<li>Otherwise &rarr; <code>RAW/UNPARSED</code>.</li>
</ul>
<h2>Bursts split by USB adapters</h2>
<p><code>burst_may_continue()</code> re-runs the splitter on the burst and inspects only the
final unvalidated segment: if it starts with a plausible Slave ID and a known Function
Code but is shorter than every candidate length, more bytes are expected. The reader
re-checks only when the buffer length changes, so a long noise burst is not re-parsed on
every poll.</p>
<h2>Read-response bits</h2>
<p>FC01/FC02 responses are decoded least-significant bit first by
<code>read_bits_from_response()</code>. <code>read_bits_details()</code> groups the bits per
data byte, shows at most 32 of them in Traffic and trims the padding of the last byte once
the matching request quantity is known.</p>
<h2>Parser row schema</h2>
<table class="grid">
<colgroup><col style="width:28%"><col></colgroup>
<thead><tr><th>Field</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td><code>time</code></td><td>Display timestamp string.</td></tr>
<tr><td><code>channel</code></td><td>BUS, A&rarr;B, B&rarr;A or SIM source.</td></tr>
<tr><td><code>type</code></td><td>REQUEST, RESPONSE, EXCEPTION, RAW/UNSYNC, RAW/UNPARSED,
UNKNOWN or REQ/RESP (FC05/06/08/22, resolved to REQUEST/RESPONSE by
SessionMetrics).</td></tr>
<tr><td><code>slave</code>, <code>fc</code></td><td>Decoded address and hexadecimal Function
Code when available.</td></tr>
<tr><td><code>details</code></td><td>Human-readable protocol details.</td></tr>
<tr><td><code>crc</code></td><td>OK, ERROR or ?.</td></tr>
<tr><td><code>raw</code></td><td>Original frame bytes rendered as hexadecimal.</td></tr>
<tr><td><code>pdu_address</code>, <code>one_based</code>, <code>qty</code></td><td>Addressing/quantity
metadata when decoded.</td></tr>
<tr><td><code>_frame_len</code></td><td>Number of observed bytes represented by the row.</td></tr>
<tr><td><code>_epoch</code></td><td>Floating timestamp used for timing/pairing: arrival
time of the read holding the frame's first byte.</td></tr>
</tbody>
</table>
"""),
    ("Session metrics and Bus Health", """
<p><code>SessionMetrics</code> is stateful per capture/session. It records counters,
pending requests, response samples and diagnostic aggregates before GUI filters are
applied.</p>
<h2>Request/response pairing</h2>
<p>A request key is <code>(Slave ID, base Function Code)</code>. Valid REQUEST rows are
queued FIFO per key. RESPONSE/EXCEPTION rows remove the oldest matching pending request
and compute response time from the two epoch timestamps.</p>
<div class="callout warn"><b>Pairing limitation.</b> Modbus RTU has no transaction
identifier. The implementation therefore uses FIFO matching by Slave and Function Code.
If a non-standard master pipelines multiple same-Slave/same-FC requests without waiting
for responses, pairing cannot be proven uniquely from RTU headers alone.</div>
<h2>Echo-shaped functions</h2>
<p>FC05, FC06, FC08 and FC22 requests and their normal responses have the same length, so
the parser emits <code>REQ/RESP</code>. <code>_resolve_echo_direction()</code> classifies the
frame before accounting: RESPONSE when an older pending request with the same key exists
(identical bytes for the exact-echo FCs 05/06/22; opposite channel in RS232 dual RX),
otherwise REQUEST.</p>
<div class="callout warn"><b>Echo limitation.</b> On a single RS485 channel, if a master
repeats the same write to a Slave that never answers, the repetition is indistinguishable
from an echo response and is paired as one.</div>
<h2>Broadcast</h2>
<p>Requests to Slave 0 are counted as requests and in <code>broadcast_requests</code>, but are
never pending: by definition they receive no response and must not become timeouts.</p>
<h2>Timeouts</h2>
<p>Pending requests older than the configured Pending timeout are expired. The timeout is
attached to the original REQUEST record through its sequence ID; MBToolkit does not
invent a fake timeout frame. The view retags only the affected rows instead of rebuilding
the table.</p>
<h2>Bus Health calculations</h2>
<ul>
<li><b>Request rate:</b> requests divided by observed elapsed session time.</li>
<li><b>Response time:</b> average, minimum, maximum and nearest-rank P95 from valid paired
responses.</li>
<li><b>Slowest Slave:</b> highest average response time among sampled Slaves.</li>
<li><b>Unvalidated bytes:</b> bytes in explicit CRC-error frames plus RAW blocks divided by
all observed bytes.</li>
<li><b>Timeout rate:</b> expired requests / observed non-broadcast requests.</li>
<li><b>Approximate bus utilisation:</b> observed bytes &times; configured serial bits per
character / (baud &times; elapsed time).</li>
<li><b>Exceptions / Slave:</b> counts of Exception responses grouped by Slave ID.</li>
</ul>
<div class="callout warn"><b>Physical-layer boundary.</b> Bus utilisation and
unvalidated-byte percentage are software/capture indicators. The program does not measure
analog RS485 voltage, bias, reflections, ringing, common-mode level or rise/fall
times.</div>
"""),
    ("Active Bus Slave Finder", """
{{figure:finder}}
{{diagram:finder_flow}}
<h2>Discovery semantics</h2>
<p>The standard probe is FC03, Address 0, Quantity 1. A CRC-valid normal response proves
the Slave exists. A CRC-valid Modbus Exception also proves the Slave exists, because the
addressed device had to receive and interpret the request to generate that
Exception.</p>
<p>FC04 fallback is optional and is attempted only after FC03 produces no accepted
response. <b>Attempts</b> (1&ndash;3) repeats each unanswered probe before moving on. Device
Identification is also optional and is performed only after a Slave has already been
found.</p>
<h2>Idle-bus check</h2>
<p>Before the first transmission of a scan, <code>bus_activity_detected()</code> listens for
<code>DISCOVERY_IDLE_CHECK_SECONDS</code> on the first configuration. Any byte, even one framed
at another baud rate, means something else is transmitting: the worker raises an error
naming the port and the first bytes, and nothing is sent. This complements the safety
checkbox.</p>
<h2>FC43/14 Device Identification</h2>
<p>The request uses Function Code 0x2B, MEI type 0x0E and Basic Device Identification read
code 0x01. The parser reads variable-length objects, validates CRC and follows
<code>More Follows</code> pages up to the configured page cap. Display output focuses on
object 0x00 VendorName, 0x01 ProductCode and 0x02 MajorMinorRevision.</p>
<h2>Driver/error handling</h2>
<p>A serial write/read failure is treated as a communication/driver error, not as an
ordinary "Slave did not respond" result. Write timeout recovery can cancel/clear driver
buffers and retry once. Stop requests use <code>threading.Event</code> and best-effort
cancel_read/cancel_write support.</p>
<div class="callout warn"><b>Operational safety.</b> This tab actively transmits Modbus RTU
requests. It must not be run on a bus that already has another active master unless the
system is explicitly designed for multi-master behavior.</div>
"""),
    ("Master (poll) tab", """
{{figure:master}}
{{diagram:master_flow}}
<p>The Master tab reads and writes values as a Modbus RTU master, in the style of Modbus
Poll. Each <b>poll window</b> describes one data area of one Slave; the state of a window
lives in a <code>MasterWindow</code> object, independent of where its pane is shown.</p>
<h2>Scheduling on one bus</h2>
<p>Modbus RTU allows a single request on the bus at a time, so one
<code>MasterEngine</code> thread serves every window over one serial port. Its
<code>next_job()</code> returns, in this order: a queued write, a queued "Read once", or
the enabled window whose next due time is earliest. A window becomes due again
<code>scan_ms</code> after its previous request started (0 polls continuously). After every
transaction the engine leaves the configured delay between polls on the bus, never less
than Modbus t3.5. Response time and the response timeout count from the end of the
transmitted request.</p>
<h2>Frames and responses</h2>
<p><code>build_read_request()</code> and <code>build_write_request()</code> build FC01&ndash;04
and FC05/06/15/16 frames within the Modbus limits (2000 bits / 125 registers per read,
1968 coils / 123 registers per write). <code>find_master_response()</code> scans the received
bytes for the CRC-valid frame of the expected length from the addressed Slave, or a
5-byte exception. Read requests echoed by an RS485 adapter are skipped because their
length and CRC do not fit. Write responses must echo the request (FC05/06) or its
address/quantity (FC15/16). Broadcast writes (Slave 0) are not answered and are reported
as sent.</p>
<h2>Data formats</h2>
<table class="grid">
<colgroup><col style="width:30%"><col></colgroup>
<thead><tr><th>Format</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td>Signed / Unsigned 16-bit</td><td>One register as a two's-complement or unsigned
integer.</td></tr>
<tr><td>Hex / Binary 16-bit</td><td>One register as <code>0xHHHH</code> or two binary
bytes.</td></tr>
<tr><td>Signed / Unsigned / Float 32-bit</td><td>Two registers. Register n carries bytes A B
and register n+1 bytes C D; the order names the value's bytes: ABCD big-endian, CDAB word
swap, BADC byte swap, DCBA little-endian. The value is shown on the first register's
row.</td></tr>
<tr><td>Signed / Unsigned 64-bit, Double</td><td>Four registers (bytes A B, C D, E F, G H):
ABCDEFGH big-endian, GHEFCDAB registers in reverse order, BADCFEHG byte swap, HGFEDCBA
little-endian. Doubles show up to 15 significant digits.</td></tr>
</tbody>
</table>
<h2>Per-address formats</h2>
<p>The window's <b>Format</b> is the default. <code>MasterWindow.formats</code> maps the
PDU address where a value starts to its own format, chosen in the right-click menu for
the selected rows (drag with the mouse, or Ctrl/Shift, for several; ttk has no rubber-band
selection, so <code>TableUiMixin._table_drag_start/move/stop</code> implement it, with
auto-scroll past the table edges). <code>apply_format_to_rows()</code> applies
16-bit formats to every selected row and 32/64-bit formats to consecutive rows in
multiples of 2/4, removing overlapping per-address formats; "Reset to window format"
removes them. <code>register_groups()</code> splits the window into values; a default
multi-register value cut by a per-address format, or running past the window, shows
"&mdash;". The same menu copies the selected rows (also Ctrl+C) as tab-separated text and
sets the address base (0 = PDU Address, 1 = manual numbering).</p>
<h2>Scaling</h2>
<p><code>MasterWindow.scales</code> maps the PDU address where a value starts to a scale
built by <code>validate_scale()</code>: two raw/engineering points, 0&ndash;6 decimals and
a unit. <code>format_window_values()</code> shows scaled values as
<code>e1 + (raw &minus; r1) &times; (e2 &minus; e1) / (r2 &minus; r1)</code> with the unit;
Hex and Binary stay raw. When writing, the typed engineering value is converted back
with <code>raw_text_for_scaled()</code> (rounded for integer formats).</p>
<h2>Open in Master</h2>
<p><code>master_definition_from_record()</code> takes Slave, function, address and
quantity from a Traffic REQUEST or from the request matched to a RESPONSE/EXCEPTION
(FC01&ndash;FC04 only). <code>master_open_definition()</code> creates the window, shows
the Master tab and, when the Master is not connected, copies the port and serial
parameters. The Bus Slave Finder opens a found Slave the same way from its result row
(FC03/FC04, address 0, 10 registers, the baud/parity/stop it answered on).</p>
<h2>Reconnection</h2>
<p>The engine receives a <code>reopen</code> callable. A serial or driver failure during
the session closes the port, posts <code>master_reconnecting</code> and retries every
<code>MASTER_RECONNECT_INTERVAL_SECONDS</code> until the port opens again
(<code>master_reconnected</code>) or the user disconnects; the values turn grey in the
meantime.</p>
<h2>Writing</h2>
<p>Double-clicking a value in an FC01 or FC03 window opens the write dialog.
<code>master_build_write()</code> validates the Slave (0&ndash;247), the address in the
window's base and the values, encodes them with the format of the clicked value and
builds an FC05, FC06, FC15 or FC16 request; 32/64-bit formats require FC16. Several values separated by
";" go to consecutive addresses. An accepted write queues a "Read once" of the window so
the table shows the new value.</p>
<h2>Window life cycle</h2>
<ul>
<li><b>Apply</b> validates the fields and updates the engine; a changed data area resets
the counters. Results of a request sent with the previous definition are ignored.</li>
<li>Each pane has a header with the window name (<b>Rename</b> or double-click),
a summary with the Slave, the function code and name (e.g. FC03 Read Holding Registers), the address and the quantity, <b>Pop out</b> and a <b>✕</b> close button, so
closing never depends on the pane width.</li>
<li><b>Pop out</b> rebuilds the pane inside a <code>tk.Toplevel</code>; closing it or
<b>Dock</b> returns it to the grid. The grid uses as many equal columns as the tab
width allows, measured from the panes' requested width (which grows with Windows
display scaling).</li>
<li>Panes created after start-up receive the application's mouse-wheel guard tag: the
wheel scrolls the window grid and never changes combobox/spinbox values.</li>
<li>The <b>Workspace</b> menu saves named <code>.mbsw</code> files (JSON) with the
connection parameters, every window, its name and address names in
<code>%APPDATA%\\MBToolkit\\Workspaces\\Master</code> (<code>get_master_workspaces_folder()</code>,
which moves workspaces left directly in <code>Workspaces</code> by earlier versions into it
once), beside <code>settings.json</code>; it lists
them to open or delete. Invalid entries are skipped with a warning.</li>
<li>Changes to the open workspace mark it "(modified)". <code>settings.json</code> keeps
<code>master.last_workspace</code>, reopened at start-up without connecting; on exit,
<code>master_confirm_close()</code> asks Yes/No/Cancel only for a saved workspace with
unsaved changes.</li>
</ul>
<div class="callout warn"><b>Operational safety.</b> Like Bus Slave Finder, the Master
transmits. Connecting requires the safety confirmation and an idle-bus check; while it is
connected the global busy flag locks Sniffer, Simulation and Finder.</div>
<div class="callout info"><b>Phase boundary.</b> Logging, conditional colours,
charts, Test Center, FC22/23 and Modbus TCP are planned later phases and are not part of
v{version}.</div>
"""),
    ("Slave (simulator) tab", """
{{figure:slave}}
{{diagram:slave_flow}}
<p>The Slave tab is the inverse of the Master: the application behaves as one or more
Modbus RTU devices, listens on a COM port and answers the requests of a real master. Each
window is one data table (Coils, Discrete Inputs, Holding Registers or Input Registers) of
one simulated Slave ID, defined by a start address and a quantity (up to 2000). Its state
lives in a <code>SlaveWindow</code>.</p>
<h2>Data store</h2>
<p><code>SlaveStore</code> keeps the values per (Slave ID, table) and address, starting
at 0, plus the set of addresses defined by the windows (<code>set_areas()</code>, called
whenever a window is added, applied or closed) and the active fault of each Slave ID. It
is guarded by a lock: the engine thread reads and writes while the GUI edits. Windows
over the same addresses therefore show the same values.</p>
<h2>Answering one request</h2>
<p><code>handle_request(store, frame)</code> executes one CRC-valid request like a real
device:</p>
<ul>
<li>a Slave ID that is not simulated is <code>ignored</code> (no reply);</li>
<li>an unsupported function gets Exception 01; a wrong length, a quantity outside the
Modbus limits, an FC05 value other than FF00/0000 or a byte count that does not match
gets Exception 03;</li>
<li>addresses not entirely inside the defined areas get Exception 02;</li>
<li>reads return the stored bits or registers; writes store the values and answer with
the echo (FC05/06) or the address/quantity (FC15/16), listing the written ranges in
<code>SlaveReply.written</code>;</li>
<li>broadcast (Slave 0) writes are executed on every simulated Slave ID whose areas cover
the addresses and are never answered.</li>
</ul>
<h2>Serial loop</h2>
<p><code>SlaveEngine</code> reads the port continuously. <code>request_length()</code>
knows the size of FC01&ndash;06 (8 bytes) and FC15/16 (9 + byte count) requests, so a
request is answered as soon as it is complete and CRC-valid. Bytes that do not form a
request (other devices' responses, noise) are dropped one at a time until a request lines
up; after <code>SLAVE_RESYNC_SILENCE_MS</code> of silence the rest of the buffer is
resolved, and a CRC-valid frame of an unknown function gets Exception 01. Before
replying the engine waits the Modbus t3.5 gap; after replying it expects the RS485 adapter
echo of its own response and removes it from the received bytes. Each handled request
is posted as <code>slave_request</code> with its Slave ID, table, address, quantity,
status and written ranges. Serial failures reopen the port like the Master.</p>
<h2>Fault simulation</h2>
<p>Faults are set per Slave ID (a real device fails on all its tables) and validated by
<code>validate_fault()</code>: delay (0&ndash;10000 ms), no response, a chosen Exception
(01, 02, 03, 04 or 06), wrong CRC, and a probability (1&ndash;100 %) drawn for every
request. When the fault triggers, no response wins over the Exception, which wins over
executing the request; the wrong CRC and the delay apply to whatever is sent. Only active
faults are stored; their description is shown in red in the header of every window of
that Slave ID.</p>
<h2>Windows and values</h2>
<ul>
<li>Double-clicking a value edits it locally: bits toggle; registers use the value's
format and scale (<code>slave_set_value()</code>). Nothing is sent on the bus.</li>
<li>Master writes highlight the written rows for <code>SLAVE_HIGHLIGHT_SECONDS</code>
(the <code>written</code> tag replaces the zebra tag so it is always visible); a
250&nbsp;ms timer removes expired highlights.</li>
<li>Each window counts the requests and exceptions that touched its addresses and shows
the last request; the connection bar counts requests, responses, exceptions, broadcasts
and requests for other IDs.</li>
<li>The Table field and the window header show the read function code with the table
name (<code>table_choice_label()</code>: "03 Holding Registers"), like the FC field of
the Master.</li>
<li>Formats, scales, names, Copy, address base, drag selection, Rename, Pop out and
close come from <code>TableUiMixin</code>, exactly as in the Master.</li>
<li>The Slave Workspace menu saves configuration only (connection, windows, names,
formats, scales and faults) in <code>%APPDATA%\\MBToolkit\\Workspaces\\Slave</code>,
format <code>MBToolkit Slave workspace</code>; opening one resets the values to 0.
<code>slave.last_workspace</code> is reopened at start-up and
<code>slave_confirm_close()</code> asks to save a changed one on exit.</li>
</ul>
<div class="callout warn"><b>Operational safety.</b> A simulated Slave ID that also
exists on the bus makes two devices answer the same request. Connecting requires a
confirmation that no real device uses the simulated IDs; while listening, the global busy
flag locks Sniffer, Simulation, Finder and Master. Windows and USB adapters usually add a
few milliseconds to every response.</div>
"""),
    ("UI, language and theme design", """
{{diagram:lifecycle}}
<h2>Canonical-language strategy</h2>
<p>Portuguese (Portugal) is the canonical static UI language.
<code>canonical_ui_text()</code> can map known English captions back to PT-PT, then
<code>translate_text()</code> renders either canonical Portuguese or an explicit English
translation. Technical English terms without an explicit mapping are left
unchanged.</p>
<p>Messages with live values are stored as PT-PT templates in <code>PT_TO_EN</code> and
rendered with <code>SnifferApp.trf(template, **values)</code>. Code never branches on
<code>current_language</code>; a regression test enforces this.</p>
<h2>Runtime language changes</h2>
<p><code>apply_language()</code> updates widget text, table headings, context menus, Help
content and live status strings. Protocol bytes and parser data are not translated; only
presentation fragments such as <code>Registos</code>/<code>Registers</code> are changed.</p>
<h2>Language-independent geometry</h2>
<p>The UI is built using the canonical Portuguese captions, then
<code>_freeze_language_layout_geometry()</code> measures key dimensions and freezes them.
This prevents shorter/longer English captions from moving the surrounding rectangles or
controls.</p>
<h2>Light/Dark invariant</h2>
<p>The application uses one ttk <code>clam</code> construction. <code>mb_theme.py</code>
configures geometry once and palette functions only change colors/state maps. Custom
Canvas widgets receive palette updates separately.</p>
<h2>Mouse-wheel behavior</h2>
<p>An application bindtag lets Treeviews/Text/Listboxes/scrollbars consume wheel events
normally while stopping wheel propagation elsewhere. This preserves table scrolling
without allowing the Notebook to change tabs with the wheel.</p>
"""),
    ("Persistence, logs and export", """
<h2>User settings</h2>
<p>On Windows, preferences are stored in <code>%APPDATA%\\MBToolkit\\settings.json</code>.
Loading is defensive and every persisted choice/range is validated before use. Saves use
a temporary file and replace operation.</p>
<p>Persisted data includes language, Light/Dark, last main tab, serial format, frame-gap
mode/value, Pending timeout, auto-scroll, transaction separators, highlighting and Finder
options (including attempts and the minimum timeout, migrated from the old 40&nbsp;ms
default to 100&nbsp;ms) and the Master and Slave connection parameters. Master and Slave
windows are not part of the settings: they are saved explicitly in workspace files. COM names, window geometry, traffic/results and the Finder safety confirmation
are intentionally not persisted.</p>
<h2>TXT capture log</h2>
<p>Real-capture logs are lazy: the file is created only when traffic actually arrives.
The disk log is complete and independent of table filters, sorting and the bounded GUI
history.</p>
<h2>CSV export</h2>
<p>CSV exports the records currently retained in <code>_frame_history</code>, not
necessarily an arbitrarily long complete session. It includes timing, channel, type,
address metadata, CRC, raw bytes, timeout status and anomaly classification.</p>
<h2>Bounded GUI history</h2>
<p>The UI retains up to approximately <code>MAX_UI_FRAMES = 20000</code> records and prunes
in chunks after a hysteresis threshold. Raw Text has a similar bounded-line policy. This
prevents the GUI from growing indefinitely while keeping the capture log complete.</p>
"""),
]

# Chapter placed after the build chapter.
BOUNDARIES_CHAPTER = ("Known boundaries and extension points", """
<h2>What the current v{version} does not implement</h2>
<ul>
<li>No Modbus TCP transport.</li>
<li>Master tab: no data logging, conditional colours, charts, Test Center, FC22/23 or
OLE-style automation.</li>
<li>Slave tab is phase 1: no FC08/FC22/FC23/FC43, no automatically changing values
(counters, ramps), no traffic view of its own and no Modbus TCP server.</li>
<li>No passive Ethernet packet capture.</li>
<li>No analog RS485 electrical measurement.</li>
</ul>
<h2>Current parser scope</h2>
<p>Known frame-shape recognition covers the Function Codes encoded in
<code>_candidate_prefixes_at()</code>. An unsupported FC can only be accepted
conservatively as <code>UNKNOWN / OK</code> when it occupies the complete remaining burst
and has a valid CRC. This intentionally favors resynchronisation reliability over
aggressive guessing.</p>
<h2>Natural refactoring seams</h2>
<ul>
<li><b>Transport abstraction:</b> <code>mb_protocol.py</code> is already mostly
transport-independent above RTU framing, making it the natural starting point for a
future shared Modbus PDU core.</li>
<li><b>Active client engine:</b> the Finder already contains robust serial
request/write/read/timeout primitives that could inform a future general Master engine,
but the thesis-quality design should separate those primitives from the Finder UI.</li>
<li><b>Server simulator:</b> <code>handle_request()</code> is transport-independent;
a Modbus TCP server would only need a new loop around it.</li>
<li><b>Testing:</b> the existing hardware-independent regression suite is a strong base;
future transport/client/server work should extend the same pattern.</li>
</ul>
<div class="callout info"><b>Documentation intent.</b> These are architectural extension
points inferred from the current code structure, not features claimed to exist in
v{version}.</div>
""")

FIGURE_CAPTIONS = {
    "sniffer": "Current Sniffer UI generated from the documented source snapshot.",
    "finder": "Current active Finder UI generated from the documented source.",
    "master": "Master tab connected to the in-memory test slave of tests/test_master.py.",
    "slave": "Slave tab answering a Master engine over the in-memory link of tests/test_slave.py.",
}

BAT_DESCRIPTIONS = {
    "MBToolkit.bat": [
        "Sets the expected versioned source folder and verifies that MBToolkit.py exists.",
        "Detects Python 3 through py -3, python on PATH, or standard Python 3.13 install "
        "locations.",
        "If Python is absent and WinGet exists, attempts a silent per-user Python 3.13 "
        "installation.",
        "Verifies tkinter; if missing, attempts a Python repair/reinstall.",
        "Verifies pyserial and installs it with pip/ensurepip when required.",
        "Prefers pythonw.exe so the GUI opens without a console window, with python as "
        "fallback.",
    ],
    "build_exe.bat": [
        "Normalizes application/distribution paths and finds Python 3.",
        "Installs/upgrades pyserial and PyInstaller.",
        "Runs the complete regression suite before building; any failure cancels the build.",
        "Cleans prior build/spec/output artifacts.",
        "Creates a one-file, windowed MBToolkit.exe with the icon embedded when available.",
    ],
    "run_tests.bat": [
        "Finds a Python 3 interpreter.",
        "Runs unittest discovery for tests/test_*.py in verbose mode.",
        "Returns a non-zero exit code and explicit warning when tests fail, so a release "
        "should not proceed.",
    ],
}

# ---------------------------------------------------------------------------
# Diagrams.  Coordinates are node centres in an abstract canvas (width x
# height).  Node styles: plain, primary, launcher, tests, protocol, physical,
# settings.  Edge options: label, dashed, both (arrow at both ends), bend
# (perpendicular offset of a single curve), via (list of waypoints).
# ---------------------------------------------------------------------------
DIAGRAMS = {
    "architecture": {
        "caption": "Module dependency and responsibility overview.",
        "size": (1060, 477),
        "max_width_pct": 100,
        "nodes": {
            "launcher": (784, 40, "MBToolkit.py\nlauncher", "launcher"),
            "gui": (784, 117, "mb_gui.py\nSnifferApp / UI composition", "primary"),
            "tests": (233, 117, "tests/test_regression.py\n{tests} regression tests", "tests"),
            "capture": (233, 193, "mb_capture.py\nCaptureMixin", "plain"),
            "view": (647, 193, "mb_view.py\nViewMixin", "plain"),
            "theme": (941, 193, "mb_theme.py\nfixed geometry + palette", "plain"),
            "finder": (210, 280, "mb_slave_finder.py\nSlaveFinderMixin", "plain"),
            "diag": (510, 280, "mb_diagnostics.py\nInspector + anomaly semantics", "plain"),
            "proto": (108, 357, "mb_protocol.py\nRTU parser + SessionMetrics", "protocol"),
            "widgets": (315, 357, "mb_widgets.py\nRefreshButton + ToggleSwitch", "plain"),
            "config": (550, 357, "mb_config.py\nconstants + settings + paths", "plain"),
            "i18n": (754, 357, "mb_i18n.py\nPT-PT / English", "plain"),
            "master_ui": (941, 280, "mb_master_ui.py\nMasterMixin", "plain"),
            "master": (960, 357, "mb_master.py\nMasterEngine + formats", "protocol"),
            "table_ui": (735, 437, "mb_table_ui.py\nTableUiMixin (shared)", "plain"),
            "slave_ui": (430, 437, "mb_slave_ui.py\nSlaveMixin", "plain"),
            "slave": (150, 437, "mb_slave.py\nSlaveStore + SlaveEngine", "protocol"),
        },
        "edges": [
            ("launcher", "gui", {}),
            ("gui", "capture", {"bend": -18}),
            ("gui", "finder", {"bend": -40}),
            ("gui", "view", {}),
            ("gui", "theme", {}),
            ("gui", "widgets", {"bend": -40}),
            ("gui", "config", {"bend": 30}),
            ("gui", "i18n", {"via": [(1030, 230)]}),
            ("gui", "master_ui", {"bend": 20}),
            ("master_ui", "master", {}),
            ("master_ui", "table_ui", {"bend": 20}),
            ("slave_ui", "table_ui", {}),
            ("slave_ui", "slave", {}),
            ("gui", "slave_ui", {"bend": 30}),
            ("tests", "capture", {"dashed": True}),
            ("tests", "finder", {"dashed": True, "bend": 20}),
            ("tests", "proto", {"dashed": True, "bend": 25}),
            ("tests", "diag", {"dashed": True}),
            ("tests", "i18n", {"dashed": True, "via": [(640, 135), (745, 200)]}),
            ("capture", "proto", {"bend": 15}),
            ("capture", "finder", {"label": "cancel I/O"}),
            ("view", "proto", {"bend": 10}),
            ("view", "diag", {}),
            ("view", "config", {"bend": -12}),
            ("view", "i18n", {}),
            ("finder", "proto", {}),
            ("finder", "widgets", {}),
            ("finder", "config", {}),
            ("diag", "proto", {}),
            ("diag", "config", {}),
            ("diag", "i18n", {}),
        ],
    },
    "pipeline": {
        "caption": "From physical bytes to UI records and disk logging.",
        "size": (1270, 137),
        "max_width_pct": 100,
        "nodes": {
            "phys": (64, 68, "RS485 / RS232\nphysical traffic", "physical"),
            "pyserial": (184, 68, "pyserial\nCOM handle", "plain"),
            "reader": (300, 68, "reader_loop()\nworker thread", "plain"),
            "burst": (443, 68, "Burst buffer\ngap + split-frame hold", "plain"),
            "parse": (588, 68, "parse_burst()\nsplit + decode", "plain"),
            "queue": (708, 68, "event_queue\n('frame', row)", "plain"),
            "process": (834, 68, "process_queue()\nTk main thread", "plain"),
            "batch": (989, 68, "add_frame_rows_batch()\nTraffic / Raw / Inspector", "plain"),
            "metrics": (1172, 36, "SessionMetrics.process()\npairing + timing + counters", "plain"),
            "log": (1172, 101, "TXT log\ncomplete real traffic", "protocol"),
        },
        "edges": [
            ("phys", "pyserial", {}), ("pyserial", "reader", {}), ("reader", "burst", {}),
            ("burst", "parse", {}), ("parse", "queue", {}), ("queue", "process", {}),
            ("process", "batch", {}), ("batch", "metrics", {"both": True}),
            ("batch", "log", {}),
        ],
    },
    "finder_flow": {
        "caption": "Discovery flow for each selected configuration and Slave ID.",
        "size": (520, 694),
        "max_width_pct": 64,
        "edge_color": "#475569",
        "nodes": {
            "start": (363, 36, "Start scan\nvalidate safety + options", "launcher"),
            "config": (363, 106, "For each configuration\n(1st: listen 1 s, abort on traffic)", "plain"),
            "slave": (363, 176, "For each selected Slave ID", "plain"),
            "tx": (225, 261, "Transmit FC03\nAddress 0 / Qty 1 (x attempts)", "plain"),
            "close": (430, 261, "Close serial handle\nfinish UI", "plain"),
            "crc": (225, 331, "CRC-valid response or Exception?", "plain"),
            "fc04": (325, 417, "Optional FC04 fallback", "plain"),
            "found": (216, 502, "Slave found", "protocol"),
            "devid": (100, 588, "Optional FC43/14\nBasic Device Identification", "plain"),
            "queue": (283, 658, "Queue result/progress event", "plain"),
        },
        "edges": [
            ("start", "config", {}), ("config", "slave", {}), ("slave", "tx", {}),
            ("slave", "close", {"dashed": True, "label": "all done"}),
            ("tx", "crc", {}),
            ("crc", "found", {"label": "yes", "bend": 8}),
            ("crc", "fc04", {"label": "no + fallback"}),
            ("fc04", "found", {"label": "response", "bend": 10}),
            ("fc04", "queue", {"label": "no response", "bend": -18}),
            ("found", "devid", {"label": "enabled", "bend": 8}),
            ("found", "queue", {"label": "disabled", "bend": 8}),
            ("devid", "queue", {}),
            ("queue", "slave", {"dashed": True, "label": "next", "via": [(462, 610), (462, 230)]}),
        ],
    },
    "master_flow": {
        "caption": "Master engine: one request at a time over one serial port.",
        "size": (1000, 290),
        "max_width_pct": 100,
        "edge_color": "#475569",
        "nodes": {
            "connect": (120, 40, "Connect\nsafety + idle-bus check", "launcher"),
            "windows": (120, 135, "Poll windows\nSlave / FC / address / qty / scan", "plain"),
            "writes": (120, 230, "Write dialog / Read once\npriority queue", "plain"),
            "next": (450, 135, "next_job()\nwrite > read once > earliest due", "primary"),
            "tx": (720, 60, "transact()\nsend request, wait response", "plain"),
            "match": (720, 210, "find_master_response()\nCRC + length + Slave/FC", "protocol"),
            "queue": (910, 135, "event_queue\nmaster_result", "plain"),
        },
        "edges": [
            ("connect", "windows", {}),
            ("windows", "next", {"label": "set_poll"}),
            ("writes", "next", {"label": "queue_write"}),
            ("next", "tx", {}),
            ("tx", "match", {}),
            ("match", "queue", {}),
            ("queue", "next", {"dashed": True, "label": "delay >= t3.5", "via": [(910, 275), (450, 275)]}),
        ],
    },
    "slave_flow": {
        "caption": "Slave engine: assemble a request, answer it from the store, apply faults.",
        "size": (1000, 260),
        "max_width_pct": 100,
        "edge_color": "#475569",
        "nodes": {
            "rx": (110, 60, "Serial bytes\nminus own RS485 echo", "physical"),
            "frame": (110, 190, "request_length() + CRC\ndrop noise / other frames", "plain"),
            "fault": (420, 60, "Fault of Slave ID?\nprobability per request", "plain"),
            "handle": (420, 190, "handle_request()\nSlaveStore read / write", "primary"),
            "reply": (740, 125, "wait t3.5 (+ delay)\nwrite response", "plain"),
            "queue": (920, 125, "event_queue\nslave_request", "plain"),
        },
        "edges": [
            ("rx", "frame", {}),
            ("frame", "fault", {"label": "request"}),
            ("fault", "handle", {"label": "execute"}),
            ("fault", "reply", {"label": "fault reply"}),
            ("handle", "reply", {"label": "response"}),
            ("reply", "queue", {}),
        ],
    },
    "lifecycle": {
        "caption": "Settings, language and theme lifecycle.",
        "size": (871, 179),
        "max_width_pct": 100,
        "edge_color": "#475569",
        "nodes": {
            "settings": (115, 142, "%APPDATA%\\MBToolkit\\settings.json", "settings"),
            "load": (301, 108, "load_ui_settings()\nvalidate + migrate", "plain"),
            "init": (462, 108, "SnifferApp.__init__\nbuild canonical PT layout", "plain"),
            "lang": (618, 36, "apply_language()\ntext only", "plain"),
            "theme": (618, 108, "apply_theme()\ncolors only", "plain"),
            "save": (775, 108, "save_current_ui_settings()", "plain"),
        },
        "edges": [
            ("settings", "load", {}), ("load", "init", {}), ("init", "lang", {}),
            ("init", "theme", {}), ("lang", "save", {}), ("theme", "save", {}),
            ("save", "settings", {"via": [(660, 150), (420, 165)]}),
        ],
    },
}

# Module chapter introductions: <b>lead sentence.</b> followed by detail.  The lead
# sentence (without markup) is also the 'Primary responsibility' in the source inventory.
MODULE_INTROS = {'MBToolkit.py': '<b>Application launcher and top-level entry point.</b> It sets the '
                 'development simulation switch before importing the GUI, applies the '
                 "Windows application identity, creates SnifferApp and enters Tkinter's "
                 'main event loop.',
 'mb_config.py': '<b>Central configuration, constants, user settings validation and '
                 'filesystem paths.</b> It defines versioned application constants, '
                 'discovery limits, GUI history limits, Modbus exception metadata, '
                 'persistent settings behavior, application/log directories and '
                 'PyInstaller resource lookup.',
 'mb_protocol.py': '<b>Protocol engine for passive Modbus RTU parsing and session '
                   'metrics.</b> It implements CRC16, RTU t3.5 timing, frame-shape '
                   'recognition, resynchronisation, decoding, request/response pairing, '
                   'timeout accounting, echo-write and broadcast classification, '
                   'split-frame detection, Bus Health metrics and debug traffic generation.',
 'mb_capture.py': '<b>Serial-port management and passive acquisition pipeline.</b> It '
                  'opens selected COM ports, starts reader threads, converts inter-frame '
                  'silence into capture bursts, parses those bursts, queues GUI events, '
                  'controls simulation, handles COM restart and performs orderly shutdown.',
 'mb_diagnostics.py': '<b>Presentation-oriented diagnostics derived from captured '
                      'records.</b> It maps Function Codes to names, recalculates/display '
                      'CRC fields, extracts payloads, classifies anomalies/results and '
                      'builds the structured Frame Inspector text.',
 'mb_view.py': '<b>Traffic view, filtering, sorting, Frame Inspector, Bus Health updates, '
               'CSV export and TXT logging.</b> It owns the bounded in-memory frame '
               'history, converts parser rows into richer view records, pairs display '
               'state with SessionMetrics, maintains table/raw views and keeps the real '
               'capture log independent from GUI filtering.',
 'mb_slave_finder.py': '<b>Active Modbus RTU Slave discovery and Device '
                       'Identification.</b> It checks that the bus is idle, builds safe '
                       'read-only FC03/FC04 probes with configurable attempts, '
                       'calculates adaptive timeouts, performs robust serial writes/reads, '
                       'accepts normal or CRC-valid Exception responses as proof of a '
                       'Slave, optionally reads FC43/14 Basic Device Identification and '
                       'drives the Finder UI through queued events.',
 'mb_i18n.py': '<b>Runtime Portuguese/English translation layer.</b> Portuguese (Portugal) '
               'is the canonical UI text. Static translations, runtime-status patterns, '
               'protocol-detail fragments and the complete English Help content are kept '
               'separate from protocol logic so switching language affects presentation '
               'only.',
 'mb_theme.py': '<b>Fixed-geometry Light/Dark theme implementation.</b> It configures a '
                'single ttk clam layout once, installs stable checkbox geometry and '
                'changes only palette values at runtime. This is deliberately designed so '
                'theme switching does not move or resize controls.',
 'mb_widgets.py': '<b>Custom reusable Tkinter widgets.</b> RefreshButton draws a stable '
                  'square refresh control on a Canvas; ToggleSwitch draws the Light/Dark '
                  'switch. Both implement their own state, hover/press behavior and '
                  'palette updates.',
 'mb_gui.py': '<b>Main application composition and global UI behavior.</b> SnifferApp '
              'combines MasterMixin, SlaveFinderMixin, CaptureMixin and ViewMixin with tk.Tk. It '
              'creates all widgets, initializes state, freezes language-independent '
              'geometry, performs runtime translation, manages theme/language persistence, '
              'prevents mouse-wheel tab switching and keeps Bus Health content responsive.',
 'mb_master.py': '<b>Modbus RTU master engine, frames and data formats.</b> It builds '
                 'FC01-04 read and FC05/06/15/16 write requests, matches responses and '
                 'exceptions, converts registers to and from 16/32-bit formats in four byte '
                 'orders and runs MasterEngine, which serves every poll window over one '
                 'serial port one request at a time. It contains no widgets.',
 'mb_master_ui.py': '<b>Master (poll) tab user interface.</b> MasterMixin builds the '
                    'connection bar and the grid of poll windows, validates window '
                    'definitions, renders values and counters, opens the write and name '
                    'dialogs, pops windows out to their own top-level windows and saves or '
                    'opens workspace files.',
 'mb_slave.py': '<b>Modbus RTU slave (simulator) engine.</b> SlaveStore keeps the data '
                'tables, defined areas and faults of every simulated Slave ID; '
                'handle_request() executes one request like a real device (reads, writes, '
                'Exceptions 01/02/03, broadcast); SlaveEngine assembles requests from the '
                'serial bytes, applies the fault simulation, answers after t3.5 and removes '
                'the adapter echo. It contains no widgets.',
 'mb_slave_ui.py': '<b>Slave (simulator) tab user interface.</b> SlaveMixin builds the '
                   'connection bar and the grid of simulated tables, edits values locally, '
                   'highlights master writes, shows per-window and global counters, edits '
                   'the faults of each Slave ID and saves or opens Slave workspaces.',
 'mb_table_ui.py': '<b>Window-grid code shared by the Master and Slave tabs.</b> '
                   'TableUiMixin builds the window header, the value table with drag '
                   'selection, zebra rows and frame, the right-click menu, the scale and '
                   'text dialogs, the grid reflow and the Workspace menu; module helpers '
                   'validate workspace names and list workspace files.',
 'tests/test_slave.py': '<b>Slave regression tests.</b> Requests and replies are checked '
                        'against the store, and the real Master and Slave engines talk over '
                        'an in-memory serial link, with adapter echo, foreign traffic, split '
                        'and garbled requests and every fault type.',
 'tests/test_master.py': '<b>Master regression tests.</b> An in-memory Modbus slave behind '
                         'a fake serial port answers reads and writes, so the tests cover '
                         'data formats, frames from the Modbus specification, response '
                         'matching, scheduling, writes, broadcast, timeouts, the idle-bus '
                         'check and workspace validation without hardware.',
 'tests/test_regression.py': '<b>Automated regression suite.</b> The tests protect RTU '
                             'timing, parser/resynchronisation behavior, pairing/timeouts, '
                             'broadcast and echo-write classification, split-frame '
                             'reassembly, in-place timeout marking, Slave Finder attempts, '
                             'idle-bus check and FC43/14 logic, plus reversible '
                             'Portuguese/English translation. Fake serial classes keep the '
                             'tests deterministic and hardware-independent.'}

# 'Detailed behavior of the key paths' cards: (callable, text).  Methods may be
# written as 'Class.method' or just 'method'.
KEY_PATH_DETAILS = {'mb_config.py': [('load_ui_settings',
                   'Reads settings.json defensively and validates every persisted '
                   'choice/range. Invalid/corrupt data falls back safely. It also migrates '
                   'the older highlight_anomalies key to highlight_results and the old '
                   '40 ms Finder timeout default to 100 ms.'),
                  ('save_ui_settings',
                   'Merges updates with validated current settings and uses a temporary '
                   'file plus replace operation for atomic persistence; settings failures '
                   'never prevent normal application use.'),
                  ('get_application_directory',
                   'Resolves a user-facing application directory consistently for '
                   'PyInstaller EXE, packaged BAT/source mode and development mode.'),
                  ('get_logs_folder',
                   'Creates and returns the MBToolkit Logs directory beside the '
                   'launcher/EXE.')],
 'mb_protocol.py': [('crc16_modbus',
                     'Computes the standard Modbus CRC-16 value (initial 0xFFFF, reflected '
                     'polynomial 0xA001) with one lookup in the precomputed 256-entry '
                     '_CRC16_TABLE per byte. append_crc() stores the low CRC byte first, '
                     'matching Modbus RTU wire order.'),
                    ('modbus_rtu_interframe_gap_seconds',
                     'Implements the automatic t3.5 rule used by capture and discovery: '
                     '3.5 character times at or below 19200 bit/s, fixed 1.750 ms above '
                     '19200 bit/s.'),
                    ('_candidate_prefixes_at',
                     'Infers only structurally plausible lengths for supported Modbus '
                     'frame shapes. This constrains resynchronisation and avoids the '
                     'former brute-force CRC scan across arbitrary lengths.'),
                    ('split_capture_buffer',
                     'Walks a burst from left to right. A valid recognised frame is '
                     'emitted immediately; otherwise the parser searches later offsets for '
                     'a recognised CRC-valid frame. Bytes before the recovered frame '
                     'become CRC ERROR if they exactly match a known frame shape, '
                     'otherwise RAW/UNSYNC. If nothing can be recovered, the remainder '
                     'becomes CRC ERROR, UNKNOWN/OK, or RAW/UNPARSED depending on its '
                     'structure and CRC.'),
                    ('burst_may_continue',
                     'Reports whether a burst ends with the start of a known frame that '
                     'has not fully arrived yet, so the reader can wait for bytes delayed '
                     'by a USB adapter latency timer instead of emitting two RAW rows.'),
                    ('read_bits_details',
                     'Formats FC01/FC02 response bits in address order, grouped per data '
                     'byte, trimmed to the request quantity when known and capped at 32 '
                     'visible bits.'),
                    ('decode_frame',
                     'Extracts Slave, FC, PDU address, one-based address, quantity and '
                     'selected payload details from a split frame. It handles Exceptions '
                     'and common read/write Function Codes without modifying the raw '
                     'bytes.'),
                    ('parse_burst',
                     'Transforms split frames into the row dictionary consumed by the rest '
                     'of the program. It attaches display time, channel, decoded fields, '
                     'raw hex, frame length and a floating epoch timestamp; with '
                     'chunk_times each frame gets the arrival time of its own serial '
                     'read.'),
                    ('SessionMetrics.process',
                     'This is the session accounting hot path. It expires old pending '
                     'requests first, resolves REQ/RESP frames, updates byte/counter '
                     'statistics, stores valid non-broadcast requests by (Slave, FC), '
                     'FIFO-pairs responses/exceptions to pending requests, calculates '
                     'response time and returns timing/pairing information to the view.'),
                    ('SessionMetrics._resolve_echo_direction',
                     'Classifies FC05/06/08/22 frames as REQUEST or RESPONSE from the '
                     'pending queue: same key, identical bytes for exact echoes and the '
                     'opposite channel in RS232 dual RX. Broadcast frames are always '
                     'requests.'),
                    ('SessionMetrics.health_summary',
                     'Builds the Bus Health model: request rate, response '
                     'average/min/max/P95, slowest Slave, unvalidated-byte rate, timeout '
                     'rate, active Slave count, approximate bus utilisation and exception '
                     'distribution.'),
                    ('build_anomaly_simulation_plan',
                     'Creates the deterministic categories required to preview diagnostic '
                     'highlighting: normal response, slow response, Exception, bad CRC, '
                     'timeout and RAW bytes.')],
 'mb_capture.py': [('selected_port_plan',
                    'Translates physical mode into one or two receive channels. RS485 and '
                    'single-RX RS232 use COM A; dual-RX RS232 requires distinct COM A and '
                    'COM B and labels their directions A→B/B→A.'),
                   ('calculated_gap_ms',
                    'Returns the manual gap after validation, or computes the automatic '
                    'RTU t3.5 value from baud/data/parity/stop settings using the shared '
                    'protocol timing helper.'),
                   ('start_capture',
                    'Validates state and serial settings, opens the selected port(s), '
                    'resets the current session, prepares lazy logging, starts reader '
                    'workers and updates the GUI to capturing state.'),
                   ('reader_loop',
                    'Runs in a daemon thread per capture channel. It accumulates serial '
                    'bytes and their read times into a burst, considers the burst '
                    'complete after the configured inter-frame silence (or after the '
                    'split-frame hold when the burst ends mid-frame), then calls '
                    'parse_burst() and posts frame events to the GUI queue.'),
                   ('run_simulation',
                    'Runs the internal diagnostic scenario without opening serial '
                    'hardware. It feeds the same parser/event path used by real capture, '
                    'including forced timeout handling.'),
                   ('process_queue',
                    'Main-thread bridge between workers and Tkinter. It drains events in '
                    'bounded batches, batches frame insertions for performance, handles '
                    'capture/discovery status events, expires requests and reschedules '
                    'itself with a faster cadence when backlog exists.'),
                   ('on_close',
                    'Performs defensive shutdown: saves settings, signals all workers, '
                    'cancels serial I/O, joins threads with timeouts, closes serial '
                    'handles/logs and destroys the Tk root.')],
 'mb_diagnostics.py': [('anomaly_kind',
                        'Classifies a record with explicit priority: bad CRC, timeout, '
                        'Exception, RAW, then slow response. The priority prevents '
                        'conflicting colors/results.'),
                       ('result_info',
                        'Turns the anomaly/pairing state into a semantic result key, '
                        'user-facing label and color name. Successful completed pairs are '
                        'distinguished from pending requests.'),
                       ('inspector_values',
                        'Builds every Frame Inspector field, including recalculated CRC '
                        'received/calculated values, decoded payload, timeout suffix and '
                        'translated result text.'),
                       ('decoded_record_text',
                        'Serialises the same Frame Inspector information into '
                        'newline-separated text for the copy-decoded-frame context '
                        'command.')],
 'mb_view.py': [('update_stats_labels',
                 'Converts SessionMetrics into both compact session counters and Bus '
                 'Health values. It recalculates health using the currently configured '
                 'serial parameters so approximate bus utilisation reflects the selected '
                 'format.'),
                ('record_passes_advanced_filters',
                 'Implements Type, FC, response-time and free-text filtering. Filtering is '
                 'display-only; it does not alter SessionMetrics or the on-disk capture '
                 'log.'),
                ('anomaly_tag_for_record',
                 'Maps the semantic result of a record to the Treeview tag used for colour '
                 'highlighting, including completed normal REQUEST/RESPONSE pairs.'),
                ('mark_timed_out_records',
                 'Finds original REQUEST records by their sequence IDs and marks them '
                 'timed_out rather than inventing artificial timeout frames. Visible '
                 'rows are retagged in place; the table is rebuilt only while the '
                 'Timeouts filter is active.'),
                ('refresh_record_tags',
                 'Re-applies the result tag to the Treeview rows of the given records '
                 'and refreshes the Frame Inspector when one of them is selected.'),
                ('update_frame_inspector',
                 'Builds the structured inspector values for the selected traffic record '
                 'and applies result styling while preserving the raw frame.'),
                ('export_session_csv',
                 'Exports the frames retained by the GUI history, including timing, '
                 'decoded addressing, raw data and anomaly/timeout fields. This differs '
                 'intentionally from the complete TXT capture log.'),
                ('records_for_display',
                 'Applies current filtering and time-order state to the bounded '
                 'source-of-truth frame history.'),
                ('add_frame_rows_batch',
                 'Central view ingestion path. It assigns stable sequence IDs, runs '
                 'SessionMetrics, enriches parser rows into view records (including the '
                 'matched request address/quantity for read responses), tracks '
                 'successful pairs, writes complete real traffic to disk, updates visible '
                 'table/raw views, prunes history and auto-scrolls.'),
                ('prune_ui_history',
                 'Keeps memory/UI work bounded by removing old records in chunks after a '
                 'hysteresis threshold. The disk log is independent and remains complete.'),
                ('ensure_log_started',
                 'Creates the TXT capture log lazily only when real traffic actually '
                 'arrives, preventing empty logs from start/stop operations with no '
                 'data.')],
 'mb_slave_finder.py': [('build_discovery_probe',
                         'Constructs a read-only FC03/FC04 request for Address 0, Quantity '
                         '1 and appends the RTU CRC. Input validation restricts Slave IDs '
                         'to 1..247 and FC to 03/04.'),
                        ('find_discovery_response',
                         'Scans received bytes for the requested Slave and Function Code. '
                         'A CRC-valid normal register response or CRC-valid Modbus '
                         'Exception is accepted; echoes and unrelated traffic are '
                         'ignored.'),
                        ('discovery_response_timeout_seconds',
                         'Calculates a response deadline from serial character time, the '
                         'expected 7-byte FC03/FC04 response and an inter-frame/processing '
                         'margin, never below the user-configured minimum.'),
                        ('bus_activity_detected',
                         'Listens passively for the idle-check period and returns any '
                         'bytes received; a non-empty result means another device is '
                         'transmitting and the scan must not start.'),
                        ('write_discovery_request',
                         'Transmits one probe without using ser.flush(), retries one write '
                         'timeout after driver/buffer recovery, waits for estimated '
                         'on-wire transmission time and raises actual driver errors '
                         'instead of disguising them as no-response Slaves.'),
                        ('build_device_identification_probe',
                         'Builds FC43 / MEI type 14 / Basic Device Identification '
                         'requests, beginning at a selectable Object ID.'),
                        ('find_device_identification_response',
                         'Parses FC43/14 responses and Exceptions from a receive buffer, '
                         'validates CRC, decodes variable-length ASCII objects and exposes '
                         'More Follows / Next Object ID for paged identification.'),
                        ('read_basic_device_identification',
                         'Repeats FC43/14 requests while More Follows is set, merging '
                         'objects until VendorName, ProductCode and MajorMinorRevision are '
                         'available or the paging limit/response terminates.'),
                        ('start_discovery_scan',
                         'Validates the safety confirmation, COM selection, Slave range, '
                         'attempts, selected serial configurations and global busy state. It '
                         'disables conflicting controls and launches the discovery '
                         'worker.'),
                        ('discovery_worker',
                         'Iterates selected serial configurations and Slave IDs. It opens '
                         'one configuration at a time, checks once that the bus is idle, '
                         'probes FC03 then optional FC04 with the selected attempts, '
                         'optionally performs Device Identification for found Slaves, '
                         'publishes progress/results, and always closes the active serial '
                         'handle.'),
                        ('finish_discovery_ui',
                         'Returns both Finder and Sniffer controls to idle state and '
                         'presents completed/stopped/error status without leaving the '
                         'application locked in a busy state.')],
 'mb_master.py': [('format_register_values',
                   'Turns raw registers into display strings for the selected format; '
                   '32-bit values are shown on the first register of each pair and an '
                   'unpaired last register shows a dash.'),
                  ('encode_register_value',
                   'Converts one user-entered value into the register(s) it occupies in '
                   'the selected format and byte order, rejecting values that do not fit.'),
                  ('build_write_request',
                   'Builds FC05/06/15/16 requests within the Modbus write limits; Slave 0 '
                   'is accepted for broadcast.'),
                  ('find_master_response',
                   'Finds the CRC-valid response of the expected length from the addressed '
                   'Slave, or a Modbus exception, and decodes read values. Adapter echoes '
                   'of read requests are skipped.'),
                  ('MasterEngine.next_job',
                   'Chooses the next transaction: queued writes first, then "Read once" '
                   'requests, then the enabled window whose next due time is earliest.'),
                  ('MasterEngine.run',
                   'Worker loop: optional idle-bus check, then one transaction at a time '
                   'with the configured delay between polls, posting master_ready, '
                   'master_result and master_stopped events.'),
                  ('MasterEngine.transact',
                   'Sends one request and waits for its response until the response '
                   'timeout, classifying the result as ok, exception, invalid, timeout or '
                   'broadcast.')],
 'mb_master_ui.py': [('build_master_tab',
                      'Builds the connection bar, toolbar and scrollable grid of poll '
                      'windows, restoring the saved connection parameters.'),
                     ('master_apply_window',
                      'Validates the fields of one window, updates its model, rebuilds its '
                      'rows and hands the new definition to the running engine.'),
                     ('master_build_write',
                      'Validates the write dialog and encodes the values with the window '
                      'format into an FC05/06/15/16 request.'),
                     ('master_connect',
                      'Checks the busy flag, safety confirmation and settings, opens the '
                      'port, starts MasterEngine with the idle-bus check and locks the other '
                      'active features.'),
                     ('_master_apply_result',
                      'Updates counters, values and the status line of the window that '
                      'issued a transaction, ignoring results of an outdated definition.'),
                     ('master_toggle_popout',
                      'Moves a window between the grid and its own top-level window by '
                      'rebuilding its pane from the model.'),
                     ('master_open_workspace',
                      'Loads a named workspace from the workspace folder, validating every '
                      'window and skipping invalid entries with a warning.'),
                     ('_master_build_workspace_menu',
                      'Rebuilds the Workspace menu each time it opens, listing the saved '
                      'workspaces under Open and Delete.'),
                     ('master_rename_window',
                      'Gives a window its own name, shown in its header and saved in the '
                      'workspace; an empty name restores the default.'),
                     ('master_set_row_format',
                      'Applies a format (or the window default) to the selected rows '
                      'through apply_format_to_rows() and redraws the values.'),
                     ('master_edit_scale',
                      'Asks for a linear scale and applies it to the values of the '
                      'selected rows.'),
                     ('master_open_definition',
                      'Creates a Master window from a definition coming from the Sniffer '
                      'or the Finder and copies the serial parameters when disconnected.'),
                     ('master_confirm_close',
                      'Asks whether to save a saved workspace that has unsaved changes '
                      'before the application closes; Cancel keeps it open.')],
 'mb_i18n.py': [('canonical_ui_text',
                 'Normalises a known English caption back to its canonical PT-PT form. '
                 'This makes language switching reversible instead of translating an '
                 'already translated string repeatedly.'),
                ('translate_text',
                 'Returns the English translation for known canonical PT-PT UI strings '
                 'when English is selected; unknown/technical terms are returned '
                 'unchanged.'),
                ('translate_details',
                 'Translates selected human-readable fragments embedded inside protocol '
                 'detail strings (DETAIL_FRAGMENTS_PT_TO_EN) while preserving numbers, '
                 'addresses, register values and other protocol data.'),
                ('english_help_blocks',
                 'Returns the complete English Help / Connections document as structured '
                 'blocks so Help switches language together with the rest of the UI.'),
                ('translate_runtime_text',
                 'Uses regular expressions to translate live status strings that contain '
                 'counters, elapsed time, selected configuration or estimated duration.')],
 'mb_theme.py': [('_configure_fixed_geometry',
                  'Defines ttk element layouts, paddings, borders, row heights and widget '
                  'metrics once. These values are intentionally independent of Light/Dark '
                  'selection.'),
                 ('_install_fixed_checkbutton_element',
                  'Creates the custom checkbox indicator element/images used to keep '
                  'checkbox dimensions stable across palette changes.'),
                 ('_apply_palette',
                  'Changes ttk colors/state maps and classic Tk colors without changing '
                  'layout definitions, supporting the invariant that theme switching '
                  'changes appearance but not geometry.'),
                 ('apply_modern_theme',
                  'Public startup helper that selects the fixed clam engine and applies '
                  'either the Light or Dark palette.')],
 'mb_widgets.py': [('RefreshButton',
                    'Canvas-based square button that draws the ↻ glyph and recentres it '
                    'from its actual rendered bounding box. It supports '
                    'normal/hover/pressed/disabled states and palette changes.'),
                   ('ToggleSwitch',
                    'Canvas-based boolean switch bound to a Tk variable. It toggles the '
                    'variable, invokes the callback and redraws track/knob colors while '
                    'preserving fixed dimensions.')],
 'mb_gui.py': [('SnifferApp.__init__',
                'Creates the root window, loads persisted preferences before widget '
                'construction, initializes capture/discovery/log/history state, constructs '
                'the UI, freezes language geometry, applies language, installs event '
                'guards/persistence and schedules queue/status polling.'),
               ('_freeze_language_layout_geometry',
                'Measures the canonical Portuguese layout and freezes key container '
                'dimensions/minimums so changing to English changes text only, not '
                'panel/control geometry.'),
               ('_guard_mouse_wheel',
                'Allows normal wheel scrolling only on truly scrollable widgets and '
                'consumes wheel events elsewhere so a ttk Notebook cannot change tabs from '
                'mouse-wheel input.'),
               ('apply_language',
                'Performs runtime translation of static widgets, tables, context menus, '
                'help content and live status strings, then re-applies saved/fixed '
                'geometry and optionally persists the selected language.'),
               ('toggle_dark_mode',
                'Applies the alternate palette using the already-created ttk geometry and '
                'updates custom Canvas widgets; the control structure itself is not '
                'rebuilt.'),
               ('save_current_ui_settings',
                'Collects validated user-facing preferences from both Sniffer and Finder '
                'and writes them to the shared settings file. COM port names, window '
                'geometry and safety confirmation are intentionally excluded.'),
               ('_apply_bus_health_layout',
                'Re-grids Bus Health labels/values into equal-height rows. Full mode uses '
                'one metric pair per row; compact mode uses two pairs per row and '
                'controlled wrapping to keep content inside each rectangle.'),
               ('_sync_bus_health_layout',
                'Chooses full versus compact Bus Health arrangement from real available '
                'height with hysteresis, then reapplies wrapping/column behavior on width '
                'changes.'),
               ('_build_ui',
                'Constructs all top-level tabs and controls. It is intentionally a large '
                'declarative layout method: global language/theme overlay, Sniffer '
                'configuration/actions/statistics, Traffic/Raw/Bus Health/Help notebook, '
                'filters/context menu, Frame Inspector and the Bus Slave Finder page.')]}

# Blue 'Design note.' callout printed after the key-path cards of a module.
DESIGN_NOTES = {'mb_protocol.py': 'Important design boundary: this module contains no Tkinter code and '
                   'can be regression-tested independently. That separation is valuable if '
                   'the project is later rebuilt for a thesis or extended with additional '
                   'front ends.',
 'mb_capture.py': 'Tkinter widgets are never updated directly by reader threads. Workers '
                  'communicate through event_queue; process_queue() runs on the Tk main '
                  'thread.',
 'mb_view.py': 'There are deliberately two histories: the bounded GUI history and the '
               'complete TXT log. Sorting/filtering only changes presentation; statistics '
               'are derived before filtering.',
 'mb_slave_finder.py': 'The Finder is active traffic generation, unlike the passive '
                       'Sniffer. The UI requires an explicit confirmation that another '
                       'master is not active and the global busy lock prevents '
                       'simultaneous capture/scan inside this application.',
 'mb_i18n.py': 'The translation design treats PT-PT as canonical and leaves technical '
               'English terms unchanged unless a translation is explicitly defined.',
 'mb_theme.py': 'The theme module is geometry-sensitive: changing colors must not rebuild '
                'ttk layouts. This is why theme engine selection and fixed geometry are '
                'separated from palette application.',
 'mb_master.py': 'The engine owns the serial port while the Master is connected. Widgets '
                 'only change definitions through set_poll(), read_once() and '
                 'queue_write(); results come back through event_queue.',
 'mb_master_ui.py': 'Window state lives in MasterWindow objects, so a pane can be destroyed '
                    'and rebuilt (pop out / dock, language switch) without losing data.',
 'mb_slave.py': 'handle_request() is a pure function of the store and the frame, so '
                'every reply is testable without a serial port; the engine only adds '
                'framing, timing, faults and echo removal around it.',
 'mb_table_ui.py': 'A pane is a plain dict of widgets and a window a model object, so the '
                   'same widget code serves MasterWindow and SlaveWindow.',
 'mb_gui.py': 'SnifferApp uses mixins to keep protocol capture, Finder, Master, Slave and '
              'view behavior in separate files while sharing one Tk root and common state.'}

# One-sentence description printed above each regression-test class table.
TEST_CLASS_DESCRIPTIONS = {'TimingRegressionTests': 'Protects RTU timing and automatic/manual gap calculations, '
                          'including the fixed 1.750 ms t3.5 rule above 19200 bit/s and '
                          'FC43 response timing.',
 'ParserRegressionTests': 'Protects CRC, resynchronisation, supported frame shapes, '
                          'random-noise robustness, request/response pairing and timeout '
                          'behavior.',
 'SlaveFinderRegressionTests': 'Protects FC03/FC04 discovery and FC43/14 Device '
                               'Identification parsing, CRC validation, Exceptions, echo '
                               'rejection and More Follows paging.',
 'InternationalizationRegressionTests': 'Protects language normalization, reversible '
                                        'static/runtime translation, translated register '
                                        'details, Frame Inspector English text and English '
                                        'Help content.',
 'ProtocolV31RegressionTests': 'Protects the v3.1 protocol fixes: table CRC against the '
                               'bit-wise reference, broadcast accounting, FC05/06 echo '
                               'pairing, dual-RX direction, split-burst detection, '
                               'per-read timestamps and FC01/02 bit formatting.',
 'ReaderV31RegressionTests': 'Feeds a frame split by a simulated 16 ms USB latency into '
                             'the real reader_loop() and requires one CRC-valid RESPONSE.',
 'ViewV31RegressionTests': 'Protects in-place timeout retagging, the Timeouts-filter '
                           'rebuild and the address-mapped register/bit data in the Frame '
                           'Inspector.',
 'FinderV31RegressionTests': 'Runs the real discovery worker against fake serial ports to '
                             'check attempts, the idle-bus abort and the 40 to 100 ms '
                             'settings migration.',
 'SourceHygieneV31Tests': 'Rejects inline language branches in the package and checks '
                          'that message templates translate.',
 'MasterFormatTests': 'Protects the 16/32-bit data formats, the four byte orders and the '
                      'rejection of values that do not fit.',
 'MasterFrameTests': 'Checks write frames against the Modbus specification examples, '
                     'definition limits, adapter echoes, exceptions, bad CRC and write '
                     'response matching.',
 'MasterEngineTests': 'Runs MasterEngine against an in-memory slave: scheduling order, '
                      'fast and slow windows on one bus, writes, broadcast, timeouts, '
                      'exceptions and the idle-bus abort.',
 'MasterWindowTests': 'Protects workspace entry validation and the FC16 float encoding '
                      'of the write dialog.',
 'MasterWorkspaceFolderTests': 'Checks that workspaces live beside settings.json, are '
                               'listed alphabetically and use valid Windows file names, '
                               'and that window names are saved.',
 'MasterPerAddressFormatTests': 'Protects the 64-bit formats and byte orders, '
                                'per-address formats, value grouping, the selection rules '
                                'and the write encoding of the clicked value.',
 'MasterSettingsTests': 'Validates the last workspace name stored in settings.json.',
 'MasterScaleTests': 'Protects scaled display, multi-register scaling, the conversion of '
                     'written engineering values and scale validation.',
 'MasterOpenFromTrafficTests': 'Checks which Traffic records can open a Master window and '
                               'with which definition.',
 'MasterReconnectTests': 'Simulates an unplugged adapter: the engine reopens the port and '
                         'resumes, keeps retrying until stopped, or ends without reopen.',
 'SlaveRequestTests': 'Checks reads and writes of every table, Exceptions 01/02/03, '
                      'ignored IDs, broadcast writes and request lengths.',
 'SlaveFaultTests': 'Validates fault settings, keeps only active faults and corrupts the '
                    'CRC.',
 'SlaveEngineTests': 'Runs the Master engine against the Slave engine over an in-memory '
                     'link: every function, exceptions, adapter echo, foreign traffic, '
                     'split and garbled requests, unknown functions and each fault, '
                     'including the probability.',
 'SlaveWindowTests': 'Protects Slave workspace entries, area validation, window overlap '
                     'and the translated fault description.',
 'SlaveSettingsTests': 'Checks the Slave workspace folder and the validated slave section '
                       'of settings.json.'}

