# TG11 Shop

Production-oriented Django ecommerce hub for `shop.tg11.org` with PostgreSQL, Docker Compose, Gunicorn, Apache reverse proxying, Stripe test-mode payments, django-allauth authentication, and a pluggable connector architecture for external marketplaces.

## Stack notes

- Django `6.0.4`
- Python `3.12`
- PostgreSQL on custom port `55432`
- Stripe Python SDK for payments and saved payment method references
- django-allauth for signup, login, and email verification
- Gunicorn behind Apache2

## Project tree

```text
.
|- accounts/
|- cart/
|- catalog/
|- checkout/
|- config/
|  |- settings/
|- connectors/
|- dashboard/
|- orders/
|- payments/
|- static/
|- templates/
|- Dockerfile
|- docker-compose.yml
|- entrypoint.sh
|- manage.py
`- requirements.txt
```

## First run

```bash
cp .env.example .env
docker compose up --build -d
```

Then create starter data:

```bash
docker compose exec web python manage.py seed_shop
```

## Update flow

```bash
git pull
docker compose up --build -d
```

## Multi-store deployment strategy

Use one deployment directory per storefront while keeping this repository as the shared codebase:

- `/var/www/bettercorporatelogowear`
- `/var/www/fortheybythem`

Each deployment gets its own `.env`, PostgreSQL database, `media/` directory, `staticfiles/` directory, Stripe keys, Apache vhost, and log units. Keep merchandising/content in the database through the dashboard/admin, and keep secrets/infra only in `.env`.

Suggested per-store differences:

```env
SITE_URL=https://bettercorporatelogowear.example
DJANGO_ALLOWED_HOSTS=bettercorporatelogowear.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://bettercorporatelogowear.example
POSTGRES_DB=bettercorporatelogowear
POSTGRES_USER=bettercorporatelogowear
DB_PORT=55433
APP_HOST=127.6.1.10
GUNICORN_BIND=127.6.1.10:8000
STRIPE_SECRET_KEY=sk_live_store_specific
STRIPE_PUBLISHABLE_KEY=pk_live_store_specific
STRIPE_WEBHOOK_SECRET=whsec_store_specific
```

Release flow stays independent: merge to the shared branch, then `git pull && docker compose up --build -d` in only the storefront directory you want to roll out. Promote to the second storefront after smoke tests and controlled checkout tests pass.

### Per-store health checks

```bash
docker compose ps
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py smoke_storefront
docker compose exec web python manage.py seed_shipping
docker compose exec web python manage.py reconcile_payments
curl -fsS https://YOUR_STORE_DOMAIN/health/
sudo journalctl -u storefront -n 100 --no-pager
sudo journalctl -u storefront-logs@web -n 100 --no-pager
sudo journalctl -u storefront-logs@db -n 100 --no-pager
```

## SMTP sanity check

Signup sends verification email immediately. If SMTP is misconfigured, signup can fail.

Run this before restarting production after `.env` email changes:

```bash
docker compose exec web python manage.py check_smtp
```

Optional live send test:

```bash
docker compose exec web python manage.py check_smtp --to your@email.tld
```

`EMAIL_HOST` must be a hostname only (for example `mail.tg11.org`), not a URL such as `https://mail.tg11.org`.

## systemd service

If you want the stack to behave like your other host-managed services, install the bundled unit at `deploy/systemd/storefront.service`.

It runs `docker compose` in the foreground under `systemd`, which means:

- `systemctl start storefront`
- `systemctl stop storefront`
- `systemctl restart storefront`
- `systemctl status storefront`
- `journalctl -u storefront -f`

all work in the usual way.

Use the templated log unit for any Docker Compose service:

```bash
sudo systemctl enable --now storefront-logs@web
sudo systemctl enable --now storefront-logs@db
sudo journalctl -u storefront-logs@web -f
sudo journalctl -u storefront-logs@db -f
```

### Install on the host

Assuming the repo lives at `/var/www/storefront`:

