# Put MyBoxd on GitHub

This repository is designed to be committed **without** your private data. The `.gitignore` excludes `.env`, your SQLite database, MovieLens downloads, virtual environments, Node modules, build output, and Letterboxd exports.

## 1. Create the repository on GitHub

On GitHub, create a new repository named **MyBoxd**.

Recommended settings:

- Visibility: **Public** if this is for your university portfolio, otherwise Private.
- Do **not** add a README, `.gitignore`, or license on GitHub because this folder already contains them.

## 2. Upload with Git from Terminal

Open Terminal in this `MyBoxd` folder and run:

```bash
git init
git add .
git commit -m "Initial MyBoxd release"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/MyBoxd.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your actual GitHub username.

If GitHub asks you to authenticate, follow the browser sign-in prompt from Git/GitHub CLI or use GitHub Desktop. Do not paste your TMDB key into GitHub.

## 3. Verify the repository

On GitHub, confirm that these **are present**:

- `README.md`
- `backend/`
- `frontend/`
- `setup_local.sh`
- `start_local.sh`
- `.github/workflows/ci.yml`

And confirm these **are not present**:

- `.env`
- `backend/myboxd.db`
- `backend/data/ml-32m.zip`
- `frontend/node_modules/`
- any Letterboxd export ZIP

GitHub Actions should automatically run the backend and frontend checks after the first push.

## 4. How someone installs MyBoxd from GitHub

```bash
git clone https://github.com/YOUR-USERNAME/MyBoxd.git
cd MyBoxd
bash setup_local.sh
```

The first setup installs dependencies and downloads MovieLens 32M. If the official GroupLens HTTPS download cannot be used, the setup automatically falls back to a mirror and verifies every MovieLens CSV against the published checksums before importing it.

Then put a TMDB API key in the generated root `.env` file:

```text
TMDB_API_KEY=your_key_here
```

Start the app:

```bash
bash start_local.sh
```

Open `http://localhost:5173`.

## Security

Never commit a real `.env` file, TMDB key, user database, Letterboxd export, or MovieLens archive. If a key has ever been exposed publicly, rotate it before publishing the repository.
