# Accounts & billing application contract

This is the v0.5 Accounts starter. The runtime is React, FastAPI, PostgreSQL and
an optional delivery worker. The builder owns runtime manifests and this profile marker.

- `application.py` creates the API, request boundary, readiness check, private notes, and request metrics.
- `auth.py` implements signup, verification, invitations, resets, sessions and admin role management.
- `security.py` owns password hashing, cookie/session authentication, CSRF, Origin and rate checks.
- `billing.py` implements one-time Stripe Checkout and raw-body signed webhooks. It does not implement subscriptions, invoices, tax calculation or a merchant refund UI.
- `integrations.py` encrypts queued email/webhook payloads, leases deliveries, retries failures and cleans expired authentication records. Run its worker in production.
- `ops.py` exposes authenticated admin summaries and private bearer-protected monitoring endpoints.

Read these modules before extending them. Keep authentication, CSRF, ownership and
last-admin checks. Every new private route must use `security.current_user(request)`
or `security.role(request, ...)`; every record lookup/mutation must constrain `user_id`.
An administrator can manage accounts but cannot read another user's private notes.
Add new numbered SQL migrations; do not modify 001 or 002 after they have run.
`app_users` is separate from the original anonymous `notes` table; anonymous notes
are never assigned to an arbitrary user automatically.

Preview always sets `APP_ENV=preview`, `PAYMENT_MODE=off`, `ENABLE_INTEGRATIONS=false`.
Email flows return a temporary local preview link, which is never returned in production.
Do not put deployment/provider secrets in source, prompts, tests or frontend storage.
Do not change checkout to trust a browser redirect, client price, or client user ID.
Cookie session tokens stay HttpOnly; only the CSRF token lives in React memory.

For preview admin access, the operator runs `python -m app.manage create-admin
--email owner@example.com` interactively in the preview API container. Never create
a default password or automatically promote the first self-registered account.

Production configuration is outside app source. Export a validated release and follow
DEPLOY.md. Role and payment changes need behavioral tests, a human code review, and
live sandbox-provider acceptance before real customers or live charges.