```bash
sudo cp /var/www/storefront/deploy/systemd/storefront.service /etc/systemd/system/storefront.service
sudo cp /var/www/storefront/deploy/systemd/storefront-logs@.service /etc/systemd/system/storefront-logs@.service
sudo cp /var/www/storefront/deploy/systemd/storefront-fulfillment.service /etc/systemd/system/storefront-fulfillment.service
sudo cp /var/www/storefront/deploy/systemd/storefront-fulfillment.timer /etc/systemd/system/storefront-fulfillment.timer
sudo systemctl daemon-reload
sudo systemctl enable storefront
sudo systemctl enable storefront-logs@web
sudo systemctl enable storefront-logs@db
sudo systemctl enable storefront-fulfillment.timer
sudo systemctl start storefront
sudo systemctl start storefront-logs@web
sudo systemctl start storefront-logs@db
sudo systemctl start storefront-fulfillment.timer
```

If your repo is not at `/var/www/storefront`, edit the `WorkingDirectory=` line first.

### Day-to-day commands

```bash
sudo systemctl restart storefront
sudo systemctl status storefront
sudo journalctl -u storefront -f
sudo systemctl status storefront-logs@web
sudo systemctl status storefront-logs@db
sudo journalctl -u storefront-logs@web -f
sudo journalctl -u storefront-logs@db -f
sudo systemctl status storefront-fulfillment.timer
sudo journalctl -u storefront-fulfillment -f
```

For image/config changes after a `git pull`, a `restart` is enough because `ExecStart` runs:

```text
docker compose up --build --remove-orphans
```

## Deployment assumptions

This Compose file uses `network_mode: host` on Linux so Gunicorn can bind directly to `127.6.0.10:8000` and PostgreSQL can stay loopback-only on `127.6.0.11:55432`. That keeps the web app off `0.0.0.0` and avoids public database exposure.

If you prefer Docker bridge networking instead, switch `network_mode: host` to a normal bridge network and publish the web port as `127.6.0.10:8000:8000`.

## Apache reverse proxy example

```apache
<VirtualHost *:80>
    ServerName shop.tg11.org
    Redirect permanent / https://shop.tg11.org/
</VirtualHost>

<VirtualHost *:443>
    ServerName shop.tg11.org

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/shop.tg11.org/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/shop.tg11.org/privkey.pem

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://127.6.0.10:8000/
    ProxyPassReverse / http://127.6.0.10:8000/
</VirtualHost>
```

Enable required modules:

```bash
a2enmod proxy proxy_http headers ssl rewrite
systemctl reload apache2
```

## Environment highlights

- `DJANGO_ALLOWED_HOSTS=shop.tg11.org`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://shop.tg11.org`
- `DB_HOST=127.6.0.11`
- `DB_PORT=55432`
- `GUNICORN_BIND=127.6.0.10:8000`
- `STRIPE_ACCOUNT_ID`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- `ENABLE_PROMOTIONS`, `ENABLE_SHIPPING_ENGINE`
- `ENABLE_LIVE_SHIPPING_RATES`, `SHIPPING_RATE_PROVIDER`, `EASYPOST_API_KEY`, `SHIPPO_API_TOKEN`
- `SHIP_FROM_NAME`, `SHIP_FROM_LINE1`, `SHIP_FROM_CITY`, `SHIP_FROM_STATE`, `SHIP_FROM_POSTAL_CODE`, `SHIP_FROM_COUNTRY`
- `TAX_PROVIDER`, `STRIPE_TAX_ENABLED`, `STRIPE_TAX_BEHAVIOR`
- `POPCUSTOMS_API_KEY`, `POPCUSTOMS_ORDERS_ENDPOINT`, `POPCUSTOMS_LISTINGS_ENDPOINT`, `POPCUSTOMS_INVENTORY_ENDPOINT`, `POPCUSTOMS_API_HEADER`
- `ETSY_API_KEY`, `ETSY_SHARED_SECRET`
- `FULFILLMENT_EMAIL_RECIPIENTS`

## Vendor listing sync

Import remote listings into local products:

