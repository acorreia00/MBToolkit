#!/usr/bin/env python3
"""Build the MBToolkit Technical Code Documentation PDF for any version.

The PDF is generated from the exact release package (ZIP or extracted
folder) plus the hand-written text in ``technical_doc_content.py``:

* package tree, line counts and SHA-256 hashes are measured from the files;
* the module reference (callables, line ranges, signatures, constants,
  imports, representative direct calls) is derived from the Python AST;
* the regression suite is executed and its result is printed on the cover;
* Appendix A renders every .py / .bat line as syntax-highlighted
  screenshots, 40 lines per landscape page;
* the HTML is laid out by headless Google Chrome / Microsoft Edge
  (print-to-PDF, two passes so the Contents page numbers are exact).

Requirements (outside the release package):
    pip install pymupdf pygments pillow
    Google Chrome or Microsoft Edge installed.

Typical use (from the repository root):
    python -B tools/build_technical_pdf.py --source-dir . \
        --version 3.2 --screenshots tools/screenshots \
        --output MBToolkit_v3.2_Technical_Code_Documentation.pdf

Run ``tools/capture_ui_screenshots.py`` first so the UI figures show the
documented version.  The generator never writes into the package folder.

The PDF itself travels inside the release ZIP (built afterwards by
``tools/build_package.py``), so the cover quotes a "Source snapshot SHA-256"
over the documented files instead of the hash of the ZIP.  .git, tools/
and the PDF are shown in the package tree but not documented.
"""

import argparse
import ast
import copy
import datetime as _dt
import hashlib
import html
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
FONTS_DIR = TOOLS_DIR / "fonts"

# Package entries that are carried in the release ZIP but are not documented
# application source (see Package.is_support_file).
SUPPORT_DIRS = {".git", "tools"}
SUPPORT_FILES = {".gitignore"}

APPENDIX_LINES_PER_PAGE = 40
CALLS_LIMIT = 5
CALLS_TEXT_LIMIT = 140
CONSTANT_TEXT_LIMIT = 150

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def esc(text):
    return html.escape(str(text), quote=False)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def read_text(path):
    data = Path(path).read_bytes()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def line_count(path):
    return len(read_text(path).splitlines())


