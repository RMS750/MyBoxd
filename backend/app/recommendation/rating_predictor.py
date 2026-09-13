from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge

from app.recommendation.affinity import movie_profile_affinity, movie_signature, signature_similarity
from app.recommendation.features import feature_dict
from app.services.taste import build_taste_profile


@dataclass
class RatingPrediction:
    rating: float
    confidence: str
    method: str


class PersonalRatingPredictor:
    """A deliberately transparent ensemble for personal star-rating prediction.

    It combines: personal feature preferences, nearest-neighbour ratings, a ridge
    metadata model, and a small public-audience prior. Crucially, every component
    is centered on the user's own rating baseline rather than a universal 2.5/5.
    """

    def __init__(self, interactions):
        self.rated = [item for item in interactions if item.rating is not None]
        self.ratings = [float(item.rating) for item in self.rated]
        self.avg = mean(self.ratings) if self.ratings else 3.0
        self.spread = max(0.55, pstdev(self.ratings) if len(self.ratings) >= 2 else 0.75)
        self.profile = build_taste_profile(interactions)

        self._rated_signatures = [(movie_signature(item.movie), float(item.rating)) for item in self.rated]
        letterboxd_offsets = [
            float(item.rating) - float(getattr(item.movie, "letterboxd_rating", 0.0))
            for item in self.rated
            if getattr(item.movie, "letterboxd_rating", None) is not None
        ]
        catalog_offsets = [
            float(item.rating) - float(item.movie.catalog_rating)
            for item in self.rated
            if getattr(item.movie, "catalog_rating", None) is not None and (getattr(item.movie, "catalog_rating_count", 0) or 0) >= 20
        ]
        tmdb_offsets = [
            float(item.rating) - float(item.movie.vote_average) / 2.0
            for item in self.rated
            if item.movie.vote_average is not None and (item.movie.vote_count or 0) >= 20
        ]
        self.letterboxd_bias = mean(letterboxd_offsets) if letterboxd_offsets else 0.0
        self.catalog_bias = mean(catalog_offsets) if catalog_offsets else 0.0
        self.audience_bias = mean(tmdb_offsets) if tmdb_offsets else 0.0

        self.vectorizer = None
        self.model = None
        metadata_rated = [item for item in self.rated if feature_dict(item.movie)]
        if len(metadata_rated) >= 12:
            self.vectorizer = DictVectorizer(sparse=True)
            features = self.vectorizer.fit_transform([feature_dict(item.movie) for item in metadata_rated])
            labels = np.array([float(item.rating) for item in metadata_rated], float)
            # Lower regularization than before because predictions are blended with
            # multiple stabilizing signals instead of trusting Ridge on its own.
            self.model = Ridge(alpha=2.5).fit(features, labels)

    def _neighbor_estimate(self, movie) -> tuple[float, float]:
        if not self._rated_signatures:
            return self.avg, 0.0
        candidate = movie_signature(movie)
        neighbours = []
        for signature, rating in self._rated_signatures:
            similarity = signature_similarity(signature, candidate)
            if similarity >= 0.08:
                neighbours.append((similarity, rating))
        if not neighbours:
            return self.avg, 0.0
        neighbours.sort(reverse=True)
        top = neighbours[:14]
        weights = [similarity ** 1.7 for similarity, _ in top]
        estimate = sum(weight * rating for weight, (_, rating) in zip(weights, top)) / sum(weights)
        evidence = min(1.0, sum(weights) / 2.5)
        return estimate, evidence

    def _profile_estimate(self, movie) -> tuple[float, float]:
        affinity, evidence = movie_profile_affinity(movie, self.profile)
        estimate = self.avg + affinity * self.spread * 1.45
        return estimate, evidence

    def _audience_estimate(self, movie) -> tuple[float, float]:
        if getattr(movie, "letterboxd_rating", None) is not None:
            estimate = float(movie.letterboxd_rating) + self.letterboxd_bias
            count = float(getattr(movie, "letterboxd_rating_count", 0) or 0)
            evidence = 0.70 if count <= 0 else min(1.0, 0.55 + np.log1p(count) / 16.0)
            return estimate, float(evidence)
        if getattr(movie, "catalog_rating", None) is not None and (getattr(movie, "catalog_rating_count", 0) or 0) >= 20:
            estimate = float(movie.catalog_rating) + self.catalog_bias
            evidence = min(0.82, 0.24 + np.log1p(float(movie.catalog_rating_count or 0)) / 16.0)
            return estimate, float(evidence)
        if movie.vote_average is None or (movie.vote_count or 0) < 20:
            return self.avg, 0.0
        estimate = float(movie.vote_average) / 2.0 + self.audience_bias
        evidence = min(0.72, 0.18 + np.log1p(float(movie.vote_count or 0)) / 18.0)
        return estimate, float(evidence)

    def predict_many(self, movies):
        if not movies:
            return []
        if not self.rated:
            return [RatingPrediction(3.0, "Low", "cold-start") for _ in movies]

        ridge_values = None
        if self.model is not None and self.vectorizer is not None:
            ridge_values = self.model.predict(self.vectorizer.transform([feature_dict(movie) for movie in movies]))

        output = []
        for index, movie in enumerate(movies):
            estimates: list[tuple[float, float]] = [(self.avg, 0.18)]  # personal baseline prior

            profile_estimate, profile_evidence = self._profile_estimate(movie)
            if profile_evidence:
                estimates.append((profile_estimate, 0.34 * profile_evidence))

            neighbour_estimate, neighbour_evidence = self._neighbor_estimate(movie)
            if neighbour_evidence:
                estimates.append((neighbour_estimate, 0.33 * neighbour_evidence))

            if ridge_values is not None:
                estimates.append((float(ridge_values[index]), 0.24))

            audience_estimate, audience_evidence = self._audience_estimate(movie)
            if audience_evidence:
                public_weight = 0.24 if getattr(movie, "letterboxd_rating", None) is not None else 0.14 if getattr(movie, "catalog_rating", None) is not None else 0.08
                estimates.append((audience_estimate, public_weight * audience_evidence))

            total_weight = sum(weight for _, weight in estimates)
            estimate = sum(value * weight for value, weight in estimates) / total_weight

            # Mildly restore personal spread after multiple shrinkage steps. This
            # fixes the previous behaviour where almost everything became ~3.3/5.
            estimate = self.avg + 1.12 * (estimate - self.avg)
            estimate = float(np.clip(estimate, 0.5, 5.0))

            evidence = min(1.0, max(0.0, total_weight - 0.18) / 0.75)
            history_factor = min(1.0, len(self.rated) / 60.0)
            confidence_value = evidence * history_factor
            confidence = "High" if confidence_value >= 0.72 else "Medium" if confidence_value >= 0.42 else "Low"
            method = "personal-ensemble" if ridge_values is not None else "personal-neighbours"
            output.append(RatingPrediction(estimate, confidence, method))
        return output


_PREDICTOR_CACHE: dict[tuple, PersonalRatingPredictor] = {}


def predictor_for(interactions):
    """Reuse a trained personal model until ratings or movie metadata change."""
    key = tuple(
        sorted(
            (item.movie_id, float(item.rating), str(item.movie.metadata_updated_at or ""))
            for item in interactions
            if item.rating is not None
        )
    )
    cached = _PREDICTOR_CACHE.get(key)
    if cached is not None:
        return cached
    model = PersonalRatingPredictor(interactions)
    _PREDICTOR_CACHE.clear()
    _PREDICTOR_CACHE[key] = model
    return model
