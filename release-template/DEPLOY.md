# Deploy your application

The release contains the validated source, build scripts, and runtime configuration. It creates no cloud resources and includes no accounts, passwords, or preview data. Public deployment files are included for the Accounts & billing profile. Port existing anonymous applications into that profile and review their authorization rules first.

## 1. Build and check locally

On the Mac with approved runtime images cached:

```sh
bash build-release.sh
docker compose up -d --wait
```

Open `http://127.0.0.1:8080`. React is compiled; FastAPI runs without reload. A migration service runs before the API and delivery worker. This local release uses preview accounts, temporary local verification links, and disabled integrations. Use disposable preview passwords. Do not treat preview accounts as production identities.

Create an administrator interactively:

```sh
docker compose exec api python -m app.manage create-admin --email owner@example.com
```

The command asks for a password without echoing it. There is no default password, and self-registration never grants administrator access. Stop with `docker compose down`; do not add `--volumes` to a deployment you want to keep.

## 2. Prepare a public server

Use a server you control with Docker Engine and the Compose plugin, a domain pointing to its public address, and inbound TCP ports 80 and 443 available. Check both A and AAAA records. Keep PostgreSQL and the API without public ports. Public HTTPS, payments and email require Internet access; the local builder and offline previews remain independent.

Images are architecture-specific. Build on the target architecture, or explicitly test your chosen Docker platform. Transfer the release and images securely. Use `docker compose config --images` to identify web/API/Postgres images; also include the built `${RELEASE_NAME}-egress:release` image for Accounts. Use `docker image save --output release-images.tar IMAGE_TAGS` and `docker image load --input release-images.tar` on the server. Do not transfer a preview database into production unintentionally.

While connected, explicitly cache the infrastructure images:

```sh
docker pull caddy:2.11.4-alpine
docker pull prom/prometheus:v3.14.0
docker pull prom/alertmanager:v0.34.1
```

Prepare runtime settings:

```sh
python3 configure-release.py
python3 configure-deployment.py --domain app.example.com --acme-email owner@example.com
```

This writes private configuration but publishes nothing. Signup and integrations default to off. To configure email, public signup, Stripe **test mode**, and an optional outgoing webhook, use this initial command instead:

```sh
python3 configure-deployment.py --domain app.example.com --acme-email owner@example.com \
  --enable-email --allow-signup --stripe-mode test \
  --webhook-url https://receiver.example.com/events
```

Keys are requested privately in the terminal. Verify the email sender in Resend first. Keep `.env`, `.secrets/`, and database dumps out of GitHub, chat, app source, and screenshots. `.env` is mode 0600; the monitoring token is container-readable inside a mode-0700 host directory. Back up the encryption key with the database: losing it makes queued payloads unreadable. The script refuses to overwrite production settings. Edit them deliberately for later changes and restart affected services. Do not casually rotate the database password or outbox encryption key.

## 3. Payments and integrations

Payments use **one-time Stripe Checkout**, with products and amounts selected by the server. Create an active one-time Stripe Price. Add this single line to `.env`, replacing the Price ID and amount (Stripe currency minor units):

```dotenv
PRODUCT_CATALOG='{"starter":{"name":"Starter access","price_id":"price_REPLACE","amount":1900,"currency":"usd"}}'
```

Configure `https://app.example.com/api/billing/webhook` in Stripe for:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `charge.refunded`

Set the endpoint signing secret in `STRIPE_WEBHOOK_SECRET`. Secret keys, Price IDs and `PAYMENT_MODE` must belong to the same test/live environment. Webhooks validate the raw body signature and timestamp, environment, session, amount and currency. Duplicate events commit once. The browser redirect never grants access. Delayed payments stay pending until a paid event. Issue refunds through Stripe; signed events update their state here. Use an endpoint/account scoped to this application to avoid unrelated order events.

Test success, cancellation, declines, delayed payments, duplicate events and refunds before enabling live keys and `PAYMENT_MODE=live`. Initial live configuration requires an explicit typed confirmation. Subscriptions, automatic tax, invoices and an entitlement engine are outside this starter; implement and test them for your product.

