from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """Return a naive UTC timestamp for portable SQL DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    interactions: Mapped[list["UserMovieInteraction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user: Mapped[User] = relationship(back_populates="sessions")


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("normalized_title", "year", name="uq_movie_title_year"),
        Index("ix_movie_metadata_ready", "metadata_updated_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    normalized_title: Mapped[str] = mapped_column(String(300), index=True)
    original_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    runtime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    production_countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    popularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    vote_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    vote_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    letterboxd_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    letterboxd_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    letterboxd_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    letterboxd_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    catalog_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    catalog_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catalog_popularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    catalog_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    poster_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    genres: Mapped[list[Genre]] = relationship(secondary=movie_genres, lazy="selectin")
    cast: Mapped[list["MovieCast"]] = relationship(back_populates="movie", cascade="all, delete-orphan", lazy="selectin")
    crew: Mapped[list["MovieCrew"]] = relationship(back_populates="movie", cascade="all, delete-orphan", lazy="selectin")
    interactions: Mapped[list["UserMovieInteraction"]] = relationship(back_populates="movie", cascade="all, delete-orphan")

    @property
    def director_names(self) -> list[str]:
        return [c.person.name for c in self.crew if c.job == "Director" and c.person]

    @property
    def actor_names(self) -> list[str]:
        return [c.person.name for c in sorted(self.cast, key=lambda x: x.order)[:8] if c.person]


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)


class MovieCast(Base):
    __tablename__ = "movie_cast"
    __table_args__ = (UniqueConstraint("movie_id", "person_id", "character", name="uq_cast_credit"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    character: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=999)
    movie: Mapped[Movie] = relationship(back_populates="cast")
    person: Mapped[Person] = relationship(lazy="joined")


class MovieCrew(Base):
    __tablename__ = "movie_crew"
    __table_args__ = (UniqueConstraint("movie_id", "person_id", "job", name="uq_crew_credit"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    job: Mapped[str] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    movie: Mapped[Movie] = relationship(back_populates="crew")
    person: Mapped[Person] = relationship(lazy="joined")


class UserMovieInteraction(Base):
    __tablename__ = "user_movie_interactions"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", name="uq_user_movie"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    watchlist: Mapped[bool] = mapped_column(Boolean, default=False)
    rewatch_count: Mapped[int] = mapped_column(Integer, default=0)
    last_watched: Mapped[date | None] = mapped_column(Date, nullable=True)
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    letterboxd_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    user: Mapped[User] = relationship(back_populates="interactions")
    movie: Mapped[Movie] = relationship(back_populates="interactions", lazy="joined")


class UserRating(Base):
    __tablename__ = "user_ratings"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", name="uq_user_rating"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    rating: Mapped[float] = mapped_column(Float)
    rated_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", name="uq_watchlist_entry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", "watched_date", name="uq_diary_entry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    watched_date: Mapped[date] = mapped_column(Date, index=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rewatch: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportSession(Base):
    __tablename__ = "import_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    movies_created: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    match_score: Mapped[float] = mapped_column(Float)
    predicted_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(30))
    components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(80))
    mae: Mapped[float] = mapped_column(Float)
    rmse: Mapped[float] = mapped_column(Float)
    r2: Mapped[float | None] = mapped_column(Float, nullable=True)
    train_size: Mapped[int] = mapped_column(Integer)
    test_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MetadataCache(Base):
    __tablename__ = "metadata_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
