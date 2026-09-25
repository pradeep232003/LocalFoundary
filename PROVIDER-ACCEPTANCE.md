# Real provider acceptance

Disconnected previews cannot exercise cloud APIs, public email or Stripe Checkout.
These gates run separately on an HTTPS test deployment with your provider test
accounts. Keep the everyday laptop preview disconnected.

1. Deploy a separate test hostname/database using DEPLOY.md. Use
   `APP_ENV=production`, `PAYMENT_MODE=test`, `ENABLE_INTEGRATIONS=true`, your
   Stripe **test** key and webhook secret, test product catalog, and Resend sender.
   Temporarily allow test signup. Provider-mode staging is separate from the
   completely isolated `ops.py stage` smoke environment.
2. Run `.venv/bin/python scripts/provider-acceptance.py --origin
   https://YOUR-TEST-HOST --product YOUR-CATALOG-ID`. The command asks privately
   for a new disposable account password and the link from the actual email.
   It creates a real test checkout, verifies idempotent retry, and waits for the
   signed provider webhook to produce a paid order. Complete the hosted checkout
   using [Stripe's test payment details](https://docs.stripe.com/testing).
3. Check the configured outgoing receiver for that report's `order_id`. Verify
   the timestamped HMAC using the receiver's shared secret and confirm the worker
   records successful delivery in Operations. Exercise a receiver failure and
   recovery. A delivered HTTP response alone does not prove receiver processing.
   This gate stays explicitly blocked in the automated report until you record
   that independent receiver evidence.
4. From the Stripe test dashboard, retry the paid event and issue a test refund.
   Confirm exactly one purchase/fulfillment and the correct refund status. Run a
   delayed/failed test payment if your selected payment methods support it.
5. Run a deliberate outage/recovery against the independent external monitor,
   inspect backup scheduler logs, and perform a deployment-host restore drill.
   Keep the resulting reports with your release review.

The script refuses live payment mode and never saves passwords, verification
tokens, cookies, provider keys, or checkout URLs in its JSON report. It does send
one real email and leaves a disposable test account/order in the staging database.
Remove test resources deliberately after recording evidence. No real provider
account or endpoint was supplied during this build, so these gates were not run.
