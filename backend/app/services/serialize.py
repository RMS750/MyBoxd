from app.models.entities import Movie, UserMovieInteraction

IMG = "https://image.tmdb.org/t/p/"


def _community(m: Movie):
    if m.letterboxd_rating is not None:
        return float(m.letterboxd_rating), int(m.letterboxd_rating_count or 0), "Letterboxd"
    if m.catalog_rating is not None:
        return float(m.catalog_rating), int(m.catalog_rating_count or 0), "MovieLens"
    if m.vote_average is not None:
        return float(m.vote_average) / 2.0, int(m.vote_count or 0), "TMDB"
    return None, 0, None


def movie_dict(m: Movie, it: UserMovieInteraction | None = None):
    community_rating, community_count, community_source = _community(m)
    popularity = m.popularity if m.popularity is not None else m.catalog_popularity
    return {
        "id": m.id,
        "tmdb_id": m.tmdb_id,
        "imdb_id": m.imdb_id,
        "title": m.title,
        "original_title": m.original_title,
        "year": m.year,
        "runtime": m.runtime,
        "genres": [g.name for g in m.genres],
        "director": m.director_names[0] if m.director_names else None,
        "actors": m.actor_names[:6],
        "overview": m.overview,
        "keywords": m.keywords or [],
        "countries": m.production_countries or [],
        "language": m.original_language,
        "popularity": popularity,
        "vote_average": m.vote_average,
        "vote_count": m.vote_count,
        "catalog_rating": m.catalog_rating,
        "catalog_rating_count": m.catalog_rating_count,
        "catalog_popularity": m.catalog_popularity,
        "catalog_source": m.catalog_source,
        "community_rating": community_rating,
        "community_rating_count": community_count,
        "community_source": community_source,
        "letterboxd_rating": m.letterboxd_rating,
        "letterboxd_rating_count": m.letterboxd_rating_count,
        "letterboxd_url": m.letterboxd_url,
        "poster_url": f"{IMG}w500{m.poster_path}" if m.poster_path else None,
        "backdrop_url": f"{IMG}w1280{m.backdrop_path}" if m.backdrop_path else None,
        "collection": m.collection_name,
        "match_confidence": m.match_confidence,
        "watched": bool(it and it.watched),
        "watchlist": bool(it and it.watchlist),
        "user_rating": it.rating if it else None,
        "rewatch_count": it.rewatch_count if it else 0,
        "last_watched": it.last_watched.isoformat() if it and it.last_watched else None,
    }
