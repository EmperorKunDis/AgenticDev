#!/usr/bin/env python3
"""Build the deterministic installer payload on GNU/Linux and macOS."""
from __future__ import annotations

import gzip
import os
from pathlib import Path
import tarfile

root = Path(os.environ["AGENTICDEV_PAYLOAD_ROOT"]).resolve()
out = Path(os.environ["AGENTICDEV_PAYLOAD_OUT"])
epoch = int(os.environ["SOURCE_DATE_EPOCH"])
excluded_roots = {".git", ".github", ".agents", ".codex", "dist", "data", ".venv",
                  "__pycache__", ".wo-cache", "secrets"}


def excluded(path: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if rel.parts and rel.parts[0] in excluded_roots:
        return True
    return path.name == ".env" or path.suffix in {".key", ".pem", ".pyc"}


with out.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                           compresslevel=9, mtime=epoch) as zipped:
    with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if excluded(path) or any(excluded(parent) for parent in path.parents
                                     if parent != root and root in parent.parents):
                continue
            name = "./" + path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if info.isfile():
                with path.open("rb") as source:
                    archive.addfile(info, source)
            else:
                archive.addfile(info)
