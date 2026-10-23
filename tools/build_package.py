#!/usr/bin/env python3
"""Build MBToolkit_vX.Y_Package.zip from the project folder.

The package holds the application files only: MBToolkit.bat, the README
files, the Technical Code Documentation PDF, the versioned application
folder ``MBToolkit vX.Y`` (code, icon, tests, build/test scripts, notes and
changelog) and the documentation tools (tools/). Nothing related to git or
GitHub is packaged: the user manages the repository and commits.

Local build/run artefacts are never packaged
(.git, __pycache__, *.pyc, build/, *.spec, MBToolkit.exe, MBToolkit Logs/).

Typical use, from the project folder:
    python -B tools/build_package.py --version 3.2

The ZIP is written beside the project folder
(``..\\MBToolkit_vX.Y_Package.zip``).  ``--snapshot-hash`` prints the
"Source snapshot SHA-256" quoted on the PDF cover, for verification.
"""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRS = {"__pycache__", "build", "MBToolkit Logs"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".spec"}
ROOT_FILES = ("README.txt", "README.md", "README.en.md", "MBToolkit.bat")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def package_entries(version):
    """Return (source path, archive name) pairs for the release ZIP."""
    app_dir = REPO_ROOT / f"MBToolkit v{version}"
    if not app_dir.is_dir():
        raise SystemExit(f"Missing application folder: {app_dir}")
    pdf = REPO_ROOT / f"MBToolkit_v{version}_Technical_Code_Documentation.pdf"
    if not pdf.is_file():
        raise SystemExit(f"Missing Technical Code Documentation: {pdf.name}")

    entries = []
    for name in ROOT_FILES:
        if not (REPO_ROOT / name).is_file():
            raise SystemExit(f"Missing root file: {name}")
        entries.append((REPO_ROOT / name, name))
    entries.append((pdf, pdf.name))
    for folder in (app_dir, REPO_ROOT / "tools"):
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(REPO_ROOT)
            if not path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in rel.parts) \
                    or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            entries.append((path, rel.as_posix()))
    return entries


def documented_files(version):
    """Files covered by the PDF's source snapshot hash (same rule as the generator)."""
    app_dir = REPO_ROOT / f"MBToolkit v{version}"
    files = [REPO_ROOT / name for name in ROOT_FILES]
    for path in app_dir.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" \
                and "build" not in path.relative_to(app_dir).parts and path.suffix != ".spec":
            files.append(path)
    return files


def snapshot_sha256(version):
    digest = hashlib.sha256()
    for path in sorted(documented_files(version), key=lambda p: p.relative_to(REPO_ROOT).as_posix()):
        rel = path.relative_to(REPO_ROOT).as_posix()
        digest.update(f"{rel}\0{sha256_file(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True, help="Release version, e.g. 3.2")
    parser.add_argument("--output", help="ZIP path (default: ../MBToolkit_vX.Y_Package.zip)")
    parser.add_argument("--snapshot-hash", action="store_true",
                        help="Only print the source snapshot SHA-256 quoted on the PDF cover")
    args = parser.parse_args(argv)

    if args.snapshot_hash:
        print(snapshot_sha256(args.version))
        return 0

    target = Path(args.output) if args.output else REPO_ROOT.parent / f"MBToolkit_v{args.version}_Package.zip"
    entries = package_entries(args.version)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in entries:
            archive.write(path, name)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise SystemExit("ZIP verification failed")
        count = len(archive.namelist())

    print(f"Wrote {target} ({count} files, {target.stat().st_size / 1e6:.1f} MB)")
    print(f"ZIP SHA-256:             {sha256_file(target)}")
    print(f"Source snapshot SHA-256: {snapshot_sha256(args.version)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
