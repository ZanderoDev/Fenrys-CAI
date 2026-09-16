from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


def safe_extract_zip(archive: Path, destination: Path, *, max_bytes: int = 512 * 1024 * 1024, max_files: int = 10_000) -> list[Path]:
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as handle:
        infos = handle.infolist()
        if len(infos) > max_files or sum(item.file_size for item in infos) > max_bytes:
            raise ValueError("Archive exceeds extraction limits")
        for info in infos:
            target = (root / info.filename).resolve()
            if not target.is_relative_to(root) or Path(info.filename).is_absolute():
                raise ValueError("Unsafe archive path")
            mode = info.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are not allowed")
        for info in infos:
            target = (root / info.filename).resolve()
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append(target)
    return extracted
