# Deploy MyBoxd as a public website

This repository is configured so visitors only open one URL. The React frontend and FastAPI backend are served from the same Render service, while Render Postgres stores accounts, imports, and the shared movie catalogue.

## 1. Push this folder to GitHub

Create an empty GitHub repository named `MyBoxd`, then from this folder run:

```bash
git init
git add .
git commit -m "Initial MyBoxd release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/MyBoxd.git
git push -u origin main
```

Never commit `.env`, `myboxd.db`, `backend/data/`, `.venv`, or `node_modules`.

## 2. Deploy on Render

1. Sign in to Render with GitHub.
2. Choose **New > Blueprint**.
3. Select the `MyBoxd` repository.
4. Render reads the root `render.yaml` and creates:
   - one web service named `myboxd`
   - one PostgreSQL database named `myboxd-db`
5. When Render asks for `TMDB_API_KEY`, enter your own private TMDB v3 API key.
6. Deploy the Blueprint.
7. Wait for the web service to show **Live**.
8. Open the service URL. The same URL serves the website and `/api`.

The free Render web service can sleep after inactivity, so the first request after a quiet period may be slow. Free Render Postgres is intended for testing and expires after 30 days; upgrade the database before that if you want a durable public portfolio deployment.

## 3. Seed the shared ~87k MovieLens catalogue once

Do this before sharing the site. The catalogue is not committed to GitHub.

### A. Copy the Render database external URL

Open `myboxd-db` in Render and copy its **External Database URL**. Treat it like a password. Do not paste it into GitHub or share it publicly.

### B. Use the verified MovieLens archive already on your Mac

If you built MyBoxd locally using the release setup, it should be at:

```text
$HOME/Downloads/MyBoxd-V5.5/MyBoxd/backend/data/ml-32m.zip
```

If your working folder differs, use the actual path to `ml-32m.zip`.

### C. Run the production catalogue importer locally

From your clean GitHub project folder:

```bash
cd "$HOME/Downloads/MyBoxd/backend"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then run this command, replacing `PASTE_RENDER_EXTERNAL_DATABASE_URL_HERE` only in your own Terminal:

```bash
DATABASE_URL='PASTE_RENDER_EXTERNAL_DATABASE_URL_HERE' \
python scripts/install_movielens_catalog_db.py \
  --zip "$HOME/Downloads/MyBoxd-V5.5/MyBoxd/backend/data/ml-32m.zip" \
  --if-missing
```

Expected final output is approximately 87,000 catalogue movies. The command is idempotent with `--if-missing`, so rerunning it after a completed import will skip the seed.

## 4. Verify the public site

Open your Render URL and:

1. Create a new test account.
2. Import a small Letterboxd export or the supplied sample data.
3. Open Dashboard and Discover.
4. Confirm posters load and recommendations appear.
5. Check `https://YOUR-RENDER-URL/health` and confirm database status is `ok`.

## Security

- Never commit your TMDB API key.
- Never commit the Render database URL.
- Rotate any TMDB key that was exposed during development before public launch.
- Use a paid/persistent database before treating the deployment as permanent.
