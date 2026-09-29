# Your generated app

React + FastAPI + PostgreSQL. Source is saved independently of the Local Foundry builder.

Install Docker Desktop, then run:

```bash
docker compose -f compose.json up -d --build --wait
open http://127.0.0.1:5173
```

Stop with `docker compose -f compose.json down`. This keeps PostgreSQL data.
The preview database uses a development-only password and has no host port.
Do not use this configuration as a public production deployment.

Source lives in `frontend/src` and `backend/app`. Vite proxies `/api` to FastAPI.
The frontend and backend run in non-root containers with read-only source mounts.
The internal network blocks outbound container traffic. The preview has a browser
content policy that permits local assets and its own API.

When changing database structure, add explicit migrations. Source rollback does
not roll back PostgreSQL data. Back up data separately with `pg_dump`.

The starter fixes its dependencies. To add a package, review and edit the
dependency manifest yourself, update its lock file, and rebuild the images.
