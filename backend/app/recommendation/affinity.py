from __future__ import annotations

import math


def _values(scores: dict[str, float], keys: list[str]) -> list[float]:
    return [float(scores[key]) for key in keys if key and key in scores]


def signed_preference(scores: dict[str, float], keys: list[str]) -> tuple[float, float]:
    """Return signed preference (-1..1) plus evidence (0..1).

    A mean is deliberately used instead of max(): a movie with one favorite genre
    and two disliked genres should not be treated as a perfect genre match.
    """
    values = _values(scores, keys)
    if not values:
        return 0.0, 0.0
    # Slightly emphasize the strongest-magnitude signals while still respecting
    # contradictory evidence from the other tags.
    weights = [0.6 + abs(value) for value in values]
    score = sum(value * weight for value, weight in zip(values, weights)) / sum(weights)
    evidence = min(1.0, 0.45 + 0.18 * len(values))
    return max(-1.0, min(1.0, score)), evidence


def movie_profile_affinity(movie, profile: dict) -> tuple[float, float]:
    groups: list[tuple[float, float, float]] = []

    genre, genre_e = signed_preference(profile.get("genre_scores", {}), [g.name for g in movie.genres])
    groups.append((genre, genre_e, 0.32))

    keyword, keyword_e = signed_preference(profile.get("keyword_scores", {}), list(movie.keywords or [])[:20])
    groups.append((keyword, keyword_e, 0.20))

    director, director_e = signed_preference(profile.get("director_scores", {}), movie.director_names[:2])
    groups.append((director, director_e, 0.16))

    actor, actor_e = signed_preference(profile.get("actor_scores", {}), movie.actor_names[:6])
    groups.append((actor, actor_e, 0.10))

    decade_key = [f"{(movie.year // 10) * 10}s"] if movie.year else []
    decade, decade_e = signed_preference(profile.get("decade_scores", {}), decade_key)
    groups.append((decade, decade_e, 0.07))

    language, language_e = signed_preference(
        profile.get("language_scores", {}),
        [movie.original_language] if movie.original_language else [],
    )
    groups.append((language, language_e, 0.05))

    country, country_e = signed_preference(profile.get("country_scores", {}), list(movie.production_countries or [])[:3])
    groups.append((country, country_e, 0.06))

    # Runtime is a preference only when the candidate has a runtime and the
    # user has enough metadata to establish a personal sweet spot.
    preferred_runtime = profile.get("preferred_runtime")
    if movie.runtime and preferred_runtime:
        delta = abs(float(movie.runtime) - float(preferred_runtime))
        runtime = 2 * math.exp(-delta / 55.0) - 1
        groups.append((runtime, 0.65, 0.04))

    numerator = 0.0
    denominator = 0.0
    available_weight = 0.0
    for value, evidence, weight in groups:
        if evidence <= 0:
            continue
        numerator += value * evidence * weight
        denominator += evidence * weight
        available_weight += weight

    if denominator <= 0:
        return 0.0, 0.0
    affinity = numerator / denominator
    evidence = min(1.0, available_weight / 0.75)
    return max(-1.0, min(1.0, affinity)), evidence


def movie_signature(movie) -> dict[str, object]:
    return {
        "genres": {g.name.casefold() for g in movie.genres},
        "keywords": {str(k).casefold() for k in (movie.keywords or [])[:20]},
        "directors": {d.casefold() for d in movie.director_names[:2]},
        "actors": {a.casefold() for a in movie.actor_names[:6]},
        "language": (movie.original_language or "").casefold(),
        "countries": {c.casefold() for c in (movie.production_countries or [])[:3]},
        "year": movie.year,
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def signature_similarity(left: dict[str, object], right: dict[str, object]) -> float:
    genre = _jaccard(left["genres"], right["genres"])
    keyword = _jaccard(left["keywords"], right["keywords"])
    director = 1.0 if left["directors"] and left["directors"] & right["directors"] else 0.0
    actor = _jaccard(left["actors"], right["actors"])
    language = 1.0 if left["language"] and left["language"] == right["language"] else 0.0
    country = _jaccard(left["countries"], right["countries"])

    year_fit = 0.0
    if left["year"] and right["year"]:
        year_fit = math.exp(-abs(int(left["year"]) - int(right["year"])) / 18.0)

    return max(
        0.0,
        min(
            1.0,
            0.34 * genre
            + 0.22 * keyword
            + 0.14 * director
            + 0.10 * actor
            + 0.06 * language
            + 0.05 * country
            + 0.09 * year_fit,
        ),
    )