```bash
python manage.py sync_channel --provider etsy --import-listings
python manage.py sync_channel --provider popcustoms --import-listings
```

Push local listing links and stock counts back to the vendor:

```bash
python manage.py sync_channel --provider etsy --push-listings --push-inventory
python manage.py sync_channel --provider popcustoms --push-listings --push-inventory
```

Etsy listing sync requires the channel account to have an OAuth access token with listing scopes, plus config JSON values for `taxonomy_id` and `shipping_profile_id`. PopCustoms listing sync uses the configurable `POPCUSTOMS_LISTINGS_ENDPOINT` and optional `POPCUSTOMS_INVENTORY_ENDPOINT` because the order webhook endpoint is separate from catalog management.

## Stripe integration

- Checkout uses hosted Stripe Checkout in payment mode.
- Saved payment methods use Stripe customer and payment method references only.
- Local records are synced from Stripe via webhook callbacks or explicit refresh in the account dashboard.
- No raw card data is stored in Django.
- This project is wired for the `tg11.org` Stripe account in `.env`; replace the Stripe key placeholders with test or live keys from the matching Dashboard account before taking payments.

### Recommended webhook

Point Stripe test-mode webhooks to:

```text
https://shop.tg11.org/payments/webhooks/stripe/
```

Suggested events:

- `checkout.session.completed`
- `payment_intent.payment_failed`

## Connector architecture

- `connectors.base.BaseConnector` defines the contract.
- `connectors.etsy.EtsyConnector` contains a real API scaffold for pulling Etsy receipts.
- `connectors.popcustoms.PopCustomsConnector` can submit queued orders to the configured PopCustoms order endpoint.
- `ChannelAccount`, `ExternalListing`, `ExternalOrder`, and `SyncJob` keep marketplace concerns isolated from core storefront models.

For Etsy, store the app keystring and shared secret in `.env`. The channel account can use the numeric Etsy shop ID as `account_identifier`, or include it in config JSON as `{"shop_id": "..."}`. OAuth access and refresh tokens are still required before private Etsy shop/order API calls can run.

## Local products

Create local inventory from `/dashboard/manage/products/new/` by setting the fulfillment source to `Internal` and entering the variant stock quantity. Cart and checkout prevent customers from buying more than the available variant stock.

Enable custom requests on products that need customer input, such as resin dice colors, gift notes, or made-to-order details. Products without custom requests enabled keep the normal product page without an extra field.

When Stripe marks an internal order as paid, TG11 Shop decrements the variant stock and sends a fulfillment email to `FULFILLMENT_EMAIL_RECIPIENTS` with the order number, items, customer email, shipping address, and notes. Multiple Stripe confirmations for the same order do not decrement stock or send the email again.

## Pricing, coupons, and shipping

Pricing is centralized in `pricing.services.calculate_cart_totals()`. Cart pages, checkout order creation, order audit snapshots, and Stripe Checkout line-item generation use the same totals path so discounts, shipping, tax, and grand totals stay consistent.

Models in the `pricing` app cover:

- `Promotion` and `PromotionScope` for percent-off, fixed-off, sale-price placeholders, and free-shipping rules scoped to products, SKUs, pages, or global.
- `Coupon` and `CouponRedemption` for codes, active windows, usage caps, first-order-only rules, and audit history.
- `ShippingZone`, `ShippingMethod`, and `ShippingRateRule` for rule-based domestic/international fallback rates.

Seed baseline fallback rates with:

```bash
docker compose exec web python manage.py seed_shipping
```

Daily reconciliation can be run manually or from a timer:

```bash
docker compose exec web python manage.py reconcile_payments
```

Carrier APIs are behind the shipping quote service. Phase 1 uses in-app fallback rates. Phase 2 is implemented with provider adapters for EasyPost and Shippo:

```env
ENABLE_LIVE_SHIPPING_RATES=1
SHIPPING_RATE_PROVIDER=easypost
EASYPOST_API_KEY=...
```

or:

```env
ENABLE_LIVE_SHIPPING_RATES=1
SHIPPING_RATE_PROVIDER=shippo
SHIPPO_API_TOKEN=...
```

