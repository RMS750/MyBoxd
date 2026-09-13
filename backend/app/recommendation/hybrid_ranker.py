from __future__ import annotations

import math

import numpy as np

from app.recommendation.affinity import movie_profile_affinity, signed_preference
from app.recommendation.explanation_engine import explain
from app.recommendation.rating_predictor import predictor_for
from app.recommendation.semantic_model import SemanticSimilarity
from app.services.taste import build_taste_profile


DEFAULT_WEIGHTS = {
    "genre": 0.18,
    "semantic": 0.15,
    "creator": 0.10,
    "decade": 0.04,
    "locale": 0.03,
    "runtime": 0.03,
    "popularity": 0.03,
    "community": 0.12,
    "predicted_rating": 0.30,
    "novelty": 0.02,
}


def _to_unit(signed: float, evidence: float = 1.0) -> float:
    # Missing evidence should be neutral (0.5), never silently positive.
    return max(0.0, min(1.0, 0.5 + 0.5 * signed * evidence))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _semantic_thresholds(interactions, baseline: float):
    rated = [item for item in interactions if item.rating is not None]
    if not rated:
        return [], []
    ratings = np.array([float(item.rating) for item in rated])
    high_cut = max(3.5, float(np.quantile(ratings, 0.72)))
    low_cut = min(3.0, float(np.quantile(ratings, 0.28)))
    liked = sorted(
        [item for item in rated if float(item.rating) >= high_cut],
        key=lambda item: float(item.rating),
        reverse=True,
    )[:30]
    disliked = sorted(
        [item for item in rated if float(item.rating) <= low_cut],
        key=lambda item: float(item.rating),
    )[:24]
    return liked, disliked


def _diversity_penalty(row, selected) -> float:
    movie = row["movie"]
    if not selected:
        return 0.0
    movie_genres = {g.name for g in movie.genres}
    movie_directors = set(movie.director_names)
    penalty = 0.0
    for previous in selected[-6:]:
        other = previous["movie"]
        other_genres = {g.name for g in other.genres}
        if movie_genres and other_genres:
            penalty += 4.0 * len(movie_genres & other_genres) / len(movie_genres | other_genres)
        if movie_directors and movie_directors & set(other.director_names):
            penalty += 5.0
        if movie.collection_name and movie.collection_name == other.collection_name:
            penalty += 7.0
    return min(15.0, penalty)


def diversify(rows, limit: int | None = None, strength: float = 1.0):
    """MMR-style reranking so every rail is not the same franchise/genre cluster."""
    pool = list(rows)
    chosen = []
    target = min(len(pool), limit or len(pool))
    while pool and len(chosen) < target:
        best = max(pool, key=lambda row: row["match_score"] - strength * _diversity_penalty(row, chosen))
        chosen.append(best)
        pool.remove(best)
    if limit is None and pool:
        chosen.extend(pool)
    return chosen


