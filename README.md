# MyBoxd

**A personalized movie recommendation platform built around your actual
taste.**

**Live Website:** https://myboxd.onrender.com

MyBoxd analyzes a user's movie ratings and viewing history to build a
personalized taste profile and recommend films they are genuinely likely
to enjoy.

Instead of simply recommending popular movies or films with similar
genres, MyBoxd attempts to understand patterns in a user's taste and
rank movies based on personal compatibility.

------------------------------------------------------------------------

## Features

### Taste DNA

MyBoxd analyzes your movie history to identify patterns in your
preferences, including favourite genres, preferred themes and styles,
rating tendencies, and positive and negative taste signals.

### Personalized Recommendations

Movies receive a **0--100 personal match score** based on how closely
they fit your taste. Recommendations include Top Picks, Safe Bets,
Hidden Gems, Wild Cards, and Anti-Recommendations.

### Letterboxd Import

Users can import Letterboxd ratings, watched films, diary entries,
reviews, and watchlists. Imports can **merge** with existing data or
**replace** it.

### Movie Discovery

Explore and search a catalogue of more than **87,000 movies**, built
from MovieLens 32M and enriched with TMDB metadata.

### Movie Roulette

Can't decide what to watch? Movie Roulette helps choose a film from your
personalized recommendation pool.

### Watch Tonight

A focused recommendation mode designed to quickly help users choose
something to watch.

### Personal Statistics

View statistics and patterns derived from your movie history and
ratings.

### Watchlist

Maintain a personal watchlist and explore recommendations based on your
taste.

### Taste Comparison

Compare movie preferences and compatibility between users.

------------------------------------------------------------------------

## Recommendation System

MyBoxd uses a custom hybrid recommendation system combining signals such
as user ratings, genre affinity, positive and negative taste patterns,
movie popularity, community ratings, metadata, keywords, film
similarity, and context-based scoring.

The goal is not just to predict whether a movie is generally considered
good, but whether a **specific user** is likely to enjoy it.

A score of `85`, for example, represents a strong match for that user's
taste --- it is **not an 85% probability**.

------------------------------------------------------------------------

## Movie Catalogue

MyBoxd uses the **MovieLens 32M** dataset as its core catalogue.

The current hosted catalogue contains **87,256 MovieLens-linked movies**
and is derived from more than **32 million community ratings**. It also
includes genre information, tags, and IMDb/TMDB identifiers where
available.

TMDB provides additional metadata such as posters, descriptions, and
movie information.

------------------------------------------------------------------------

## Technology Stack

**Frontend:** React, TypeScript, Vite, CSS\
**Backend:** Python, FastAPI, SQLAlchemy, Pydantic\
**Database:** PostgreSQL, Alembic\
**Data & Recommendations:** NumPy, Pandas, Scikit-learn, custom hybrid
ranking algorithms\
**Deployment:** Docker, Render, GitHub

------------------------------------------------------------------------

## Project Structure

``` text
MyBoxd/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── importers/
│   │   ├── models/
│   │   ├── recommendation/
│   │   ├── schemas/
│   │   └── services/
│   ├── alembic/
│   ├── scripts/
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/
│       ├── context/
│       ├── hooks/
│       ├── pages/
│       └── services/
├── sample_data/
├── scripts/
├── Dockerfile
├── render.yaml
└── README.md
```

------------------------------------------------------------------------

## Running MyBoxd Locally

Clone the repository:

``` bash
git clone https://github.com/RMS750/MyBoxd.git
cd MyBoxd
```

Create the backend environment:

``` bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file using `.env.example` as a reference and configure
your database connection and TMDB API access. Never commit API keys,
database passwords, or `.env` files to GitHub.

Run the backend:

``` bash
uvicorn app.main:app --reload
```

In another terminal, run the frontend:

``` bash
cd frontend
npm install
npm run dev
```

------------------------------------------------------------------------

## Testing

Backend tests:

``` bash
cd backend
pytest
```

Code-quality checks:

``` bash
ruff check .
```

Frontend production build:

``` bash
cd frontend
npm install
npm run build
```

------------------------------------------------------------------------

## Privacy & Security

MyBoxd supports individual user accounts and keeps user movie data
separated between accounts.

Sensitive information such as API keys, database credentials, and
environment variables is excluded from the public repository. Never
commit `.env` files or production credentials.

------------------------------------------------------------------------

## Deployment

The production application is containerized with Docker and deployed on
Render. The React frontend and FastAPI backend are served from the same
application, while PostgreSQL is used as the production database.

Deployment configuration is included in `render.yaml`.

------------------------------------------------------------------------

## Data Sources

-   **MovieLens 32M** --- catalogue and community-rating data
-   **TMDB** --- additional movie metadata and imagery
-   User-provided **Letterboxd exports** --- personalized taste analysis

MyBoxd is an independent project and is not affiliated with Letterboxd,
TMDB, or GroupLens.

------------------------------------------------------------------------

## Future Development

Planned improvements include larger personalized discovery pages,
genre-specific recommendation feeds, improved hidden-gem detection,
better recommendation explanations, more advanced taste analysis,
expanded movie metadata, improved social compatibility features, and
continuous catalogue updates.

------------------------------------------------------------------------

## Author

Created by **Yahya Sarsri**

GitHub: https://github.com/RMS750

------------------------------------------------------------------------

## License

See the `LICENSE` file for licensing information.
