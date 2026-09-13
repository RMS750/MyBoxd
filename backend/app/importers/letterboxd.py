from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from app.config import settings
from app.utils.text import normalize_title, parse_date, parse_rating, parse_year

SUPPORTED = {"ratings.csv", "watched.csv", "watchlist.csv", "reviews.csv", "diary.csv"}
MAX_TOTAL_BYTES = settings.max_upload_mb * 1024 * 1024
MAX_CSV_BYTES = min(MAX_TOTAL_BYTES, 15 * 1024 * 1024)
MAX_ZIP_UNCOMPRESSED = max(MAX_TOTAL_BYTES * 5, 50 * 1024 * 1024)
MAX_ZIP_MEMBERS = 250


@dataclass
class NormalizedMovieRecord:
    title: str
    year: int | None
    rating: float | None = None
    watched: bool = False
    watchlist: bool = False
    rewatch_count: int = 0
    last_watched: object | None = None
    review: str | None = None
    letterboxd_uri: str | None = None
    diary_dates: list[object] = field(default_factory=list)


@dataclass
class ImportResult:
    records: list[NormalizedMovieRecord]
    source_files: list[str]
    errors: list[str]
    rows_processed: int


def _value(row: dict[str, str], *names: str) -> str:
    lookup = {k.strip().casefold(): (v or "") for k, v in row.items() if k}
    return next((lookup[n.casefold()].strip() for n in names if n.casefold() in lookup), "")


def _rows(name: str, raw: bytes):
    if len(raw) > MAX_CSV_BYTES:
        return [], [f"{name}: file is too large"]
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            reader = csv.DictReader(io.StringIO(raw.decode(enc)))
            if not reader.fieldnames:
                return [], [f"{name}: missing header row"]
            return list(reader), []
        except UnicodeDecodeError:
            continue
        except csv.Error as exc:
            return [], [f"{name}: CSV parse error: {exc}"]
    return [], [f"{name}: unsupported text encoding"]


def _safe_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    return not p.is_absolute() and ".." not in p.parts and not normalized.startswith("/")


def _files(files: Iterable[tuple[str, bytes]]):
    found: dict[str, bytes] = {}
    errors: list[str] = []
    total = 0
    for filename, raw in files:
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"Upload is too large. Maximum total upload size is {settings.max_upload_mb} MB.")
        base = Path(filename).name.casefold()
        if base.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    infos = zf.infolist()
                    if len(infos) > MAX_ZIP_MEMBERS:
                        raise ValueError("ZIP contains too many files")
                    if sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED:
                        raise ValueError("ZIP expands to an unsafe size")
                    for info in infos:
                        if not _safe_zip_member(info.filename):
                            raise ValueError("ZIP contains an unsafe path")
                        name = Path(info.filename).name.casefold()
                        if name in SUPPORTED and name not in found:
                            if info.file_size > MAX_CSV_BYTES:
                                errors.append(f"{name}: file is too large")
                                continue
                            found[name] = zf.read(info)
            except zipfile.BadZipFile:
                errors.append(f"{filename}: invalid ZIP file")
            except ValueError as exc:
                errors.append(f"{filename}: {exc}")
        elif base in SUPPORTED:
            if len(raw) > MAX_CSV_BYTES:
                errors.append(f"{filename}: file is too large")
            else:
                found[base] = raw
        elif base.endswith(".csv"):
            errors.append(f"{filename}: unsupported Letterboxd CSV filename")
        else:
            errors.append(f"{filename}: unsupported file type")
    return found, errors


def parse_letterboxd_files(files: Iterable[tuple[str, bytes]]) -> ImportResult:
    recognized, errors = _files(files)
    if not recognized:
        detail = " ".join(errors[:3]) if errors else ""
        raise ValueError(
            "No supported Letterboxd files found. Upload ratings.csv, watched.csv, watchlist.csv, "
            f"reviews.csv, diary.csv, or the export ZIP. {detail}".strip()
        )
    merged: dict[tuple[str, int | None], NormalizedMovieRecord] = {}
    diary_counts = defaultdict(int)
    processed = 0
    for name, raw in recognized.items():
        rows, errs = _rows(name, raw)
        errors.extend(errs)
        for idx, row in enumerate(rows, 2):
            processed += 1
            try:
                title = _value(row, "Name", "Title", "Film")
                if not title:
                    errors.append(f"{name} row {idx}: missing movie title")
                    continue
                year = parse_year(_value(row, "Year"))
                key = (normalize_title(title), year)
                rec = merged.setdefault(key, NormalizedMovieRecord(title.strip(), year))
                rec.letterboxd_uri = rec.letterboxd_uri or _value(row, "Letterboxd URI", "URI") or None
                rating = parse_rating(_value(row, "Rating"))
                if rating is not None:
                    rec.rating = rating
                if name in {"ratings.csv", "watched.csv"}:
                    rec.watched = True
                elif name == "watchlist.csv":
                    rec.watchlist = True
                elif name == "reviews.csv":
                    rec.watched = True
                    rec.review = _value(row, "Review") or rec.review
                elif name == "diary.csv":
                    rec.watched = True
                    watched_date = parse_date(_value(row, "Watched Date", "Date"))
                    if watched_date:
                        rec.diary_dates.append(watched_date)
                        diary_counts[key] += 1
                    if _value(row, "Rewatch").casefold() in {"yes", "true", "1", "x"}:
                        rec.rewatch_count += 1
                watched_date = parse_date(_value(row, "Watched Date", "Date"))
                if watched_date and (rec.last_watched is None or watched_date > rec.last_watched):
                    rec.last_watched = watched_date
            except Exception as exc:  # malformed rows should not abort a whole export
                errors.append(f"{name} row {idx}: {exc}")
    for key, count in diary_counts.items():
        merged[key].rewatch_count = max(merged[key].rewatch_count, max(0, count - 1))
    return ImportResult(list(merged.values()), sorted(recognized), errors[:500], processed)
