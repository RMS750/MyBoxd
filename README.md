# MyBoxd

MyBoxd is a full-stack Letterboxd taste-analysis and movie-recommendation web app. Users can create an account, import Letterboxd data, explore their Taste DNA, receive explainable personalized recommendations, search films, and discover hidden gems.

## Stack

- React + TypeScript + Vite
- FastAPI + SQLAlchemy + Alembic
- PostgreSQL in production / SQLite locally
- MovieLens 32M for the local recommendation catalogue
- TMDB for metadata, posters, matching, and newer films

## Run locally

```bash
bash setup_local.sh
bash start_local.sh
```

Then open `http://localhost:5173`.

## Public deployment

The repository includes a root `Dockerfile` and `render.yaml` that deploy the frontend and API together on one Render URL with PostgreSQL. See `DEPLOY.md` for the complete deployment and catalogue-seeding steps.

## Private configuration

Copy `.env.example` to `.env` locally and add your own `TMDB_API_KEY`. Never commit `.env` or database credentials.
