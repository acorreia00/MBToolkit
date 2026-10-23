#!/usr/bin/env python3
"""MBSniffer fixed-geometry Light/Dark theme.

The application uses one ttk construction for its entire lifetime. Light/Dark
switching changes colours only; it never changes ttk theme engine, layouts,
padding, borders, margins, widget metrics or row heights.
"""

import tkinter as tk
from tkinter import ttk


BOOTSTRAP_ACTIVE = False
THEME_ENGINE = "clam"

LIGHT = {
    "root": "#f3f4f6",
    "panel": "#f3f4f6",
    "panel_alt": "#ffffff",
    "input": "#ffffff",
    "input_readonly": "#f5f6f7",
    "text": "#1f2328",
    "muted": "#59636e",
    "disabled": "#8b949e",
    "border": "#c3c9d0",
    "divider": "#d6dbe0",
    "button": "#ffffff",
    "button_hover": "#f0f5fa",
    "button_pressed": "#e3edf6",
    "accent": "#2f80d1",
    "accent_hover": "#3b8edb",
    "accent_pressed": "#246eB8",
    "select": "#2f80d1",
    "select_text": "#ffffff",
    "scroll_trough": "#e8ebee",
    "scroll_thumb": "#b9c2ca",
    "scroll_thumb_hover": "#929faa",
}

DARK = {
    "root": "#171a1f",
    "panel": "#171a1f",
    "panel_alt": "#1f242a",
    "input": "#20262c",
    "input_readonly": "#252c33",
    "text": "#e8eaed",
    "muted": "#aab2ba",
    "disabled": "#707982",
    "border": "#46525d",
    "divider": "#46525d",
    "button": "#252c33",
    "button_hover": "#303942",
    "button_pressed": "#1f252b",
    "accent": "#2f8fd8",
    "accent_hover": "#43a2e8",
    "accent_pressed": "#287bb8",
    "select": "#285f80",
    "select_text": "#ffffff",
    "scroll_trough": "#1d2329",
    "scroll_thumb": "#65717c",
    "scroll_thumb_hover": "#7d8994",
}

_CHECK_IMAGES = None
_CHECK_ELEMENT = "MBS.Check.indicator"
_FIXED_GEOMETRY_READY = False
_INTERP_ID = None


def theme_colors(root=None, dark=False):
    return dict(DARK if dark else LIGHT)


def _ensure_engine(style):
    """Select/configure the fixed engine once per Tk interpreter."""
    global _FIXED_GEOMETRY_READY, _CHECK_IMAGES, _INTERP_ID

    # A normal MBSniffer process owns one Tk root. Handling a replaced Tk
    # interpreter as well makes tests/relaunches in the same Python process
    # safe and prevents stale PhotoImage command references.
    current_interp = id(style.master.tk)
    if _INTERP_ID != current_interp:
        _INTERP_ID = current_interp
        _FIXED_GEOMETRY_READY = False
        _CHECK_IMAGES = None

    try:
        if THEME_ENGINE in style.theme_names() and style.theme_use() != THEME_ENGINE:
            style.theme_use(THEME_ENGINE)
    except Exception:
        pass

    if not _FIXED_GEOMETRY_READY:
        _configure_fixed_geometry(style)
        _FIXED_GEOMETRY_READY = True


