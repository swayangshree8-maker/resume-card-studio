# Private website control backend

This Flask service adds a mobile admin panel at `webcontrol/control.html`, editable announcement/title settings, and anonymous page-view totals. It does not receive or store resume, card, rent, name, email, or password data from the Studio. The admin page is public static HTML; access is protected by the backend login, a six-hour signed bearer token, strict origin allowlisting, and a five-failure login throttle.

## Run locally

1. Install Python 3.10+ and run `py -m pip install -r requirements.txt` from the project folder.
2. Generate a strong password hash with `py -m webcontrol.app hash-password`; use a unique password with at least 14 characters. Keep the printed hash private.
3. Set `ADMIN_USERNAME`, either `ADMIN_PASSWORD_HASH` or `ADMIN_PASSWORD`, and a random `TOKEN_SECRET` in the server environment. `TOKEN_SECRET` must be a new random value of at least 32 bytes. Do not commit `.env` or secrets.
4. Set `CORS_ALLOW_ORIGIN` to the exact website origin, such as `https://swayangshree8-maker.github.io`. Start with `py -m webcontrol.app`.

## Deploy on AWS

AWS deployment files are in the `aws` directory. Follow `aws/README.md`. AWS requires an account, and its Free account plan is time-limited; plan for the server to stop when that plan expires.

The local server binds to `127.0.0.1`; it is not exposed to the public internet. For mobile access from anywhere, deploy this backend to a Python host that provides HTTPS and persistent storage. Set its private environment variables there. A SQLite database on an ephemeral host filesystem will be lost when the instance is replaced, so configure a persistent disk or a managed database before relying on saved settings/analytics.

## Connect the GitHub Pages site

Set `window.RCS_API_BASE` in `webcontrol/webcontrol-config.js` to the public HTTPS API origin (no trailing slash), add that exact origin to the `connect-src` CSP in `index.html` and `control.html`, and set `CORS_ALLOW_ORIGIN` on the backend to the exact GitHub Pages origin. Never put the admin password, `TOKEN_SECRET`, or any private API key in the site files.

## Data and privacy

Only a site title, an optional short public announcement, and aggregate route page views are stored. Page views are retained for up to 400 days. No browser resume/card data or visitor identifiers are sent. Protect the hosting account and database; use HTTPS and keep a private backup of the database.
