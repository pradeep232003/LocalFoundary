# Your Accounts & billing app

React + FastAPI + PostgreSQL with login, email verification, password reset,
invitations, admin/member/viewer roles, private notes, one-time Stripe Checkout,
transactional email, outgoing webhooks and an operations dashboard.

Start the preview in Local Foundry. Create an account, open the preview verification
link, then sign in. Previews have no outbound network or real payments.

To create a preview administrator, run from this source directory:

```sh
docker compose -f compose.json exec api python -m app.manage create-admin --email owner@example.com
```

If you started the preview through the builder, use its runtime file instead:

```sh
docker compose -f ../runtime.json exec api python -m app.manage create-admin --email owner@example.com
```

The command asks for a password without displaying or storing it in shell history.
For standalone source exports, first build/start with `docker compose -f compose.json up -d --build --wait`.
For a production-ready build configuration, use the builder's **Release** export.
See `backend/PLATFORM.md` for the application contract and safe extension points.

## Known trade-off: account-keyed login throttling

Failed sign-ins are rate limited per email address (8 per 15 minutes) as well as
per client address (80). The address limit means anyone who knows a user's email
can lock that user out of sign-in for the window by submitting bad passwords,
which is the usual cost of throttling credential stuffing on a named account.
It is deliberate rather than overlooked. If lockout matters more than stuffing for
your product, replace the address bucket in `security.rate_limit` with a stepped
delay or a challenge, and extend the tests in `tests/test_accounts.py` before you
change the numbers.
