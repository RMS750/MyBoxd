from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean, median, pstdev

from app.models.entities import UserMovieInteraction


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _scores(items, getter):
    """Build *relative* preferences instead of absolute average-rating scores.

    The old implementation centered every feature around 2.75/5. That makes nearly
    every genre look positive for a generous rater. These scores instead answer:
    "does this user rate this feature higher or lower than their own normal?"
    """
    rated = [item for item in items if item.rating is not None]
    ratings = [float(item.rating) for item in rated]
    if not ratings:
        return {}

    baseline = mean(ratings)
    values = defaultdict(list)
    for item in rated:
        for feature in getter(item):
            if feature:
                values[str(feature)].append(float(item.rating))

    output: dict[str, float] = {}
    for feature, feature_ratings in values.items():
        support = len(feature_ratings)
        # Bayesian shrinkage toward this user's own average. One-off 5-star films
        # should not instantly make an actor/director a defining preference.
        prior = 3.5
        shrunk_mean = (sum(feature_ratings) + baseline * prior) / (support + prior)
        delta = shrunk_mean - baseline
        support_confidence = 1.0 - math.exp(-support / 3.0)
        score = math.tanh(delta / 0.62) * support_confidence
        output[feature] = round(_clip(score), 4)

    return dict(sorted(output.items(), key=lambda row: row[1], reverse=True))


def _weighted_preferred_value(rows: list[tuple[float, float]], baseline: float) -> float | None:
    if not rows:
        return None
    # Movies above the user's baseline count more, but every rated movie still has
    # a small vote so the preference is not based on only a handful of favorites.
    weighted = [(value, 0.35 + max(0.0, rating - baseline)) for value, rating in rows]
    return sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted)