Live rates require the ship-from fields in `.env`. If the carrier provider fails and `ENABLE_SHIPPING_FALLBACK_RATES=1`, checkout falls back to active `ShippingRateRule` records and logs/sends an ops alert if `PRICING_ALERT_EMAILS_ENABLED=1`. External-source carts can also use supplier-aware fallback timing and pricing, for example `POPCUSTOMS_FALLBACK_DOMESTIC_MIN_DAYS=7`, `POPCUSTOMS_FALLBACK_DOMESTIC_MAX_DAYS=21`, and `POPCUSTOMS_FALLBACK_DOMESTIC_SHIPPING_AMOUNT=8.95` to show a 1-3 week PopCustoms window instead of a generic 3-7 day fallback.

Provider webhook endpoints:

```text
https://shop.tg11.org/webhooks/easypost/
https://shop.tg11.org/webhooks/shippo/
```

If your provider gives a hosted webhook relay URL such as WeSupply, store that URL in `.env` as `EASYPOST_WEBHOOK_URL` for reference and put the shared secret in `EASYPOST_WEBHOOK_SECRET`. Incoming webhook payloads are recorded in `ShippingWebhookEvent`; when a payload includes an order number or a matching external shipment/rate ID plus tracking data, TG11 Shop creates a fulfillment update.

Stripe Tax can be enabled with:

```env
TAX_PROVIDER=stripe_tax
STRIPE_TAX_ENABLED=1
STRIPE_TAX_BEHAVIOR=exclusive
```

Tax calculations run inside the central pricing engine before the Stripe Checkout Session is created. The order stores `tax_total`, `tax_snapshot`, and the complete `pricing_snapshot` for reconciliation and refunds.

External products can also enforce a retail floor from supplier cost by setting `AUTO_ENFORCE_EXTERNAL_RETAIL_FLOOR=1`. The current floor uses `EXTERNAL_RETAIL_MARKUP_PERCENT`, `EXTERNAL_RETAIL_ROUND_TO`, `EXTERNAL_RETAIL_PRICE_ENDING`, and source overhead such as `POPCUSTOMS_PRICING_OVERHEAD`, so a supplier cost can be rolled into the displayed product price instead of appearing only at checkout.

### Incident runbooks

Carrier outage: disable real-time provider adapters, keep `ENABLE_SHIPPING_ENGINE=1`, and rely on fallback `ShippingRateRule` records.

Bad coupon or sale rule: disable the `Coupon` or `Promotion` in admin, then run `reconcile_payments` and inspect affected orders by `discount_snapshot`.

Wrong shipping/tax total: disable the relevant `ShippingRateRule` or promotion, create a test cart in the dashboard/admin, and compare order `pricing_snapshot` against the payment record before re-enabling.

### Fulfillment jobs

Paid external orders create `SyncJob` records. Submit pending jobs manually with:

```bash
docker compose exec web python manage.py process_fulfillment_jobs --provider popcustoms
```

PopCustoms channel setup can use `TG11` as the account identifier while the API key and order endpoint remain in `.env`.

To process queued fulfillment jobs automatically, install and start `deploy/systemd/storefront-fulfillment.timer`.

## Seed data

`python manage.py seed_shop` creates:

- a starter admin account
- a native product
- an Etsy-linked product
- a demo Etsy channel account and external listing

## Tests

Run the targeted suite with:

```bash
python manage.py test accounts cart checkout
```

## Media and persistence

- PostgreSQL data lives in the `postgres_data` Docker volume.
- Media uploads persist in the project `./media` directory mounted into the container.

## Going live checklist

1. Replace the default secret key and database password.
2. Set real SMTP settings.
3. Add live Stripe keys and webhook signing secret.
4. Confirm Apache is forwarding `X-Forwarded-Proto https`.
5. Run `docker compose exec web python manage.py createsuperuser` if you want a non-seeded admin.
6. Test PopCustoms fulfillment with a low-risk order before enabling automatic production submissions.
