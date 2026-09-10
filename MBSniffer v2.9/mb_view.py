#!/usr/bin/env python3
"""Traffic rendering, filtering, Raw Hex view, statistics and log handling."""

import csv
import math
import os
import subprocess
import sys
import time
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

from mb_config import (
    MAX_UI_FRAMES,
    MAX_RAW_TEXT_LINES,
    UI_PRUNE_CHUNK_FRAMES,
    RAW_TEXT_PRUNE_CHUNK_LINES,
    SLOW_RESPONSE_THRESHOLD_MS,
    get_application_directory,
    get_logs_folder,
)
from mb_diagnostics import (
    anomaly_kind,
    decoded_record_text,
    inspector_values,
)

class ViewMixin:
    """Methods for rendering, filtering, statistics and logging."""

    def reset_session_metrics(self):
        self.metrics.reset()
        self.update_stats_labels()

    def update_stats_labels(self):
        self.stat_requests_var.set(f"Pedidos: {self.metrics.requests}")
        self.stat_responses_var.set(f"Respostas: {self.metrics.responses}")
        self.stat_pending_var.set(f"Pendentes: {self.metrics.pending_count()}")
        self.stat_timeouts_var.set(f"Timeouts: {self.metrics.timeouts}")
        self.stat_crc_var.set(f"Erros de CRC: {self.metrics.crc_errors}")
        self.stat_exceptions_var.set(f"Exceções: {self.metrics.exceptions}")
        self.stat_raw_var.set(f"RAW: {self.metrics.raw}")

        try:
            health_now = (
                time.time()
                if getattr(self, "capture_active", False) or getattr(self, "busy", False)
                else self.metrics.last_event_time
            )
            summary = self.metrics.health_summary(
                baud=self.baud_var.get(),
                data_bits=self.data_var.get(),
                parity=self.parity_var.get(),
                stop_bits=self.stop_var.get(),
                now=health_now,
            )
        except Exception:
            summary = self.metrics.health_summary()

        def ms(value):
            return "—" if value is None else f"{value:.1f} ms"

        if hasattr(self, "stat_slaves_var"):
            self.stat_slaves_var.set(f"Slaves: {summary['active_slaves']}")

        mappings = {
            "health_requests_var": str(self.metrics.requests),
            "health_responses_var": str(self.metrics.responses),
            "health_crc_count_var": str(self.metrics.crc_errors),
            "health_timeout_count_var": str(self.metrics.timeouts),
            "health_exception_count_var": str(self.metrics.exceptions),
            "health_req_rate_var": f"{summary['request_rate']:.2f} req/s",
            "health_resp_avg_var": ms(summary["response_avg_ms"]),
            "health_resp_min_var": ms(summary["response_min_ms"]),
            "health_resp_max_var": ms(summary["response_max_ms"]),
            "health_p95_var": ms(summary["response_p95_ms"]),
            "health_nonvalidated_rate_var": f"{summary['nonvalidated_rate_pct']:.2f} %",
            "health_timeout_rate_var": f"{summary['timeout_rate_pct']:.2f} %",
            "health_bus_load_var": f"{summary['bus_load_pct']:.2f} %",
            "health_slaves_var": str(summary["active_slaves"]),
            "health_total_bytes_var": str(summary["total_bytes"]),
            "health_exception_slaves_var": summary["exception_summary"],
        }

        slowest_slave = summary["slowest_slave"]
        if slowest_slave is None:
            mappings["health_slowest_var"] = "—"
        else:
            mappings["health_slowest_var"] = (
                f"Slave {slowest_slave} — média {summary['slowest_avg_ms']:.1f} ms"
            )

        for attr, value in mappings.items():
            var = getattr(self, attr, None)
            if var is not None:
                var.set(value)

    # ------------------------------------------------------------------
    # Bus activity, filters, anomaly highlighting and Frame Inspector.
    # ------------------------------------------------------------------
    def pulse_bus_activity(self):
        var = getattr(self, "bus_activity_var", None)
        if var is None:
            return

        var.set("BUS ● RX")
        previous = getattr(self, "_bus_activity_after_id", None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass

        try:
            self._bus_activity_after_id = self.after(
                180,
                self._clear_bus_activity_pulse,
            )
        except tk.TclError:
            self._bus_activity_after_id = None

    def _clear_bus_activity_pulse(self):
        self._bus_activity_after_id = None
        var = getattr(self, "bus_activity_var", None)
        if var is not None:
            var.set("BUS ○")

    def schedule_advanced_filter_refresh(self, *_args):
        previous = getattr(self, "_advanced_filter_after_id", None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass
        try:
            self._advanced_filter_after_id = self.after(
                120,
                self.render_filtered_view,
            )
        except tk.TclError:
            self._advanced_filter_after_id = None

    def clear_advanced_filters(self):
        pending = getattr(self, "_advanced_filter_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
            self._advanced_filter_after_id = None

        self.advanced_filter_type_var.set("Todos")
        self.advanced_filter_fc_var.set("")
        self.advanced_filter_response_ms_var.set("")
        self.advanced_filter_text_var.set("")
        self._transaction_filter_seqs = None

        self.slave_filter_all_mode = True
        for var in self.slave_filter_vars.values():
            var.set(True)
        self.update_slave_heading()

        self.render_filtered_view()

    @staticmethod
    def normalized_fc_filter(value):
        text = str(value or "").strip().upper()
        if not text or text == "TODOS":
            return ""
        if text.startswith("0X"):
            text = text[2:]
        try:
            number = int(text, 16)
        except ValueError:
            return "__INVALID__"
        if not 0 <= number <= 0xFF:
            return "__INVALID__"
        return f"{number:02X}"

    def record_passes_advanced_filters(self, record):
        transaction_filter = getattr(self, "_transaction_filter_seqs", None)
        if transaction_filter is not None:
            if record.get("seq") not in transaction_filter:
                return False

        kind = self.advanced_filter_type_var.get()
        row_type = str(record.get("type", ""))

        if kind == "Requests" and row_type != "REQUEST":
            return False
        if kind == "Responses" and row_type != "RESPONSE":
            return False
        if kind == "Exceptions" and row_type != "EXCEPTION":
            return False
        if kind == "CRC errors" and record.get("crc") != "ERROR":
            return False
        if kind == "Timeouts" and not record.get("timed_out"):
            return False
        if kind == "RAW" and not row_type.startswith("RAW"):
            return False

        fc_filter = self.normalized_fc_filter(
            self.advanced_filter_fc_var.get()
        )
        if fc_filter == "__INVALID__":
            return False
        if fc_filter:
            record_fc_text = str(record.get("fc", "")).upper()
            candidates = {record_fc_text}
            if str(record.get("type", "")) == "EXCEPTION":
                try:
                    candidates.add(f"{int(record_fc_text, 16) & 0x7F:02X}")
                except ValueError:
                    pass
            if fc_filter not in candidates:
                return False

        response_limit = self.advanced_filter_response_ms_var.get().strip()
        if response_limit:
            try:
                minimum_ms = float(response_limit.replace(",", "."))
                response_ms = float(record.get("response_text", ""))
            except (TypeError, ValueError):
                return False
            if response_ms <= minimum_ms:
                return False

        query = self.advanced_filter_text_var.get().strip().casefold()
        if query:
            haystack = " ".join((
                str(record.get("details", "")),
                str(record.get("raw", "")),
                str(record.get("slave", "")),
                str(record.get("fc", "")),
                str(record.get("type", "")),
                str(record.get("channel", "")),
            )).casefold()
            if query not in haystack:
                return False

        return True

    def configure_anomaly_tags(self, dark=None):
        if not hasattr(self, "tree"):
            return

        if dark is None:
            dark = bool(getattr(self, "dark_mode_var", tk.BooleanVar(value=False)).get())

        if dark:
            palette = {
                "result_success": ("#20372a", "#a7e4b8"),
                "anomaly_exception": ("#3b2728", "#ffc0c5"),
                "anomaly_crc": ("#482427", "#ffb3ba"),
                "anomaly_timeout": ("#42351f", "#ffd27a"),
                "anomaly_slow": ("#3b3422", "#ffe19a"),
                "anomaly_raw": ("#30283c", "#d8c5ff"),
            }
        else:
            palette = {
                "result_success": ("#e4f4e9", "#1f6b3a"),
                "anomaly_exception": ("#ffe8e9", "#8c1d24"),
                "anomaly_crc": ("#ffdfe1", "#8c1d24"),
                "anomaly_timeout": ("#fff0cf", "#774b00"),
                "anomaly_slow": ("#fff6dd", "#6b5200"),
                "anomaly_raw": ("#f0e9ff", "#5d3d8f"),
            }

        for tag, (background, foreground) in palette.items():
            self.tree.tag_configure(
                tag,
                background=background,
                foreground=foreground,
            )

    def anomaly_tag_for_record(self, record):
        """
        Return the optional result-highlight tag for one logical traffic row.

        "Realçar resultados" is a presentation option only:
        - diagnostic outcomes retain their existing anomaly colors;
        - a successfully completed normal REQUEST/RESPONSE transaction is green;
        - unmatched/pending requests remain neutral.
        """
        if not getattr(self, "highlight_anomalies_var", None):
            return ""
        if not self.highlight_anomalies_var.get():
            return ""

        kind = anomaly_kind(record, SLOW_RESPONSE_THRESHOLD_MS)
        if kind:
            return f"anomaly_{kind}"

        row_type = str(record.get("type", ""))

        # A normal, CRC-valid matched RESPONSE is a successful result.
        if (
            row_type == "RESPONSE"
            and record.get("crc") == "OK"
            and record.get("matched")
        ):
            return "result_success"

        # Once the normal response has arrived, also mark its REQUEST so the
        # complete successful transaction pair reads as one result.
        if (
            row_type == "REQUEST"
            and record.get("seq") in self._successful_request_seqs
            and not record.get("timed_out")
        ):
            return "result_success"

        return ""

    def on_highlight_anomalies_changed(self):
        self.configure_anomaly_tags()
        self.configure_inspector_result_styles()
        self.render_filtered_view()
        self.update_frame_inspector(self.selected_record())
        saver = getattr(self, "_schedule_ui_settings_save", None)
        if callable(saver):
            saver()

    def mark_timed_out_records(self, expired, rerender=True):
        if not expired:
            return 0

        seqs = {
            item.get("seq")
            for item in expired
            if item.get("seq") is not None
        }
        if not seqs:
            return 0

        changed = 0
        for record in self._frame_history:
            if record.get("seq") in seqs and not record.get("timed_out"):
                record["timed_out"] = True
                changed += 1

        if changed and rerender:
            self.render_filtered_view()
        return changed

    def selected_record(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._record_by_iid.get(selection[0])

    def update_frame_inspector(self, record=None):
        if not hasattr(self, "inspector_vars"):
            return

        successful_request = bool(
            record
            and record.get("type") == "REQUEST"
            and record.get("seq") in self._successful_request_seqs
        )
        values = inspector_values(
            record,
            successful_request=successful_request,
        )
        for key, var in self.inspector_vars.items():
            if key in values:
                var.set(values[key])
        self.selected_raw_var.set(values.get("raw", ""))

        result_label = getattr(self, "inspector_result_label", None)
        if result_label is not None:
            style_key = values.get("result_key", "neutral")
            if not self.highlight_anomalies_var.get():
                style_key = "neutral"
            try:
                result_label.configure(
                    style=f"MBS.Result.{style_key}.TLabel"
                )
            except tk.TclError:
                pass

    def toggle_frame_inspector(self):
        if getattr(self, "inspector_collapsed", False):
            self.inspector_body.grid()
            self.inspector_collapsed = False
            self.inspector_toggle_btn.configure(text="Recolher")
        else:
            self.inspector_body.grid_remove()
            self.inspector_collapsed = True
            self.inspector_toggle_btn.configure(text="Expandir")

        scheduler = getattr(self, "_schedule_bus_health_layout_sync", None)
        if callable(scheduler):
            scheduler()

    def copy_to_clipboard(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(str(text))
            self.update_idletasks()
        except tk.TclError:
            pass

    def copy_selected_raw(self):
        record = self.selected_record()
        if record:
            self.copy_to_clipboard(record.get("raw", ""))

    def copy_selected_decoded(self):
        record = self.selected_record()
        if record:
            successful_request = bool(
                record.get("type") == "REQUEST"
                and record.get("seq") in self._successful_request_seqs
            )
            self.copy_to_clipboard(
                decoded_record_text(
                    record,
                    successful_request=successful_request,
                )
            )

    def context_filter_selected_slave(self):
        record = self.selected_record()
        if not record:
            return
        slave = str(record.get("slave", "") or "")
        if not slave or slave not in self.slave_filter_vars:
            return

        self._transaction_filter_seqs = None
        self.slave_filter_all_mode = False
        for key, var in self.slave_filter_vars.items():
            var.set(key == slave)
        self.update_slave_heading()
        self.render_filtered_view()

    def context_filter_selected_fc(self):
        record = self.selected_record()
        if not record:
            return
        fc = str(record.get("fc", "") or "")
        if not fc:
            return
        if str(record.get("type", "")) == "EXCEPTION":
            try:
                fc = f"{int(fc, 16) & 0x7F:02X}"
            except ValueError:
                pass
        self.advanced_filter_fc_var.set(fc)
        self._transaction_filter_seqs = None
        self.render_filtered_view()

    def context_show_selected_transaction(self):
        record = self.selected_record()
        if not record:
            return

        seq = record.get("seq")
        seqs = {seq}

        if record.get("request_seq") is not None:
            seqs.add(record["request_seq"])
        else:
            for candidate in self._frame_history:
                if candidate.get("request_seq") == seq:
                    seqs.add(candidate.get("seq"))
                    break

        self.slave_filter_all_mode = True
        for var in self.slave_filter_vars.values():
            var.set(True)
        self.update_slave_heading()

        self.advanced_filter_type_var.set("Todos")
        self.advanced_filter_fc_var.set("")
        self.advanced_filter_response_ms_var.set("")
        self.advanced_filter_text_var.set("")

        self._transaction_filter_seqs = {
            value for value in seqs if value is not None
        }
        self.render_filtered_view()

    def clear_transaction_filter(self):
        self._transaction_filter_seqs = None
        self.render_filtered_view()

    def show_traffic_context_menu(self, event):
        row_iid = self.tree.identify_row(event.y)
        if not row_iid or row_iid not in self._record_by_iid:
            return

        self.tree.selection_set(row_iid)
        self.tree.focus(row_iid)
        self.on_row_select()

        try:
            self.traffic_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.traffic_context_menu.grab_release()
            except tk.TclError:
                pass

    def export_session_csv(self, path=None):
        interactive = path is None
        records = list(self._frame_history)
        if not records:
            if path is None:
                messagebox.showinfo(
                    "Exportar CSV",
                    "Não existem frames na sessão atual para exportar.",
                )
            return None

        if path is None:
            filename = datetime.now().strftime(
                "MBSniffer_session_%Y%m%d_%H%M%S.csv"
            )
            path = filedialog.asksaveasfilename(
                title="Exportar sessão para CSV",
                defaultextension=".csv",
                initialfile=filename,
                filetypes=[("CSV", "*.csv"), ("Todos os ficheiros", "*.*")],
            )
            if not path:
                return None

        fieldnames = [
            "Time",
            "Delta ms",
            "Response ms",
            "Channel",
            "Type",
            "Slave",
            "FC",
            "Details",
            "CRC",
            "Raw",
            "PDU Address",
            "1-based Address",
            "Qty",
            "Byte Count",
            "Timed out",
            "Anomaly",
        ]

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()

                for record in records:
                    inspector = inspector_values(record)
                    byte_count_text = inspector["byte_count"].split(
                        ":", 1
                    )[-1].strip()
                    writer.writerow({
                        "Time": record.get("time", ""),
                        "Delta ms": record.get("delta_text", ""),
                        "Response ms": record.get("response_text", ""),
                        "Channel": record.get("channel", ""),
                        "Type": record.get("type", ""),
                        "Slave": record.get("slave", ""),
                        "FC": record.get("fc", ""),
                        "Details": record.get("details", ""),
                        "CRC": record.get("crc", ""),
                        "Raw": record.get("raw", ""),
                        "PDU Address": (
                            "" if record.get("pdu_address") is None
                            else record.get("pdu_address")
                        ),
                        "1-based Address": (
                            "" if record.get("one_based") is None
                            else record.get("one_based")
                        ),
                        "Qty": (
                            "" if record.get("qty") is None
                            else record.get("qty")
                        ),
                        "Byte Count": (
                            "" if byte_count_text == "—"
                            else byte_count_text
                        ),
                        "Timed out": "Yes" if record.get("timed_out") else "No",
                        "Anomaly": anomaly_kind(
                            record,
                            SLOW_RESPONSE_THRESHOLD_MS,
                        ) or "",
                    })

            if interactive:
                try:
                    messagebox.showinfo(
                        "Exportar CSV",
                        f"Sessão exportada para:\n\n{path}",
                    )
                except tk.TclError:
                    pass
            return path

        except OSError as exc:
            messagebox.showerror(
                "Exportar CSV",
                f"Não foi possível guardar o CSV:\n\n{exc}",
            )
            return None

    def tree_record_column_values(self, record):
        return {
            "time": record.get("time", ""),
            "delta": record.get("delta_text", ""),
            "response": record.get("response_text", ""),
            "channel": record.get("channel", ""),
            "type": record.get("type", ""),
            "slave": record.get("slave", ""),
            "fc": record.get("fc", ""),
            "details": record.get("details", ""),
            "crc": record.get("crc", ""),
        }

    def measure_tree_column_width(self, column, records, heading_text=None):
        """
        Measure the pixel width required by a non-wrapped Treeview column.

        Details is handled separately because it uses the remaining viewport
        width and wraps instead of expanding horizontally without limit.
        """
        heading = (
            heading_text
            if heading_text is not None
            else self.tree_headings.get(column, column)
        )
        max_px = self.tree_heading_font.measure(str(heading))

        for record in records:
            value = self.tree_record_column_values(record).get(column, "")
            max_px = max(max_px, self.tree_cell_font.measure(str(value)))

        return max_px + self.tree_column_padding_px

    def available_details_width(self):
        """
        Return the width that can be assigned to Details without intentionally
        forcing horizontal scrolling in the current Treeview viewport.
        """
        tree_width = int(self.tree.winfo_width())
        if tree_width <= 20:
            tree_width = 1100  # sensible pre-layout fallback

        other_total = 0
        for column in self.tree["columns"]:
            if column == "details":
                continue
            other_total += int(self.tree.column(column, "width"))

        return max(
            self.tree_detail_min_width_px,
            tree_width - other_total - self.tree_detail_border_reserve_px
        )

    def wrap_text_to_pixels(self, value, max_px):
        """
        Word-wrap text using the actual Tk font width.

        Long individual tokens are split character-by-character as a fallback,
        so a cell can never force the Details column wider than its target.
        """
        text = str(value or "")
        if not text:
            return ""

        max_px = max(40, int(max_px))
        paragraphs = text.splitlines() or [text]
        output_lines = []

        for paragraph in paragraphs:
            words = paragraph.split()
            if not words:
                output_lines.append("")
                continue

            line = ""
            for word in words:
                candidate = word if not line else f"{line} {word}"
                if self.tree_cell_font.measure(candidate) <= max_px:
                    line = candidate
                    continue

                if line:
                    output_lines.append(line)
                    line = ""

                # The token itself may be wider than the available space.
                if self.tree_cell_font.measure(word) <= max_px:
                    line = word
                    continue

                chunk = ""
                for char in word:
                    candidate_chunk = chunk + char
                    if chunk and self.tree_cell_font.measure(candidate_chunk) > max_px:
                        output_lines.append(chunk)
                        chunk = char
                    else:
                        chunk = candidate_chunk
                line = chunk

            if line:
                output_lines.append(line)

        return "\n".join(output_lines)

    def details_horizontal_rule(self):
        """
        Return a rule that fills the Details column as far as the Treeview cell
        permits. A slight overdraw is intentional; Treeview clips it at the
        column boundary.
        """
        details_width = max(
            40,
            int(self.tree.column("details", "width"))
        )
        char_px = max(1, self.tree_cell_font.measure("─"))
        count = max(8, int(math.ceil(details_width / char_px)) + 4)
        return "─" * count

    def completed_pairs_for_records(self, records):
        """
        Return complete visible REQUEST/RESPONSE pairs in current display order.

        Each matched RESPONSE stores the exact request sequence id. This allows
        correct boundaries in both Hora ↑ and Hora ↓ without relying on row
        adjacency alone.
        """
        seq_to_index = {
            record.get("seq"): index
            for index, record in enumerate(records)
        }

        pairs = []
        for response in records:
            request_seq = response.get("request_seq")
            response_seq = response.get("seq")

            if request_seq is None or request_seq not in seq_to_index:
                continue

            request_index = seq_to_index[request_seq]
            response_index = seq_to_index.get(response_seq)
            if response_index is None:
                continue

            start_index = min(request_index, response_index)
            end_index = max(request_index, response_index)

            pairs.append({
                "request_seq": request_seq,
                "response_seq": response_seq,
                "start_index": start_index,
                "end_index": end_index,
                # Separator belongs after whichever logical frame is visually
                # the end of the pair.
                "end_seq": records[end_index].get("seq"),
            })

        pairs.sort(key=lambda item: item["start_index"])
        return pairs

    def separator_after_sequences(self, records):
        """
        Return logical frame seq ids that need a separator AFTER them.

        There is intentionally no separator after the final complete visible
        pair because there is nothing below it to divide.
        """
        if not self.separate_transactions_var.get():
            return set()

        pairs = self.completed_pairs_for_records(records)
        if len(pairs) < 2:
            return set()

        return {
            pair["end_seq"]
            for pair in pairs[:-1]
        }

    def tree_separator_values(self):
        return (
            "", "", "", "", "", "", "",
            self.details_horizontal_rule(),
            ""
        )

    def insert_tree_separator_after_seq(self, seq):
        """Insert one Details-width separator after the visual rows of seq."""
        if seq in self._tree_separator_iid_by_seq:
            return

        iids = self._tree_iids_by_seq.get(seq, [])
        if not iids:
            return

        last_iid = iids[-1]
        insert_at = self.tree.index(last_iid) + 1

        iid = self.tree.insert(
            "",
            insert_at,
            values=self.tree_separator_values()
        )
        self._raw_by_iid[iid] = ""
        self._tree_separator_iid_by_seq[seq] = iid

    def sync_tree_transaction_separators(self, records=None):
        """
        Synchronize standalone transaction separator rows without rebuilding
        normal traffic rows.
        """
        if records is None:
            records = self.records_for_display()

        desired = self.separator_after_sequences(records)
        existing = set(self._tree_separator_iid_by_seq)

        # Remove boundaries that are no longer valid (filter/order changes).
        for seq in existing - desired:
            iid = self._tree_separator_iid_by_seq.pop(seq, None)
            if iid and self.tree.exists(iid):
                self.tree.delete(iid)
            self._raw_by_iid.pop(iid, None)

        # Add newly required boundaries.
        for seq in desired - existing:
            self.insert_tree_separator_after_seq(seq)

    def detail_lines_for_record(self, record):
        """
        Return wrapped Details as separate visual Treeview rows.

        ttk.Treeview has one global row height for the entire widget. Putting
        newline-wrapped text in one item would therefore make every REQUEST and
        RESPONSE row as tall as the largest Details message. Continuation rows
        preserve wrapping while keeping normal rows compact.
        """
        content_width = max(
            40,
            int(self.tree.column("details", "width"))
            - self.tree_column_padding_px
        )
        wrapped = self.wrap_text_to_pixels(
            record.get("details", ""),
            content_width
        )

        if not wrapped:
            return [""]

        return wrapped.splitlines()

    def set_tree_rowheight_for_records(self, records):
        """Treeview row height stays fixed; wrapping uses continuation rows."""
        self.tree_style.configure(
            self.tree_style_name,
            rowheight=self.tree_single_line_rowheight
        )

    def update_tree_rowheight_for_record(self, record):
        """No-op by design: one logical frame may use several compact rows."""
        return

    def autofit_tree_columns(self, records=None):
        """
        Non-Details columns fit the longest visible value/title.

        Details deliberately behaves differently: it consumes the remaining
        viewport width and wraps. This keeps the full row information visible
        without letting long register lists create an extremely wide table.
        """
        if records is None:
            records = self.records_for_display()

        # First compact every non-Details column.
        for column in self.tree["columns"]:
            if column == "details":
                continue

            width = self.measure_tree_column_width(column, records)
            self.tree.column(
                column,
                width=width,
                minwidth=width,
                anchor="center",
                stretch=False
            )

        # Then allocate the remaining viewport to Details.
        heading_min = self.measure_tree_column_width(
            "details",
            [],
            heading_text=self.tree_headings["details"]
        )
        details_width = max(
            heading_min,
            self.available_details_width()
        )
        self.tree.column(
            "details",
            width=details_width,
            minwidth=heading_min,
            anchor="w",
            stretch=True
        )

        self.set_tree_rowheight_for_records(records)

    def expand_tree_columns_for_record(self, record):
        """
        Incrementally enlarge only the compact non-Details columns.

        Returns True when another column became wider. If that happens the
        remaining Details width changes, so the caller can rebuild/re-wrap the
        visible table once for the batch.
        """
        values = self.tree_record_column_values(record)
        layout_changed = False

        for column in self.tree["columns"]:
            if column == "details":
                continue

            heading_px = self.tree_heading_font.measure(
                str(self.tree_headings.get(column, column))
            )
            value_px = self.tree_cell_font.measure(str(values.get(column, "")))
            required = max(heading_px, value_px) + self.tree_column_padding_px
            current = int(self.tree.column(column, "width"))

            if required > current:
                self.tree.column(
                    column,
                    width=required,
                    minwidth=required,
                    anchor="center",
                    stretch=False
                )
                layout_changed = True

        if layout_changed:
            heading_min = self.measure_tree_column_width(
                "details",
                [],
                heading_text=self.tree_headings["details"]
            )
            details_width = max(
                heading_min,
                self.available_details_width()
            )
            self.tree.column(
                "details",
                width=details_width,
                minwidth=heading_min,
                anchor="w",
                stretch=True
            )

        return layout_changed

    def refresh_tree_heading_width(self, column):
        """
        Dynamic Hora/Slave headings remain compact. Details is intentionally
        excluded because it is viewport-driven and wrapped.
        """
        if column == "details":
            return

        records = self.records_for_display()
        width = self.measure_tree_column_width(column, records)
        self.tree.column(
            column,
            width=width,
            minwidth=width,
            anchor="center",
            stretch=False
        )

    def schedule_tree_reflow(self, _event=None):
        """
        Debounce window/Treeview resizing and then re-wrap Details to the new
        available width.
        """
        if self._tree_reflow_after_id is not None:
            try:
                self.after_cancel(self._tree_reflow_after_id)
            except Exception:
                pass

        self._tree_reflow_after_id = self.after(
            120,
            self.reflow_tree_after_resize
        )

    def reflow_tree_after_resize(self):
        self._tree_reflow_after_id = None
        if not hasattr(self, "tree"):
            return
        self.render_filtered_view()

    def _slave_sort_key(self, slave):
        try:
            return (0, int(slave))
        except (TypeError, ValueError):
            return (1, str(slave))

    def rebuild_slave_filter_menu(self):
        self.slave_filter_menu.delete(0, "end")

        self.slave_filter_menu.add_command(
            label="Todos",
            command=self.select_all_slaves
        )
        self.slave_filter_menu.add_command(
            label="Nenhum",
            command=self.select_no_slaves
        )

        if self.slave_filter_vars:
            self.slave_filter_menu.add_separator()
            for slave in sorted(self.slave_filter_vars, key=self._slave_sort_key):
                self.slave_filter_menu.add_checkbutton(
                    label=f"Slave {slave}",
                    variable=self.slave_filter_vars[slave],
                    command=self.on_slave_filter_changed
                )
        else:
            self.slave_filter_menu.add_separator()
            self.slave_filter_menu.add_command(
                label="Nenhum slave detetado",
                state="disabled"
            )

        self.update_slave_heading()

    def update_slave_heading(self):
        if self.slave_filter_all_mode:
            label = "Slave ▾"
        else:
            selected = [
                slave for slave, var in self.slave_filter_vars.items()
                if var.get()
            ]
            label = "Slave (Filtro) ▾" if selected else "Slave (Nenhum) ▾"

        self.tree_headings["slave"] = label
        self.tree.heading(
            "slave",
            text=label,
            anchor="center",
            command=self.show_slave_filter_menu
        )
        self.refresh_tree_heading_width("slave")

    def show_slave_filter_menu(self):
        """
        Open the slave filter menu at the position where the Slave heading
        was clicked.
        """
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery() + 8
            self.slave_filter_menu.tk_popup(x, y)
        finally:
            try:
                self.slave_filter_menu.grab_release()
            except tk.TclError:
                pass

    def register_slave_for_filter(self, slave):
        slave = str(slave or "").strip()
        if not slave:
            return

        if slave in self.slave_filter_vars:
            return

        self.slave_filter_vars[slave] = tk.BooleanVar(
            value=self.slave_filter_all_mode
        )
        self.rebuild_slave_filter_menu()

    def select_all_slaves(self):
        self.slave_filter_all_mode = True
        for var in self.slave_filter_vars.values():
            var.set(True)
        self.update_slave_heading()
        self.render_filtered_view()

    def select_no_slaves(self):
        self.slave_filter_all_mode = False
        for var in self.slave_filter_vars.values():
            var.set(False)
        self.update_slave_heading()
        self.render_filtered_view()

    def on_slave_filter_changed(self):
        if not self.slave_filter_vars:
            self.slave_filter_all_mode = True
        else:
            values = [var.get() for var in self.slave_filter_vars.values()]
            # If every currently known slave is checked, remain in "All" mode
            # so future slaves are automatically displayed too.
            self.slave_filter_all_mode = bool(values) and all(values)

        self.update_slave_heading()
        self.render_filtered_view()

    def selected_slave_ids(self):
        return {
            slave for slave, var in self.slave_filter_vars.items()
            if var.get()
        }

    def record_passes_slave_filter(self, record):
        # "Todos" includes RAW/unsynchronised data where a slave ID could not
        # be identified. "Nenhum" hides absolutely all traffic.
        if self.slave_filter_all_mode:
            return True

        selected = self.selected_slave_ids()
        if not selected:
            return False

        return str(record.get("slave", "")) in selected

    def time_order_descending(self):
        return self.time_order_var.get().startswith("Decrescente")

    def on_time_order_changed(self):
        label = "Hora ↓" if self.time_order_descending() else "Hora ↑"
        self.tree_headings["time"] = label
        self.tree.heading(
            "time",
            text=label,
            anchor="center",
            command=self.toggle_time_order
        )
        self.render_filtered_view()

    def toggle_time_order(self):
        if self.time_order_descending():
            self.time_order_var.set("Crescente — antigo → recente")
        else:
            self.time_order_var.set("Decrescente — recente → antigo")
        self.on_time_order_changed()

    def records_for_display(self):
        records = [
            record for record in self._frame_history
            if (
                self.record_passes_slave_filter(record)
                and self.record_passes_advanced_filters(record)
            )
        ]
        if self.time_order_descending():
            records.reverse()
        return records

    def raw_line_for_record(self, record):
        # Keep fixed-width timing fields so the rest of every Raw Hex line
        # starts at exactly the same horizontal position. When a value does not
        # exist, show a completely blank field instead of "-", "dt=", "resp="
        # or "ms".
        delta_field = (
            f"dt={record['delta_text']:>7}ms "
            if record.get("delta_text")
            else " " * 13
        )
        response_field = (
            f"resp={record['response_text']:>7}ms "
            if record.get("response_text")
            else " " * 15
        )

        return (
            f"[{record['time']}] "
            f"{delta_field}"
            f"{response_field}"
            f"{record['channel']:<6} {record['type']:<10} "
            f"Slave={record['slave'] or '-':<3} FC={record['fc'] or '-':<2} "
            f"CRC={record['crc']:<5} | {record['raw']} | {record['details']}\n"
        )

    def raw_separator_width_chars(self, raw_lines=None):
        """
        Width of one Raw Hex separator in visible character cells.

        Raw Hex now wraps to the viewport, so the separator must span only the
        visible width. Using the longest unwrapped data line would make the
        separator wrap onto multiple lines.
        """
        try:
            # Leave a small pixel reserve for Text internal borders/padding so
            # the last separator character does not wrap onto a second line.
            widget_px = max(1, int(self.raw_text.winfo_width()) - 14)
            char_px = max(1, self.raw_text_font.measure("─"))
            viewport_chars = max(
                1,
                int(widget_px // char_px)
            )
        except Exception:
            viewport_chars = 1

        return viewport_chars

    def raw_transaction_separator(self, width_chars=None):
        if width_chars is None:
            width_chars = self._raw_separator_width_chars
        return "─" * max(1, int(width_chars)) + "\n"

    def schedule_raw_separator_reflow(self, _event=None):
        if self._raw_reflow_after_id is not None:
            try:
                self.after_cancel(self._raw_reflow_after_id)
            except Exception:
                pass

        self._raw_reflow_after_id = self.after(
            120,
            self.reflow_raw_separator_after_resize
        )

    def reflow_raw_separator_after_resize(self):
        self._raw_reflow_after_id = None
        if self.separate_transactions_var.get():
            self.render_raw_text_only()

    def insert_tree_record(self, record, index="end", allow_separator=True):
        detail_lines = self.detail_lines_for_record(record)
        visual_rows = []

        # Main row: all columns + first Details line.
        visual_rows.append({
            "kind": "main",
            "values": (
                record["time"],
                record["delta_text"],
                record["response_text"],
                record["channel"],
                record["type"],
                record["slave"],
                record["fc"],
                detail_lines[0],
                record["crc"],
            ),
            "raw": record["raw"],
        })

        # Wrapped continuation lines keep only the Details text.
        for continuation in detail_lines[1:]:
            visual_rows.append({
                "kind": "continuation",
                "values": (
                    "", "", "", "", "", "", "",
                    continuation,
                    ""
                ),
                "raw": record["raw"],
            })

        inserted_main_iid = None
        inserted_iids = []

        # index=0 requires reverse insertion to preserve visual block order.
        rows_to_insert = (
            list(reversed(visual_rows))
            if index == 0
            else visual_rows
        )

        row_tag = self.anomaly_tag_for_record(record)

        for visual in rows_to_insert:
            iid = self.tree.insert(
                "",
                index,
                values=visual["values"],
                tags=((row_tag,) if row_tag else ()),
            )

            self._raw_by_iid[iid] = visual["raw"]
            self._record_by_iid[iid] = record

            if index == 0:
                inserted_iids.insert(0, iid)
                self._tree_history.appendleft((iid, True))
            else:
                inserted_iids.append(iid)
                self._tree_history.append((iid, True))

            if visual["kind"] == "main":
                inserted_main_iid = iid

        self._tree_iids_by_seq[record["seq"]] = inserted_iids
        self._ui_frame_count += 1
        return inserted_main_iid

    def render_raw_text_only(self):
        records = self.records_for_display()
        separator_after = self.separator_after_sequences(records)

        line_by_seq = {
            record["seq"]: self.raw_line_for_record(record)
            for record in records
        }
        all_raw_lines = list(line_by_seq.values())
        self._raw_separator_width_chars = self.raw_separator_width_chars(
            all_raw_lines
        )
        separator_line = self.raw_transaction_separator(
            self._raw_separator_width_chars
        )

        # Respect the visual line cap, counting transaction separators as one
        # line each.
        if not self.time_order_descending():
            selected_reversed = []
            line_count = 0

            for record in reversed(records):
                cost = 1 + (1 if record["seq"] in separator_after else 0)
                if line_count + cost > MAX_RAW_TEXT_LINES:
                    break
                selected_reversed.append(record)
                line_count += cost

            raw_records = list(reversed(selected_reversed))
        else:
            selected = []
            line_count = 0

            for record in records:
                cost = 1 + (1 if record["seq"] in separator_after else 0)
                if line_count + cost > MAX_RAW_TEXT_LINES:
                    break
                selected.append(record)
                line_count += cost

            raw_records = selected

        parts = []
        for record in raw_records:
            parts.append(line_by_seq[record["seq"]])
            if record["seq"] in separator_after:
                parts.append(separator_line)

        block = "".join(parts)
        self.raw_text.delete("1.0", "end")
        if block:
            self.raw_text.insert("end", block)
        self._raw_text_line_count = block.count("\\n")

    def render_filtered_view(self):
        # This is intentionally called on user-driven filter/sort changes and
        # infrequent history-prune events, not once per received frame.
        selected_record = self.selected_record()
        selected_seq = (
            selected_record.get("seq")
            if selected_record is not None
            else None
        )

        for item in self.tree.get_children():
            self.tree.delete(item)

        self._raw_by_iid = {}
        self._record_by_iid = {}
        self._tree_history.clear()
        self._tree_iids_by_seq.clear()
        self._tree_separator_iid_by_seq.clear()
        self._ui_frame_count = 0
        self.selected_raw_var.set("")

        descending = self.time_order_descending()
        records = self.records_for_display()

        # Column sizing determines the wrap width, so it must happen before
        # inserting the visible rows.
        self.autofit_tree_columns(records)

        for record in records:
            self.insert_tree_record(
                record,
                index="end",
                allow_separator=False
            )

        self.sync_tree_transaction_separators(records)
        self.render_raw_text_only()

        if selected_seq is not None:
            iids = self._tree_iids_by_seq.get(selected_seq, [])
            if iids:
                try:
                    self.tree.selection_set(iids[0])
                    self.tree.focus(iids[0])
                    self.update_frame_inspector(
                        self._record_by_iid.get(iids[0])
                    )
                except tk.TclError:
                    pass
            else:
                self.update_frame_inspector(None)

        if self.auto_scroll_var.get() and self._tree_history:
            if descending:
                iid = self._tree_history[0][0]
                self.tree.see(iid)
                self.raw_text.see("1.0")
            else:
                iid = self._tree_history[-1][0]
                self.tree.see(iid)
                self.raw_text.see("end")

    def add_frame_row(self, row):
        # Kept as a convenience wrapper for callers/tests.
        self.add_frame_rows_batch([row])

    def add_frame_rows_batch(self, rows):
        if not rows:
            return

        raw_lines_log = []
        any_visible = False
        tree_layout_changed = False
        pair_boundary_changed = False
        expired_requests = []

        self.pulse_bus_activity()

        for row in rows:
            seq = self._next_frame_seq
            self._next_frame_seq += 1
            row["_view_seq"] = seq

            timing = self.metrics.process(row)

            delta_text = (
                f"{timing['delta_ms']:.1f}" if timing["delta_ms"] is not None else ""
            )
            response_text = (
                f"{timing['response_ms']:.1f}"
                if timing["response_ms"] is not None
                else ""
            )

            # Keep pairing for response-time/statistics, but do not copy the
            # request Address/1-based/Qty into RESPONSE/EXCEPTION details.
            # Those fields remain visible only on the REQUEST itself.
            matched = timing.get("matched_request")
            expired_requests.extend(
                timing.get("expired_requests", [])
            )

            self.register_slave_for_filter(row.get("slave", ""))

            record = {
                "seq": seq,
                "epoch": float(row.get("_epoch", time.time())),
                "time": row["time"],
                "delta_text": delta_text,
                "response_text": response_text,
                "channel": row["channel"],
                "type": row["type"],
                "slave": row["slave"],
                "fc": row["fc"],
                "details": row["details"],
                "crc": row["crc"],
                "raw": row["raw"],
                "pdu_address": row.get("pdu_address"),
                "one_based": row.get("one_based"),
                "qty": row.get("qty"),
                "frame_len": row.get("_frame_len", 0),
                "timed_out": False,
                "matched": matched is not None,
                "request_seq": (
                    matched.get("seq")
                    if matched is not None
                    else None
                ),
            }
            self._frame_history.append(record)

            # Track successful normal transaction pairs independently of whether
            # highlighting is currently enabled. This lets the user toggle
            # "Realçar resultados" on/off against the exact same session.
            if (
                record.get("type") == "RESPONSE"
                and record.get("crc") == "OK"
                and record.get("matched")
                and anomaly_kind(record, SLOW_RESPONSE_THRESHOLD_MS) is None
                and record.get("request_seq") is not None
            ):
                self._successful_request_seqs.add(record["request_seq"])

                # If the REQUEST is already visible, update it immediately
                # without rebuilding the entire Treeview.
                if self.highlight_anomalies_var.get():
                    for request_iid in self._tree_iids_by_seq.get(
                        record["request_seq"], []
                    ):
                        try:
                            self.tree.item(
                                request_iid,
                                tags=("result_success",),
                            )
                        except tk.TclError:
                            pass

            # Disk log is always complete and ignores GUI filters/sorting.
            raw_lines_log.append(self.raw_line_for_record(record))

            if (
                self.record_passes_slave_filter(record)
                and self.record_passes_advanced_filters(record)
            ):
                any_visible = True
                if self.expand_tree_columns_for_record(record):
                    tree_layout_changed = True

                self.update_tree_rowheight_for_record(record)

                if self.time_order_descending():
                    self.insert_tree_record(
                        record,
                        index=0,
                        allow_separator=False
                    )

                    raw_block = self.raw_line_for_record(record)
                    self.raw_text.insert("1.0", raw_block)
                    self._raw_text_line_count += raw_block.count("\n")
                else:
                    self.insert_tree_record(
                        record,
                        index="end",
                        allow_separator=False
                    )

                    raw_block = self.raw_line_for_record(record)
                    self.raw_text.insert("end", raw_block)
                    self._raw_text_line_count += raw_block.count("\n")

                if record.get("matched"):
                    pair_boundary_changed = True

        if expired_requests:
            # A new frame can itself cause older requests to cross the Pending
            # timeout. Mark those original REQUEST records before final render.
            self.mark_timed_out_records(
                expired_requests,
                rerender=False,
            )

        log_block = "".join(raw_lines_log)

        # Only real traffic is allowed to create a .txt log. GUI filters do not
        # change the complete saved traffic.
        if self.capture_active and log_block:
            if self.ensure_log_started():
                self.log_line(log_block)

        self.update_stats_labels()
        rebuilt = self.prune_ui_history()

        if expired_requests and not rebuilt:
            self.render_filtered_view()
            rebuilt = True

        if tree_layout_changed and not rebuilt:
            self.render_filtered_view()
            rebuilt = True

        if not rebuilt and pair_boundary_changed:
            visible_records = self.records_for_display()
            self.sync_tree_transaction_separators(visible_records)
            self.render_raw_text_only()

        # Raw Hex has its own bounded line count. Rebuild it in the correct
        # chronological direction when its hysteresis threshold is reached.
        if (
            not rebuilt
            and self._raw_text_line_count
            > MAX_RAW_TEXT_LINES + RAW_TEXT_PRUNE_CHUNK_LINES
        ):
            self.render_raw_text_only()

        if self.auto_scroll_var.get() and any_visible and self._tree_history:
            if self.time_order_descending():
                self.tree.see(self._tree_history[0][0])
                self.raw_text.see("1.0")
            else:
                self.tree.see(self._tree_history[-1][0])
                self.raw_text.see("end")

    def prune_ui_history(self):
        """
        Keep the GUI source history bounded.

        The full disk log is independent and remains complete. Pruning happens
        by deque chunks and only triggers a full GUI rebuild occasionally.
        """
        trigger_frames = MAX_UI_FRAMES + UI_PRUNE_CHUNK_FRAMES

        if len(self._frame_history) <= trigger_frames:
            return False

        while len(self._frame_history) > MAX_UI_FRAMES:
            self._frame_history.popleft()

        retained_sequences = {
            record.get("seq")
            for record in self._frame_history
            if record.get("seq") is not None
        }
        self._successful_request_seqs.intersection_update(retained_sequences)

        self.render_filtered_view()
        return True

    def on_row_select(self, _event=None):
        record = self.selected_record()
        self.update_frame_inspector(record)

    def finish_capture_ui(self):
        self.busy = False
        self.capture_active = False
        self.status_var.set("● Parado")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.restart_btn.configure(state="normal")
        self.set_simulation_button_state("normal")
        self.set_sniffer_refresh_state("normal")
        self.serial_objects = []
        self.serial_by_port = {}
        self.reader_threads = []
        self.close_log()
        self.update_com_status()

    def app_directory(self):
        return get_application_directory()

    def prepare_log_session(self, prefix, started_at, header):
        """
        Prepare a real-capture log session without creating a file.

        The .txt file is created only after the first received frame/RAW block.
        """
        self.close_log()
        self.pending_log_filename = started_at.strftime(
            prefix + "_%Y%m%d_%H%M%S.txt"
        )
        self.pending_log_header = header
        self.pending_log_notes = []
        self.log_start_failed = False
        self.log_path = None

    def ensure_log_started(self):
        """
        Create the pending real-capture log on first actual traffic.

        Returns True when the log is open. A creation failure is reported only
        once for the current capture session.
        """
        if self.log_file:
            return True

        if not self.pending_log_filename or self.log_start_failed:
            return False

        try:
            target = get_logs_folder() / self.pending_log_filename
            self.log_file = target.open("w", encoding="utf-8", buffering=1)
            self.log_path = target

            if self.pending_log_header:
                self.log_file.write(self.pending_log_header)

            if self.pending_log_notes:
                self.log_file.write("".join(self.pending_log_notes))

            self.pending_log_notes = []
            return True

        except OSError as exc:
            self.log_start_failed = True
            self.log_file = None
            self.log_path = None
            messagebox.showerror(
                "Erro ao criar log",
                "Foi detetado tráfego, mas não foi possível criar o ficheiro de log em:\n\n"
                f"{get_logs_folder()}\n\n"
                f"{exc}"
            )
            return False

    def queue_log_note(self, text):
        """
        Write a capture note to an already-open log, or keep it in memory until
        the first traffic frame creates the log.
        """
        if self.log_file:
            self.log_line(text)
        elif self.capture_active and self.pending_log_filename:
            self.pending_log_notes.append(text)

    def log_line(self, text):
        if self.log_file:
            try:
                self.log_file.write(text)
            except Exception:
                pass

    def close_log(self):
        if self.log_file:
            try:
                self.log_file.write(
                    f"# Stop: {datetime.now().isoformat(timespec='milliseconds')}\n"
                )
                self.log_file.close()
            except Exception:
                pass

        self.log_file = None
        self.log_path = None
        self.pending_log_filename = None
        self.pending_log_header = ""
        self.pending_log_notes = []
        self.log_start_failed = False

    def open_log_folder(self):
        try:
            folder = get_logs_folder()
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Abrir pasta", str(exc))

    def clear_view(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.raw_text.delete("1.0", "end")
        self.selected_raw_var.set("")
        self._raw_by_iid = {}
        self._record_by_iid = {}
        self._tree_history.clear()
        self._tree_iids_by_seq.clear()
        self._tree_separator_iid_by_seq.clear()
        self._frame_history.clear()
        self._next_frame_seq = 1
        self._ui_frame_count = 0
        self._raw_text_line_count = 0
        self._raw_separator_width_chars = 1

        self.slave_filter_vars.clear()
        self.slave_filter_all_mode = True
        self.rebuild_slave_filter_menu()

        self._transaction_filter_seqs = None
        self._successful_request_seqs.clear()
        if hasattr(self, "advanced_filter_type_var"):
            self.advanced_filter_type_var.set("Todos")
            self.advanced_filter_fc_var.set("")
            self.advanced_filter_response_ms_var.set("")
            self.advanced_filter_text_var.set("")
        self.update_frame_inspector(None)
        if hasattr(self, "bus_activity_var"):
            self.bus_activity_var.set("BUS ○")

        self.time_order_var.set("Crescente — antigo → recente")
        self.tree_headings["time"] = "Hora ↑"
        self.tree.heading(
            "time",
            text=self.tree_headings["time"],
            anchor="center",
            command=self.toggle_time_order
        )

        # With no traffic, widths/row height return to their default layout.
        self.autofit_tree_columns([])

        self.reset_session_metrics()