def build_taste_profile(interactions: list[UserMovieInteraction]):
    rated = [item for item in interactions if item.rating is not None]
    watched = [item for item in interactions if getattr(item, "watched", item.rating is not None)]
    ratings = [float(item.rating) for item in rated]
    baseline = mean(ratings) if ratings else 3.0

    genre_scores = _scores(rated, lambda x: [g.name for g in x.movie.genres])
    director_scores = _scores(rated, lambda x: x.movie.director_names)
    actor_scores = _scores(rated, lambda x: x.movie.actor_names[:6])
    decade_scores = _scores(rated, lambda x: [f"{(x.movie.year // 10) * 10}s"] if x.movie.year else [])
    country_scores = _scores(rated, lambda x: x.movie.production_countries or [])
    language_scores = _scores(rated, lambda x: [x.movie.original_language] if x.movie.original_language else [])
    keyword_scores = _scores(rated, lambda x: x.movie.keywords or [])

    runtime_rows = [(float(x.movie.runtime), float(x.rating)) for x in rated if x.movie.runtime]
    popularity_rows = [
        (math.log1p(max(0.0, float(x.movie.popularity))), float(x.rating))
        for x in rated
        if x.movie.popularity is not None
    ]
    preferred_runtime = _weighted_preferred_value(runtime_rows, baseline)
    preferred_log_popularity = _weighted_preferred_value(popularity_rows, baseline)

    high = sorted(rated, key=lambda x: (float(x.rating or 0), x.movie.vote_count or 0), reverse=True)[:8]
    low = sorted(rated, key=lambda x: (float(x.rating or 6), -(x.movie.vote_count or 0)))[:8]
    def public_rating(item):
        if getattr(item.movie, "letterboxd_rating", None) is not None:
            return float(item.movie.letterboxd_rating)
        if getattr(item.movie, "catalog_rating", None) is not None:
            return float(item.movie.catalog_rating)
        if item.movie.vote_average is not None:
            return float(item.movie.vote_average) / 2.0
        return None

    audience_comparable = [x for x in rated if public_rating(x) is not None]
    higher = sorted(
        audience_comparable,
        key=lambda x: float(x.rating or 0) - float(public_rating(x) or 0),
        reverse=True,
    )[:5]
    lower = sorted(
        audience_comparable,
        key=lambda x: float(x.rating or 0) - float(public_rating(x) or 0),
    )[:5]

    enriched_rated = sum(1 for x in rated if getattr(x.movie, "metadata_updated_at", None) is not None or bool(getattr(x.movie, "genres", [])))
    coverage = enriched_rated / len(rated) if rated else 0.0

    return {
        "counts": {
            "watched": len(watched),
            "rated": len(rated),
            "watchlist": sum(1 for x in interactions if getattr(x, "watchlist", False)),
        },
        "average_rating": round(baseline, 2) if ratings else None,
        "rating_std": round(pstdev(ratings), 3) if len(ratings) >= 2 else 0.75,
        "rating_distribution": {
            str(step / 2): sum(1 for rating in ratings if rating == step / 2)
            for step in range(1, 11)
        },
        "genre_scores": genre_scores,
        "director_scores": director_scores,
        "actor_scores": actor_scores,
        "decade_scores": decade_scores,
        "country_scores": country_scores,
        "language_scores": language_scores,
        "keyword_scores": keyword_scores,
        "preferred_runtime": round(preferred_runtime) if preferred_runtime else None,
        "preferred_log_popularity": round(preferred_log_popularity, 3) if preferred_log_popularity is not None else None,
        "metadata_coverage": {
            "rated_movies": len(rated),
            "enriched_rated_movies": enriched_rated,
            "percentage": round(coverage * 100, 1),
            "sufficient": coverage >= 0.75 or enriched_rated >= 150,
        },
        "highest_rated": [{"id": getattr(x.movie, "id", None), "title": x.movie.title, "rating": x.rating} for x in high],
        "lowest_rated": [{"id": getattr(x.movie, "id", None), "title": x.movie.title, "rating": x.rating} for x in low],
        "higher_than_audience": [
            {
                "id": getattr(x.movie, "id", None),
                "title": x.movie.title,
                "delta": round(float(x.rating or 0) - float(public_rating(x) or 0), 2),
                "public_rating": round(float(public_rating(x) or 0), 2),
                "public_source": "Letterboxd" if getattr(x.movie, "letterboxd_rating", None) is not None else "MovieLens" if getattr(x.movie, "catalog_rating", None) is not None else "TMDB",
            }
            for x in higher
        ],
        "lower_than_audience": [
            {
                "id": getattr(x.movie, "id", None),
                "title": x.movie.title,
                "delta": round(float(x.rating or 0) - float(public_rating(x) or 0), 2),
                "public_rating": round(float(public_rating(x) or 0), 2),
                "public_source": "Letterboxd" if getattr(x.movie, "letterboxd_rating", None) is not None else "MovieLens" if getattr(x.movie, "catalog_rating", None) is not None else "TMDB",
            }
            for x in lower
        ],
    }


DIMS = {
    "psychological": {
        "psychological", "identity", "paranoia", "memory", "obsession", "mind", "dream",
        "surrealism", "mental illness", "unreliable narrator", "psychology",
    },
    "dark": {
        "murder", "death", "crime", "dystopia", "horror", "suicide", "war", "violence",
        "revenge", "serial killer", "abuse", "torture",
    },
    "experimental": {
        "surrealism", "avant-garde", "experimental", "nonlinear timeline", "dream", "symbolism",
        "absurdism", "anthology", "nonlinear", "metafiction",
    },
    "emotional_intensity": {
        "grief", "family", "love", "tragedy", "trauma", "friendship", "coming of age",
        "relationship", "loss", "loneliness",
    },
    "fast_paced": {
        "chase", "heist", "martial arts", "action", "survival", "escape", "spy", "assassin",
        "race", "mission",
    },
    "character_driven": {
        "character study", "relationship", "family", "coming of age", "biography", "friendship",
        "identity", "life", "marriage",
    },
    "visual_spectacle": {
        "space", "epic", "superhero", "fantasy world", "alien", "battle", "future", "adventure",
        "magic", "monster",
    },
}


def _dimension_signature(movie, dimension: str, terms: set[str]) -> float:
    tokens = {str(keyword).casefold() for keyword in (movie.keywords or [])}
    tokens |= {genre.name.casefold() for genre in movie.genres}
    text = (movie.overview or "").casefold()
    hits = sum(1 for term in terms if term in tokens or term in text)
    signal = min(1.0, hits / 2.0)

    genre_names = {g.name for g in movie.genres}
    if dimension == "fast_paced" and genre_names & {"Action", "Thriller"}:
        signal = max(signal, 0.60)
    if dimension == "character_driven" and genre_names & {"Drama", "Romance"}:
        signal = max(signal, 0.50)
    if dimension == "visual_spectacle" and genre_names & {"Science Fiction", "Fantasy", "Adventure", "Action"}:
        signal = max(signal, 0.50)
    if dimension == "dark" and genre_names & {"Horror", "Crime", "War"}:
        signal = max(signal, 0.45)
    return signal