def _configure_fixed_geometry(style):
    """
    Define every geometry/state rule once.

    Nothing in this function is called as part of a Light/Dark toggle after
    startup. This is what guarantees that the page construction cannot move.
    """

    # ------------------------------------------------------------------
    # LabelFrames: titles above the rectangular border in both modes.
    # ------------------------------------------------------------------
    style.configure(
        "TLabelframe",
        borderwidth=1,
        relief="solid",
        padding=0,
        labeloutside=True,
        labelmargins=(0, 0, 0, 4),
    )
    style.configure(
        "TLabelframe.Label",
        borderwidth=0,
        padding=0,
        font=("Segoe UI", 9, "bold"),
    )

    # ------------------------------------------------------------------
    # Notebook/tabs: fixed Vista-like top geometry.
    # ------------------------------------------------------------------
    style.configure(
        "TNotebook",
        borderwidth=1,
        padding=0,
        tabmargins=(2, 2, 2, 0),
    )
    style.configure(
        "TNotebook.Tab",
        borderwidth=1,
        padding=(12, 6),
        font=("Segoe UI", 9),
    )
    style.map(
        "TNotebook.Tab",
        expand=[("selected", (2, 2, 2, 2))],
        padding=[("selected", (12, 6))],
        relief=[
            ("selected", "flat"),
            ("active", "flat"),
            ("pressed", "flat"),
        ],
    )

    # ------------------------------------------------------------------
    # Buttons.
    # ------------------------------------------------------------------
    style.configure(
        "TButton",
        borderwidth=1,
        relief="solid",
        padding=(7, 4),
        font=("Segoe UI", 9),
    )
    style.configure(
        "MBS.Toolbar.TButton",
        borderwidth=1,
        relief="solid",
        padding=(9, 5),
        font=("Segoe UI", 9),
    )
    style.configure(
        "MBS.Primary.TButton",
        borderwidth=1,
        relief="solid",
        padding=(9, 5),
        font=("Segoe UI", 9, "bold"),
    )
    style.configure(
        "MBS.Compact.TButton",
        borderwidth=1,
        relief="solid",
        padding=(7, 4),
        font=("Segoe UI", 9),
    )

    # ------------------------------------------------------------------
    # Input controls.
    # ------------------------------------------------------------------
    style.configure("TEntry", borderwidth=1, relief="solid", padding=1)
    style.configure("TCombobox", borderwidth=1, relief="solid", padding=1, arrowsize=10)
    style.configure("TSpinbox", borderwidth=1, relief="solid", padding=1, arrowsize=7)

    # ------------------------------------------------------------------
    # Checkboxes: fixed 15x15 image indicator. The image pixels are recoloured
    # on toggle; the element/layout never changes.
    # ------------------------------------------------------------------
    style.configure(
        "TCheckbutton",
        borderwidth=0,
        relief="flat",
        padding=(1, 1),
        font=("Segoe UI", 9),
    )

    # Create the indicator element from the active clam layout once.
    _install_fixed_checkbutton_element(style)

    # ------------------------------------------------------------------
    # Treeviews.
    # ------------------------------------------------------------------
    style.configure(
        "Treeview",
        borderwidth=1,
        relief="solid",
        font=("Segoe UI", 9),
    )
    style.configure(
        "MBSniffer.Treeview",
        borderwidth=1,
        relief="solid",
        font=("Segoe UI", 9),
    )

    # Important: right + bottom border only. This reproduces Light mode's
    # vertical column divider lines without making every heading look like a
    # separate raised rectangular button.
    for heading in ("Treeview.Heading", "MBSniffer.Treeview.Heading"):
        style.configure(
            heading,
            borderwidth=(0, 0, 1, 1),
            relief="solid",
            padding=(5, 4),
            font=("Segoe UI", 9),
        )
        style.map(
            heading,
            relief=[
                ("active", "solid"),
                ("pressed", "solid"),
            ],
        )

    # Keep MBSniffer.Treeview on the same heading layout as Treeview.
    try:
        heading_layout = style.layout("Treeview.Heading")
        if heading_layout:
            style.layout("MBSniffer.Treeview.Heading", heading_layout)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Scrollbars and named labels.
    # ------------------------------------------------------------------
    # Minimal scrollbars: slim track + thumb only, without arrow buttons or extra controls.
    style.layout(
        "Vertical.TScrollbar",
        [(
            "Vertical.Scrollbar.trough",
            {
                "sticky": "ns",
                "children": [
                    ("Vertical.Scrollbar.thumb", {"sticky": "nswe"})
                ],
            },
        )],
    )
    style.layout(
        "Horizontal.TScrollbar",
        [(
            "Horizontal.Scrollbar.trough",
            {
                "sticky": "we",
                "children": [
                    ("Horizontal.Scrollbar.thumb", {"sticky": "nswe"})
                ],
            },
        )],
    )
    style.configure(
        "Vertical.TScrollbar",
        width=6,
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "Horizontal.TScrollbar",
        width=6,
        borderwidth=0,
        relief="flat",
    )

    style.configure(
        "Horizontal.TProgressbar",
        borderwidth=0,
        thickness=8,
        relief="flat",
    )

    style.configure("MBS.Stat.TLabel", font=("Segoe UI", 9))
    style.configure("MBS.Status.TLabel", font=("Segoe UI", 9, "bold"))


def _paint_checkbox_image(image, *, fill, border, check=None):
    """Repaint one fixed-size checkbox image without changing its dimensions."""
    size = 15
    image.put(border, to=(0, 0, size, size))
    image.put(fill, to=(1, 1, size - 1, size - 1))

    if check:
        # White/black check mark. Coordinates remain identical in both modes.
        points = (
            (3, 7), (4, 8), (5, 9), (6, 10),
            (7, 9), (8, 8), (9, 7), (10, 6), (11, 5), (12, 4),
        )
        for x, y in points:
            image.put(check, to=(x, y, x + 1, y + 2))
            if x + 1 < size - 1:
                image.put(check, to=(x + 1, y, x + 2, y + 1))