def rank_movies(interactions, candidates, weights=None):
    if not candidates:
        return []

    weights = weights or DEFAULT_WEIGHTS
    total = sum(float(value) for value in weights.values()) or 1.0
    weights = {key: float(value) / total for key, value in weights.items()}
    profile = build_taste_profile(interactions)
    baseline = float(profile.get("average_rating") or 3.0)
    spread = max(0.55, float(profile.get("rating_std") or 0.75))

    liked, disliked = _semantic_thresholds(interactions, baseline)
    semantic_model = SemanticSimilarity()
    liked_similarity = semantic_model.similarities([item.movie for item in liked], candidates) if liked else [0.0] * len(candidates)
    disliked_similarity = semantic_model.similarities([item.movie for item in disliked], candidates) if disliked else [0.0] * len(candidates)
    predictions = predictor_for(interactions).predict_many(candidates)

    rows = []
    for movie, positive_semantic, negative_semantic, prediction in zip(
        candidates, liked_similarity, disliked_similarity, predictions
    ):
        genre_signed, genre_evidence = signed_preference(profile.get("genre_scores", {}), [g.name for g in movie.genres])
        director_signed, director_evidence = signed_preference(profile.get("director_scores", {}), movie.director_names[:2])
        actor_signed, actor_evidence = signed_preference(profile.get("actor_scores", {}), movie.actor_names[:6])
        creator_weight = director_evidence + actor_evidence
        creator_signed = (
            (director_signed * director_evidence + actor_signed * actor_evidence) / creator_weight
            if creator_weight else 0.0
        )
        creator_evidence = min(1.0, creator_weight / 1.2)

        decade_keys = [f"{(movie.year // 10) * 10}s"] if movie.year else []
        decade_signed, decade_evidence = signed_preference(profile.get("decade_scores", {}), decade_keys)
        language_signed, language_evidence = signed_preference(
            profile.get("language_scores", {}),
            [movie.original_language] if movie.original_language else [],
        )
        country_signed, country_evidence = signed_preference(
            profile.get("country_scores", {}),
            list(movie.production_countries or [])[:3],
        )
        locale_evidence = language_evidence + country_evidence
        locale_signed = (
            (language_signed * language_evidence + country_signed * country_evidence) / locale_evidence
            if locale_evidence else 0.0
        )
        locale_evidence = min(1.0, locale_evidence / 1.2)

        preferred_runtime = profile.get("preferred_runtime")
        if movie.runtime and preferred_runtime:
            runtime_fit = math.exp(-abs(float(movie.runtime) - float(preferred_runtime)) / 55.0)
        else:
            runtime_fit = 0.5

        preferred_popularity = profile.get("preferred_log_popularity")
        effective_popularity = movie.popularity if movie.popularity is not None else getattr(movie, "catalog_popularity", None)
        if effective_popularity is not None and preferred_popularity is not None:
            popularity_value = math.log1p(max(0.0, float(effective_popularity)))
            popularity_fit = math.exp(-abs(popularity_value - float(preferred_popularity)) / 2.0)
        else:
            popularity_fit = 0.5

        # Public quality is a real prior, not a verdict. Letterboxd's weighted
        # average is used when available because it maps directly to the same 0.5–5
        # star scale as the user's history. TMDB is a weaker fallback.
        community_fit = 0.5
        community_rating = None
        if getattr(movie, "letterboxd_rating", None) is not None:
            community_rating = float(movie.letterboxd_rating)
            community_fit = _sigmoid((community_rating - 3.05) * 2.35)
        elif getattr(movie, "catalog_rating", None) is not None:
            community_rating = float(movie.catalog_rating)
            community_fit = _sigmoid((community_rating - 3.10) * 1.55)
        elif movie.vote_average is not None:
            community_rating = float(movie.vote_average) / 2.0
            community_fit = _sigmoid((community_rating - 3.25) * 1.20)

        if liked and disliked:
            semantic_margin = float(positive_semantic) - float(negative_semantic)
        elif liked:
            semantic_margin = (float(positive_semantic) - 0.25) * 0.75
        elif disliked:
            semantic_margin = (0.25 - float(negative_semantic)) * 0.75
        else:
            semantic_margin = 0.0
        semantic_fit = _to_unit(max(-1.0, min(1.0, semantic_margin)))

        prediction_z = (float(prediction.rating) - baseline) / spread
        rating_fit = _sigmoid(1.35 * prediction_z)
        confidence_factor = {"High": 1.0, "Medium": 0.86, "Low": 0.68}.get(prediction.confidence, 0.68)
        rating_fit = 0.5 + (rating_fit - 0.5) * confidence_factor

        profile_affinity, profile_evidence = movie_profile_affinity(movie, profile)
        novelty = max(0.0, min(1.0, 1.0 - max(float(positive_semantic), 0.35 + 0.35 * max(0.0, profile_affinity))))

        components = {
            "genre": _to_unit(genre_signed, genre_evidence),
            "semantic": semantic_fit,
            "creator": _to_unit(creator_signed, creator_evidence),
            "decade": _to_unit(decade_signed, decade_evidence),
            "locale": _to_unit(locale_signed, locale_evidence),
            "runtime": runtime_fit,
            "popularity": popularity_fit,
            "community": community_fit,
            "predicted_rating": rating_fit,
            "novelty": novelty,
        }
        raw = sum(components[key] * weights.get(key, 0.0) for key in components)

        # Convert the model evidence into a *continuous* latent preference signal.
        # V4 used hard public-rating caps (30/40/52/62), which could create visible
        # score piles. V5 deliberately has no buckets or cliffs: every input nudges
        # the score smoothly, and the final tanh calibration can use the full 0–100
        # range while keeping truly extreme scores rare.
        prediction_signal = math.tanh(prediction_z / 1.15)
        affinity_signal = profile_affinity * profile_evidence
        semantic_dislike = max(0.0, float(negative_semantic) - 0.72 * float(positive_semantic))

        # Community reception is an asymmetric prior. Poor reception is useful
        # evidence that a superficially genre-compatible film may still be a bad
        # recommendation, while a high public average only gives a modest boost.
        # Rating-count confidence prevents a tiny sample from moving the model much.
        community_signal = 0.0
        lb = getattr(movie, "letterboxd_rating", None)
        if lb is not None:
            lb = float(lb)
            count = float(getattr(movie, "letterboxd_rating_count", 0) or 0)
            reception = math.tanh((lb - 3.10) / 0.72)
            reception_confidence = min(1.0, 0.48 + math.log1p(count) / 15.0) if count > 0 else 0.58
            community_signal = reception * reception_confidence * (1.30 if reception < 0 else 0.42)
        elif getattr(movie, "catalog_rating", None) is not None:
            catalog_stars = float(movie.catalog_rating)
            reception = math.tanh((catalog_stars - 3.15) / 0.82)
            count = float(getattr(movie, "catalog_rating_count", 0) or 0)
            reception_confidence = min(0.82, 0.30 + math.log1p(count) / 16.0) if count > 0 else 0.30
            community_signal = reception * reception_confidence * (0.82 if reception < 0 else 0.30)
        elif movie.vote_average is not None:
            tmdb_stars = float(movie.vote_average) / 2.0
            reception = math.tanh((tmdb_stars - 3.25) / 0.90)
            count = float(movie.vote_count or 0)
            reception_confidence = min(0.72, 0.25 + math.log1p(count) / 18.0) if count > 0 else 0.30
            community_signal = reception * reception_confidence * (0.65 if reception < 0 else 0.24)

        latent = (
            3.35 * (raw - 0.5)
            + 0.82 * prediction_signal
            + 0.72 * affinity_signal
            + community_signal
            - 0.72 * semantic_dislike
        )

        # Smooth calibration: neutral evidence -> ~50, strong negative evidence can
        # reach single digits, strong positive evidence can reach the 90s. No hard
        # caps means nearby films receive nearby scores instead of snapping to 30/40.
        score = 50.0 + 48.0 * math.tanh(latent / 1.42)
        score = round(max(1.0, min(99.0, score)), 1)

        rows.append(
            {
                "movie": movie,
                "match_score": score,
                "predicted_rating": round(float(prediction.rating), 2),
                "confidence": prediction.confidence,
                "prediction_method": prediction.method,
                "category": "GOOD MATCH",  # assigned after relative calibration below
                "components": {key: round(float(value), 3) for key, value in components.items()},
                "profile_affinity": round(profile_affinity, 3),
                "semantic_positive": round(float(positive_semantic), 3),
                "semantic_negative": round(float(negative_semantic), 3),
                "explanation": explain(movie, components, liked, profile),
            }
        )

    rows.sort(key=lambda row: (row["match_score"], row["predicted_rating"]), reverse=True)
    scores = np.array([row["match_score"] for row in rows], float)
    safe_cut = max(68.0, float(np.quantile(scores, 0.82))) if len(scores) >= 5 else 72.0

    for row in rows:
        score = float(row["match_score"])
        prediction = float(row["predicted_rating"])
        negative = float(row.get("semantic_negative", 0.0))
        novelty = float(row["components"]["novelty"])
        if (
            score >= safe_cut
            and prediction >= baseline + 0.15
            and negative < 0.72
            and row["confidence"] != "Low"
        ):
            row["category"] = "SAFE BET"
        elif novelty >= 0.60 and score >= 49.0:
            row["category"] = "WILD CARD"
        elif score >= 57.0:
            row["category"] = "GOOD MATCH"
        else:
            row["category"] = "RISKY PICK"

    return rows
