# Security

Do not put secrets in the repository. `TMDB_API_KEY`, production database credentials, and hosting secrets belong in deployment environment variables.

MyBoxd uses HTTP-only session cookies, PBKDF2 password hashing, CSRF tokens for authenticated mutations, strict CORS allow-lists, ORM parameterization, file-size limits, in-memory ZIP parsing with traversal/expanded-size checks, user ownership filtering, and production-friendly error handling/security headers.

For a public deployment, serve the frontend and API over HTTPS and set `ENVIRONMENT=production`. Prefer a same-site frontend/API domain pair such as `myboxd.app` and `api.myboxd.app`. Rotate leaked credentials immediately and report security issues privately rather than opening a public issue containing exploit details or personal data.