def load_content(path):
    spec = importlib.util.spec_from_file_location("technical_doc_content", path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def file_uri(path):
    return Path(path).resolve().as_uri()


def first_sentence(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    match = re.search(r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)[.!?](?=\s+[A-Z0-9(\"'`])", text)
    sentence = text[: match.end()] if match else text
    if sentence[-1] not in ".!?":
        sentence += "."
    return sentence


def docstring_sentence(node):
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return ""
    paragraph = doc.strip().split("\n\n", 1)[0]
    return first_sentence(paragraph)


def humanize(name, kind):
    if kind == "class":
        return f"{name}."
    if name.startswith("test_"):
        return "Regression test: " + name[5:].replace("_", " ") + "."
    if name == "__init__":
        return "Init."
    stripped = name.strip("_")
    if stripped.startswith("on_"):
        return "Event handler for " + stripped[3:].replace("_", " ") + "."
    if stripped.startswith("schedule_"):
        return "Schedules " + stripped[9:].replace("_", " ") + "."
    words = stripped.replace("_", " ").strip()
    return (words[:1].upper() + words[1:] + ".") if words else f"{name}."


def version_key(text):
    return tuple(int(part) if part.isdigit() else 0 for part in str(text).split("."))


def format_date(day):
    return f"{day.day} {day.strftime('%B %Y')}"


# ---------------------------------------------------------------------------
# Package discovery
# ---------------------------------------------------------------------------

class Package:
    def __init__(self, root, version, content, zip_path=None):
        self.root = Path(root)
        self.version = version
        self.content = content
        self.zip_path = Path(zip_path) if zip_path else None
        folder = self.root / f"MBToolkit v{version}"
        if not folder.is_dir():
            candidates = [p for p in self.root.iterdir() if p.is_dir() and p.name.startswith("MBToolkit v")]
            if len(candidates) != 1:
                raise SystemExit(f"Cannot find the 'MBToolkit v{version}' folder in {self.root}")
            folder = candidates[0]
        self.app_dir = folder
        self.files = self._list_files()

    def _list_files(self):
        if self.zip_path:
            names = [n for n in zipfile.ZipFile(self.zip_path).namelist() if not n.endswith("/")]
        else:
            names = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]
        names = [n for n in names if "__pycache__" not in n and not n.endswith(".pyc")]
        # The package also carries the git history, the documentation tools and
        # this PDF itself; they are listed in the tree but are not documented
        # application source.
        return [n for n in names if not self.is_support_file(n)]

    @staticmethod
    def is_support_file(relpath):
        parts = relpath.split("/")
        if parts[0] in SUPPORT_DIRS or parts[0] in SUPPORT_FILES:
            return True
        if len(parts) == 1 and relpath.lower().endswith((".pdf", ".exe")):
            return True
        # Local build artefacts (same rule as tools/build_package.py).
        return "build" in parts[1:-1] or relpath.lower().endswith(".spec")

    def snapshot_sha256(self):
        """One SHA-256 over every documented file (path + content hash).

        The PDF travels inside the release ZIP, so it cannot quote the hash of
        that ZIP; this hash identifies the documented source instead and is
        reproducible with ``tools/build_package.py --snapshot-hash``.
        """
        digest = hashlib.sha256()
        for relpath in sorted(self.files):
            digest.update(f"{relpath}\0{sha256_file(self.path(relpath))}\n".encode("utf-8"))
        return digest.hexdigest()

    def order_key(self, relpath):
        prefix = self.app_dir.name + "/"
        if relpath.startswith(prefix):
            inner = relpath[len(prefix):]
            order = self.content.FILE_ORDER
            return (1, order.index(inner) if inner in order else len(order), inner)
        order = self.content.ROOT_FILE_ORDER
        return (0, order.index(relpath) if relpath in order else len(order), relpath)

    def ordered(self, suffixes):
        selected = [f for f in self.files if f.lower().endswith(suffixes)]
        return sorted(selected, key=self.order_key)

    def python_files(self):
        return self.ordered((".py",))

    def batch_files(self):
        order = getattr(self.content, "BAT_ORDER", [])
        bats = [f for f in self.files if f.lower().endswith(".bat")]
        return sorted(bats, key=lambda f: (order.index(Path(f).name) if Path(f).name in order else len(order), f))

    def source_files(self):
        """All .py then all .bat files, in documentation order."""
        return self.python_files() + self.batch_files()

    def path(self, relpath):
        return self.root / relpath

    def inner(self, relpath):
        prefix = self.app_dir.name + "/"
        return relpath[len(prefix):] if relpath.startswith(prefix) else relpath

    def tree_text(self):
        zip_name = self.zip_path.name if self.zip_path else f"MBToolkit_v{self.version}_Package.zip"
        roots = sorted([f for f in self.files if "/" not in f], key=self.order_key)
        inner = sorted([f for f in self.files if f.startswith(self.app_dir.name + "/")], key=self.order_key)
        lines = [zip_name]
        support = ["tools/  (documentation and package builders)",
                   f"MBToolkit_v{self.version}_Technical_Code_Documentation.pdf  (this document)"]
        entries = ([(s, None) for s in support] + [(r, None) for r in roots]
                   + [(self.app_dir.name + "/", inner)])
        for idx, (name, children) in enumerate(entries):
            last = idx == len(entries) - 1
            lines.append(("└── " if last else "├── ") + name)
            if children:
                for cidx, child in enumerate(children):
                    clast = cidx == len(children) - 1
                    lines.append("    " + ("└── " if clast else "├── ") + self.inner(child))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------

def strip_annotations(args):
    args = copy.deepcopy(args)
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        arg.annotation = None
    if args.vararg:
        args.vararg.annotation = None
    if args.kwarg:
        args.kwarg.annotation = None
    return args


def representative_calls(node):
    seen = []
    for sub in ast.walk(node):
        if sub in node.decorator_list:
            continue
        if isinstance(sub, ast.Call):
            try:
                text = ast.unparse(sub.func)
            except Exception:
                continue
            if text not in seen:
                seen.append(text)
    if not seen:
        return "—"
    text = ", ".join(seen[:CALLS_LIMIT])
    if len(text) > CALLS_TEXT_LIMIT:
        text = text[: CALLS_TEXT_LIMIT - 1] + "…"
    return text


def import_names(tree):
    out = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = ("." * node.level) + (node.module or "")
            for idx, alias in enumerate(node.names):
                out.append(f"{module}.{alias.name}" if idx == 0 else alias.name)
    return out


def module_constants(tree):
    out = []
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not names or value is None:
            continue
        text = ast.unparse(value)
        if len(text) > CONSTANT_TEXT_LIMIT:
            text = text[: CONSTANT_TEXT_LIMIT - 3] + "…"
        for name in names:
            out.append((name, text))
    return out


class ModuleInfo:
    def __init__(self, package, relpath):
        self.relpath = relpath
        self.inner = package.inner(relpath)
        self.name = Path(relpath).name
        self.path = package.path(relpath)
        self.text = read_text(self.path)
        self.lines = len(self.text.splitlines())
        self.sha = sha256_file(self.path)
        self.tree = ast.parse(self.text)
        content = package.content
        self.intro = content.MODULE_INTROS.get(self.inner) or content.MODULE_INTROS.get(self.name)
        if not self.intro:
            lead = docstring_sentence(self.tree) or f"{self.name}."
            self.intro = f"<b>{esc(lead)}</b>"
        self.lead = first_sentence(re.search(r"<b>(.*?)</b>", self.intro).group(1)
                                   if "<b>" in self.intro else self.intro)
        self.details = content.KEY_PATH_DETAILS.get(self.inner) or content.KEY_PATH_DETAILS.get(self.name) or []
        self.design_note = content.DESIGN_NOTES.get(self.inner) or content.DESIGN_NOTES.get(self.name)
        self.imports = import_names(self.tree)
        self.constants = module_constants(self.tree)
        self.callables = self._callables()

    def _detail_for(self, qualname):
        bare = qualname.split(".")[-1]
        for name, text in self.details:
            if name == qualname:
                return text
        for name, text in self.details:
            if name == bare and "." not in name:
                return text
        return None

    def detail_lines(self, name):
        for item in self.callables:
            if item["qualname"] == name or item["name"] == name:
                return item["lines"]
        return ""

    def _callables(self):
        out = []

        def function_row(node, qualname):
            detail = self._detail_for(qualname)
            responsibility = (first_sentence(detail) if detail else "") or docstring_sentence(node) \
                or humanize(node.name, "function")
            return {
                "kind": "function",
                "name": node.name,
                "qualname": qualname,
                "signature": f"{node.name}({ast.unparse(strip_annotations(node.args))})",
                "lines": f"{node.lineno}-{node.end_lineno}",
                "responsibility": responsibility,
                "calls": representative_calls(node),
            }

        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(function_row(node, node.name))
            elif isinstance(node, ast.ClassDef):
                detail = self._detail_for(node.name)
                out.append({
                    "kind": "class",
                    "name": node.name,
                    "qualname": node.name,
                    "signature": "",
                    "lines": f"{node.lineno}-{node.end_lineno}",
                    "responsibility": (first_sentence(detail) if detail else "")
                    or docstring_sentence(node) or humanize(node.name, "class"),
                    "calls": "Class container",
                })
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out.append(function_row(sub, f"{node.name}.{sub.name}"))
        return out


def test_classes(module):
    out = []
    for node in module.tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [ast.unparse(b) for b in node.bases]
        if not any("TestCase" in b for b in bases):
            continue
        tests = []
        for sub in node.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                tests.append((sub.name, f"{sub.lineno}-{sub.end_lineno}",
                              docstring_sentence(sub) or humanize(sub.name, "function")))
        out.append((node.name, tests))
    return out


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

def run_regression_tests(package, python_exe):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [python_exe, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=package.app_dir, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900,
    )
    output = proc.stdout + proc.stderr
    ran = re.search(r"Ran (\d+) tests?", output)
    total = int(ran.group(1)) if ran else 0
    failures = errors = 0
    status = re.search(r"FAILED \(([^)]*)\)", output)
    if status:
        for part in status.group(1).split(","):
            key, _, value = part.strip().partition("=")
            if key == "failures":
                failures = int(value)
            elif key == "errors":
                errors = int(value)
    ok = proc.returncode == 0 and total > 0
    return {"total": total, "failures": failures, "errors": errors, "ok": ok, "output": output}


# ---------------------------------------------------------------------------
# Appendix screenshots (Pillow + Pygments "friendly" style)
# ---------------------------------------------------------------------------

class CodeRenderer:
    WIDTH = 1500
    MARGIN = 21
    TITLE_BASELINE = 35
    CODE_TOP = 49
    LINE_HEIGHT = 17.5
    CODE_X = 56
    LINENO_RIGHT = 51
    FONT_PX = 13.33

    def __init__(self):
        from PIL import ImageFont
        from pygments.styles import get_style_by_name
        self.style = get_style_by_name("friendly")
        self.fonts = {
            (False, False): ImageFont.truetype(str(FONTS_DIR / "DejaVuSansMono.ttf"), self.FONT_PX),
            (True, False): ImageFont.truetype(str(FONTS_DIR / "DejaVuSansMono-Bold.ttf"), self.FONT_PX),
            (False, True): ImageFont.truetype(str(FONTS_DIR / "DejaVuSansMono-Oblique.ttf"), self.FONT_PX),
            (True, True): ImageFont.truetype(str(FONTS_DIR / "DejaVuSansMono-BoldOblique.ttf"), self.FONT_PX),
        }
        title_font = None
        for candidate in (r"C:\Windows\Fonts\LiberationSans-Bold.ttf", r"C:\Windows\Fonts\arialbd.ttf",
                          str(FONTS_DIR / "DejaVuSans-Bold.ttf")):
            if Path(candidate).exists():
                title_font = candidate
                break
        self.title_font = ImageFont.truetype(title_font, 17)
        self.char_w = self.fonts[(False, False)].getlength("M")
        self.max_cols = int((self.WIDTH - self.MARGIN - self.CODE_X - 6) // self.char_w)
        self.bg = self._hex(self.style.background_color or "#f0f0f0")

    @staticmethod
    def _hex(value):
        value = value.lstrip("#")
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    def token_lines(self, text, filename):
        from pygments.lexers import get_lexer_for_filename
        try:
            lexer = get_lexer_for_filename(filename, stripnl=False, ensurenl=False)
        except Exception:
            from pygments.lexers import TextLexer
            lexer = TextLexer()
        lines = [[]]
        for ttype, value in lexer.get_tokens(text.expandtabs(4)):
            style = self.style.style_for_token(ttype)
            fmt = (style["color"], bool(style["bold"]), bool(style["italic"]))
            parts = value.split("\n")
            for idx, part in enumerate(parts):
                if idx:
                    lines.append([])
                if part:
                    lines[-1].append((part, fmt))
        if lines and not lines[-1] and text.endswith("\n"):
            lines.pop()
        return lines

    def wrap(self, tokens):
        rows, current, width = [], [], 0
        for value, fmt in tokens:
            while value:
                room = self.max_cols - width
                if room <= 0:
                    rows.append(current)
                    current, width = [], 0
                    room = self.max_cols
                piece, value = value[:room], value[room:]
                current.append((piece, fmt))
                width += len(piece)
        rows.append(current)
        return rows

    def render(self, title, numbered_rows, out_path):
        from PIL import Image, ImageDraw
        visual = []
        for number, tokens in numbered_rows:
            for idx, row in enumerate(self.wrap(tokens)):
                visual.append((number if idx == 0 else None, row))
        code_h = len(visual) * self.LINE_HEIGHT
        height = int(round(self.CODE_TOP + code_h + self.MARGIN))
        image = Image.new("RGB", (self.WIDTH, height), (248, 250, 252))
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, self.WIDTH - 1, height - 1], outline=(203, 213, 225))
        draw.text((self.MARGIN, self.TITLE_BASELINE), title, font=self.title_font, fill=(17, 24, 39), anchor="ls")
        draw.rectangle([self.MARGIN, self.CODE_TOP, self.WIDTH - self.MARGIN - 1,
                        int(round(self.CODE_TOP + code_h)) - 1], fill=self.bg)
        regular = self.fonts[(False, False)]
        for idx, (number, row) in enumerate(visual):
            baseline = self.CODE_TOP + idx * self.LINE_HEIGHT + 13.2
            if number is not None:
                draw.text((self.LINENO_RIGHT, baseline), str(number), font=regular, fill=(112, 112, 112), anchor="rs")
            x = self.CODE_X
            for value, (color, bold, italic) in row:
                fill = self._hex(color) if color else (17, 17, 17)
                draw.text((x, baseline), value, font=self.fonts[(bold, italic)], fill=fill, anchor="ls")
                x += self.char_w * len(value)
        image = image.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        image.save(out_path, optimize=True)
        return image.size


# ---------------------------------------------------------------------------
# Diagrams (inline SVG)
# ---------------------------------------------------------------------------

NODE_STYLES = {
    "plain": "#f8fafc",
    "primary": "#bfdbfe",
    "launcher": "#dbeafe",
    "tests": "#fef3c7",
    "protocol": "#dcfce7",
    "physical": "#e2e8f0",
    "settings": "#fef3c7",
}


def svg_diagram(spec, tests_count):
    width, height = spec["size"]
    font_px = 10.2
    line_h = 12.0
    edge_color = spec.get("edge_color", "#64748b")
    nodes = {}
    parts = []
    for key, (cx, cy, label, style) in spec["nodes"].items():
        label = label.replace("{tests}", str(tests_count))
        lines = label.split("\n")
        w = max(len(line) for line in lines) * font_px * 0.56 + 22
        h = len(lines) * line_h + 16
        nodes[key] = (cx, cy, w, h, lines, NODE_STYLES.get(style, NODE_STYLES["plain"]))

    def boundary(node, toward):
        cx, cy, w, h = node[:4]
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        scale = min((w / 2) / abs(dx) if dx else math.inf, (h / 2) / abs(dy) if dy else math.inf)
        return cx + dx * scale, cy + dy * scale

    marker = (f'<marker id="ah-{id(spec)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
              f'markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L10,5 L0,9 z" fill="{edge_color}"/></marker>')
    edges_svg = []
    labels_svg = []
    for src, dst, opts in spec["edges"]:
        a, b = nodes[src], nodes[dst]
        via = opts.get("via") or []
        bend = opts.get("bend", 0)
        if via:
            start = boundary(a, via[0])
            end = boundary(b, via[-1])
            pts = [start] + list(via) + [end]
            d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
            ext = [pts[0]] + pts + [pts[-1]]
            for i in range(1, len(ext) - 2):
                p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
                c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
                c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
                d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
            inner = pts[1:-1]
            mid = ((inner[0][0] + inner[-1][0]) / 2, (inner[0][1] + inner[-1][1]) / 2)
        else:
            ax, ay = a[0], a[1]
            bx, by = b[0], b[1]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            length = math.hypot(bx - ax, by - ay) or 1
            nx, ny = -(by - ay) / length, (bx - ax) / length
            ctrl = (mx + nx * bend * 2, my + ny * bend * 2)
            start = boundary(a, ctrl if bend else (bx, by))
            end = boundary(b, ctrl if bend else (ax, ay))
            if bend:
                d = f"M{start[0]:.1f},{start[1]:.1f} Q{ctrl[0]:.1f},{ctrl[1]:.1f} {end[0]:.1f},{end[1]:.1f}"
                mid = (0.25 * start[0] + 0.5 * ctrl[0] + 0.25 * end[0], 0.25 * start[1] + 0.5 * ctrl[1] + 0.25 * end[1])
            else:
                d = f"M{start[0]:.1f},{start[1]:.1f} L{end[0]:.1f},{end[1]:.1f}"
                mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        dash = ' stroke-dasharray="5,4"' if opts.get("dashed") else ""
        both = f' marker-start="url(#ah-{id(spec)})"' if opts.get("both") else ""
        edges_svg.append(f'<path d="{d}" fill="none" stroke="{edge_color}" stroke-width="1.1"{dash}'
                         f' marker-end="url(#ah-{id(spec)})"{both}/>')
        if opts.get("label"):
            labels_svg.append(
                f'<text x="{mid[0] + 4:.1f}" y="{mid[1] + 4:.1f}" font-family="DejaVu Serif" '
                f'font-size="13" fill="#111827">{esc(opts["label"])}</text>')
    for key, (cx, cy, w, h, lines, fill) in nodes.items():
        parts.append(f'<rect x="{cx - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" '
                     f'rx="11" ry="11" fill="{fill}" stroke="#64748b" stroke-width="1"/>')
        top = cy - (len(lines) - 1) * line_h / 2
        for idx, line in enumerate(lines):
            parts.append(f'<text x="{cx:.1f}" y="{top + idx * line_h + font_px * 0.36:.1f}" text-anchor="middle" '
                         f'font-family="DejaVu Sans" font-size="{font_px}" fill="#111827">{esc(line)}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'style="width:{spec.get("max_width_pct", 100)}%"><defs>{marker}</defs>'
           + "".join(edges_svg) + "".join(parts) + "".join(labels_svg) + "</svg>")
    return (f'<figure class="diagram">{svg}<figcaption>{esc(spec["caption"])}</figcaption></figure>')


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

CSS = r"""
@font-face { font-family: "DejaVu Sans"; src: url("{fonts}/DejaVuSans.ttf"); }
@font-face { font-family: "DejaVu Sans"; font-weight: bold; src: url("{fonts}/DejaVuSans-Bold.ttf"); }
@font-face { font-family: "DejaVu Sans"; font-style: italic; src: url("{fonts}/DejaVuSans-Oblique.ttf"); }
@font-face { font-family: "DejaVu Sans Mono"; src: url("{fonts}/DejaVuSansMono.ttf"); }
@font-face { font-family: "DejaVu Sans Mono"; font-weight: bold; src: url("{fonts}/DejaVuSansMono-Bold.ttf"); }
@font-face { font-family: "DejaVu Serif"; src: url("{fonts}/DejaVuSerif.ttf"); }

@page {
  size: A4;
  margin: 17mm 16mm 18mm 16mm;
  @bottom-center {
    content: "MBToolkit v{version} Technical Code Documentation  |  " counter(page) " / " counter(pages);
    font-family: "DejaVu Serif", Georgia, serif; font-size: 8pt; color: #64748b;
  }
}
@page appendix {
  size: A4 landscape;
  margin: 9mm 12mm 12mm 12mm;
  @bottom-center {
    content: "MBToolkit v{version} - source appendix  |  " counter(page) " / " counter(pages);
    font-family: "DejaVu Serif", Georgia, serif; font-size: 8pt; color: #64748b;
  }
}
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "DejaVu Sans", sans-serif; font-size: 9.5pt; line-height: 1.45;
       color: #172033; }
.serif-preload { font-family: "DejaVu Serif"; font-size: 1pt; color: #fff; position: absolute; }
p { margin: 0 0 7pt 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.7pt; background: #f1f5f9;
       padding: 0 2pt; border-radius: 3px; overflow-wrap: anywhere; }
b, strong { font-weight: bold; }
h1 { font-size: 25pt; line-height: 1.32; color: #0f2745; margin: 0 0 20pt 0; break-before: page;
     break-after: avoid; }
h2 { font-size: 17pt; line-height: 1.3; color: #0f2745; margin: 20pt 0 13pt 0; padding-bottom: 8pt;
     border-bottom: 1px solid #cbd5e1; break-after: avoid; }
h3 { font-size: 12.5pt; color: #0f2745; margin: 16pt 0 9pt 0; break-after: avoid; }
h1 + h2, h1 + figure + h2 { margin-top: 6pt; }
.lead { font-size: 10.2pt; }
ul, ol { margin: 0 0 8pt 0; padding-left: 18pt; }
ul { list-style: none; padding-left: 13pt; }
ul > li::before { content: "•"; display: inline-block; width: 8pt; margin-left: -9pt; }
li { margin: 0 0 3.5pt 0; }
ol > li { padding-left: 2pt; }
ol > li::marker { color: #172033; }

/* Cover */
.cover { position: relative; padding-top: 22pt; }
.cover .logo { position: absolute; right: 0; top: 22pt; width: 72pt; height: 72pt; }
.cover h1 { break-before: auto; font-size: 34pt; line-height: 1.17; color: #0b3768; margin: 34pt 0 18pt 0;
            width: 78%; }
.cover .subtitle { font-size: 15pt; line-height: 1.45; color: #475569; margin: 0 0 46pt 0; }
.cover dl { background: #eff6ff; border-left: 4px solid #2f80d1; padding: 13pt 16pt 12pt 16pt;
            margin: 0 0 24pt 0; }
.cover dt { font-weight: bold; margin-top: 9pt; }
.cover dt:first-child { margin-top: 0; }
.cover dd { margin: 2pt 0 0 0; }
.cover dd code { font-size: 8.7pt; }
.cover dd code.sha { font-size: 7.2pt; }

/* Contents */
.toc h1 { break-before: page; font-size: 17pt; margin: 18pt 0 22pt 0; padding-bottom: 12pt;
          border-bottom: 1px solid #cbd5e1; }
.toc ol { list-style: none; padding: 0 0 0 10pt; margin: 0; }
.toc li { display: flex; align-items: baseline; margin: 0 0 6.2pt 0; padding: 0; }
.toc .num { width: 22pt; text-align: right; padding-right: 4pt; flex: none; }
.toc a { color: #1d4f91; text-decoration: none; flex: none; }
.toc .dots { flex: 1; overflow: hidden; white-space: nowrap; color: #64748b; margin: 0 3pt; }
.toc .dots::after { content: ". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . ."; letter-spacing: -1.6pt; }
.toc .page { color: #64748b; flex: none; }

/* Cards, callouts, code blocks */
.cards { display: flex; gap: 8pt; margin: 0 0 12pt 0; }
.card { background: #f8fafc; border: 1px solid #dbe2ea; border-radius: 3px; padding: 9pt 9pt 9pt 9pt; }
.card .label { font-weight: bold; display: block; margin-bottom: 1pt; }
.card.narrow { flex: 0 0 29%; }
.card.wide { flex: 1; }
.card code.sha { font-size: 7.2pt; }
.callout { padding: 10pt 14pt; margin: 10pt 0 14pt 0; border-left: 4px solid #2f80d1; background: #eff6ff;
           break-inside: avoid; }
.callout.warn { border-left-color: #d97706; background: #fff7ed; }
.callout.ok { border-left-color: #15803d; background: #f0fdf4; }
.callout.fail { border-left-color: #b91c1c; background: #fef2f2; }
pre.tree { background: #0f172a; color: #e2e8f0; border-radius: 6px; padding: 14pt 14pt 13pt 14pt;
           font-family: "DejaVu Sans Mono", monospace; font-size: 8.7pt; line-height: 1.5; margin: 0 0 14pt 0;
           white-space: pre; break-inside: avoid; }
figure { margin: 6pt 0 14pt 0; text-align: center; break-inside: avoid; }
figure svg { display: block; margin: 0 auto; }
figure img.ui { width: 100%; border: 1px solid #94a3b8; box-sizing: border-box; display: block; }
figcaption { font-size: 8.5pt; color: #64748b; margin-top: 9pt; }

/* Tables */
table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8.3pt; line-height: 1.42;
        margin: 0 0 12pt 0; }
th { background: #e9f1fb; color: #163a63; font-weight: bold; text-align: left; padding: 7pt 6pt;
     border-top: 0.75pt solid #b8c5d4; border-bottom: 0.75pt solid #b8c5d4; }
td { padding: 6pt 6pt 6pt 6pt; vertical-align: top; border-bottom: 0.75pt solid #ccd6e0;
     overflow-wrap: break-word; }
td.nowrap { white-space: nowrap; }
th, td { border-left: 0.75pt solid #ccd6e0; border-right: 0.75pt solid #ccd6e0; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
td code { font-size: 8.3pt; }
td .sig { display: block; font-size: 7.5pt; color: #64748b; margin-top: 1pt; overflow-wrap: anywhere; }
tr.classrow td { background: #f8fafc; font-weight: bold; }
td.calls code { background: #f1f5f9; }
.imports { margin: 0 0 12pt 0; }
.imports code { font-size: 8.7pt; }

/* Key-path cards */
.detail { border: 1px solid #d7e0ea; border-radius: 6px; padding: 9pt 13pt 6pt 13pt; margin: 0 0 8pt 0;
          break-inside: avoid; }
.detail .head { font-size: 8pt; font-weight: bold; color: #64748b; margin-bottom: 5pt; }
.detail .head code { font-size: 8pt; font-weight: bold; color: #0f2745; }

.module { break-before: page; }
.module > h2:first-child { margin-top: 18pt; }

/* Appendix */
.appendix-page { page: appendix; break-before: page; }
.appendix-label { font-size: 8pt; color: #475569; margin: 0 0 7pt 0; height: 11pt; }
.appendix-page h2 { font-size: 13pt; margin: 0 0 5pt 0; padding-bottom: 4pt; }
.appendix-page .lines { font-size: 8.5pt; margin: 0 0 6pt 0; }
.appendix-page img { width: 100%; display: block; }
"""


def wbr(text):
    """Escape identifier text and allow line breaks after '_', '.' and '/'."""
    return re.sub(r"([_./])", r"\1<wbr>", esc(text))


def table(headers, rows, widths=None, row_classes=None):
    cols = ""
    if widths:
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths) + "</colgroup>"
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for idx, row in enumerate(rows):
        cls = f' class="{row_classes[idx]}"' if row_classes and row_classes[idx] else ""
        body.append(f"<tr{cls}>" + "".join(row) + "</tr>")
    return f'<table class="grid">{cols}<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


class Document:
    def __init__(self, package, content, tests, screenshots, workdir, build_date, renderer):
        self.p = package
        self.c = content
        self.tests = tests
        self.screens = screenshots
        self.work = Path(workdir)
        self.date = build_date
        self.renderer = renderer
        self.version = package.version
        self.modules = [ModuleInfo(package, rel) for rel in package.python_files()]
        self.chapters = []  # (number, title, anchor)
        self.page_numbers = {}

    # -- generic -----------------------------------------------------------
    def fill(self, text):
        out = text.replace("{version}", self.version).replace("{tests}", str(self.tests["total"]))

        def diagram(match):
            spec = self.c.DIAGRAMS[match.group(1)]
            return svg_diagram(spec, self.tests["total"])

        def figure(match):
            key = match.group(1)
            shot = self.screens.get(key)
            caption = esc(self.c.FIGURE_CAPTIONS.get(key, ""))
            if not shot:
                return f'<figure><div class="callout warn">UI screenshot "{key}" not supplied.</div></figure>'
            return f'<figure><img class="ui" src="{file_uri(shot)}"><figcaption>{caption}</figcaption></figure>'

        out = re.sub(r"\{\{diagram:(\w+)\}\}", diagram, out)
        out = re.sub(r"\{\{figure:(\w+)\}\}", figure, out)
        return out

    def chapter(self, title, body, cls=""):
        number = len(self.chapters) + 1
        anchor = f"ch{number}"
        self.chapters.append((number, title, anchor))
        return f'<section class="{cls}"><h1 id="{anchor}">{number}. {esc(title)}</h1>{body}</section>'

    # -- parts -------------------------------------------------------------
    def cover(self):
        icon = self.work / "logo.png"
        ico = self.p.app_dir / "MBToolkit.ico"
        logo = ""
        if ico.exists():
            from PIL import Image
            img = Image.open(ico)
            sizes = getattr(img, "info", {}).get("sizes") or [img.size]
            img.size = max(sizes)
            img.load()
            img.save(icon)
            logo = f'<img class="logo" src="{file_uri(icon)}">'
        zip_name = f"MBToolkit_v{self.version}_Package.zip"
        snapshot_sha = self.p.snapshot_sha256()
        t = self.tests
        verification = (f"{t['total']}/{t['total']} regression tests passed before documentation generation."
                        if t["ok"] else
                        f"Regression suite NOT clean: {t['total']} run, {t['failures']} failures, "
                        f"{t['errors']} errors.")
        notes = "".join(f"<p>{n}</p>" for n in self.c.COVER_NOTES)
        return f"""
<section class="cover">{logo}
<h1>MBToolkit v{self.version}<br>Technical Code<br>Documentation</h1>
<div class="subtitle">{esc(self.c.COVER_SUBTITLE)}</div>
<dl>
<dt>Documented package</dt><dd><code>{esc(zip_name)}</code></dd>
<dt>Source snapshot SHA-256</dt><dd><code class="sha">{snapshot_sha}</code></dd>
<dt>Documentation build date</dt><dd>{format_date(self.date)}</dd>
<dt>Verification</dt><dd>{esc(verification)}</dd>
</dl>
{notes}
</section>"""

    def toc(self):
        items = []
        for number, title, anchor in self.chapters:
            page = self.page_numbers.get(anchor, "")
            items.append(f'<li><span class="num">{number}.</span><a href="#{anchor}">{esc(title)}</a>'
                         f'<span class="dots"></span><span class="page">{page}</span></li>')
        return f'<section class="toc"><h1 id="contents">Contents</h1><ol>{"".join(items)}</ol></section>'

    def snapshot_chapter(self):
        py_lines = sum(m.lines for m in self.modules)
        bat_lines = sum(line_count(self.p.path(f)) for f in self.p.batch_files())
        inventory = table(
            ["Python module", "Lines", "Primary responsibility"],
            [[f"<td><code>{esc(m.name)}</code></td>", f"<td>{m.lines}</td>", f"<td>{esc(m.lead)}</td>"]
             for m in self.modules],
            ["22%", "8%", "70%"])
        hashes = []
        for rel in self.p.source_files():
            path = self.p.path(rel)
            hashes.append([f"<td><code>{esc(rel)}</code></td>", f"<td>{line_count(path)}</td>",
                           f'<td><code class="sha">{sha256_file(path)}</code></td>'])
        integrity = table(["Source file", "Lines", "SHA-256"], hashes, ["37%", "8%", "55%"])
        t = self.tests
        status = (f"The supplied suite was executed directly from this source tree. All {t['total']} tests passed."
                  if t["ok"] else
                  f"The supplied suite was executed directly from this source tree: {t['total']} run, "
                  f"{t['failures']} failures, {t['errors']} errors.")
        body = f"""
<p class="lead">This reference was generated from the current MBToolkit v{self.version} package, without
modifying the application source.</p>
<div class="cards"><div class="card narrow"><span class="label">Python source lines</span>{py_lines:,}</div>
<div class="card wide"><span class="label">Documented Python + BAT lines</span>{py_lines + bat_lines:,}</div></div>
<h2>Package structure</h2>
<pre class="tree">{esc(self.p.tree_text())}</pre>
<h2>Source inventory</h2>
{inventory}
<h2>Integrity hashes</h2>
{integrity}
<div class="callout {'ok' if t['ok'] else 'fail'}"><b>Regression status.</b> {esc(status)}</div>
"""
        return self.chapter("Documented source snapshot", body)

    def changes_chapter(self):
        rows = [[f"<td><b>v{esc(v)}</b></td>", f"<td>{esc(d) or '—'}</td>", f"<td>{s}</td>"]
                for v, d, s in self.c.VERSION_HISTORY if version_key(v) <= version_key(self.version)]
        history = table(["Version", "Date", "Summary"], rows, ["12%", "22%", "66%"])
        details = self.c.VERSION_CHANGES.get(self.version, "<p>No change notes recorded for this version.</p>")
        body = (f"<p>Release history of the documented code base. The detailed list below applies to "
                f"v{self.version}, the version described by every other chapter of this document.</p>"
                f"{history}<h2>Changes in v{self.version}</h2>{self.fill(details)}")
        return self.chapter("Version history and changes in this version", body)

    def module_section(self, m):
        out = [f'<div class="module"><h2 id="mod-{esc(m.name)}">{esc(m.name)}</h2>',
               f'<p class="lead">{m.intro}</p>',
               f'<div class="cards"><div class="card narrow"><span class="label">Source lines</span>{m.lines}</div>'
               f'<div class="card wide"><span class="label">SHA-256</span><code class="sha">{m.sha}</code></div></div>']
        if m.imports:
            out.append(f'<p class="imports"><b>Imports:</b> <code>{esc(", ".join(m.imports))}</code></p>')
        if m.constants:
            out.append("<h3>Module constants / configuration data</h3>")
            out.append(table(["Name", "Definition"],
                             [[f"<td><code>{wbr(n)}</code></td>", f"<td><code>{esc(v)}</code></td>"]
                              for n, v in m.constants], ["50%", "50%"]))
        out.append("<h3>Complete callable reference</h3>")
        out.append(f"<p>The table below includes every top-level function, class and class method in this file. "
                   f"Line numbers refer to the exact v{self.version} source snapshot documented here.</p>")
        rows, classes = [], []
        for item in m.callables:
            if item["kind"] == "class":
                rows.append([f'<td><code>class {esc(item["name"])}</code></td>', f'<td class="nowrap">{item["lines"]}</td>',
                             f'<td>{esc(item["responsibility"])}</td>', "<td>Class container</td>"])
                classes.append("classrow")
            else:
                calls = item["calls"]
                calls_html = "—" if calls == "—" else f"<code>{wbr(calls)}</code>"
                rows.append([f'<td><code>{wbr(item["qualname"])}</code><span class="sig">{esc(item["signature"])}</span></td>',
                             f'<td class="nowrap">{item["lines"]}</td>', f'<td>{esc(item["responsibility"])}</td>',
                             f'<td class="calls">{calls_html}</td>'])
                classes.append("")
        out.append(table(["Callable", "Lines", "Responsibility", "Representative direct calls"], rows,
                         ["33%", "10%", "26%", "31%"], classes))
        if m.details:
            out.append("<h3>Detailed behavior of the key paths</h3>")
            for name, text in m.details:
                lines = m.detail_lines(name)
                out.append(f'<div class="detail"><div class="head"><code>{esc(name)}</code> lines {lines}</div>'
                           f"<p>{text}</p></div>")
        if m.design_note:
            out.append(f'<div class="callout info"><b>Design note.</b> {m.design_note}</div>')
        out.append("</div>")
        return "".join(out)

    def module_chapter(self):
        body = ("<p>The following chapters provide a complete callable inventory for every Python module. Each "
                "function/method is tied to its exact source-line range. The complete source itself appears as "
                "screenshots in Appendix A.</p>")
        body += "".join(self.module_section(m) for m in self.modules)
        return self.chapter("Module-by-module reference", body)

    def tests_chapter(self):
        t = self.tests
        cmd = '<code>python -m unittest discover -s tests -p "test_*.py" -v</code>'
        if t["ok"]:
            intro = f'<p class="lead">The documented package was executed with {cmd}. All {t["total"]} tests passed.</p>'
            result = (f'<div class="callout ok">Verification result: <b>{t["total"]} tests run - {t["total"]} passed - '
                      f'0 failures/errors</b>.</div>')
        else:
            intro = f'<p class="lead">The documented package was executed with {cmd}.</p>'
            result = (f'<div class="callout fail">Verification result: <b>{t["total"]} tests run - '
                      f'{t["failures"]} failures - {t["errors"]} errors</b>.</div>')
        parts = [intro, result]
        for m in self.modules:
            for cls, tests in test_classes(m):
                parts.append(f"<h3>{esc(cls)}</h3>")
                desc = self.c.TEST_CLASS_DESCRIPTIONS.get(cls)
                if desc:
                    parts.append(f"<p>{desc}</p>")
                parts.append(table(["Test", "Lines", "What it protects"],
                                   [[f"<td><code>{wbr(n)}</code></td>", f'<td class="nowrap">{l}</td>', f"<td>{esc(w)}</td>"]
                                    for n, l, w in tests], ["60%", "10%", "30%"]))
        return self.chapter("Regression-test suite", "".join(parts))

    def build_chapter(self):
        bats = self.p.batch_files()
        words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
        parts = [f"<p>The package contains {words.get(len(bats), len(bats))} Windows batch files. Their complete "
                 f"source is reproduced in Appendix A.</p>"]
        for rel in bats:
            path = self.p.path(rel)
            bullets = self.c.BAT_DESCRIPTIONS.get(Path(rel).name, [])
            parts.append(f'<h2>{esc(rel)}</h2><p class="lead">Windows batch automation included in the package.</p>'
                         f'<div class="cards"><div class="card narrow"><span class="label">Lines</span>{line_count(path)}</div>'
                         f'<div class="card wide"><span class="label">SHA-256</span><code class="sha">{sha256_file(path)}</code>'
                         f'</div></div>')
            if bullets:
                parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
        return self.chapter("Build and launch automation", "".join(parts))

    def appendix(self):
        number = len(self.chapters) + 1
        anchor = f"ch{number}"
        self.chapters.append((number, "Appendix A - Complete source screenshots", anchor))
        parts = [f'<section><h1 id="{anchor}">Appendix A - Complete source-code screenshots</h1>'
                 "<p>Every Python and batch source file in the package is reproduced below as syntax-highlighted "
                 "screenshots with original line numbers. Very long source lines are visually wrapped inside the "
                 "screenshot for readability; this does not alter the source file. The SHA-256 values in the "
                 "module chapters identify the exact files represented.</p></section>"]
        img_dir = self.work / "appendix"
        img_dir.mkdir(exist_ok=True)
        counter = 0
        for rel in self.p.source_files():
            path = self.p.path(rel)
            text = read_text(path)
            lines = self.renderer.token_lines(text, path.name)
            total = len(lines)
            for start in range(0, max(total, 1), APPENDIX_LINES_PER_PAGE):
                chunk = lines[start:start + APPENDIX_LINES_PER_PAGE]
                first, last = start + 1, start + len(chunk)
                counter += 1
                out = img_dir / f"src_{counter:04d}.png"
                self.renderer.render(f"{rel} — lines {first}-{last}",
                                     list(zip(range(first, last + 1), chunk)), out)
                heading = ""
                if start == 0:
                    heading = f'<h2>{esc(rel)}</h2><p class="lines">{total} source lines.</p>'
                parts.append(f'<section class="appendix-page"><div class="appendix-label">{esc(rel)} - lines '
                             f'{first}-{last}</div>{heading}<img src="{file_uri(out)}"></section>')
        return "".join(parts)

    def build_html(self):
        self.chapters = []
        body = [self.snapshot_chapter(), self.changes_chapter()]
        for title, html_body in self.c.CHAPTERS:
            body.append(self.chapter(title, self.fill(html_body)))
        body.append(self.module_chapter())
        body.append(self.tests_chapter())
        body.append(self.build_chapter())
        title, html_body = self.c.BOUNDARIES_CHAPTER
        body.append(self.chapter(title, self.fill(html_body)))
        if not hasattr(self, "_appendix_html"):
            self._appendix_html = self.appendix()
        else:
            n = len(self.chapters) + 1
            self.chapters.append((n, "Appendix A - Complete source screenshots", f"ch{n}"))
        css = CSS.replace("{fonts}", FONTS_DIR.resolve().as_uri()).replace("{version}", self.version)
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f"<title>MBToolkit v{self.version} Technical Code Documentation</title>"
                f"<style>{css}</style></head><body>"
                '<span class="serif-preload">.</span>'
                f"{self.cover()}{self.toc()}{''.join(body)}{self._appendix_html}</body></html>")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def find_browser(explicit=None):
    candidates = [explicit] if explicit else []
    candidates += [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome") or "", shutil.which("msedge") or "", shutil.which("google-chrome") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("Google Chrome or Microsoft Edge is required to lay out the PDF.")


def print_pdf(browser, html_path, pdf_path, profile_dir):
    if pdf_path.exists():
        pdf_path.unlink()
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={profile_dir}", "--allow-file-access-from-files", "--no-pdf-header-footer",
           "--generate-pdf-document-outline", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=30000", f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    if not pdf_path.exists():
        raise SystemExit("The browser did not produce a PDF.")


def chapter_pages(pdf_path, chapters):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pages = {}
    toc = doc.get_toc(simple=True)
    for number, title, anchor in chapters:
        wanted = f"{number}. {title}" if not title.startswith("Appendix") else "Appendix A"
        wanted = re.sub(r"\s+", "", wanted)
        for level, text, page in toc:
            if re.sub(r"\s+", "", text).startswith(wanted):
                pages[anchor] = page
                break
    count = doc.page_count
    doc.close()
    return pages, count


def finalize(pdf_path, out_path, version):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    doc.set_metadata({"title": f"MBToolkit v{version} Technical Code Documentation", "author": "",
                      "subject": "", "keywords": "", "creator": "tools/build_technical_pdf.py",
                      "producer": "MBToolkit documentation generator"})
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", help="Release ZIP (MBToolkit_vX.Y_Package.zip). Preferred: documents the exact package.")
    source.add_argument("--source-dir", help="Extracted package root (folder containing MBToolkit.bat and 'MBToolkit vX.Y').")
    parser.add_argument("--version", required=True, help="Documented version, e.g. 3.1")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--content", default=str(TOOLS_DIR / "technical_doc_content.py"))
    parser.add_argument("--screenshots", help="Folder with the PNG figures from capture_ui_screenshots.py")
    parser.add_argument("--python", default=sys.executable, help="Python used to run the regression suite")
    parser.add_argument("--browser", help="Path to chrome.exe / msedge.exe")
    parser.add_argument("--date", help="Documentation build date (YYYY-MM-DD); default today")
    parser.add_argument("--keep-html", help="Optional folder to keep the intermediate HTML for inspection")
    args = parser.parse_args(argv)

    sys.dont_write_bytecode = True
    content = load_content(args.content)
    build_date = _dt.date.fromisoformat(args.date) if args.date else _dt.date.today()
    browser = find_browser(args.browser)

    with tempfile.TemporaryDirectory(prefix="mbs_doc_") as tmp:
        tmp = Path(tmp)
        if args.package:
            root = tmp / "package"
            with zipfile.ZipFile(args.package) as archive:
                archive.extractall(root)
            package = Package(root, args.version, content, zip_path=args.package)
        else:
            package = Package(args.source_dir, args.version, content)

        print(f"Running regression suite in {package.app_dir} ...")
        tests = run_regression_tests(package, args.python)
        print(f"  {tests['total']} tests, ok={tests['ok']}")

        screenshots = {}
        if args.screenshots:
            for key in content.FIGURE_CAPTIONS:
                candidate = Path(args.screenshots) / f"{key}.png"
                if candidate.exists():
                    screenshots[key] = candidate

        doc = Document(package, content, tests, screenshots, tmp, build_date, CodeRenderer())
        html_path = tmp / "document.html"
        profile = tmp / "browser-profile"
        draft = tmp / "draft.pdf"

        print("Rendering pass 1 ...")
        html_path.write_text(doc.build_html(), encoding="utf-8")
        print_pdf(browser, html_path, draft, profile)
        doc.page_numbers, pages = chapter_pages(draft, doc.chapters)

        print("Rendering pass 2 (contents page numbers) ...")
        html_path.write_text(doc.build_html(), encoding="utf-8")
        print_pdf(browser, html_path, draft, profile)
        check, pages = chapter_pages(draft, doc.chapters)
        if check != doc.page_numbers:
            doc.page_numbers = check
            html_path.write_text(doc.build_html(), encoding="utf-8")
            print_pdf(browser, html_path, draft, profile)

        if args.keep_html:
            keep = Path(args.keep_html)
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copy2(html_path, keep / "document.html")

        finalize(draft, args.output, args.version)
        size_mb = Path(args.output).stat().st_size / 1e6
        print(f"Wrote {args.output} ({pages} pages, {size_mb:.1f} MB)")
        if not tests["ok"]:
            print("WARNING: the regression suite did not pass; the PDF says so on the cover.")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
