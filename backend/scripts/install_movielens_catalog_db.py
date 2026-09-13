from __future__ import annotations

import argparse
import bisect
import csv
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import engine
from app.models.entities import Genre, Movie, movie_genres
from app.utils.text import normalize_title

SOURCE = "movielens-32m"
GENRE_MAP = {"Children's": "Family", "Sci-Fi": "Science Fiction", "Musical": "Music"}
TMDB_GENRE_IDS = {
    "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35, "Crime": 80,
    "Documentary": 99, "Drama": 18, "Family": 10751, "Fantasy": 14, "History": 36,
    "Horror": 27, "Music": 10402, "Mystery": 9648, "Romance": 10749,
    "Science Fiction": 878, "Thriller": 53, "War": 10752, "Western": 37,
}


def _member(zf: zipfile.ZipFile, basename: str) -> str:
    matches = [name for name in zf.namelist() if name.endswith("/" + basename) or name == basename]
    if not matches:
        raise SystemExit(f"MovieLens archive is missing {basename}")
    return matches[0]


def _parse_title(value: str) -> tuple[str, int | None]:
    text = value.strip()
    if len(text) >= 7 and text.endswith(")") and text[-6] == "(" and text[-5:-1].isdigit():
        return text[:-7].strip(), int(text[-5:-1])
    return text, None


def _insert_ignore(table, rows):
    if not rows:
        return
    dialect = engine.dialect.name
    if dialect == "postgresql":
        stmt = pg_insert(table).values(rows).on_conflict_do_nothing()
    elif dialect == "sqlite":
        stmt = sqlite_insert(table).values(rows).on_conflict_do_nothing()
    else:
        raise SystemExit(f"Unsupported database for catalogue seeding: {dialect}")
    with engine.begin() as conn:
        conn.execute(stmt)


def _catalog_count() -> int:
    with engine.connect() as conn:
        return int(conn.scalar(select(func.count()).select_from(Movie).where(Movie.catalog_source == SOURCE)) or 0)


