#!/usr/bin/env python3
"""Small reusable Tk widgets for MBSniffer."""

import tkinter as tk


class RefreshButton(tk.Canvas):
    # The fixed clam UI gives the refresh control stable dimensions, so the ↻
    # can now use its measured rendered-bbox centre without manual offsets.
    OPTICAL_OFFSET_X = 0
    OPTICAL_OFFSET_Y = 0

    """
    Square refresh button using the Unicode ↻ glyph.

    The glyph is centered from its actual rendered Tk bounding box. No manual
    X/Y optical offset is applied.
    """

    def __init__(
        self,
        master,
        command,
        size=26,
        cursor="hand2",
        **kwargs,
    ):
        self._command = command
        self._hover = False
        self._pressed = False
        self._state = "normal"
        self._dark_mode = False
        self._final_redraw_after_id = None

        super().__init__(
            master,
            width=size,
            height=size,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor=cursor,
            takefocus=0,
            **kwargs,
        )

        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self._redraw()
        self._schedule_final_redraw()

    @staticmethod
    def _system_color(widget, name, fallback):
        try:
            widget.winfo_rgb(name)
            return name
        except Exception:
            return fallback

    def _schedule_final_redraw(self):
        """
        Redraw after Tk has settled requested widget dimensions.

        Some themed comboboxes report their final height only after the first
        layout pass. A short deferred redraw prevents the Unicode glyph from
        staying centered for an earlier 24 px square after the control becomes
        26 px high.
        """
        try:
            if self._final_redraw_after_id is not None:
                self.after_cancel(self._final_redraw_after_id)
            self._final_redraw_after_id = self.after(20, self._final_redraw)
        except tk.TclError:
            self._final_redraw_after_id = None

    def _final_redraw(self):
        self._final_redraw_after_id = None
        try:
            self._redraw()
        except tk.TclError:
            pass

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            self._state = str(state)

        result = super().configure(cnf, **kwargs)
        try:
            self._redraw()
            self._schedule_final_redraw()
        except tk.TclError:
            pass
        return result

    config = configure

    def cget(self, key):
        if key == "state":
            return self._state
        return super().cget(key)

    def invoke(self):
        if self._state != "disabled" and callable(self._command):
            return self._command()
        return None

    def set_dark_mode(self, enabled):
        self._dark_mode = bool(enabled)
        self._redraw()
        self._schedule_final_redraw()

    def _palette(self):
        if self._dark_mode:
            face = "#2a3138"
            hover = "#36404a"
            pressed = "#20262c"
            text = "#e8eaed"
            gray = "#707982"
            border = "#4a5560"
            highlight = "#2f8fd8"

            if self._state == "disabled":
                return face, gray, border
            if self._pressed:
                return pressed, text, highlight
            if self._hover:
                return hover, text, highlight
            return face, text, border

        face = self._system_color(self, "SystemButtonFace", "#f0f0f0")
        text = self._system_color(self, "SystemButtonText", "#202020")
        gray = self._system_color(self, "SystemGrayText", "#8a8a8a")
        shadow = self._system_color(self, "System3DShadow", "#adadad")
        highlight = self._system_color(self, "SystemHighlight", "#7a9fc2")

        if self._state == "disabled":
            return face, gray, shadow
        if self._pressed:
            return face, text, highlight
        if self._hover:
            return face, text, highlight
        return face, text, shadow

    def _center_item_bbox(self, item, width, height):
        """Center the visible Tk bbox of one Canvas item on the square."""
        target_x = width / 2.0
        target_y = height / 2.0

        # Tk text bboxes land on integer pixels. Repeat because a fractional
        # first move may be rounded by the Canvas implementation.
        for _ in range(4):
            bbox = self.bbox(item)
            if not bbox:
                return
            current_x = (bbox[0] + bbox[2]) / 2.0
            current_y = (bbox[1] + bbox[3]) / 2.0
            dx = target_x - current_x
            dy = target_y - current_y

            if abs(dx) <= 0.5 and abs(dy) <= 0.5:
                break

            # Move by integral pixels when a full-pixel correction is needed.
            move_x = round(dx) if abs(dx) > 0.5 else 0
            move_y = round(dy) if abs(dy) > 0.5 else 0
            if move_x == 0 and move_y == 0:
                break
            self.move(item, move_x, move_y)

        # Keep the explicit offset hook at zero so all three refresh buttons
        # use the same measured centre.
        if self.OPTICAL_OFFSET_X or self.OPTICAL_OFFSET_Y:
            self.move(
                item,
                self.OPTICAL_OFFSET_X,
                self.OPTICAL_OFFSET_Y,
            )

    def _redraw(self, _event=None):
        if not self.winfo_exists():
            return

        # During a <Configure> callback winfo_width()/height() may still
        # report the previous geometry on some Tk builds. Prefer the event's
        # new dimensions so centering is calculated for the final square.
        if _event is not None and hasattr(_event, "width") and hasattr(_event, "height"):
            width = max(2, int(_event.width))
            height = max(2, int(_event.height))
        else:
            width = max(2, int(self.winfo_width()))
            height = max(2, int(self.winfo_height()))

        background, foreground, border = self._palette()

        self.delete("all")
        self.create_rectangle(
            0,
            0,
            width - 1,
            height - 1,
            fill=background,
            outline=border,
            width=1,
            tags=("background",),
        )

        glyph = self.create_text(
            width / 2.0,
            height / 2.0,
            text="↻",
            fill=foreground,
            font=("Segoe UI Symbol", 13),
            anchor="center",
            tags=("glyph",),
        )
        self._center_item_bbox(glyph, width, height)

    def _on_enter(self, _event):
        if self._state != "disabled":
            self._hover = True
            self._redraw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event):
        if self._state != "disabled":
            self._pressed = True
            self._redraw()

    def _on_release(self, event):
        if self._state == "disabled":
            return

        was_pressed = self._pressed
        self._pressed = False
        self._redraw()

        inside = (
            0 <= event.x < self.winfo_width()
            and 0 <= event.y < self.winfo_height()
        )
        if was_pressed and inside and callable(self._command):
            self._command()



