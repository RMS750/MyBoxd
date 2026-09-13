# MyBoxd Beta Privacy Notice

MyBoxd is an independent portfolio/beta application for analyzing Letterboxd exports. It is not affiliated with Letterboxd or TMDB.

## What is stored

For registered users MyBoxd stores the account email, a one-way password hash, normalized movie interactions derived from the uploaded Letterboxd export, recommendation preferences, import summaries, and generated model/evaluation records. Global public movie metadata obtained from TMDB is cached separately and may be reused between users.

The raw Letterboxd upload is processed in memory by the API and is not intentionally retained as a public or permanent uploaded file. Friend-comparison exports are parsed for the comparison request and are not persisted as another account.

## Why it is stored

Private viewing/rating history is used to build the user's taste profile, rating predictor, recommendation rankings, statistics, watchlist ranking, Taste DNA, and evaluation results.

## User controls

Settings provides controls to delete imported private data while retaining the account, or to permanently delete the account. Deleting private data does not remove reusable public TMDB metadata that contains no user's Letterboxd history.

## Security model

Passwords are salted and hashed with PBKDF2-HMAC-SHA256. Authentication uses random server-side sessions referenced by HTTP-only cookies. Mutating authenticated API calls also require a per-session CSRF token. User-owned database queries are scoped by authenticated user ID.

## Third parties

When TMDB is configured, MyBoxd sends movie search/discovery/detail requests to TMDB to obtain public metadata. MyBoxd does not send a user's password or raw Letterboxd CSV to TMDB.

This is a beta privacy notice, not a claim of regulatory certification. A production operator should add jurisdiction-appropriate terms, retention periods, contact details, and incident procedures before operating MyBoxd commercially.