def _dimension_preference(rated, baseline: float, signature_getter) -> tuple[int, float]:
    rows = []
    for item in rated:
        signal = float(signature_getter(item.movie))
        if signal > 0:
            rows.append((signal, float(item.rating)))
    if not rows:
        return 50, 0.0

    weighted_rating = sum(signal * rating for signal, rating in rows) / sum(signal for signal, _ in rows)
    delta = weighted_rating - baseline
    effective_support = sum(signal for signal, _ in rows)
    confidence = effective_support / (effective_support + 3.0)
    signed = math.tanh(delta / 0.62) * confidence
    score = round(max(5.0, min(95.0, 50.0 + 45.0 * signed)))
    return score, effective_support


def build_taste_dna(interactions, profile):
    rated = [
        x for x in interactions
        if x.rating is not None and (getattr(x.movie, "metadata_updated_at", None) is not None or bool(getattr(x.movie, "genres", [])))
    ]
    baseline = float(profile.get("average_rating") or 3.0)
    dimensions: dict[str, int] = {}
    support: dict[str, float] = {}

    for dimension, terms in DIMS.items():
        score, evidence = _dimension_preference(
            rated,
            baseline,
            lambda movie, d=dimension, t=terms: _dimension_signature(movie, d, t),
        )
        dimensions[dimension] = score
        support[dimension] = round(evidence, 1)

    # Mainstream is treated as a preference, not simply "how popular are the films
    # you watched". If the user rates popular and obscure films equally, this stays
    # close to neutral instead of automatically labeling them mainstream.
    pop_rows = [x for x in rated if x.movie.popularity is not None]
    if pop_rows:
        def mainstream_signal(movie):
            return min(1.0, math.log1p(max(0.0, float(movie.popularity or 0))) / math.log(101))
        score, evidence = _dimension_preference(pop_rows, baseline, mainstream_signal)
        dimensions["mainstream"] = score
        support["mainstream"] = round(evidence, 1)
    else:
        dimensions["mainstream"] = 50
        support["mainstream"] = 0.0

    labels = {
        "psychological": "psychologically layered stories",
        "dark": "darker subject matter",
        "experimental": "unconventional filmmaking",
        "emotional_intensity": "emotionally intense stories",
        "fast_paced": "momentum and tension",
        "character_driven": "character-driven storytelling",
        "visual_spectacle": "ambitious visual spectacle",
        "mainstream": "mainstream cinema",
    }
    strongest = [
        labels[key]
        for key, value in sorted(dimensions.items(), key=lambda row: row[1], reverse=True)
        if value >= 62 and support.get(key, 0) >= 1.5
    ][:3]
    avoidances = [
        labels[key]
        for key, value in sorted(dimensions.items(), key=lambda row: row[1])
        if value <= 38 and support.get(key, 0) >= 1.5
    ][:2]
    genres = [key for key, value in profile.get("genre_scores", {}).items() if value >= 0.12][:3]

    if strongest:
        summary = "Your ratings most strongly reward " + ", ".join(strongest) + "."
    else:
        summary = "Your ratings are fairly balanced across the measured storytelling dimensions."
    if genres:
        summary += f" Your clearest above-baseline genre preferences are {', '.join(genres)}."
    if avoidances:
        summary += f" You are comparatively tougher on {', '.join(avoidances)}."

    coverage = profile.get("metadata_coverage", {})
    sufficient = bool(coverage.get("sufficient"))
    return {
        "dimensions": dimensions,
        "dimension_support": support,
        "summary": summary,
        "derived_from": "relative rating behavior + TMDB genres, keywords, overview text, and popularity",
        "metadata_coverage": {
            "rated_movies": coverage.get("rated_movies", 0),
            "enriched_rated_movies": coverage.get("enriched_rated_movies", 0),
            "percentage": coverage.get("percentage", 0),
            "sufficient": sufficient,
        },
        "interpretation_note": (
            "Scores above 50 mean you rate that signal above your own baseline; below 50 means you rate it below baseline."
            if sufficient
            else "Metadata coverage is still limited; enrich more rated films before treating these dimensions as stable."
        ),
    }