def _install_fixed_checkbutton_element(style):
    global _CHECK_IMAGES

    root = style.master
    if _CHECK_IMAGES is None:
        _CHECK_IMAGES = {
            "off": tk.PhotoImage(master=root, width=15, height=15),
            "on": tk.PhotoImage(master=root, width=15, height=15),
            "disabled_off": tk.PhotoImage(master=root, width=15, height=15),
            "disabled_on": tk.PhotoImage(master=root, width=15, height=15),
        }

    try:
        if _CHECK_ELEMENT not in style.element_names():
            style.element_create(
                _CHECK_ELEMENT,
                "image",
                _CHECK_IMAGES["off"],
                ("disabled selected", _CHECK_IMAGES["disabled_on"]),
                ("disabled", _CHECK_IMAGES["disabled_off"]),
                ("selected", _CHECK_IMAGES["on"]),
                sticky="",
            )
    except tk.TclError:
        pass

    try:
        layout = style.layout("TCheckbutton")
    except Exception:
        layout = None

    if not layout:
        return

    def replace_indicator(nodes):
        result = []
        for name, options in nodes:
            options = dict(options)
            if "children" in options:
                options["children"] = replace_indicator(options["children"])
            if name == "Checkbutton.indicator":
                name = _CHECK_ELEMENT
            result.append((name, options))
        return result

    # Avoid repeatedly replacing an already-custom element.
    if _CHECK_ELEMENT not in repr(layout):
        try:
            style.layout("TCheckbutton", replace_indicator(layout))
        except tk.TclError:
            pass


def _repaint_checkboxes(colors, dark):
    if not _CHECK_IMAGES:
        return

    if dark:
        face = colors["input_readonly"]
        border = colors["disabled"]
        check = colors["select_text"]
        disabled_face = colors["panel_alt"]
        disabled_check = colors["disabled"]
    else:
        face = colors["input"]
        border = "#7a7a7a"
        check = "#111111"
        disabled_face = "#e4e4e4"
        disabled_check = "#999999"

    _paint_checkbox_image(
        _CHECK_IMAGES["off"],
        fill=face,
        border=border,
    )
    _paint_checkbox_image(
        _CHECK_IMAGES["on"],
        fill=face,
        border=border,
        check=check,
    )
    _paint_checkbox_image(
        _CHECK_IMAGES["disabled_off"],
        fill=disabled_face,
        border=colors["disabled"],
    )
    _paint_checkbox_image(
        _CHECK_IMAGES["disabled_on"],
        fill=disabled_face,
        border=colors["disabled"],
        check=disabled_check,
    )