def install(zip_path: Path, if_missing: bool = False) -> None:
    if not zip_path.exists():
        raise SystemExit(f"MovieLens archive not found: {zip_path}")
    existing = _catalog_count()
    if if_missing and existing >= 50_000:
        print(f"MovieLens catalogue already installed ({existing:,} movies).")
        return

    print(f"Database dialect: {engine.dialect.name}")
    print(f"MovieLens archive: {zip_path}")

    with zipfile.ZipFile(zip_path) as zf:
        movies_member = _member(zf, "movies.csv")
        links_member = _member(zf, "links.csv")
        ratings_member = _member(zf, "ratings.csv")
        tags_member = _member(zf, "tags.csv")
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"MovieLens archive is corrupt near {bad}")

        print("Reading MovieLens links...")
        links: dict[int, tuple[str | None, int | None]] = {}
        with io.TextIOWrapper(zf.open(links_member), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                movie_id = int(row["movieId"])
                imdb = (row.get("imdbId") or "").strip() or None
                tmdb_raw = (row.get("tmdbId") or "").strip()
                tmdb = int(float(tmdb_raw)) if tmdb_raw else None
                links[movie_id] = (imdb, tmdb)

        print("Aggregating MovieLens ratings...")
        sums: dict[int, float] = defaultdict(float)
        counts: dict[int, int] = defaultdict(int)
        processed = 0
        with io.TextIOWrapper(zf.open(ratings_member), encoding="utf-8", newline="") as fh:
            next(fh, None)
            for line in fh:
                parts = line.rstrip("\n").split(",", 3)
                if len(parts) < 3:
                    continue
                mid = int(parts[1])
                sums[mid] += float(parts[2])
                counts[mid] += 1
                processed += 1
                if processed % 5_000_000 == 0:
                    print(f"  {processed:,} ratings processed...")

        sorted_counts = sorted(counts.values())
        total_counted = max(1, len(sorted_counts))

        print("Reading MovieLens tags...")
        tags: dict[int, list[str]] = defaultdict(list)
        seen: dict[int, set[str]] = defaultdict(set)
        with io.TextIOWrapper(zf.open(tags_member), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                mid = int(row["movieId"])
                if len(tags[mid]) >= 18:
                    continue
                tag = " ".join((row.get("tag") or "").strip().casefold().split())
                if not tag or len(tag) > 80 or tag in seen[mid]:
                    continue
                seen[mid].add(tag)
                tags[mid].append(tag)

        print("Reading movie catalogue...")
        records = []
        genre_names: set[str] = set()
        with io.TextIOWrapper(zf.open(movies_member), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ml_id = int(row["movieId"])
                title, year = _parse_title(row["title"])
                genres = []
                for raw in [g for g in (row.get("genres") or "").split("|") if g and g != "(no genres listed)"]:
                    name = GENRE_MAP.get(raw, raw)
                    if name not in genres:
                        genres.append(name)
                        genre_names.add(name)
                imdb_id, tmdb_id = links.get(ml_id, (None, None))
                count = int(counts.get(ml_id, 0))
                avg = (sums[ml_id] / count) if count else None
                popularity = round(100.0 * bisect.bisect_right(sorted_counts, count) / total_counted, 3) if count else 0.0
                records.append({
                    "title": title,
                    "normalized_title": normalize_title(title),
                    "year": year,
                    "genres": genres,
                    "keywords": tags.get(ml_id, []),
                    "imdb_id": imdb_id,
                    "tmdb_id": tmdb_id,
                    "catalog_rating": round(avg, 4) if avg is not None else None,
                    "catalog_rating_count": count,
                    "catalog_popularity": popularity,
                })

    print("Writing genres...")
    genre_rows = [{"tmdb_id": TMDB_GENRE_IDS.get(name), "name": name} for name in sorted(genre_names)]
    _insert_ignore(Genre.__table__, genre_rows)
    with engine.connect() as conn:
        genre_ids = {name: gid for gid, name in conn.execute(select(Genre.id, Genre.name))}

    print("Writing movies...")
    for start in range(0, len(records), 1500):
        chunk = records[start:start + 1500]
        rows = [{
            "tmdb_id": r["tmdb_id"],
            "title": r["title"],
            "normalized_title": r["normalized_title"],
            "year": r["year"],
            "production_countries": [],
            "keywords": r["keywords"],
            "catalog_rating": r["catalog_rating"],
            "catalog_rating_count": r["catalog_rating_count"],
            "catalog_popularity": r["catalog_popularity"],
            "catalog_source": SOURCE,
            "imdb_id": r["imdb_id"],
        } for r in chunk]
        _insert_ignore(Movie.__table__, rows)
        if start and start % 15000 == 0:
            print(f"  {start:,} movies written...")

    print("Linking genres...")
    with engine.connect() as conn:
        by_tmdb = {int(tmdb): int(mid) for mid, tmdb in conn.execute(select(Movie.id, Movie.tmdb_id).where(Movie.tmdb_id.is_not(None)))}
        by_key = {(str(norm), year): int(mid) for mid, norm, year in conn.execute(select(Movie.id, Movie.normalized_title, Movie.year))}

    pairs = []
    for rec in records:
        mid = by_tmdb.get(int(rec["tmdb_id"])) if rec["tmdb_id"] is not None else None
        mid = mid or by_key.get((rec["normalized_title"], rec["year"]))
        if not mid:
            continue
        for genre_name in rec["genres"]:
            gid = genre_ids.get(genre_name)
            if gid:
                pairs.append({"movie_id": mid, "genre_id": gid})
        if len(pairs) >= 8000:
            _insert_ignore(movie_genres, pairs)
            pairs.clear()
    if pairs:
        _insert_ignore(movie_genres, pairs)

    installed = _catalog_count()
    with engine.connect() as conn:
        total = int(conn.scalar(select(func.count()).select_from(Movie)) or 0)
    print(f"MovieLens catalogue ready: {installed:,} catalogue movies; {total:,} total movies.")
    if installed < 50_000:
        raise SystemExit("Catalogue import looks incomplete; expected at least 50,000 MovieLens rows.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", required=True)
    parser.add_argument("--if-missing", action="store_true")
    args = parser.parse_args()
    install(Path(args.zip_path).expanduser().resolve(), if_missing=args.if_missing)


if __name__ == "__main__":
    main()