def build_stats(interactions):
    watched = [x for x in interactions if x.watched]
    rated = [x for x in watched if x.rating is not None]
    ratings = [float(x.rating) for x in rated]
    genres = Counter(g.name for x in watched for g in x.movie.genres)
    directors = Counter(d for x in watched for d in x.movie.director_names)
    actors = Counter(a for x in watched for a in x.movie.actor_names[:5])
    years = Counter(x.movie.year for x in rated if x.movie.year)
    decades = Counter((x.movie.year // 10) * 10 for x in rated if x.movie.year)
    runtimes = [x for x in watched if x.movie.runtime]
    obscure = [x for x in rated if x.movie.popularity is not None]
    controversy = [x for x in rated if x.movie.vote_average is not None]
    profile = build_taste_profile(interactions)

    max_obscure = max(
        obscure,
        key=lambda x: float(x.rating or 0) - math.log1p(float(x.movie.popularity or 0)) / 10,
    ) if obscure else None
    max_controversy = max(
        controversy,
        key=lambda x: abs(float(x.rating or 0) * 2 - float(x.movie.vote_average or 0)),
    ) if controversy else None

    favorite_genre = next((k for k, v in profile["genre_scores"].items() if v > 0.08), None)
    favorite_director = next((k for k, v in profile["director_scores"].items() if v > 0.08), None)
    favorite_actor = next((k for k, v in profile["actor_scores"].items() if v > 0.08), None)
    favorite_decade = next((k for k, v in profile["decade_scores"].items() if v > 0.08), None)

    return {
        "total_watched": len(watched),
        "total_rated": len(rated),
        "total_watchlist": sum(1 for x in interactions if getattr(x, "watchlist", False) and not getattr(x, "watched", False)),
        "average_rating": round(mean(ratings), 2) if ratings else None,
        "median_rating": round(median(ratings), 2) if ratings else None,
        "most_common_rating": Counter(ratings).most_common(1)[0][0] if ratings else None,
        "five_star_percentage": round(100 * sum(1 for r in ratings if r == 5) / len(ratings), 1) if ratings else 0,
        "rewatch_count": sum(getattr(x, "rewatch_count", 0) or 0 for x in watched),
        "most_watched_genre": genres.most_common(1)[0][0] if genres else None,
        "favorite_genre": favorite_genre,
        "most_watched_director": directors.most_common(1)[0][0] if directors else None,
        "favorite_director": favorite_director,
        "most_watched_actor": actors.most_common(1)[0][0] if actors else None,
        "favorite_actor": favorite_actor,
        "favorite_year": years.most_common(1)[0][0] if years else None,
        "most_watched_decade": f"{decades.most_common(1)[0][0]}s" if decades else None,
        "favorite_decade": favorite_decade,
        "longest_movie": {
            "title": max(runtimes, key=lambda x: x.movie.runtime).movie.title,
            "runtime": max(runtimes, key=lambda x: x.movie.runtime).movie.runtime,
        } if runtimes else None,
        "shortest_movie": {
            "title": min(runtimes, key=lambda x: x.movie.runtime).movie.title,
            "runtime": min(runtimes, key=lambda x: x.movie.runtime).movie.runtime,
        } if runtimes else None,
        "highest_rated_obscure": {"title": max_obscure.movie.title, "rating": max_obscure.rating} if max_obscure else None,
        "most_controversial_opinion": {
            "title": max_controversy.movie.title,
            "difference": round(float(max_controversy.rating or 0) * 2 - float(max_controversy.movie.vote_average or 0), 1),
        } if max_controversy else None,
        "most_generous_genre": favorite_genre,
        "harshest_genre": min(profile["genre_scores"], key=profile["genre_scores"].get) if profile["genre_scores"] else None,
        "rating_distribution": profile["rating_distribution"],
        "metadata_coverage": profile["metadata_coverage"],
    }
