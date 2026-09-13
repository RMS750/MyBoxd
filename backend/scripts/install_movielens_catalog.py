from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.utils.text import normalize_title

SOURCE = "movielens-32m"
GENRE_MAP = {
    "Children's": "Family",
    "Sci-Fi": "Science Fiction",
    "Musical": "Music",
}
TMDB_GENRE_IDS = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Science Fiction": 878,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}


def _sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise SystemExit("MovieLens local catalogue installer currently targets the local SQLite build only.")
    raw = settings.database_url[len(prefix):]
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


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


def _already_installed(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT COUNT(*) FROM movies WHERE catalog_source = ?", (SOURCE,)).fetchone()
        return int(row[0] if row else 0)
    except sqlite3.OperationalError:
        return 0


def install(zip_path: Path, if_missing: bool = False) -> None:
    db_path = _sqlite_path()
    if not zip_path.exists():
        raise SystemExit(f"MovieLens archive not found: {zip_path}")
    print(f"Database: {db_path}")
    print(f"MovieLens archive: {zip_path}")

    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    existing = _already_installed(conn)
    if if_missing and existing >= 50_000:
        print(f"MovieLens catalogue already installed ({existing:,} local catalogue movies).")
        conn.close()
        return

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

        print("Aggregating 32 million MovieLens ratings (one-time setup)...")
        sums: dict[int, float] = defaultdict(float)
        counts: dict[int, int] = defaultdict(int)
        processed = 0
        with io.TextIOWrapper(zf.open(ratings_member), encoding="utf-8", newline="") as fh:
            next(fh, None)
            for line in fh:
                # ratings.csv has no quoted text fields, so split is much faster than csv.DictReader.
                parts = line.rstrip("\n").split(",", 3)
                if len(parts) < 3:
                    continue
                movie_id = int(parts[1])
                rating = float(parts[2])
                sums[movie_id] += rating
                counts[movie_id] += 1
                processed += 1
                if processed % 5_000_000 == 0:
                    print(f"  {processed:,} ratings processed...")

        sorted_counts = sorted(counts.values())
        total_counted = max(1, len(sorted_counts))

        print("Reading MovieLens tags for local semantic matching...")
        tags: dict[int, list[str]] = defaultdict(list)
        tag_seen: dict[int, set[str]] = defaultdict(set)
        with io.TextIOWrapper(zf.open(tags_member), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                movie_id = int(row["movieId"])
                if len(tags[movie_id]) >= 18:
                    continue
                tag = " ".join((row.get("tag") or "").strip().casefold().split())
                if not tag or len(tag) > 80 or tag in tag_seen[movie_id]:
                    continue
                tag_seen[movie_id].add(tag)
                tags[movie_id].append(tag)
        tag_seen.clear()

        print("Reading 87k movie catalogue...")
        records = []
        genre_names: set[str] = set()
        with io.TextIOWrapper(zf.open(movies_member), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ml_id = int(row["movieId"])
                title, year = _parse_title(row["title"])
                raw_genres = [g for g in (row.get("genres") or "").split("|") if g and g != "(no genres listed)"]
                genres = []
                for raw in raw_genres:
                    name = GENRE_MAP.get(raw, raw)
                    if name not in genres:
                        genres.append(name)
                        genre_names.add(name)
                imdb_id, tmdb_id = links.get(ml_id, (None, None))
                count = int(counts.get(ml_id, 0))
                avg = (sums[ml_id] / count) if count else None
                popularity = round(100.0 * bisect.bisect_right(sorted_counts, count) / total_counted, 3) if count else 0.0
                records.append(
                    {
                        "ml_id": ml_id,
                        "title": title,
                        "normalized_title": normalize_title(title),
                        "year": year,
                        "genres": genres,
                        "keywords": tags.get(ml_id, []),
                        "imdb_id": imdb_id,
                        "tmdb_id": tmdb_id,
                        "rating": round(avg, 4) if avg is not None else None,
                        "rating_count": count,
                        "popularity": popularity,
                    }
                )

    print("Writing catalogue into MyBoxd (server is stopped, so this is lock-safe)...")
    for name in sorted(genre_names):
        tmdb_id = TMDB_GENRE_IDS.get(name)
        try:
            conn.execute("INSERT OR IGNORE INTO genres (tmdb_id, name) VALUES (?, ?)", (tmdb_id, name))
        except sqlite3.IntegrityError:
            conn.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (name,))
    conn.commit()
    genre_ids = {name: gid for gid, name in conn.execute("SELECT id, name FROM genres")}

    insert_sql = """
        INSERT OR IGNORE INTO movies (
            tmdb_id, title, normalized_title, year, production_countries, keywords,
            catalog_rating, catalog_rating_count, catalog_popularity, catalog_source, imdb_id
        ) VALUES (?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)
    """
    batch = []
    for rec in records:
        batch.append((
            rec["tmdb_id"], rec["title"], rec["normalized_title"], rec["year"],
            json.dumps(rec["keywords"], ensure_ascii=False),
            rec["rating"], rec["rating_count"], rec["popularity"], SOURCE, rec["imdb_id"],
        ))
        if len(batch) >= 2000:
            conn.executemany(insert_sql, batch)
            conn.commit()
            batch.clear()
    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    # Map both newly inserted catalogue rows and richer movies that already existed
    # from the user's Letterboxd/TMDB import.
    by_tmdb: dict[int, int] = {}
    by_key: dict[tuple[str, int | None], int] = {}
    for movie_id, tmdb_id, normalized, year in conn.execute(
        "SELECT id, tmdb_id, normalized_title, year FROM movies"
    ):
        if tmdb_id is not None:
            by_tmdb[int(tmdb_id)] = int(movie_id)
        by_key.setdefault((str(normalized), year), int(movie_id))

    updates = []
    genre_pairs = []
    for rec in records:
        movie_id = by_tmdb.get(int(rec["tmdb_id"])) if rec["tmdb_id"] is not None else None
        movie_id = movie_id or by_key.get((rec["normalized_title"], rec["year"]))
        if not movie_id:
            continue
        updates.append((
            rec["rating"], rec["rating_count"], rec["popularity"], rec["imdb_id"], SOURCE,
            json.dumps(rec["keywords"], ensure_ascii=False), movie_id,
        ))
        for genre_name in rec["genres"]:
            genre_id = genre_ids.get(genre_name)
            if genre_id:
                genre_pairs.append((movie_id, genre_id))
        if len(updates) >= 3000:
            conn.executemany(
                """UPDATE movies SET
                    catalog_rating = COALESCE(catalog_rating, ?),
                    catalog_rating_count = COALESCE(catalog_rating_count, ?),
                    catalog_popularity = COALESCE(catalog_popularity, ?),
                    imdb_id = COALESCE(imdb_id, ?),
                    catalog_source = COALESCE(catalog_source, ?),
                    keywords = CASE WHEN keywords IS NULL OR keywords = '[]' THEN ? ELSE keywords END
                    WHERE id = ?""",
                updates,
            )
            conn.commit()
            updates.clear()
        if len(genre_pairs) >= 8000:
            conn.executemany("INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)", genre_pairs)
            conn.commit()
            genre_pairs.clear()

    if updates:
        conn.executemany(
            """UPDATE movies SET
                catalog_rating = COALESCE(catalog_rating, ?),
                catalog_rating_count = COALESCE(catalog_rating_count, ?),
                catalog_popularity = COALESCE(catalog_popularity, ?),
                imdb_id = COALESCE(imdb_id, ?),
                catalog_source = COALESCE(catalog_source, ?),
                keywords = CASE WHEN keywords IS NULL OR keywords = '[]' THEN ? ELSE keywords END
                WHERE id = ?""",
            updates,
        )
    if genre_pairs:
        conn.executemany("INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)", genre_pairs)
    conn.commit()

    installed = _already_installed(conn)
    total_movies = int(conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0])
    conn.execute("PRAGMA optimize")
    conn.close()
    print(f"MovieLens catalogue ready: {installed:,} linked catalogue movies; {total_movies:,} total movies in MyBoxd.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", default="data/ml-32m.zip")
    parser.add_argument("--if-missing", action="store_true")
    args = parser.parse_args()
    install(Path(args.zip_path).expanduser().resolve(), if_missing=args.if_missing)


if __name__ == "__main__":
    main()