class ToggleSwitch(tk.Canvas):
    """Compact on/off slider used for the Light/Dark mode control."""

    def __init__(
        self,
        master,
        variable,
        command=None,
        width=42,
        height=22,
        cursor="hand2",
        **kwargs,
    ):
        self.variable = variable
        self.command = command
        self._dark_mode = False
        self._hover = False
        self._final_redraw_after_id = None

        super().__init__(
            master,
            width=width,
            height=height,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor=cursor,
            takefocus=0,
            **kwargs,
        )

        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._toggle, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.variable.trace_add("write", lambda *_a: self._redraw())
        self._redraw()
        self._schedule_final_redraw()

    def _schedule_final_redraw(self):
        try:
            if self._final_redraw_after_id is not None:
                self.after_cancel(self._final_redraw_after_id)
            self._final_redraw_after_id = self.after(20, self._final_redraw)
        except tk.TclError:
            self._final_redraw_after_id = None

    def _final_redraw(self):
        self._final_redraw_after_id = None
        try:
            self._redraw()
        except tk.TclError:
            pass

    def set_dark_mode(self, enabled):
        self._dark_mode = bool(enabled)
        self._redraw()
        self._schedule_final_redraw()

    def _parent_bg(self):
        if self._dark_mode:
            return "#171a1f"
        try:
            self.winfo_rgb("SystemButtonFace")
            return "SystemButtonFace"
        except Exception:
            return "#f0f0f0"

    def _press(self, _event=None):
        # Deliberately do not focus the Canvas. This removes the white focus
        # rectangle that appeared around the switch after mouse clicks.
        return "break"

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        if callable(self.command):
            self.command()
        return "break"

    def _enter(self, _event=None):
        self._hover = True
        self._redraw()

    def _leave(self, _event=None):
        self._hover = False
        self._redraw()

    def _redraw(self, _event=None):
        if not self.winfo_exists():
            return

        # Use the final dimensions delivered by <Configure>. Without this, the
        # first draw can happen while Tk still reports the initial 1x1 Canvas,
        # which made the switch look small until the first mouse hover.
        if _event is not None and hasattr(_event, "width") and hasattr(_event, "height"):
            width = max(22, int(_event.width))
            height = max(14, int(_event.height))
        else:
            width = max(22, int(self.winfo_width()))
            height = max(14, int(self.winfo_height()))

        on = bool(self.variable.get())

        self.configure(background=self._parent_bg())
        self.delete("all")

        pad = 2
        radius = (height - 2 * pad) / 2.0
        x0, y0 = pad, pad
        x1, y1 = width - pad, height - pad

        if self._dark_mode:
            off_track = "#5a646e"
            on_track = "#2f8fd8"
            hover_track = "#43a2e8"
            knob = "#f4f6f8"
            outline = "#68737d"
        else:
            off_track = "#a8a8a8"
            on_track = "#2689d9"
            hover_track = "#3b9be5"
            knob = "#ffffff"
            outline = "#8f8f8f"

        track = hover_track if self._hover and on else (on_track if on else off_track)

        # Rounded track: rectangle + two circles.
        self.create_rectangle(
            x0 + radius,
            y0,
            x1 - radius,
            y1,
            fill=track,
            outline=track,
        )
        self.create_oval(
            x0,
            y0,
            x0 + 2 * radius,
            y1,
            fill=track,
            outline=track,
        )
        self.create_oval(
            x1 - 2 * radius,
            y0,
            x1,
            y1,
            fill=track,
            outline=track,
        )

        knob_radius = max(4.0, radius - 2)
        knob_cx = (x1 - radius) if on else (x0 + radius)
        knob_cy = height / 2.0
        self.create_oval(
            knob_cx - knob_radius,
            knob_cy - knob_radius,
            knob_cx + knob_radius,
            knob_cy + knob_radius,
            fill=knob,
            outline=outline,
            width=1,
        )