Email/webhook payloads are encrypted in the database. The worker leases jobs, retries with backoff and records failures. Resend uses a stable idempotency key. Outgoing webhooks are **at least once**: receivers must verify `X-Foundry-Signature` (`t=timestamp,v1=HMAC-SHA256` over `timestamp + '.' + raw_body`), enforce a short timestamp tolerance, and deduplicate `X-Foundry-Event`. Retrieve the signing key from `.env` through a private channel when configuring your receiver. Deliveries expire after 23 hours; account links expire after 30 minutes. Request a new invitation/reset for expired links. Review queued events before changing their destination.

The API and worker stay on an internal network. Only the CONNECT proxy has outbound access to exact configured hosts on port 443. It resolves DNS, rejects private/loopback/link-local/metadata/multicast addresses, and connects to the checked IP. TLS verification stays enabled. Add new integrations through reviewed adapters and deliberate allowlist changes.

## 4. Start publicly

Use this same Compose file list for subsequent operations:

```bash
dc=(docker compose -f compose.yaml -f compose.public.yaml -f compose.online.yaml -f compose.monitoring.yaml)
"${dc[@]}" config --quiet
"${dc[@]}" up -d --wait --wait-timeout 180
"${dc[@]}" exec api python -m app.manage create-admin --email owner@example.com
```

Skip the last command if that administrator already exists. Caddy obtains and renews certificates. Check `https://app.example.com/api/health`, then sign in through HTTPS. Secure cookies do not work through HTTP loopback in production. The loopback web binding remains for local diagnostics; only Caddy exposes public ports.

Before inviting users, verify login, role permissions, email delivery, signed test payments, and cross-account record isolation. Review AI changes to these rules before every release. Access changes revoke sessions; the final active verified administrator cannot be disabled or demoted.

## 5. Monitor, back up and upgrade

The administrator's **Operations** page shows request totals, server errors, configured services, worker heartbeat, delivery attempts, alerts and audit activity. Structured API logs contain request ID, registered route, status and duration, without bodies, email links, query strings or credentials. Audit retention is 90 days; sent deliveries and alerts are retained for 30 days.

Prometheus retains 15 days / at most 2 GB of metrics. Internal bearer authentication protects `/ops/metrics`. Alertmanager sends app, worker, server-error and dead-delivery alerts to Operations. Monitoring ports are not public. **For paging during an app/server outage, configure a separate external uptime monitor and Alertmanager receiver.** The default in-app receiver can display alerts only while the app is reachable. Add external destinations with deliberate restricted egress. This deployment uses one host and database; it is not high availability.

```bash
"${dc[@]}" logs --tail 100 api worker caddy
umask 077
"${dc[@]}" exec -T db pg_dump -U app -d app -Fc > database.dump
```

Keep encrypted backups off the host and test restores separately. Preserve `.env`, keys, Compose project name and volumes when upgrading. Review migrations and back up first. Image rollback does not reverse schema changes. Before an upgrade, stop API/worker, recreate the completed migration service with `"${dc[@]}" rm -f migrate`, then start the stack so new migrations finish before the API. Retain prior images until application and restore checks pass.

Sessions use HttpOnly, Secure-in-production, SameSite=Lax cookies, a 12-hour lifetime and 30-minute idle limit. Mutations enforce Origin and CSRF. Passwords use scrypt (N=131072,r=8,p=1), with bounded concurrent hashing. Database rate limits cover account actions, checkout and record creation. Arbitrary forwarded IP headers are not trusted, so network-level limits are shared behind the reverse proxy; add a reviewed edge rate limiter for high public traffic. Production disables API docs and uses CSP, body limits and container limits. App/API/worker/proxy/database run non-root; the Caddy gateway drops capabilities and writes only its certificate/config volumes. The application database user remains the schema owner.

This foundation still requires a product-specific security review. MFA, SSO, advanced recovery, distributed abuse protection and business-specific authorization need implementation when your product requires them. Generated code can weaken controls; passing build checks is not a security audit.

## References

- [Stripe Checkout](https://docs.stripe.com/api/checkout/sessions/create), [webhooks](https://docs.stripe.com/webhooks), [idempotency](https://docs.stripe.com/api/idempotent_requests)
- [Resend email API](https://resend.com/docs/api-reference/emails/send-email), [24-hour idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [OWASP passwords](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
