# MyBoxd release notes

## Public web release

- Removed version numbers from the project name.
- Preserved the working local MovieLens fallback installer and checksum verification.
- Added a database-agnostic MovieLens catalogue seeder for PostgreSQL deployments.
- Added a single-origin production deployment: React and FastAPI are served from the same Render service.
- Production frontend uses `/api`, avoiding cross-site authentication cookie problems.
- Added Render Blueprint configuration for the app and PostgreSQL.
- Retains the local SQLite workflow for development.
