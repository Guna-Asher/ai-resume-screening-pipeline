"""Input normalisation: directory / single PDF / ZIP (or any mix) -> one flat list of PDFs.

Everything downstream sees only PdfInput, never where a file came from. ZIPs are extracted
defensively (no extractall): path traversal is rejected, sizes and file counts are capped, and only
.pdf entries are ever written to disk.
"""
import os
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

MB = 1024 * 1024


@dataclass(frozen=True)
class InputLimits:
    max_files: int = 200              # PDFs per run
    max_file_bytes: int = 20 * MB     # one PDF
    max_archive_bytes: int = 100 * MB  # one ZIP file
    max_extracted_bytes: int = 300 * MB  # all PDFs extracted from ZIPs in a run
    max_upload_files: int = 100       # web: files per request
    max_upload_bytes: int = 200 * MB  # web: total request size

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "InputLimits":
        env = os.environ if env is None else env
        d = cls()

        def mb(name: str, default: int) -> int:
            try:
                return int(float(env[name]) * MB)
            except (KeyError, ValueError):
                return default

        def count(name: str, default: int) -> int:
            try:
                return int(env[name])
            except (KeyError, ValueError):
                return default

        return cls(max_files=count("MAX_FILES", d.max_files), max_file_bytes=mb("MAX_PDF_MB", d.max_file_bytes),
                   max_archive_bytes=mb("MAX_ZIP_MB", d.max_archive_bytes),
                   max_extracted_bytes=mb("MAX_EXTRACTED_MB", d.max_extracted_bytes),
                   max_upload_files=count("MAX_UPLOAD_FILES", d.max_upload_files),
                   max_upload_bytes=mb("MAX_UPLOAD_MB", d.max_upload_bytes))


@dataclass(frozen=True)
class PdfInput:
    path: Path
    name: str      # display name, unique within a run (e.g. "resumes.zip/team/a.pdf")


@dataclass
class InputProblem:
    name: str
    message: str   # safe to show to users
    code: str      # stable machine-readable reason


@dataclass
class CollectedInputs:
    pdfs: list[PdfInput] = field(default_factory=list)
    problems: list[InputProblem] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


class _Collector:
    def __init__(self, workdir: Path, limits: InputLimits):
        self.workdir, self.limits = workdir, limits
        self.out = CollectedInputs()
        self._names: set[str] = set()
        self._extracted = 0
        self._zips = 0
        self.full = False

    def problem(self, name: str, message: str, code: str) -> None:
        self.out.problems.append(InputProblem(name, message, code))

    def add_pdf(self, path: Path, name: str) -> None:
        if len(self.out.pdfs) >= self.limits.max_files:
            if not self.full:
                self.full = True
                self.problem("(input)", f"More than {self.limits.max_files} PDFs were provided; the rest were not processed.",
                             "too_many_files")
            return
        unique, n = name, 2
        while unique in self._names:
            unique, n = f"{name} ({n})", n + 1
        self._names.add(unique)
        self.out.pdfs.append(PdfInput(path, unique))

    def add_path(self, path: Path, name: str) -> None:
        suffix = path.suffix.lower()
        if path.is_dir():
            for child in sorted(path.iterdir()):
                self.add_path(child, child.name if name == "." else f"{name}/{child.name}")
        elif suffix == ".pdf":
            if path.stat().st_size > self.limits.max_file_bytes:
                self.problem(name, f"PDF is larger than {self.limits.max_file_bytes // MB} MB and was skipped.", "file_too_large")
            else:
                self.add_pdf(path, name)
        elif suffix == ".zip":
            self.add_zip(path, name)
        else:
            self.out.ignored.append(name)

    def add_zip(self, path: Path, name: str) -> None:
        if path.stat().st_size > self.limits.max_archive_bytes:
            return self.problem(name, f"ZIP is larger than {self.limits.max_archive_bytes // MB} MB and was skipped.", "zip_too_large")
        self._zips += 1
        dest = (self.workdir / f"zip{self._zips}").resolve()
        dest.mkdir(parents=True)
        try:
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if self.full:
                        break
                    self._extract_entry(zf, info, dest, name)
        except (zipfile.BadZipFile, OSError, NotImplementedError):
            self.problem(name, "The ZIP archive is unreadable or corrupt.", "corrupt_zip")

    def _extract_entry(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path, zip_name: str) -> None:
        if info.is_dir():
            return
        rel = info.filename.replace("\\", "/")
        parts = PurePosixPath(rel).parts
        label = f"{zip_name}/{rel}"
        if rel.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", rel):
            return self.problem(label, "Unsafe path in ZIP (path traversal); entry rejected.", "unsafe_zip_entry")
        if "__MACOSX" in parts or parts[-1].startswith("."):
            return  # OS metadata, not a user file
        if not rel.lower().endswith(".pdf"):
            self.out.ignored.append(label)  # includes nested ZIPs: archives are not unpacked recursively
            return
        if info.file_size > self.limits.max_file_bytes:
            return self.problem(label, f"PDF is larger than {self.limits.max_file_bytes // MB} MB and was skipped.",
                                "file_too_large")
        target = (dest / rel).resolve()
        if not target.is_relative_to(dest):
            return self.problem(label, "Unsafe path in ZIP (path traversal); entry rejected.", "unsafe_zip_entry")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            written = self._copy_limited(zf, info, target)
        except (RuntimeError, zipfile.BadZipFile, zlib.error, OSError):
            target.unlink(missing_ok=True)
            return self.problem(label, "This entry could not be extracted (corrupt or encrypted).", "corrupt_zip_entry")
        if written is None:
            target.unlink(missing_ok=True)
            return self.problem(label, "This entry exceeds the size limit and was skipped.", "file_too_large")
        self._extracted += written
        if self._extracted > self.limits.max_extracted_bytes:
            self.full = True
            target.unlink(missing_ok=True)
            return self.problem(zip_name, "The extracted-size limit was reached; remaining entries were skipped.", "extracted_size_limit")
        self.add_pdf(target, label)

    def _copy_limited(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> int | None:
        """Copy while counting real bytes (the size declared in the ZIP header can lie)."""
        total = 0
        with zf.open(info) as src, open(target, "wb") as dst:
            while chunk := src.read(64 * 1024):
                total += len(chunk)
                if total > self.limits.max_file_bytes:
                    return None
                dst.write(chunk)
        return total


def collect_inputs(sources: Path | Sequence[Path], workdir: Path,
                   limits: InputLimits | None = None) -> CollectedInputs:
    """Flatten sources into PDFs. ZIP contents are extracted under `workdir` (caller cleans it up).

    Raises FileNotFoundError if a source path does not exist.
    """
    paths = [sources] if isinstance(sources, Path) else list(sources)
    c = _Collector(workdir, limits or InputLimits())
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Input not found: {p}")
        c.add_path(p, "." if p.is_dir() and len(paths) == 1 else p.name)
    return c.out
