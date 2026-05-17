"""Directory scanner with symlink safety policy (T4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .config import Config


_cfg_scanner = Config.load_cached()


@dataclass(frozen=True)
class ScanResult:
    files: tuple[Path, ...]
    skipped_symlinks: tuple[Path, ...]


def scan_memory_dir(
    path: str | Path,
    *,
    pattern: str | None = None,
    follow_symlinks: bool = False,
) -> ScanResult:
    """Scan markdown files with safe default symlink handling.

    Default policy does not follow symlinks. If enabled, any symlink target
    must resolve inside the scan root; out-of-root links are skipped.

    Parameters
    ----------
    path:
        Root directory to scan.
    pattern:
        Glob pattern for file selection.  Defaults to
        ``Config().injection.file_pattern`` (``"*.md"`` from bowl.yaml).
    follow_symlinks:
        If True, follow symlinks that resolve inside the scan root.
    """
    if pattern is None:
        pattern = _cfg_scanner.injection.file_pattern
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"scan root is not a directory: {root}")

    files: list[Path] = []
    skipped: list[Path] = []
    visited_dirs: set[Path] = set()

    def walk(directory: Path) -> None:
        real_dir = directory.resolve()
        if real_dir in visited_dirs:
            return
        visited_dirs.add(real_dir)

        for entry in directory.iterdir():
            if entry.is_symlink():
                if not follow_symlinks:
                    skipped.append(entry)
                    continue
                target = entry.resolve(strict=False)
                if root != target and root not in target.parents:
                    skipped.append(entry)
                    continue

            if entry.is_dir():
                walk(entry)
                continue

            if entry.is_file() and entry.match(pattern):
                files.append(entry.resolve())

    walk(root)
    files_sorted = tuple(sorted(set(files)))
    skipped_sorted = tuple(sorted(set(s.resolve(strict=False) for s in skipped)))
    return ScanResult(files=files_sorted, skipped_symlinks=skipped_sorted)