def _apply_palette(root, style, colors, dark):
    """
    Apply colours only.

    No call in this function changes:
    - theme engine
    - layout
    - padding
    - border width
    - relief
    - margins
    - font
    - widget dimensions
    """
    c = colors

    style.configure(".", background=c["root"], foreground=c["text"])
    style.configure("TFrame", background=c["root"])
    style.configure("TLabel", background=c["root"], foreground=c["text"])
    style.configure(
        "TLabelframe",
        background=c["root"],
        foreground=c["text"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.configure(
        "TLabelframe.Label",
        background=c["root"],
        foreground=c["text"],
    )

    # Notebook.
    style.configure(
        "TNotebook",
        background=c["root"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.configure(
        "TNotebook.Tab",
        background=c["panel"],
        foreground=c["text"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", c["panel_alt"]),
            ("active", c["panel_alt"]),
        ],
        foreground=[
            ("selected", c["text"]),
            ("active", c["text"]),
        ],
    )

    # Buttons: neutral controls have clear contrast; the primary action uses
    # the same restrained accent in Light and Dark.
    for name in (
        "TButton",
        "MBS.Toolbar.TButton",
        "MBS.Compact.TButton",
    ):
        style.configure(
            name,
            background=c["button"],
            foreground=c["text"],
            bordercolor=c["border"],
            lightcolor=c["border"],
            darkcolor=c["border"],
            focuscolor=c["accent"],
        )
        style.map(
            name,
            background=[
                ("pressed", c["button_pressed"]),
                ("active", c["button_hover"]),
                ("disabled", c["panel"]),
            ],
            foreground=[("disabled", c["disabled"])],
        )

    style.configure(
        "MBS.Primary.TButton",
        background=c["accent"],
        foreground=c["select_text"],
        bordercolor=c["accent"],
        lightcolor=c["accent"],
        darkcolor=c["accent"],
        focuscolor=c["accent"],
    )
    style.map(
        "MBS.Primary.TButton",
        background=[
            ("pressed", c["accent_pressed"]),
            ("active", c["accent_hover"]),
            ("disabled", c["panel"]),
        ],
        foreground=[
            ("disabled", c["disabled"]),
        ],
        bordercolor=[
            ("pressed", c["accent_pressed"]),
            ("active", c["accent_hover"]),
            ("disabled", c["border"]),
        ],
    )

    # Entry / Spinbox.
    for name in ("TEntry", "TSpinbox"):
        style.configure(
            name,
            fieldbackground=c["input"],
            background=c["input"],
            foreground=c["text"],
            bordercolor=c["border"],
            lightcolor=c["border"],
            darkcolor=c["border"],
            insertcolor=c["text"],
        )
        style.map(
            name,
            fieldbackground=[
                ("readonly", c["input_readonly"]),
                ("disabled", c["panel"]),
            ],
            foreground=[("disabled", c["disabled"])],
        )

    # Combobox.
    style.configure(
        "TCombobox",
        fieldbackground=c["input"],
        background=c["button"],
        foreground=c["text"],
        arrowcolor=c["text"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", c["input_readonly"]),
            ("disabled", c["panel"]),
        ],
        foreground=[
            ("readonly", c["text"]),
            ("disabled", c["disabled"]),
        ],
        background=[
            ("active", c["button_hover"]),
            ("disabled", c["panel"]),
        ],
        arrowcolor=[("disabled", c["disabled"])],
    )

    # Checkbox label/background only; indicator pixels are repainted separately.
    style.configure(
        "TCheckbutton",
        background=c["root"],
        foreground=c["text"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", c["root"])],
        foreground=[("disabled", c["disabled"])],
    )
    _repaint_checkboxes(c, dark)

    # Treeview body and flat heading.
    for name in ("Treeview", "MBSniffer.Treeview"):
        style.configure(
            name,
            background=c["input"],
            fieldbackground=c["input"],
            foreground=c["text"],
            bordercolor=c["border"],
            lightcolor=c["border"],
            darkcolor=c["border"],
        )
        style.map(
            name,
            background=[("selected", c["select"])],
            foreground=[("selected", c["select_text"])],
        )

    for name in ("Treeview.Heading", "MBSniffer.Treeview.Heading"):
        style.configure(
            name,
            background=c["input"],
            foreground=c["text"],
            bordercolor=c["divider"],
            lightcolor=c["divider"],
            darkcolor=c["divider"],
        )
        style.map(
            name,
            background=[
                ("active", c["input_readonly"]),
                ("pressed", c["input_readonly"]),
            ],
            foreground=[("active", c["text"])],
        )

    # Scrollbars: only the slim thumb should be visually apparent.
    # The required trough element remains for ttk mechanics, but is painted
    # exactly like the content background so it disappears visually.
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar", "TScrollbar"):
        style.configure(
            name,
            background=c["scroll_thumb"],
            troughcolor=c["input"],
            bordercolor=c["input"],
            darkcolor=c["scroll_thumb"],
            lightcolor=c["scroll_thumb"],
        )
        style.map(
            name,
            background=[
                ("active", c["scroll_thumb_hover"]),
                ("pressed", c["scroll_thumb_hover"]),
            ],
            darkcolor=[
                ("active", c["scroll_thumb_hover"]),
                ("pressed", c["scroll_thumb_hover"]),
            ],
            lightcolor=[
                ("active", c["scroll_thumb_hover"]),
                ("pressed", c["scroll_thumb_hover"]),
            ],
        )

    style.configure(
        "Horizontal.TProgressbar",
        background=c["accent"],
        troughcolor=c["scroll_trough"],
        bordercolor=c["scroll_trough"],
        lightcolor=c["accent"],
        darkcolor=c["accent"],
    )

    style.configure("MBS.Stat.TLabel", background=c["root"], foreground=c["text"])
    style.configure("MBS.Status.TLabel", background=c["root"], foreground=c["text"])

    try:
        root.configure(background=c["root"])
    except Exception:
        pass

    return style


def apply_theme(root, dark=False, style=None):
    """
    Change palette only.

    The ttk engine and all geometry were fixed before the UI was built.
    """
    style = style or ttk.Style(root)
    _ensure_engine(style)
    return _apply_palette(root, style, DARK if dark else LIGHT, bool(dark))


def apply_light_theme(root, style=None):
    return apply_theme(root, dark=False, style=style)


def apply_dark_theme(root, style=None):
    return apply_theme(root, dark=True, style=style)


def apply_modern_theme(root, dark=False):
    """Initial application setup with the same engine used for both modes."""
    style = ttk.Style(root)
    _ensure_engine(style)
    return _apply_palette(root, style, DARK if dark else LIGHT, bool(dark))
