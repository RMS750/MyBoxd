from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.entities import Movie, User


def _reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_authenticated_import_to_recommendation_search_and_delete_flow():
    _reset()
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"name": "Smoke", "email": "smoke@example.com", "password": "goodpassword123"},
        )
        assert registered.status_code == 201, registered.text
        csrf = registered.json()["user"]["csrf_token"]

        ratings = b"Date,Name,Year,Rating\n2026-01-02,Arrival,2016,5\n2026-01-03,Her,2013,4.5\n"
        watchlist = b"Date,Name,Year\n2026-01-04,Moon,2009\n"
        imported = client.post(
            "/api/import",
            files=[
                ("files", ("ratings.csv", ratings, "text/csv")),
                ("files", ("watchlist.csv", watchlist, "text/csv")),
            ],
            headers={"X-CSRF-Token": csrf},
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["movies"] == 3

        stats = client.get("/api/stats")
        assert stats.status_code == 200
        assert stats.json()["total_watched"] == 2
        assert stats.json()["total_watchlist"] == 1

        # Seed one globally reusable metadata candidate so this route-level smoke test
        # remains deterministic without making a real TMDB call.
        with SessionLocal() as db:
            candidate = Movie(
                title="The Double Life of Veronique",
                normalized_title="the double life of veronique",
                year=1991,
                runtime=98,
                overview="Two women share a mysterious emotional connection.",
                original_language="fr",
                production_countries=["France", "Poland"],
                keywords=["identity", "connection"],
                popularity=18.0,
                vote_average=7.5,
                vote_count=900,
                metadata_updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(candidate)
            db.commit()
            candidate_id = candidate.id

        recs = client.get("/api/recommendations?limit=5")
        assert recs.status_code == 200, recs.text
        rows = recs.json()["recommendations"]
        assert rows and any(row["id"] == candidate_id for row in rows)
        assert rows[0]["explanation"]
        assert 0 <= rows[0]["match_score"] <= 100

        searched = client.get("/api/search?q=veronique")
        assert searched.status_code == 200, searched.text
        assert any(row["id"] == candidate_id for row in searched.json()["results"])

        reviews = client.get(f"/api/movies/{candidate_id}/reviews")
        assert reviews.status_code == 200, reviews.text
        assert reviews.json()["reviews"] == []

        account_delete = client.delete("/api/settings/account", headers={"X-CSRF-Token": csrf})
        assert account_delete.status_code == 200, account_delete.text
        assert client.get("/api/auth/me").status_code == 401
        with SessionLocal() as db:
            assert db.scalar(select(User).where(User.email == "smoke@example.com")) is None


def test_new_account_recommendations_are_local_and_fast():
    """A fresh login must render without remote discovery or database writes."""
    _reset()
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"name": "Fresh", "email": "fresh-test@example.com", "password": "goodpassword123"},
        )
        assert registered.status_code == 201, registered.text
        response = client.get("/api/recommendations?limit=12")
        assert response.status_code == 200, response.text
        assert response.json()["recommendations"] == []


def test_existing_user_recommendations_use_local_catalogue_only():
    """Recommendation lists should rank local catalogue rows without TMDB fan-out."""
    from app.models.entities import Genre, UserMovieInteraction

    _reset()
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"name": "Fast", "email": "fast@example.com", "password": "goodpassword123"},
        )
        assert registered.status_code == 201
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "fast@example.com"))
            drama = Genre(name="Drama")
            mystery = Genre(name="Mystery")
            db.add_all([drama, mystery])
            db.flush()
            watched = Movie(
                title="Loved Film", normalized_title="loved film", year=2020, runtime=110,
                overview="A psychological identity mystery.", original_language="en",
                production_countries=["US"], keywords=["identity"], popularity=30,
                vote_average=8, vote_count=1000,
                metadata_updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                genres=[drama, mystery],
            )
            db.add(watched)
            db.flush()
            db.add(UserMovieInteraction(user_id=user.id, movie_id=watched.id, watched=True, rating=5.0, watchlist=False))
            for i in range(40):
                candidate = Movie(
                    title=f"Local Candidate {i}", normalized_title=f"local candidate {i}", year=2000 + (i % 24),
                    overview="A psychological mystery about identity and memory.",
                    production_countries=[], keywords=[], catalog_rating=3.2 + (i % 8) * 0.15,
                    catalog_rating_count=100 + i * 10, catalog_popularity=float(10 + i),
                    catalog_source="movielens-32m", tmdb_id=900000 + i, genres=[drama, mystery],
                )
                db.add(candidate)
            db.commit()
        recs = client.get("/api/recommendations?limit=12")
        assert recs.status_code == 200, recs.text
        rows = recs.json()["recommendations"]
        assert len(rows) == 12
        scores = [row["match_score"] for row in rows]
        assert scores == sorted(scores, reverse=True)

        feed = client.get("/api/discover-feed")
        assert feed.status_code == 200, feed.text
        data = feed.json()
        top_ids = {row["id"] for row in data["top"]}
        gem_ids = {row["id"] for row in data["gems"]}
        assert top_ids.isdisjoint(gem_ids)
        assert data["catalogue_backed"] is True
