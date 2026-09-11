#!/usr/bin/env python3
"""Main Tkinter window composition for MBSniffer."""

import queue
import threading
from collections import deque

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from mb_config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS,
    MAX_PENDING_REQUEST_TIMEOUT_SECONDS,
    MAX_RAW_TEXT_LINES,
    MAX_UI_FRAMES,
    MIN_PENDING_REQUEST_TIMEOUT_SECONDS,
    SLOW_RESPONSE_THRESHOLD_MS,
    debug_sim,
    load_ui_settings,
    resource_path,
    save_ui_settings,
)
from mb_protocol import SessionMetrics
from mb_slave_finder import SlaveFinderMixin
from mb_capture import CaptureMixin
from mb_view import ViewMixin
from mb_widgets import RefreshButton, ToggleSwitch
from mb_theme import apply_modern_theme, apply_theme, theme_colors
from mb_i18n import (
    LANGUAGE_CHOICES,
    LANGUAGE_ENGLISH,
    LANGUAGE_PORTUGUESE,
    canonical_ui_text,
    english_help_blocks,
    normalize_language,
    translate_text,
    translate_runtime_text,
)


class SnifferApp(SlaveFinderMixin, CaptureMixin, ViewMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")

        # Load the remembered mode before any ttk widgets are constructed.
        # Light and Dark use one fixed ttk construction; only colours differ.
        self.ui_settings = load_ui_settings()
        self.current_language = normalize_language(
            self.ui_settings.get("language", LANGUAGE_PORTUGUESE)
        )
        self.initial_dark_mode = bool(self.ui_settings.get("dark_mode", False))
        self.ui_style = apply_modern_theme(
            self,
            dark=self.initial_dark_mode,
        )

        # Explicit application/window icon. This works when launched through
        # MBSniffer.bat (Python) and when bundled as a PyInstaller EXE.
        try:
            icon_file = resource_path("MBSniffer.ico")
            if icon_file.exists():
                self.iconbitmap(default=str(icon_file))
        except Exception:
            pass

        self.geometry("1280x780")
        self.minsize(1050, 650)

        self.serial_objects = []
        self.serial_by_port = {}
        self.reader_threads = []
        self.reader_generation = 0
        self.stop_event = threading.Event()
        self.event_queue = queue.Queue()
        self.busy = False
        self.capture_active = False
        self.restart_in_progress = False

        # Active slave-discovery state. This is deliberately independent from
        # passive capture/simulation state, but shares the global busy lock so
        # the application can never act as scanner and sniffer at the same time.
        self.discovery_active = False
        self.discovery_stop_event = threading.Event()
        self.discovery_thread = None
        self.discovery_serial = None
        self.discovery_found_count = 0
        self._closing = False
        self._process_queue_error_shown = False

        self.log_file = None
        self.log_path = None

        # Real-capture logs are created lazily: starting/stopping a capture with
        # zero received traffic must not create an empty .txt file.
        self.pending_log_filename = None
        self.pending_log_header = ""
        self.pending_log_notes = []
        self.log_start_failed = False
        self._raw_by_iid = {}
        self._record_by_iid = {}
        self._transaction_filter_seqs = None
        self._successful_request_seqs = set()
        self._advanced_filter_after_id = None
        self._bus_activity_after_id = None

        # Bounded GUI-history bookkeeping.
        self._tree_history = deque()   # current visible Treeview rows
        self._ui_frame_count = 0
        self._raw_text_line_count = 0

        # Source-of-truth for the bounded GUI history. Filtering/sorting only
        # changes the view; it never changes statistics or the disk log.
        self._frame_history = deque()
        self._next_frame_seq = 1

        # Visible Treeview bookkeeping by logical frame sequence.
        self._tree_iids_by_seq = {}
        self._tree_separator_iid_by_seq = {}

        # Raw Hex separator width/reflow bookkeeping.
        self._raw_separator_width_chars = 1
        self._raw_reflow_after_id = None

        # Slave filter state. "All mode" also controls whether newly discovered
        # slaves are automatically selected.
        self.slave_filter_vars = {}
        self.slave_filter_all_mode = True

        self.metrics = SessionMetrics()

        self._build_ui()
        self._freeze_language_layout_geometry()
        self._capture_portuguese_help()
        self.apply_language(save=False)
        self._install_mouse_wheel_guard()
        self.rebuild_slave_filter_menu()
        self.refresh_ports()
        self.update_mode_ui()
        self.update_gap_state()
        self.update_com_status()
        self._restore_saved_main_tab()
        self._install_ui_settings_persistence()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self.process_queue)
        self.after(1000, self.poll_com_status)


    def _freeze_language_layout_geometry(self):
        """Freeze language-independent container geometry using the PT layout.

        The UI is constructed from the canonical Portuguese captions. Capture
        the natural geometry before any runtime translation and use those
        dimensions as layout constraints. Language changes may replace text,
        but must never move or resize the surrounding controls/panels.
        """
        try:
            self.update_idletasks()
        except tk.TclError:
            return

        # The global language/theme overlay is anchored to the top-right.
        # Freeze the canonical PT grid-cell widths. English captions are shorter
        # here, so this preserves the exact existing PT positions and prevents
        # the Dark Mode switch / language combobox from sliding left or right.
        overlay = getattr(self, "theme_overlay", None)
        if overlay is not None:
            try:
                self.update_idletasks()
                canonical_column_widths = [
                    max(1, int(overlay.grid_bbox(column, 0)[2]))
                    for column in range(4)
                ]
                for column, width in enumerate(canonical_column_widths):
                    overlay.columnconfigure(column, minsize=width)
                self.update_idletasks()
                self._language_overlay_width = max(1, overlay.winfo_reqwidth())
                self._language_overlay_height = max(1, overlay.winfo_reqheight())
                overlay.place_configure(
                    width=self._language_overlay_width,
                    height=self._language_overlay_height,
                )
            except (tk.TclError, IndexError, TypeError):
                pass

        # The Finder configuration includes wrapped explanatory text. It must
        # be measured while the Finder page is actually laid out; measuring a
        # hidden Notebook page can under-estimate the PT height by one line.
        page = getattr(self, "discovery_page", None)
        options = getattr(self, "_discovery_options_frame", None)
        if page is not None and options is not None:
            try:
                selected_tab = self.main_notebook.select()
                self.main_notebook.select(page)
                self.update_idletasks()
                height = max(options.winfo_height(), options.winfo_reqheight(), 1)
                # grid row height also includes the widget's external pady.
                # Preserve the complete PT cell, not only the LabelFrame body.
                try:
                    cell_height = max(height, int(page.grid_bbox(0, 1)[3]))
                except (tk.TclError, TypeError, IndexError):
                    cell_height = height + 12
                self._language_discovery_options_height = height
                page.rowconfigure(1, minsize=cell_height)
                options.grid_configure(sticky="nsew")
                self.main_notebook.select(selected_tab)
                self.update_idletasks()
            except tk.TclError:
                pass

    def _guard_mouse_wheel(self, event):
        """
        Keep wheel input local to genuinely scrollable content widgets.

        Treeviews and Text widgets retain their normal vertical wheel scrolling,
        as do the scrollbar widgets themselves.  Everywhere else the event is
        consumed before ttk class bindings see it; in particular, this prevents
        Windows ttk Notebook tabs from changing when the user turns the wheel
        over a tab or over non-scrollable page content.
        """
        widget = getattr(event, "widget", None)
        if isinstance(
            widget,
            (ttk.Treeview, tk.Text, tk.Listbox, ttk.Scrollbar, tk.Scrollbar),
        ):
            return None
        return "break"

    def _install_mouse_wheel_guard(self):
        """
        Prepend one application bindtag to every existing widget.

        The UI is statically constructed before this method is called, so this
        covers the Sniffer, Bus Health, Help and Bus Slave Finder pages without
        changing individual widget behavior or notebook keyboard navigation.
        """
        tag = "MBSniffer.MouseWheelGuard"

        for sequence in (
            "<MouseWheel>",
            "<Shift-MouseWheel>",
            "<Button-4>",
            "<Button-5>",
        ):
            try:
                self.bind_class(
                    tag,
                    sequence,
                    self._guard_mouse_wheel,
                )
            except tk.TclError:
                pass

        stack = [self]
        while stack:
            widget = stack.pop()
            try:
                tags = tuple(widget.bindtags())
                if tag not in tags:
                    widget.bindtags((tag,) + tags)
                stack.extend(widget.winfo_children())
            except tk.TclError:
                continue

    def _apply_classic_widget_palette(self, dark):
        """Apply palette to the small set of classic Tk widgets."""
        colors = theme_colors(self, dark)

        if hasattr(self, "raw_text"):
            self.raw_text.configure(
                background=colors["input"],
                foreground=colors["text"],
                insertbackground=colors["text"],
                selectbackground=colors["select"],
                selectforeground=colors["select_text"],
            )

        if hasattr(self, "help_text"):
            self.help_text.configure(
                background=colors["input"],
                foreground=colors["text"],
                insertbackground=colors["text"],
                selectbackground=colors["select"],
                selectforeground=colors["select_text"],
            )

        for menu_name in ("slave_filter_menu", "traffic_context_menu"):
            menu = getattr(self, menu_name, None)
            if menu is None:
                continue
            try:
                menu.configure(
                    background=colors["panel"],
                    foreground=colors["text"],
                    activebackground=colors["select"],
                    activeforeground=colors["select_text"],
                    selectcolor=colors["text"],
                )
            except tk.TclError:
                pass

        if hasattr(self, "tree"):
            self.configure_anomaly_tags(dark)
            self.configure_inspector_result_styles()

        for name in (
            "refresh_a_btn",
            "refresh_b_btn",
            "discovery_refresh_btn",
            "dark_mode_switch",
        ):
            widget = getattr(self, name, None)
            setter = getattr(widget, "set_dark_mode", None)
            if callable(setter):
                setter(dark)

    def configure_inspector_result_styles(self):
        """
        Match the Inspector Result foreground to the Traffic result palette.

        Only colour values are configured here; no padding/font/layout metrics
        are changed, so Light/Dark construction remains identical.
        """
        if not hasattr(self, "ui_style"):
            return

        colors = theme_colors(
            self,
            bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get()),
        )

        tag_map = {
            "success": "result_success",
            "slow": "anomaly_slow",
            "exception": "anomaly_exception",
            "crc": "anomaly_crc",
            "timeout": "anomaly_timeout",
            "raw": "anomaly_raw",
        }

        self.ui_style.configure(
            "MBS.Result.neutral.TLabel",
            background=colors["root"],
            foreground=colors["text"],
        )
        self.ui_style.configure(
            "MBS.Result.pending.TLabel",
            background=colors["root"],
            foreground=colors["text"],
        )

        if hasattr(self, "tree"):
            for key, tag in tag_map.items():
                try:
                    foreground = self.tree.tag_configure(tag)["foreground"]
                except Exception:
                    foreground = colors["text"]

                self.ui_style.configure(
                    f"MBS.Result.{key}.TLabel",
                    background=colors["root"],
                    foreground=foreground,
                )

    def tr(self, text):
        """Translate one canonical UI string to the currently selected language."""
        return translate_text(text, self.current_language)

    def trf(self, text, **values):
        """Translate a format template and substitute values afterwards."""
        return self.tr(text).format(**values)

    def _capture_portuguese_help(self):
        """Store the original PT-PT Help text and tag ranges exactly as built."""
        if not hasattr(self, "help_text"):
            return
        try:
            self._help_pt_text = self.help_text.get("1.0", "end-1c")
            ranges = {}
            for tag in self.help_text.tag_names():
                if tag == "sel":
                    continue
                tag_ranges = list(self.help_text.tag_ranges(tag))
                ranges[tag] = [
                    (str(tag_ranges[i]), str(tag_ranges[i + 1]))
                    for i in range(0, len(tag_ranges), 2)
                ]
            self._help_pt_tag_ranges = ranges
        except tk.TclError:
            self._help_pt_text = ""
            self._help_pt_tag_ranges = {}

    def _render_help_language(self):
        """Render Help in English or restore the original PT-PT text byte-for-byte."""
        if not hasattr(self, "help_text"):
            return
        try:
            self.help_text.configure(state="normal")
            self.help_text.delete("1.0", "end")

            if self.current_language == LANGUAGE_ENGLISH:
                max_ui_frames_text = f"{MAX_UI_FRAMES:_}".replace("_", " ")
                max_raw_lines_text = f"{MAX_RAW_TEXT_LINES:_}".replace("_", " ")
                for tag, text in english_help_blocks(
                    max_ui_frames_text,
                    max_raw_lines_text,
                    MIN_PENDING_REQUEST_TIMEOUT_SECONDS,
                    MAX_PENDING_REQUEST_TIMEOUT_SECONDS,
                    debug_sim=(debug_sim == 1),
                ):
                    self.help_text.insert("end", text, tag)
            else:
                self.help_text.insert("1.0", getattr(self, "_help_pt_text", ""))
                for tag, ranges in getattr(self, "_help_pt_tag_ranges", {}).items():
                    for start, end in ranges:
                        self.help_text.tag_add(tag, start, end)

            self.help_text.configure(state="disabled")
            self.help_text.see("1.0")
        except tk.TclError:
            pass

    def _translate_widget_tree(self):
        """Translate static widget captions without changing widget geometry."""
        stack = [self]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
            except tk.TclError:
                continue

            # Text widgets contain documents, not captions.
            if isinstance(widget, tk.Text):
                continue

            try:
                keys = widget.keys()
            except Exception:
                keys = ()
            if "text" in keys:
                try:
                    current = widget.cget("text")
                    if current:
                        widget.configure(text=self.tr(current))
                except (tk.TclError, TypeError):
                    pass

            if isinstance(widget, ttk.Notebook):
                try:
                    for tab_id in widget.tabs():
                        current = widget.tab(tab_id, "text")
                        widget.tab(tab_id, text=self.tr(current))
                except tk.TclError:
                    pass

    def _translate_traffic_context_menu(self):
        menu = getattr(self, "traffic_context_menu", None)
        if menu is None:
            return
        labels = (
            (0, "Copiar Raw Hex"),
            (1, "Copiar frame descodificado"),
            (3, "Filtrar por este Slave"),
            (4, "Filtrar por este FC"),
            (5, "Mostrar apenas esta transação"),
            (6, "Limpar filtro de transação"),
        )
        for index, canonical in labels:
            try:
                menu.entryconfigure(index, label=self.tr(canonical))
            except tk.TclError:
                pass

    def _apply_table_language(self):
        """Refresh headings and filter values that are not normal widget captions."""
        if hasattr(self, "advanced_filter_type_combo"):
            current = canonical_ui_text(self.advanced_filter_type_var.get())
            canonical_values = (
                "Todos", "Requests", "Responses", "Exceptions",
                "CRC errors", "Timeouts", "RAW",
            )
            self.advanced_filter_type_combo.configure(
                values=tuple(self.tr(v) for v in canonical_values)
            )
            self.advanced_filter_type_var.set(self.tr(current))

        if hasattr(self, "time_order_var"):
            canonical_order = canonical_ui_text(self.time_order_var.get())
            self.time_order_var.set(self.tr(canonical_order))

        if hasattr(self, "tree") and hasattr(self, "tree_headings"):
            canonical_headings = {
                "time": "Hora ↓" if self.time_order_descending() else "Hora ↑",
                "delta": "Δt (ms)",
                "response": "Resp. (ms)",
                "channel": "COM",
                "type": "Tipo",
                "slave": canonical_ui_text(self.tree_headings.get("slave", "Slave ▾")),
                "fc": "FC",
                "details": "Detalhes",
                "crc": "CRC",
            }
            for col, canonical in canonical_headings.items():
                translated = self.tr(canonical)
                self.tree_headings[col] = translated
                try:
                    self.tree.heading(col, text=translated)
                except tk.TclError:
                    pass

        if hasattr(self, "discovery_tree"):
            canonical = {
                "slave": "Slave",
                "baud": "Baud",
                "config": "Config.",
                "fc": "FC",
                "result": "Resultado",
                "resp": "Resp. (ms)",
                "device_id": "Device Identification",
                "raw": "Raw Hex",
            }
            for col, value in canonical.items():
                try:
                    self.discovery_tree.heading(col, text=self.tr(value))
                except tk.TclError:
                    pass

    def apply_language(self, save=True):
        """Apply the selected language immediately to the complete UI."""
        selected = getattr(self, "language_var", None)
        if selected is not None:
            self.current_language = normalize_language(selected.get())
            if selected.get() != self.current_language:
                selected.set(self.current_language)

        self._translate_widget_tree()
        self._apply_table_language()
        self._translate_traffic_context_menu()
        self._render_help_language()

        # Rebuild dynamic captions/values in the selected language.
        try:
            self.update_mode_ui()
            self.update_com_status()
            self.update_stats_labels()
            self.rebuild_slave_filter_menu()
            self.update_slave_heading()
            self.update_frame_inspector(self.selected_record())
            self.update_discovery_estimate()
        except (AttributeError, tk.TclError):
            pass

        # Translate idle/current status variables without altering state.
        for name in ("status_var", "discovery_status_var", "discovery_found_var"):
            var = getattr(self, name, None)
            if var is not None:
                try:
                    var.set(translate_runtime_text(var.get(), self.current_language))
                except tk.TclError:
                    pass

        # Refresh translated row contents without allowing the language change
        # itself to alter table/card geometry.  Column widths are restored after
        # rendering; normal viewport resizing and new traffic may still use the
        # existing responsive/autofit behaviour.
        traffic_widths = {}
        discovery_widths = {}
        try:
            if hasattr(self, "tree"):
                traffic_widths = {
                    col: int(self.tree.column(col, "width"))
                    for col in self.tree["columns"]
                }
            if hasattr(self, "discovery_tree"):
                discovery_widths = {
                    col: int(self.discovery_tree.column(col, "width"))
                    for col in self.discovery_tree["columns"]
                }
            self.render_filtered_view()
            for col, width in traffic_widths.items():
                self.tree.column(col, width=width)
            for col, width in discovery_widths.items():
                self.discovery_tree.column(col, width=width)
        except (AttributeError, tk.TclError):
            pass

        if save:
            self.save_current_ui_settings()

    def on_language_changed(self, _event=None):
        self.apply_language(save=True)

    def toggle_dark_mode(self):
        """
        Switch Light/Dark colours only.

        No ttk theme replacement, layout change, padding change or row-height
        change occurs here. The page construction is immutable after startup.
        """
        dark = bool(self.dark_mode_var.get())

        self.ui_style = apply_theme(
            self,
            dark=dark,
            style=self.ui_style,
        )
        self._apply_classic_widget_palette(dark)

        # Remember Dark mode together with the rest of the user's preferences.
        self.save_current_ui_settings()

    def _restore_saved_main_tab(self):
        saved = self.ui_settings.get("last_main_tab", "Sniffer")
        try:
            self.main_notebook.select(
                self.discovery_page if saved == "Bus Slave Finder"
                else self.sniffer_page
            )
        except tk.TclError:
            pass

    def _current_main_tab_name(self):
        try:
            selected = self.main_notebook.select()
            return (
                "Bus Slave Finder"
                if selected == str(self.discovery_page)
                else "Sniffer"
            )
        except Exception:
            return "Sniffer"

    def _schedule_ui_settings_save(self, *_args):
        if getattr(self, "_closing", False):
            return

        previous = getattr(self, "_settings_save_after_id", None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass

        try:
            self._settings_save_after_id = self.after(
                300,
                self.save_current_ui_settings,
            )
        except tk.TclError:
            self._settings_save_after_id = None

    def save_current_ui_settings(self):
        """Persist all roaming-safe user preferences in one settings.json."""
        pending = getattr(self, "_settings_save_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._settings_save_after_id = None

        try:
            finder_bauds = [
                int(baud)
                for baud, var in self.discovery_baud_vars.items()
                if bool(var.get())
            ]
            finder_parities = [
                parity
                for parity, var in self.discovery_parity_vars.items()
                if bool(var.get())
            ]
            finder_stops = [
                stop
                for stop, var in self.discovery_stop_vars.items()
                if bool(var.get())
            ]

            payload = {
                "dark_mode": bool(self.dark_mode_var.get()),
                "language": normalize_language(self.current_language),
                "last_main_tab": self._current_main_tab_name(),
                "sniffer": {
                    "physical_mode": self.mode_var.get(),
                    "baud": self.baud_var.get(),
                    "data_bits": self.data_var.get(),
                    "parity": self.parity_var.get(),
                    "stop_bits": self.stop_var.get(),
                    "frame_gap_mode": self.gap_mode_var.get(),
                    "frame_gap_ms": self.gap_ms_var.get(),
                    "pending_timeout_s": self.pending_timeout_var.get(),
                    "auto_scroll": bool(self.auto_scroll_var.get()),
                    "separate_transactions": bool(
                        self.separate_transactions_var.get()
                    ),
                    "highlight_results": bool(
                        self.highlight_anomalies_var.get()
                    ),
                },
                "bus_slave_finder": {
                    "baud_rates": finder_bauds,
                    "parities": finder_parities,
                    "stop_bits": finder_stops,
                    "slave_start": self.discovery_slave_start_var.get(),
                    "slave_end": self.discovery_slave_end_var.get(),
                    "min_timeout_ms": self.discovery_min_timeout_var.get(),
                    "fc04_fallback": bool(
                        self.discovery_fc04_fallback_var.get()
                    ),
                    "device_identification": bool(
                        self.discovery_device_identification_var.get()
                    ),
                },
            }
            save_ui_settings(settings=payload)
        except Exception:
            # Persistence is convenience state only.
            pass

    def _install_ui_settings_persistence(self):
        """Debounced persistence for all roaming-safe user preferences."""
        self._settings_save_after_id = None

        variables = (
            self.mode_var,
            self.baud_var,
            self.data_var,
            self.parity_var,
            self.stop_var,
            self.gap_mode_var,
            self.gap_ms_var,
            self.pending_timeout_var,
            self.auto_scroll_var,
            self.separate_transactions_var,
            self.highlight_anomalies_var,
            self.discovery_slave_start_var,
            self.discovery_slave_end_var,
            self.discovery_min_timeout_var,
            self.discovery_fc04_fallback_var,
            self.discovery_device_identification_var,
        )

        for variable in variables:
            variable.trace_add(
                "write",
                lambda *_a: self._schedule_ui_settings_save(),
            )

        for mapping in (
            self.discovery_baud_vars,
            self.discovery_parity_vars,
            self.discovery_stop_vars,
        ):
            for variable in mapping.values():
                variable.trace_add(
                    "write",
                    lambda *_a: self._schedule_ui_settings_save(),
                )

        self.main_notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _e: self._schedule_ui_settings_save(),
            add="+",
        )

    def _schedule_bus_health_layout_sync(self, _event=None):
        """Debounce Bus Health reflow after notebook/window/Inspector resizing."""
        previous = getattr(self, "_bus_health_layout_after_id", None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass

        try:
            self._bus_health_layout_after_id = self.after_idle(
                self._sync_bus_health_layout
            )
        except tk.TclError:
            self._bus_health_layout_after_id = None

    def _initialize_bus_health_layout(self):
        """Measure the natural full Bus Health height before adaptive reflow."""
        self._bus_health_layout_after_id = None

        cards = getattr(self, "_health_cards", ())
        if not cards:
            return

        try:
            self.update_idletasks()
        except tk.TclError:
            return

        if getattr(self, "_health_full_required_card_height", None) is None:
            requested = [
                card.winfo_reqheight()
                for card in cards
                if card.winfo_exists()
            ]
            if requested:
                self._health_full_required_card_height = max(requested)

        self._sync_bus_health_layout()

    def _apply_bus_health_layout(self, compact):
        """
        Re-grid Bus Health metrics inside equal vertical bands.

        Full mode uses one metric/value pair per row.  Compact mode uses two
        pairs per row.  In both modes every used row receives the same weight,
        so the metrics are distributed evenly over the card height instead of
        accumulating at the top.  Compact columns use proportional uniform
        widths (label/value + label/value), which keeps both halves aligned and
        prevents one metric group from consuming the neighbouring group.
        """
        groups = getattr(self, "_health_metric_groups", ())
        if not groups:
            return

        for card, pairs in groups:
            for label_widget, value_widget in pairs:
                label_widget.grid_forget()
                value_widget.grid_forget()

            # Clear weights left by the other layout before applying the new
            # one.  Uniform groups are local to each LabelFrame.
            for column in range(4):
                card.columnconfigure(column, weight=0, minsize=0, uniform="")
            for row in range(max(6, len(pairs))):
                card.rowconfigure(row, weight=0, minsize=0, uniform="")

            if compact:
                # Size the four compact columns from their real content.
                # The two label columns absorb any spare width equally; value
                # columns keep their natural size.  This avoids the clipping
                # caused by forcing every card into one fixed percentage split.
                for column in (0, 2):
                    card.columnconfigure(column, weight=1, minsize=0, uniform="")
                for column in (1, 3):
                    card.columnconfigure(column, weight=0, minsize=0, uniform="")

                used_rows = max(1, (len(pairs) + 1) // 2)
                for row in range(used_rows):
                    card.rowconfigure(
                        row,
                        weight=1,
                        minsize=0,
                        uniform="health_metric_rows",
                    )

                pair_count = len(pairs)
                card_width = max(320, int(card.winfo_width()))
                # At normal widths the technical labels/values remain on one
                # line.  Near the application's minimum width labels may wrap
                # so the pair stays inside the LabelFrame instead of colliding
                # with the neighbouring pair.
                compact_label_wrap = (
                    0 if card_width >= 390 else max(80, int(card_width * 0.29))
                )

                for index, (label_widget, value_widget) in enumerate(pairs):
                    row = index // 2
                    group = index % 2

                    try:
                        label_widget.configure(wraplength=compact_label_wrap)
                        value_widget.configure(wraplength=0)
                    except tk.TclError:
                        pass

                    # Odd final metrics use the complete last row, leaving the
                    # value the whole right-hand side of the card.
                    if index == pair_count - 1 and pair_count % 2:
                        label_widget.grid(
                            row=row,
                            column=0,
                            sticky="w",
                            padx=(6, 3),
                            pady=1,
                        )
                        value_widget.grid(
                            row=row,
                            column=1,
                            columnspan=3,
                            sticky="e",
                            padx=(3, 6),
                            pady=1,
                        )
                        continue

                    base_column = group * 2
                    label_widget.grid(
                        row=row,
                        column=base_column,
                        sticky="w",
                        padx=((6 if base_column == 0 else 5), 3),
                        pady=1,
                    )
                    value_widget.grid(
                        row=row,
                        column=base_column + 1,
                        sticky="e",
                        padx=(3, (5 if base_column == 0 else 6)),
                        pady=1,
                    )
            else:
                # One pair per row, with every row sharing the card height
                # equally.  Proportional columns keep labels and values aligned
                # while still allowing long values to use the right-hand side.
                card.columnconfigure(0, weight=1, minsize=0, uniform="")
                card.columnconfigure(1, weight=0, minsize=0, uniform="")

                used_rows = max(1, len(pairs))
                for row in range(used_rows):
                    card.rowconfigure(
                        row,
                        weight=1,
                        minsize=0,
                        uniform="health_metric_rows",
                    )

                card_width = max(320, int(card.winfo_width()))
                full_label_wrap = (
                    0 if card_width >= 330 else max(100, int(card_width * 0.55))
                )

                for row, (label_widget, value_widget) in enumerate(pairs):
                    try:
                        label_widget.configure(wraplength=full_label_wrap)
                        value_widget.configure(wraplength=0)
                    except tk.TclError:
                        pass
                    label_widget.grid(
                        row=row,
                        column=0,
                        sticky="w",
                        padx=(10, 6),
                        pady=1,
                    )
                    value_widget.grid(
                        row=row,
                        column=1,
                        sticky="e",
                        padx=(6, 10),
                        pady=1,
                    )

        self._health_layout_compact = bool(compact)

    def _sync_bus_health_layout(self):
        """
        Keep Bus Health metrics inside their rectangles at every available height.

        The natural/full card height is measured from the real widgets. If the
        Frame Inspector expands and the notebook becomes too short, the metrics
        reflow automatically. When enough vertical room returns, the original
        layout is restored. Hysteresis prevents resize oscillation.
        """
        self._bus_health_layout_after_id = None

        health_frame = getattr(self, "health_frame", None)
        cards = getattr(self, "_health_cards", ())
        full_required = getattr(
            self,
            "_health_full_required_card_height",
            None,
        )
        if health_frame is None or not cards:
            return

        try:
            if not health_frame.winfo_exists():
                return

            available_frame_height = health_frame.winfo_height()
            if available_frame_height <= 1:
                return

            # Each card has 6 px external top and bottom grid padding.
            available_card_height = max(0, available_frame_height - 12)

            if full_required is None:
                self.update_idletasks()
                full_required = max(card.winfo_reqheight() for card in cards)
                self._health_full_required_card_height = full_required

            compact = bool(getattr(self, "_health_layout_compact", False))
            if compact:
                should_compact = available_card_height < (full_required + 8)
            else:
                should_compact = available_card_height < (full_required + 2)

            if should_compact != compact:
                self._apply_bus_health_layout(should_compact)
                self.update_idletasks()
            else:
                # Width can change without crossing the vertical compact/full
                # threshold. Reapply the current layout so wrap limits and the
                # equal-width grid continue to match the real card size.
                self._apply_bus_health_layout(compact)

        except tk.TclError:
            return

    def _build_ui(self):
        sniffer_saved = self.ui_settings.get("sniffer", {})
        if not isinstance(sniffer_saved, dict):
            sniffer_saved = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Refresh controls use a custom Canvas widget whose arrow geometry is
        # centered explicitly; this avoids ttk theme/font/image alignment drift.

        self.main_notebook = ttk.Notebook(self)
        self.main_notebook.grid(row=0, column=0, sticky="nsew")

        self.sniffer_page = ttk.Frame(self.main_notebook)
        self.sniffer_page.columnconfigure(0, weight=1)
        self.sniffer_page.rowconfigure(1, weight=1)
        self.main_notebook.add(self.sniffer_page, text="Sniffer")

        self.discovery_page = ttk.Frame(self.main_notebook)
        self.discovery_page.columnconfigure(0, weight=1)
        self.discovery_page.rowconfigure(3, weight=1)
        self.main_notebook.add(self.discovery_page, text="Bus Slave Finder")

        # Global Light/Dark control: root-level overlay in the top-right corner.
        # It is outside both tabs and therefore applies equally to Sniffer and
        # Bus Slave Finder. `place()` means it consumes no layout height.
        self.theme_overlay = ttk.Frame(self)
        self.theme_overlay.place(
            relx=1.0,
            x=-12,
            y=4,
            anchor="ne",
        )

        ttk.Label(
            self.theme_overlay,
            text="Modo escuro",
        ).grid(row=0, column=0, sticky="e", padx=(0, 6))

        self.dark_mode_var = tk.BooleanVar(value=self.initial_dark_mode)
        self.dark_mode_switch = ToggleSwitch(
            self.theme_overlay,
            variable=self.dark_mode_var,
            command=self.toggle_dark_mode,
            width=42,
            height=22,
        )
        self.dark_mode_switch.grid(row=0, column=1, sticky="e")

        self.language_label = ttk.Label(
            self.theme_overlay,
            text="Linguagem",
        )
        self.language_label.grid(
            row=0, column=2, sticky="e", padx=(18, 6)
        )
        self.language_var = tk.StringVar(value=self.current_language)
        self.language_combo = ttk.Combobox(
            self.theme_overlay,
            textvariable=self.language_var,
            values=LANGUAGE_CHOICES,
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=0, column=3, sticky="e")
        self.language_combo.bind(
            "<<ComboboxSelected>>", self.on_language_changed
        )
        self.theme_overlay.lift()

        # ==================================================================
        # Compact top workspace: configuration on the left, controls/stats
        # on the right.  This reclaims vertical space for the traffic view.
        # ==================================================================
        top_area = ttk.Frame(self.sniffer_page)
        top_area.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        # Keep the 3:2 workspace split independent of translated text widths.
        # Without a shared uniform group Tk first honours each child widget's
        # requested width, so changing language moves the two main rectangles.
        top_area.columnconfigure(0, weight=3, uniform="top_workspace")
        top_area.columnconfigure(1, weight=2, uniform="top_workspace")
        # The left Configuração card defines the natural top-workspace height.
        # The right stack stretches to exactly the same top/bottom limits.
        top_area.rowconfigure(0, weight=1)

        cfg = ttk.LabelFrame(top_area, text="Configuração")
        cfg.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        cfg.columnconfigure(0, weight=1)

        # Four compact equal columns.  Widgets keep the same fixed widths as
        # v2.6; only the card itself is narrower, eliminating wasted whitespace.
        config_grid = ttk.Frame(cfg)
        config_grid.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        for col in range(4):
            config_grid.columnconfigure(col, weight=1, uniform="sniffer_cfg")

        def config_cell(row, column):
            cell = ttk.Frame(config_grid)
            cell.grid(
                row=row, column=column, sticky="w",
                padx=(0 if column == 0 else 8, 8 if column < 3 else 0),
                pady=(0, 7),
            )
            return cell

        # Row 1 — physical mode / COM A / COM B / capture status
        cell = config_cell(0, 0)
        ttk.Label(cell, text="Modo físico").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.mode_var = tk.StringVar(value=sniffer_saved.get("physical_mode", "RS485 2-wire"))
        self.mode_combo = ttk.Combobox(
            cell, textvariable=self.mode_var, width=13, state="readonly",
            values=["RS485 2-wire", "RS232 single RX", "RS232 dual RX"],
        )
        self.mode_combo.grid(row=1, column=0, sticky="w")
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_mode_ui())

        cell = config_cell(0, 1)
        ttk.Label(cell, text="COM A").grid(row=0, column=0, sticky="w", pady=(0, 2))
        com_a_controls = ttk.Frame(cell)
        com_a_controls.grid(row=1, column=0, sticky="w")
        self.port_a_var = tk.StringVar()
        self.port_a_combo = ttk.Combobox(
            com_a_controls, textvariable=self.port_a_var, width=13, state="readonly"
        )
        self.port_a_combo.grid(row=0, column=0, sticky="w")
        self.port_a_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_com_status())
        self.refresh_a_btn = RefreshButton(com_a_controls, command=self.refresh_ports, size=24)
        self.refresh_a_btn.grid(row=0, column=1, sticky="w", padx=(4, 0))

        def _sync_sniffer_refresh_a_square(_event=None):
            height = self.port_a_combo.winfo_height()
            if height > 1:
                self.refresh_a_btn.configure(width=height, height=height)

        self.port_a_combo.bind("<Configure>", _sync_sniffer_refresh_a_square, add="+")

        cell = config_cell(0, 2)
        self.port_b_label = ttk.Label(cell, text="COM B")
        self.port_b_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        com_b_controls = ttk.Frame(cell)
        com_b_controls.grid(row=1, column=0, sticky="w")
        self.port_b_var = tk.StringVar()
        self.port_b_combo = ttk.Combobox(
            com_b_controls, textvariable=self.port_b_var, width=13, state="readonly"
        )
        self.port_b_combo.grid(row=0, column=0, sticky="w")
        self.port_b_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_com_status())
        self.refresh_b_btn = RefreshButton(com_b_controls, command=self.refresh_ports, size=24)
        self.refresh_b_btn.grid(row=0, column=1, sticky="w", padx=(4, 0))

        def _sync_sniffer_refresh_b_square(_event=None):
            height = self.port_b_combo.winfo_height()
            if height > 1:
                self.refresh_b_btn.configure(width=height, height=height)

        self.port_b_combo.bind("<Configure>", _sync_sniffer_refresh_b_square, add="+")

        cell = config_cell(0, 3)
        ttk.Label(cell, text="Estado").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.status_var = tk.StringVar(value="● Parado")
        ttk.Label(
            cell,
            textvariable=self.status_var,
            style="MBS.Status.TLabel",
            width=22,
            anchor="w",
        ).grid(
            row=1, column=0, sticky="w"
        )

        # Row 2 — serial format
        cell = config_cell(1, 0)
        ttk.Label(cell, text="Baud rate").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.baud_var = tk.StringVar(value=sniffer_saved.get("baud", "9600"))
        ttk.Combobox(
            cell, textvariable=self.baud_var, width=13,
            values=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
        ).grid(row=1, column=0, sticky="w")

        cell = config_cell(1, 1)
        ttk.Label(cell, text="Data bits").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.data_var = tk.StringVar(value=sniffer_saved.get("data_bits", "8"))
        ttk.Combobox(
            cell, textvariable=self.data_var, width=13, state="readonly",
            values=["5", "6", "7", "8"],
        ).grid(row=1, column=0, sticky="w")

        cell = config_cell(1, 2)
        ttk.Label(cell, text="Parity").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.parity_var = tk.StringVar(value=sniffer_saved.get("parity", "None"))
        ttk.Combobox(
            cell, textvariable=self.parity_var, width=13, state="readonly",
            values=["None", "Even", "Odd", "Mark", "Space"],
        ).grid(row=1, column=0, sticky="w")

        cell = config_cell(1, 3)
        ttk.Label(cell, text="Stop bits").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.stop_var = tk.StringVar(value=sniffer_saved.get("stop_bits", "1"))
        ttk.Combobox(
            cell, textvariable=self.stop_var, width=13, state="readonly",
            values=["1", "1.5", "2"],
        ).grid(row=1, column=0, sticky="w")

        # Row 3 — timing and display options
        cell = config_cell(2, 0)
        ttk.Label(cell, text="Frame gap").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.gap_mode_var = tk.StringVar(value=sniffer_saved.get("frame_gap_mode", "Auto"))
        self.gap_combo = ttk.Combobox(
            cell, textvariable=self.gap_mode_var, width=13, state="readonly",
            values=["Auto", "Manual"],
        )
        self.gap_combo.grid(row=1, column=0, sticky="w")
        self.gap_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_gap_state())

        cell = config_cell(2, 1)
        ttk.Label(cell, text="Gap manual (ms)").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.gap_ms_var = tk.StringVar(value=sniffer_saved.get("frame_gap_ms", ""))
        self.gap_entry = ttk.Entry(cell, textvariable=self.gap_ms_var, width=15, state="disabled")
        self.gap_entry.grid(row=1, column=0, sticky="w")

        cell = config_cell(2, 2)
        ttk.Label(cell, text="Visualização").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.auto_scroll_var = tk.BooleanVar(value=sniffer_saved.get("auto_scroll", True))
        ttk.Checkbutton(cell, text="Auto-scroll", variable=self.auto_scroll_var).grid(
            row=1, column=0, sticky="w"
        )

        cell = config_cell(2, 3)
        ttk.Label(cell, text="Pending timeout (s)").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.pending_timeout_var = tk.StringVar(value=sniffer_saved.get("pending_timeout_s", f"{DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS:g}"))
        # Direct numeric entry is cleaner here than tiny spin arrows. Range
        # validation still happens in get_pending_timeout_seconds().
        self.pending_timeout_entry = ttk.Entry(
            cell,
            textvariable=self.pending_timeout_var,
            width=13,
        )
        self.pending_timeout_entry.grid(row=1, column=0, sticky="w")
        ttk.Label(
            cell,
            text=(
                f"min {MIN_PENDING_REQUEST_TIMEOUT_SECONDS:g} / "
                f"default {DEFAULT_PENDING_REQUEST_TIMEOUT_SECONDS:g} / "
                f"max {MAX_PENDING_REQUEST_TIMEOUT_SECONDS:g}"
            ),
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        # COM status + mode help: compact footer inside the configuration card.
        com_status = ttk.Frame(cfg)
        com_status.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 3))
        ttk.Label(com_status, text="Estado COM").grid(
            row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14)
        )
        self.port_a_status_var = tk.StringVar(value="COM A - —")
        self.port_b_status_var = tk.StringVar(value="COM B - —")
        ttk.Label(com_status, textvariable=self.port_a_status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(com_status, textvariable=self.port_b_status_var).grid(
            row=1, column=1, sticky="w", pady=(1, 0)
        )

        self.mode_help_var = tk.StringVar()
        ttk.Label(cfg, textvariable=self.mode_help_var).grid(
            row=2, column=0, sticky="w", padx=10, pady=(2, 7)
        )

        # ------------------------------------------------------------------
        # Right-hand command/status panel.
        # ------------------------------------------------------------------
        side_panel = ttk.Frame(top_area)
        side_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        side_panel.columnconfigure(0, weight=1)
        side_panel.rowconfigure(0, weight=0)
        side_panel.rowconfigure(1, weight=1)

        actions = ttk.LabelFrame(side_panel, text="Controlos")
        # Same top coordinate as Configuração; only the gap below Controlos
        # separates it from Estatísticas.
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        actions.columnconfigure(0, weight=1, uniform="action_columns")
        actions.columnconfigure(1, weight=1, uniform="action_columns")

        self.start_btn = ttk.Button(
            actions, text="Iniciar Captura", command=self.start_capture,
            style="MBS.Primary.TButton"
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=(7, 3))

        self.stop_btn = ttk.Button(
            actions, text="Parar", command=self.stop_capture, state="disabled",
            style="MBS.Toolbar.TButton"
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(7, 3))

        self.restart_btn = ttk.Button(
            actions, text="Reiniciar COM", command=self.restart_com_port,
            style="MBS.Toolbar.TButton"
        )
        self.restart_btn.grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=3)

        ttk.Button(
            actions, text="Limpar", command=self.clear_view,
            style="MBS.Toolbar.TButton"
        ).grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=3)

        ttk.Button(
            actions, text="Abrir pasta de logs", command=self.open_log_folder,
            style="MBS.Toolbar.TButton"
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=3)

        self.sim_btn = None
        if debug_sim == 1:
            self.sim_btn = ttk.Button(
                actions, text="Simulação", command=self.run_simulation,
                style="MBS.Toolbar.TButton"
            )
            self.sim_btn.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=3)
            options_row = 4
        else:
            options_row = 3

        options_bar = ttk.Frame(actions)
        options_bar.grid(
            row=options_row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(3, 7),
        )
        options_bar.columnconfigure(2, weight=1)

        self.separate_transactions_var = tk.BooleanVar(
            value=sniffer_saved.get("separate_transactions", True)
        )
        ttk.Checkbutton(
            options_bar,
            text="Separar transações",
            variable=self.separate_transactions_var,
            command=self.render_filtered_view,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.highlight_anomalies_var = tk.BooleanVar(
            value=sniffer_saved.get("highlight_results", False)
        )
        ttk.Checkbutton(
            options_bar,
            text="Realçar resultados",
            variable=self.highlight_anomalies_var,
            command=self.on_highlight_anomalies_changed,
        ).grid(row=0, column=1, sticky="w")

        self.bus_activity_var = tk.StringVar(value="BUS ○")
        ttk.Label(
            options_bar,
            textvariable=self.bus_activity_var,
            style="MBS.Status.TLabel",
            anchor="e",
            width=9,
        ).grid(row=0, column=2, sticky="e")

        stats = ttk.LabelFrame(side_panel, text="Estatísticas da sessão")
        # Expand vertically into all remaining space so the lower border always
        # lines up with the lower border of Configuração, even if Configuração
        # changes height in the future.
        stats.grid(row=1, column=0, sticky="nsew")
        for col in range(4):
            stats.columnconfigure(col, weight=1, uniform="stats")

        self.stat_requests_var = tk.StringVar(value="Pedidos: 0")
        self.stat_responses_var = tk.StringVar(value="Respostas: 0")
        self.stat_pending_var = tk.StringVar(value="Pendentes: 0")
        self.stat_timeouts_var = tk.StringVar(value="Timeouts: 0")
        self.stat_crc_var = tk.StringVar(value="Erros de CRC: 0")
        self.stat_exceptions_var = tk.StringVar(value="Exceções: 0")
        self.stat_raw_var = tk.StringVar(value="RAW: 0")
        self.stat_slaves_var = tk.StringVar(value="Slaves: 0")

        stat_vars = [
            self.stat_requests_var,
            self.stat_responses_var,
            self.stat_pending_var,
            self.stat_timeouts_var,
            self.stat_crc_var,
            self.stat_exceptions_var,
            self.stat_raw_var,
            self.stat_slaves_var,
        ]
        for idx, var in enumerate(stat_vars):
            ttk.Label(stats, textvariable=var, style="MBS.Stat.TLabel").grid(
                row=idx // 4,
                column=idx % 4,
                sticky="w",
                padx=(8, 5),
                pady=(6 if idx < 4 else 4, 6),
            )

        # Notebook
        notebook = ttk.Notebook(self.sniffer_page)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 8))

        parsed = ttk.Frame(notebook)
        parsed.columnconfigure(0, weight=1)
        parsed.rowconfigure(1, weight=1)
        notebook.add(parsed, text="Tráfego")

        filter_bar = ttk.Frame(parsed)
        filter_bar.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=4,
            pady=(4, 3),
        )
        filter_bar.columnconfigure(8, weight=1)
        # "Pesquisa" is wider than "Search". Keep its canonical PT cell width
        # reserved so the search Entry never moves when language changes.
        filter_bar.columnconfigure(7, minsize=65)

        ttk.Label(filter_bar, text="Filtros").grid(
            row=0, column=0, sticky="w", padx=(2, 6)
        )

        self.advanced_filter_type_var = tk.StringVar(value="Todos")
        type_filter = ttk.Combobox(
            filter_bar,
            textvariable=self.advanced_filter_type_var,
            state="readonly",
            width=11,
            values=(
                "Todos",
                "Requests",
                "Responses",
                "Exceptions",
                "CRC errors",
                "Timeouts",
                "RAW",
            ),
        )
        type_filter.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.advanced_filter_type_combo = type_filter
        type_filter.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.render_filtered_view(),
        )

        ttk.Label(filter_bar, text="FC (hex)").grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        self.advanced_filter_fc_var = tk.StringVar(value="")
        fc_filter = ttk.Entry(
            filter_bar,
            textvariable=self.advanced_filter_fc_var,
            width=7,
        )
        fc_filter.grid(row=0, column=3, sticky="w", padx=(0, 8))

        ttk.Label(filter_bar, text="Resp. >").grid(
            row=0, column=4, sticky="w", padx=(0, 4)
        )
        self.advanced_filter_response_ms_var = tk.StringVar(value="")
        response_filter = ttk.Entry(
            filter_bar,
            textvariable=self.advanced_filter_response_ms_var,
            width=7,
        )
        response_filter.grid(row=0, column=5, sticky="w")
        ttk.Label(filter_bar, text="ms").grid(
            row=0, column=6, sticky="w", padx=(3, 8)
        )

        ttk.Label(filter_bar, text="Pesquisa").grid(
            row=0, column=7, sticky="w", padx=(0, 4)
        )
        self.advanced_filter_text_var = tk.StringVar(value="")
        search_filter = ttk.Entry(
            filter_bar,
            textvariable=self.advanced_filter_text_var,
            width=22,
        )
        search_filter.grid(row=0, column=8, sticky="ew")

        filter_actions = ttk.Frame(filter_bar)
        filter_actions.grid(row=0, column=9, sticky="e")
        ttk.Button(
            filter_actions,
            text="Limpar filtros",
            command=self.clear_advanced_filters,
            style="MBS.Compact.TButton",
        ).grid(row=0, column=0, padx=(6, 4))
        ttk.Button(
            filter_actions,
            text="Exportar CSV",
            command=self.export_session_csv,
            style="MBS.Compact.TButton",
        ).grid(row=0, column=1)

        for variable in (
            self.advanced_filter_fc_var,
            self.advanced_filter_response_ms_var,
            self.advanced_filter_text_var,
        ):
            variable.trace_add(
                "write",
                self.schedule_advanced_filter_refresh,
            )

        cols = ("time", "delta", "response", "channel", "type", "slave", "fc", "details", "crc")
        # Dedicated style so wrapped multi-line rows do not affect unrelated
        # widgets. Treeview has one row height for the whole table, therefore
        # the row height is adjusted to the largest wrapped Details cell that
        # is currently visible.
        self.tree_style_name = "MBSniffer.Treeview"
        self.tree_style = ttk.Style(self)
        self.tree = ttk.Treeview(
            parsed,
            columns=cols,
            show="headings",
            selectmode="browse",
            style=self.tree_style_name
        )

        self._tree_reflow_after_id = None
        self.tree_detail_min_width_px = 220
        self.tree_detail_border_reserve_px = 18

        # Internal sort state. The user changes it only by clicking Hora.
        self.time_order_var = tk.StringVar(
            value="Crescente — antigo → recente"
        )

        self.tree_headings = {
            "time": "Hora ↑",
            "delta": "Δt (ms)",
            "response": "Resp. (ms)",
            "channel": "COM",
            "type": "Tipo",
            "slave": "Slave ▾",
            "fc": "FC",
            "details": "Detalhes",
            "crc": "CRC",
        }

        # Keep columns as compact as possible while leaving breathing room
        # between the longest text and the column borders.
        self.tree_column_padding_px = 28  # total horizontal padding
        self.tree_cell_font = tkfont.nametofont("TkDefaultFont")
        try:
            heading_font_name = ttk.Style(self).lookup("Treeview.Heading", "font")
            self.tree_heading_font = (
                tkfont.nametofont(heading_font_name)
                if heading_font_name
                else self.tree_cell_font
            )
        except Exception:
            self.tree_heading_font = self.tree_cell_font

        self.tree_font_linespace = max(
            1,
            int(self.tree_cell_font.metrics("linespace"))
        )
        self.tree_single_line_rowheight = max(
            20,
            self.tree_font_linespace + 5
        )
        self.tree_style.configure(
            self.tree_style_name,
            rowheight=self.tree_single_line_rowheight
        )

        for col in cols:
            align = "w" if col == "details" else "center"
            self.tree.heading(
                col,
                text=self.tree_headings[col],
                anchor=align
            )
            initial_width = self.measure_tree_column_width(
                col,
                [],
                heading_text=self.tree_headings[col]
            )
            self.tree.column(
                col,
                width=initial_width,
                minwidth=initial_width,
                anchor=align,
                stretch=(col == "details")
            )

        self.tree.heading(
            "time",
            text=self.tree_headings["time"],
            anchor="center",
            command=self.toggle_time_order
        )
        self.tree.heading(
            "slave",
            text=self.tree_headings["slave"],
            anchor="center",
            command=self.show_slave_filter_menu
        )

        # Popup menu opened directly from the Slave column heading.
        self.slave_filter_menu = tk.Menu(self, tearoff=False)

        # Right-click actions for the selected traffic frame.
        self.traffic_context_menu = tk.Menu(self, tearoff=False)
        self.traffic_context_menu.add_command(
            label="Copiar Raw Hex",
            command=self.copy_selected_raw,
        )
        self.traffic_context_menu.add_command(
            label="Copiar frame descodificado",
            command=self.copy_selected_decoded,
        )
        self.traffic_context_menu.add_separator()
        self.traffic_context_menu.add_command(
            label="Filtrar por este Slave",
            command=self.context_filter_selected_slave,
        )
        self.traffic_context_menu.add_command(
            label="Filtrar por este FC",
            command=self.context_filter_selected_fc,
        )
        self.traffic_context_menu.add_command(
            label="Mostrar apenas esta transação",
            command=self.context_show_selected_transaction,
        )
        self.traffic_context_menu.add_command(
            label="Limpar filtro de transação",
            command=self.clear_transaction_filter,
        )

        ys = ttk.Scrollbar(parsed, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        ys.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)
        self.tree.bind("<Button-3>", self.show_traffic_context_menu, add="+")
        self.tree.bind("<Configure>", self.schedule_tree_reflow)
        self.configure_anomaly_tags(self.initial_dark_mode)

        raw = ttk.Frame(notebook)
        raw.columnconfigure(0, weight=1)
        raw.rowconfigure(0, weight=1)
        notebook.add(raw, text="Raw Hex / Log")

        self.raw_text = tk.Text(
            raw,
            wrap="word",
            font=("Consolas", 10)
        )
        self.raw_text_font = tkfont.Font(font=self.raw_text.cget("font"))
        self.raw_text.bind("<Configure>", self.schedule_raw_separator_reflow)

        raw_y = ttk.Scrollbar(raw, orient="vertical", command=self.raw_text.yview)
        self.raw_text.configure(yscrollcommand=raw_y.set)
        self.raw_text.grid(row=0, column=0, sticky="nsew")
        raw_y.grid(row=0, column=1, sticky="ns")

        # Bus Health — session-level diagnostic metrics.
        self.health_frame = ttk.Frame(notebook)
        health_frame = self.health_frame
        health_frame.columnconfigure(0, weight=1, uniform="health")
        health_frame.columnconfigure(1, weight=1, uniform="health")
        health_frame.columnconfigure(2, weight=1, uniform="health")
        health_frame.rowconfigure(0, weight=1)
        notebook.add(health_frame, text="Bus Health")

        traffic_health = ttk.LabelFrame(
            health_frame,
            text="Tráfego",
        )
        traffic_health.grid(
            row=0, column=0, sticky="nsew", padx=(6, 3), pady=6
        )
        traffic_health.columnconfigure(1, weight=1)

        response_health = ttk.LabelFrame(
            health_frame,
            text="Tempos de resposta",
        )
        response_health.grid(
            row=0, column=1, sticky="nsew", padx=3, pady=6
        )
        response_health.columnconfigure(1, weight=1)

        quality_health = ttk.LabelFrame(
            health_frame,
            text="Qualidade",
        )
        quality_health.grid(
            row=0, column=2, sticky="nsew", padx=(3, 6), pady=6
        )
        quality_health.columnconfigure(1, weight=1)

        self.health_requests_var = tk.StringVar(value="0")
        self.health_responses_var = tk.StringVar(value="0")
        self.health_crc_count_var = tk.StringVar(value="0")
        self.health_timeout_count_var = tk.StringVar(value="0")
        self.health_exception_count_var = tk.StringVar(value="0")
        self.health_req_rate_var = tk.StringVar(value="0.00 req/s")
        self.health_resp_avg_var = tk.StringVar(value="—")
        self.health_resp_min_var = tk.StringVar(value="—")
        self.health_resp_max_var = tk.StringVar(value="—")
        self.health_p95_var = tk.StringVar(value="—")
        self.health_nonvalidated_rate_var = tk.StringVar(value="0.00 %")
        self.health_timeout_rate_var = tk.StringVar(value="0.00 %")
        self.health_bus_load_var = tk.StringVar(value="0.00 %")
        self.health_slaves_var = tk.StringVar(value="0")
        self.health_total_bytes_var = tk.StringVar(value="0")
        self.health_slowest_var = tk.StringVar(value="—")
        self.health_exception_slaves_var = tk.StringVar(value="—")

        self._health_metric_groups = []

        def health_item(parent, label, variable, *, wraplength=0):
            return (
                ttk.Label(parent, text=label),
                ttk.Label(
                    parent,
                    textvariable=variable,
                    anchor="e",
                    wraplength=wraplength,
                    justify="right",
                ),
            )

        traffic_pairs = [
            health_item(traffic_health, "Pedidos", self.health_requests_var),
            health_item(traffic_health, "Respostas", self.health_responses_var),
            health_item(traffic_health, "Taxa de pedidos", self.health_req_rate_var),
            health_item(traffic_health, "Slaves ativos", self.health_slaves_var),
            health_item(traffic_health, "Bytes observados", self.health_total_bytes_var),
            health_item(traffic_health, "Utilização do bus ~", self.health_bus_load_var),
        ]
        response_pairs = [
            health_item(response_health, "Média", self.health_resp_avg_var),
            health_item(response_health, "Mínimo", self.health_resp_min_var),
            health_item(response_health, "Máximo", self.health_resp_max_var),
            health_item(response_health, "P95", self.health_p95_var),
            health_item(response_health, "Slave mais lento", self.health_slowest_var),
        ]
        quality_pairs = [
            health_item(quality_health, "Erros de CRC", self.health_crc_count_var),
            health_item(quality_health, "Bytes não validados", self.health_nonvalidated_rate_var),
            health_item(quality_health, "Timeouts", self.health_timeout_count_var),
            health_item(quality_health, "Taxa de timeout", self.health_timeout_rate_var),
            health_item(quality_health, "Exceções", self.health_exception_count_var),
            health_item(
                quality_health,
                "Exceções / Slave",
                self.health_exception_slaves_var,
                wraplength=190,
            ),
        ]

        self._health_metric_groups = [
            (traffic_health, traffic_pairs),
            (response_health, response_pairs),
            (quality_health, quality_pairs),
        ]
        self._health_cards = (
            traffic_health,
            response_health,
            quality_health,
        )
        self._health_layout_compact = False
        self._health_full_required_card_height = None
        self._bus_health_layout_after_id = None

        # Start with the normal layout, then adapt only if the real available
        # height is insufficient.
        self._apply_bus_health_layout(False)

        health_frame.bind(
            "<Configure>",
            self._schedule_bus_health_layout_sync,
            add="+",
        )
        notebook.bind(
            "<<NotebookTabChanged>>",
            self._schedule_bus_health_layout_sync,
            add="+",
        )
        self.after_idle(self._initialize_bus_health_layout)

        # Help tab
        help_frame = ttk.Frame(notebook)
        help_frame.columnconfigure(0, weight=1)
        help_frame.rowconfigure(0, weight=1)
        notebook.add(help_frame, text="Ajuda / Ligações")

        self.help_text = tk.Text(
            help_frame,
            wrap="word",
            font=("Segoe UI", 10),
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=5
        )
        help_scroll = ttk.Scrollbar(help_frame, orient="vertical", command=self.help_text.yview)
        self.help_text.configure(yscrollcommand=help_scroll.set)
        self.help_text.grid(row=0, column=0, sticky="nsew")
        help_scroll.grid(row=0, column=1, sticky="ns")

        self.help_text.tag_configure("title", font=("Segoe UI", 14, "bold"), spacing1=8, spacing3=8)
        self.help_text.tag_configure("heading", font=("Segoe UI", 11, "bold"), spacing1=10, spacing3=4)
        self.help_text.tag_configure("subheading", font=("Segoe UI", 10, "bold"), spacing1=6, spacing3=2)
        self.help_text.tag_configure("mono", font=("Consolas", 10), lmargin1=18, lmargin2=18)
        self.help_text.tag_configure("warning", font=("Segoe UI", 10, "bold"), lmargin1=12, lmargin2=12)
        self.help_text.tag_configure("bullet", lmargin1=12, lmargin2=28)

        def h(text_value, tag=None):
            self.help_text.insert("end", text_value, tag)

        max_ui_frames_text = f"{MAX_UI_FRAMES:_}".replace("_", " ")
        max_raw_lines_text = f"{MAX_RAW_TEXT_LINES:_}".replace("_", " ")

        h("MBSniffer — Ajuda e ligações\n", "title")
        h(
            "O MBSniffer foi pensado para diagnóstico de comunicações Modbus RTU. "
            "O separador Sniffer é passivo: abre a(s) porta(s) COM para receção e "
            "não transmite pedidos. O separador Bus Slave Finder é uma ferramenta "
            "ativa de pesquisa e deve ser utilizado apenas quando não existe outro "
            "master ativo no mesmo barramento.\n"
        )

        h("Início rápido — Sniffer\n", "heading")
        h("1. Escolhe o modo físico correto: RS485 2-wire, RS232 single RX ou RS232 dual RX.\n", "bullet")
        h("2. Seleciona a(s) porta(s) COM e os parâmetros série da comunicação observada.\n", "bullet")
        h("3. Mantém Frame gap em Auto, salvo quando tens uma razão concreta para o ajustar.\n", "bullet")
        h("4. Clica em “Iniciar Captura” e confirma atividade através de BUS ● RX.\n", "bullet")
        h("5. Usa Tráfego para diagnóstico rápido e Raw Hex / Log para confirmar os bytes reais.\n", "bullet")
        h("6. Seleciona um frame para obter a análise detalhada no Frame Inspector.\n", "bullet")

        h("1. RS485 2-wire\n", "heading")
        h(
            "Neste modo uma única COM observa pedidos e respostas no mesmo par diferencial. "
            "O adaptador do sniffer deve ser ligado em paralelo e não deve atuar como master.\n"
        )
        h("Ligação típica:\n", "subheading")
        h(
            "        Equipamento A          Equipamento B\n"
            "             D+ --------------- D+\n"
            "             D- --------------- D-\n"
            "               \\               /\n"
            "                \\             /\n"
            "                 D+           D-\n"
            "                  USB-RS485 sniffer\n\n",
            "mono"
        )
        h("• Liga D+ do sniffer em paralelo com D+ do barramento.\n", "bullet")
        h("• Liga D− do sniffer em paralelo com D− do barramento.\n", "bullet")
        h(
            "• Se existir C/COM/0 V de referência, liga-o apenas quando souberes que "
            "corresponde à referência correta da interface RS485.\n",
            "bullet"
        )
        h(
            "• Não acrescentes uma terceira resistência de 120 Ω se o barramento já "
            "estiver terminado nas duas extremidades.\n",
            "warning"
        )
        h(
            "• Se o adaptador USB-RS485 tiver terminação ou bias selecionáveis, deixa-os "
            "desativados durante uma captura passiva, salvo se forem intencionalmente "
            "necessários na instalação.\n",
            "bullet"
        )
        h(
            "• A/B não é uma nomenclatura universal: fabricantes diferentes podem usar "
            "polaridades opostas. Dá prioridade a D+/D− e à documentação do equipamento.\n",
            "bullet"
        )

        h("2. RS232 single RX\n", "heading")
        h(
            "Observa apenas uma direção RS232. O RS232 é full-duplex: cada direção utiliza "
            "uma linha TX independente, pelo que uma única entrada RX não consegue observar "
            "simultaneamente os dois sentidos.\n"
        )
        h(
            "        Equipamento A                    Equipamento B\n"
            "             TX ----------------------------> RX\n"
            "              \\\n"
            "               \\----> RX do USB-RS232 sniffer (COM A)\n"
            "\n"
            "             GND --------------------------- GND\n"
            "               \\--------------------------> GND sniffer\n\n"
            "        TX do sniffer: NÃO LIGAR\n\n",
            "mono"
        )
        h("• Liga RX do sniffer ao TX da direção que pretendes observar.\n", "bullet")
        h("• Liga também o GND comum.\n", "bullet")
        h("• Deixa fisicamente desligado o TX do adaptador usado como sniffer.\n", "warning")

        h("3. RS232 dual RX\n", "heading")
        h(
            "Permite observar as duas direções RS232 ao mesmo tempo. São necessários "
            "dois canais RX independentes, normalmente dois adaptadores USB-RS232.\n"
        )
        h(
            "        Equipamento A                    Equipamento B\n"
            "             TX ----------------------------> RX\n"
            "              \\----> RX sniffer COM A   (A → B)\n"
            "\n"
            "             RX <----------------------------- TX\n"
            "                                      \\----> RX sniffer COM B   (B → A)\n"
            "\n"
            "             GND ---------------------------- GND\n"
            "               \\---------------------------- GND COM A\n"
            "                \\--------------------------- GND COM B\n\n"
            "        TX de ambos os sniffers: NÃO LIGAR\n\n",
            "mono"
        )
        h("• COM A é apresentada como A→B e COM B como B→A.\n", "bullet")
        h("• As duas COM devem usar os mesmos parâmetros série da ligação observada.\n", "bullet")

        h("RS232 não é TTL\n", "heading")
        h(
            "Não ligues sinais RS232 diretamente a interfaces USB-TTL/UART de 3,3 V ou "
            "5 V. Usa um adaptador USB-RS232 com transceiver apropriado aos níveis RS232.\n",
            "warning"
        )

        h("Parâmetros da comunicação série\n", "heading")
        h(
            "Baud, Data bits, Parity e Stop bits têm de coincidir com a comunicação real. "
            "Parâmetros errados podem produzir bytes aparentemente aleatórios, frames com "
            "CRC inválido ou ausência total de frames reconhecíveis.\n"
        )
        h("• Baud rate — velocidade em bit/s, por exemplo 9600 ou 19200.\n", "bullet")
        h("• Data bits — normalmente 8 em Modbus RTU.\n", "bullet")
        h("• Parity — None, Even, Odd, Mark ou Space, conforme a instalação.\n", "bullet")
        h("• Stop bits — 1, 1.5 ou 2, conforme a configuração observada.\n", "bullet")

        h("Frame gap\n", "heading")
        h(
            "Em Auto, o programa usa 3,5 tempos de carácter até 19200 bit/s, inclusive. "
            "Acima de 19200 bit/s usa o t3.5 fixo de 1,750 ms recomendado para Modbus RTU. "
            "O modo Manual permite definir outro valor em milissegundos para diagnóstico "
            "de equipamentos ou drivers com comportamento particular.\n"
        )
        h(
            "Os adaptadores USB e o Windows podem agrupar bytes e introduzir latência. "
            "Por isso, os timestamps do MBSniffer são úteis para diagnóstico de sequência "
            "e tempos relativos, mas não substituem um analisador lógico quando são "
            "necessárias medições temporais de elevada precisão.\n"
        )

        h("Pending timeout\n", "heading")
        h(
            "Define durante quanto tempo um REQUEST CRC-válido pode permanecer à espera de "
            "uma RESPONSE/EXCEPTION emparelhável. Ao expirar, o REQUEST original é marcado "
            "como timeout e aumenta os contadores de Timeout/Timeout rate.\n"
        )
        h(
            f"Intervalo permitido: {MIN_PENDING_REQUEST_TIMEOUT_SECONDS:g} a "
            f"{MAX_PENDING_REQUEST_TIMEOUT_SECONDS:g} s. O valor deve ser superior ao "
            "tempo de resposta máximo normal da instalação para evitar falsos timeouts.\n"
        )

        h("Como interpretar a tabela Tráfego\n", "heading")
        h("• REQUEST — pedido Modbus RTU reconhecido pelo parser.\n", "bullet")
        h("• RESPONSE — resposta Modbus RTU reconhecida que não é uma EXCEPTION.\n", "bullet")
        h(
            "• EXCEPTION — resposta Modbus com Function Code de exceção (bit 7 ativo). "
            "Detalhes mostra o código e a descrição normalizada.\n",
            "bullet"
        )
        h("• CRC OK — CRC recebido coincide com o CRC calculado.\n", "bullet")
        h(
            "• CRC ERROR — a estrutura parece um frame suportado, mas o CRC recebido não "
            "coincide com o CRC calculado.\n",
            "bullet"
        )
        h(
            "• RAW/UNSYNC — bytes descartados durante uma recuperação de sincronismo antes "
            "de ser encontrado, mais à frente no mesmo burst, um frame de estrutura "
            "reconhecida com CRC válido.\n",
            "bullet"
        )
        h(
            "• RAW/UNPARSED — restante conjunto de bytes que não pôde ser interpretado nem "
            "ressincronizado como um frame Modbus válido. É este estado que aparece, por "
            "exemplo, num bloco de ruído sem um frame válido posterior no mesmo burst.\n",
            "bullet"
        )
        h(
            "RAW/UNSYNC e RAW/UNPARSED são portanto situações diferentes e ambas podem "
            "aparecer na coluna Tipo. Nenhuma delas representa uma resposta Modbus válida.\n"
        )

        h("Colunas da tabela Tráfego\n", "heading")
        h("• Hora — timestamp do início do burst/frame processado.\n", "bullet")
        h("• Δt — intervalo desde o frame anterior observada.\n", "bullet")
        h(
            "• Resp. — tempo entre um REQUEST e a RESPONSE/EXCEPTION emparelhada. "
            "Fica vazio quando não existe um par válido.\n",
            "bullet"
        )
        h("• COM — identifica o canal de captura: BUS em RS485, A→B/B→A em RS232 dual RX e SIM no modo de desenvolvimento. Não representa necessariamente o número COM do Windows.\n", "bullet")
        h("• Tipo — REQUEST, RESPONSE, EXCEPTION ou um estado RAW.\n", "bullet")
        h("• Slave — Unit/Slave ID Modbus quando identificável.\n", "bullet")
        h("• FC — Function Code hexadecimal observado no frame.\n", "bullet")
        h("• Detalhes — endereço, quantidade, dados ou descrição da operação.\n", "bullet")
        h("• CRC — OK, ERROR ou ? quando não existe um frame Modbus completo.\n", "bullet")

        h("Emparelhamento REQUEST / RESPONSE\n", "heading")
        h(
            "Modbus RTU não possui Transaction ID. O MBSniffer emparelha frames por "
            "(Slave ID, Function Code) em ordem FIFO. Isto é apropriado para tráfego RTU "
            "normal, mas pode tornar-se ambíguo se existirem pedidos sobrepostos com o mesmo "
            "Slave e FC antes das respostas correspondentes.\n"
        )
        h(
            "Uma EXCEPTION usa internamente o Function Code base para emparelhamento. "
            "Exemplo: uma resposta 0x83 é associada a um REQUEST FC03 quando existe um "
            "pedido pendente compatível.\n"
        )

        h("PDU Address, 1-based e Qty\n", "heading")
        h(
            "PDU Address é o endereço codificado no pedido Modbus. 1-based é simplesmente "
            "PDU Address + 1 e serve para comparação com manuais que numeram o primeiro "
            "registo/coil como 1. Qty é a quantidade pedida.\n"
        )
        h(
            "Estes campos pertencem ao REQUEST. Uma RESPONSE não repete automaticamente "
            "Address ou Qty no protocolo, por isso o MBSniffer não inventa esses campos na "
            "linha da resposta.\n"
        )

        h("Códigos de exceção Modbus\n", "heading")
        h("• 0x01 — Illegal Function: função não suportada ou não permitida.\n", "bullet")
        h("• 0x02 — Illegal Data Address: endereço/gama de endereços inválida.\n", "bullet")
        h("• 0x03 — Illegal Data Value: valor, quantidade ou campo inválido.\n", "bullet")
        h("• 0x04 — Server Device Failure: falha interna do dispositivo.\n", "bullet")
        h("• 0x05 — Acknowledge: pedido aceite; processamento ainda em curso.\n", "bullet")
        h("• 0x06 — Server Device Busy: dispositivo temporariamente ocupado.\n", "bullet")
        h("• 0x08 — Memory Parity Error.\n", "bullet")
        h("• 0x0A — Gateway Path Unavailable.\n", "bullet")
        h("• 0x0B — Gateway Target Device Failed to Respond.\n", "bullet")

        h("Filtros avançados\n", "heading")
        h(
            "A barra no topo de Tráfego permite combinar vários filtros sem alterar os "
            "dados originais da sessão:\n"
        )
        h("• Tipo — Todos, Requests, Responses, Exceptions, CRC errors, Timeouts ou RAW.\n", "bullet")
        h("• FC (hex) — por exemplo 03, 04, 10 ou 0x04.\n", "bullet")
        h("• Resp. > — mostra apenas respostas acima do limite indicado em ms.\n", "bullet")
        h(
            "• Pesquisa — procura texto em Detalhes, Raw Hex, Slave, FC, Tipo e COM/canal.\n",
            "bullet"
        )
        h(
            "O filtro Slave continua disponível no cabeçalho da coluna e combina-se com "
            "os filtros avançados. “Limpar filtros” repõe todos os filtros de visualização. "
            "Os filtros não alteram as estatísticas nem o conteúdo do log de captura.\n"
        )

        h("Realçar resultados\n", "heading")
        h(
            "Esta opção vem desligada por defeito para manter a tabela neutra. Quando está "
            "ativa, os resultados passam a ser diferenciados por cor: uma transação normal "
            "concluída com RESPONSE CRC-válida fica verde; CRC error, timeout, Exception, "
            "RAW e resposta lenta mantêm as respetivas cores de diagnóstico.\n"
        )
        h(
            "Numa transação normal concluída com sucesso, tanto o REQUEST como a RESPONSE "
            "correspondente ficam verdes. Um REQUEST ainda pendente permanece neutro. "
            "Uma resposta lenta continua com a cor de resposta lenta, mesmo sendo válida, "
            "para não esconder o resultado de diagnóstico.\n"
        )
        h(
            f"Uma resposta é considerada lenta a partir de "
            f"{SLOW_RESPONSE_THRESHOLD_MS:g} ms. Este limite é uma referência visual do "
            "MBSniffer; deve ser interpretado no contexto do equipamento e do ciclo de poll.\n"
        )

        h("Código de cores dos resultados\n", "heading")
        h("• Verde — Sucesso: REQUEST/RESPONSE normal, emparelhada e com CRC válido.\n", "bullet")
        h(
            f"• Amarelo — Resposta lenta: tempo de resposta >= "
            f"{SLOW_RESPONSE_THRESHOLD_MS:g} ms.\n",
            "bullet"
        )
        h("• Vermelho — CRC Error ou resposta Modbus Exception.\n", "bullet")
        h("• Laranja — Timeout: REQUEST expirou sem resposta emparelhada.\n", "bullet")
        h("• Roxo — RAW/UNSYNC ou RAW/UNPARSED: bytes sem frame Modbus válido.\n", "bullet")
        h(
            "Com “Realçar resultados” desligado, a tabela permanece neutra. O Frame "
            "Inspector continua a indicar a classificação do resultado em texto; quando "
            "o destaque está ligado, o campo Resultado também usa a respetiva cor.\n"
        )

        h("Frame Inspector\n", "heading")
        h(
            "Seleciona uma linha de Tráfego para analisar o frame sem ter de interpretar "
            "manualmente todos os bytes. O Inspector mostra Slave, Tipo, Function Code + "
            "nome, tempo de resposta, Resultado, PDU Address, 1-based, "
            "Qty, ByteCount, CRC recebido, CRC calculado, dados/registos/Exception e Raw Hex.\n"
        )
        h(
            "“Recolher” esconde o conteúdo do Inspector e devolve espaço vertical à tabela. "
            "“Expandir” volta a apresentar a análise.\n"
        )

        h("Menu de contexto do Tráfego\n", "heading")
        h("Clica com o botão direito numa frame real para:\n")
        h("• Copiar Raw Hex.\n", "bullet")
        h("• Copiar o frame descodificado.\n", "bullet")
        h("• Filtrar pelo Slave dessa frame.\n", "bullet")
        h("• Filtrar pelo Function Code dessa frame.\n", "bullet")
        h("• Mostrar apenas a transação REQUEST/RESPONSE correspondente.\n", "bullet")
        h("• Limpar o filtro temporário de transação.\n", "bullet")

        h("Bus Health\n", "heading")
        h(
            "O separador Bus Health resume a qualidade e o desempenho da sessão sem "
            "substituir a tabela de frames.\n"
        )
        h("• Pedidos / Respostas — contadores da sessão.\n", "bullet")
        h("• Taxa de pedidos — número médio de pedidos observados por segundo.\n", "bullet")
        h("• Slaves ativos — IDs Modbus válidos observados na sessão.\n", "bullet")
        h("• Bytes observados — soma dos bytes entregues ao parser.\n", "bullet")
        h(
            "• Utilização bus ~ — estimativa com base em bytes observados, baud, data bits, "
            "parity e stop bits. É aproximada e depende do ponto de captura.\n",
            "bullet"
        )
        h("• Média / Mínimo / Máximo — tempos de resposta emparelhados.\n", "bullet")
        h("• P95 — 95% das respostas medidas ficaram abaixo ou iguais a este valor.\n", "bullet")
        h(
            "• Slave mais lento — Slave com maior tempo médio de resposta entre as amostras "
            "observadas.\n",
            "bullet"
        )
        h("• Bytes não validados — percentagem dos bytes observados que pertencem a frames com CRC inválido ou a blocos RAW. Não prova, por si só, a existência de ruído elétrico; parâmetros série errados, captura incompleta ou funções não suportadas pelo parser também podem produzir RAW.\n", "bullet")
        h("• Taxa de timeout — percentagem de REQUEST que expiraram sem resposta emparelhada.\n", "bullet")
        h("• Exceções / Slave — distribuição das respostas Exception por Slave ID.\n", "bullet")

        h("Indicador BUS RX\n", "heading")
        h(
            "BUS ● RX pulsa brevemente quando chega um lote de frames à interface. Em repouso "
            "é apresentado BUS ○. Serve apenas como confirmação visual de atividade recebida; "
            "não representa qualidade elétrica nem garante que os frames sejam válidos.\n"
        )

        h("Raw Hex / Log\n", "heading")
        h(
            "Mostra os bytes capturados em hexadecimal com informação de contexto. As linhas "
            "longas fazem wrap à largura disponível. A vista acompanha os mesmos filtros "
            "visuais usados em Tráfego; o ficheiro TXT em disco, quando existe, mantém a "
            "captura completa e não é truncado pelos filtros.\n"
        )

        h("Exportar CSV\n", "heading")
        h(
            "Exportar CSV grava os frames atualmente retidos no histórico da interface em "
            "UTF-8 compatível com Excel. Inclui Time, Δt, Response time, Channel, Type, "
            "Slave, FC, Details, CRC, Raw, PDU Address, 1-based, Qty, ByteCount, Timeout "
            "e classe de anomalia.\n"
        )
        h(
            f"A interface mantém aproximadamente os últimos {max_ui_frames_text} frames. "
            "Por isso, em sessões maiores o CSV representa o histórico ainda retido pela GUI, "
            "enquanto o TXT de uma captura real continua a ser o registo completo em disco.\n"
        )

        h("Logs de captura\n", "heading")
        h(
            "O log TXT só é criado depois de chegar tráfego real. Iniciar e parar sem receber "
            "frames não cria um ficheiro vazio.\n"
        )
        h("Pasta dos logs:\n")
        h("        <pasta da aplicação>\\MBSniffer Logs\n", "mono")
        h(
            "Os filtros, ordenação, Realçar resultados e o Frame Inspector são apenas funções "
            "de visualização e não alteram os frames gravados no log.\n"
        )

        h("Limites do histórico visível\n", "heading")
        h(
            f"Para manter a aplicação responsiva, a interface conserva aproximadamente "
            f"{max_ui_frames_text} frames e {max_raw_lines_text} linhas de Raw Hex. "
            "A remoção é feita por blocos. O log TXT de captura, quando ativo, é independente "
            "deste limite.\n"
        )

        h("Estado e portas COM\n", "heading")
        h(
            "Estado COM distingue uma porta aberta pelo MBSniffer, uma porta apenas detetada "
            "pelo Windows e uma porta que deixou de ser detetada. O estado é atualizado "
            "periodicamente.\n"
        )
        h(
            "Reiniciar COM fecha e volta a abrir a(s) porta(s) usada(s) pelo Sniffer. "
            "Isto reinicia o handle da porta série dentro do MBSniffer; não reinicia o "
            "driver USB/COM do Windows.\n"
        )
        h(
            "Os botões ↻ ao lado das COM atualizam a enumeração de portas disponível no "
            "Sniffer e no Bus Slave Finder.\n"
        )

        h("Bus Slave Finder — pesquisa ativa\n", "heading")
        h(
            "O Bus Slave Finder transmite pedidos Modbus RTU, por isso não é uma função "
            "passiva. Antes de iniciar, confirma que não existe outro master ativo no mesmo "
            "barramento.\n"
        )
        h(
            "Seleciona COM, baud rates, paridades, stop bits e intervalo de Slave IDs. "
            "Data bits é fixo em 8. A pesquisa tenta FC03 Address 0 Qty 1; uma resposta "
            "normal ou uma Exception Modbus com CRC válido confirma que o Slave existe.\n"
        )
        h(
            "FC04 fallback é opcional e aumenta o número máximo de tentativas. O timeout "
            "mínimo é adaptado ao baud rate. Um write timeout significa falha ao transmitir "
            "pela porta/driver e não deve ser interpretado simplesmente como “slave sem resposta”.\n"
        )
        h(
            "Device Identification (FC43/14) é opcional. Quando ativo, só é enviado depois "
            "de um Slave ter sido encontrado e tenta ler Basic Device Identification: "
            "VendorName, ProductCode e MajorMinorRevision. Uma Exception ou ausência de "
            "resposta a FC43/14 não invalida a descoberta do Slave.\n"
        )
        h(
            "O Finder e o Sniffer partilham o bloqueio global de atividade para impedir que "
            "a mesma aplicação faça pesquisa ativa e captura ao mesmo tempo.\n"
        )

        h("Preferências guardadas\n", "heading")
        h(
            "As preferências do utilizador são guardadas em "
            "%APPDATA%\\MBSniffer\\settings.json. Incluem Light/Dark, último separador, "
            "parâmetros série, Frame gap, Pending timeout, Auto-scroll, Separar transações, "
            "Realçar resultados e opções do Bus Slave Finder.\n"
        )
        h(
            "As portas COM não são guardadas porque são específicas de cada computador. "
            "A confirmação de segurança do Bus Slave Finder também não é persistida.\n"
        )

        h("Boas práticas de diagnóstico\n", "heading")
        h("• Confirma primeiro cablagem, polaridade e parâmetros série.\n", "bullet")
        h("• Em RS485, mantém a derivação do sniffer curta e evita alterar a terminação existente.\n", "bullet")
        h("• Garante que nenhum outro programa tem a mesma COM aberta.\n", "bullet")
        h("• Usa CRC ERROR e RAW como indícios de framing, ruído, parâmetros errados ou captura incompleta.\n", "bullet")
        h("• Usa Exceptions como respostas válidas do protocolo: não são equivalentes a CRC error.\n", "bullet")
        h("• Compara tempos de resposta com o comportamento normal do equipamento, não apenas com um limite genérico.\n", "bullet")
        h("• Guarda o TXT quando precisares de análise posterior da captura completa.\n", "bullet")

        if debug_sim == 1:
            h("Modo Simulação\n", "heading")
            h(
                "Este modo de desenvolvimento aparece apenas quando debug_sim = 1 em "
                "MBSniffer.py. Não abre portas série e nunca cria logs TXT.\n"
            )
            h(
                "Cada execução usa sempre o mesmo tipo de cenário de diagnóstico: uma "
                "resposta normal, uma resposta lenta, uma Modbus Exception, um CRC error, "
                "um timeout e um bloco RAW/UNPARSED. Assim é possível comparar diretamente "
                "a mesma informação com e sem destaque visual.\n"
            )
            h(
                "“Realçar resultados” não altera os dados gerados pela Simulação. Desligado, "
                "todas as linhas usam as cores normais da tabela; ligado, a transação normal "
                "concluída fica verde e as linhas de Exception, CRC error, timeout, resposta "
                "lenta e RAW recebem as respetivas cores de diagnóstico.\n"
            )
            h(
                "As frames deste cenário usam o canal SIM para não serem confundidas com uma "
                "captura física real.\n"
            )

        h("Limitação importante\n", "heading")
        h(
            "O MBSniffer interpreta bytes, CRC, Function Code, endereços, quantidades, "
            "emparelhamento e tempos observados pelo sistema operativo. Não mede diretamente "
            "níveis elétricos, ringing, reflexões, bias, common-mode, tempos de subida/descida "
            "ou integridade analógica do sinal. Para esses problemas continua a ser necessário "
            "um osciloscópio ou analisador adequado à interface física.\n"
        )

        self.help_text.configure(state="disabled")

        detail = ttk.LabelFrame(self.sniffer_page, text="Frame Inspector")
        detail.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        detail.columnconfigure(0, weight=1)

        inspector_header = ttk.Frame(detail)
        inspector_header.grid(
            row=0, column=0, sticky="ew", padx=8, pady=(4, 2)
        )
        inspector_header.columnconfigure(0, weight=1)
        ttk.Label(
            inspector_header,
            text=(
                "Seleciona uma linha no Tráfego para ver a descodificação "
                "estruturada do frame."
            ),
        ).grid(row=0, column=0, sticky="w")

        self.inspector_collapsed = False
        self.inspector_toggle_btn = ttk.Button(
            inspector_header,
            text="Recolher",
            command=self.toggle_frame_inspector,
            style="MBS.Compact.TButton",
        )
        self.inspector_toggle_btn.grid(row=0, column=1, sticky="e")

        self.inspector_body = ttk.Frame(detail)
        self.inspector_body.grid(
            row=1, column=0, sticky="ew", padx=8, pady=(2, 7)
        )
        for col in range(4):
            self.inspector_body.columnconfigure(
                col,
                weight=1,
                uniform="inspector",
            )

        self.inspector_vars = {
            "slave": tk.StringVar(value="Slave: —"),
            "type": tk.StringVar(value="Tipo: —"),
            "function": tk.StringVar(value="Function: —"),
            "response": tk.StringVar(value="Resp.: —"),
            "result": tk.StringVar(value="Resultado: —"),
            "pdu": tk.StringVar(value="PDU Address: —"),
            "one_based": tk.StringVar(value="1-based: —"),
            "qty": tk.StringVar(value="Qty: —"),
            "byte_count": tk.StringVar(value="ByteCount: —"),
            "crc": tk.StringVar(value="CRC: —"),
            "data": tk.StringVar(value="Dados: —"),
        }

        inspector_grid = (
            ("slave", 0, 0),
            ("type", 0, 1),
            ("function", 0, 2),
            ("response", 0, 3),
            ("pdu", 1, 0),
            ("one_based", 1, 1),
            ("qty", 1, 2),
            ("byte_count", 1, 3),
        )
        for key, row, col in inspector_grid:
            ttk.Label(
                self.inspector_body,
                textvariable=self.inspector_vars[key],
                anchor="w",
            ).grid(
                row=row,
                column=col,
                sticky="ew",
                padx=(0 if col == 0 else 8, 8 if col < 3 else 0),
                pady=2,
            )

        self.inspector_result_label = ttk.Label(
            self.inspector_body,
            textvariable=self.inspector_vars["result"],
            anchor="w",
            style="MBS.Result.neutral.TLabel",
        )
        self.inspector_result_label.grid(
            row=2,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(3, 2),
        )

        ttk.Label(
            self.inspector_body,
            textvariable=self.inspector_vars["crc"],
            anchor="w",
        ).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=2
        )
        # Data/Register payloads can be very long. A readonly Entry keeps the
        # inspector compact instead of letting content change requested width.
        ttk.Entry(
            self.inspector_body,
            textvariable=self.inspector_vars["data"],
            state="readonly",
        ).grid(
            row=3,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(8, 0),
            pady=2,
        )

        self.selected_raw_var = tk.StringVar()
        ttk.Entry(
            self.inspector_body,
            textvariable=self.selected_raw_var,
            state="readonly",
        ).grid(
            row=4,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(4, 0),
        )

        self.build_discovery_tab(self.discovery_page)
        self.update_stats_labels()
        self.update_frame_inspector(None)

        # Classic Tk/Canvas widgets are outside ttk.Style; apply the remembered
        # startup palette after every such widget has been created.
        self._apply_classic_widget_palette(self.initial_dark_mode)

