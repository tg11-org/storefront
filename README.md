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
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`

## Stripe integration

- Checkout uses hosted Stripe Checkout in payment mode.
- Saved payment methods use Stripe customer and payment method references only.
- Local records are synced from Stripe via webhook callbacks or explicit refresh in the account dashboard.
- No raw card data is stored in Django.

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
- `connectors.popcustoms.PopCustomsConnector` is an explicit TODO placeholder.
- `ChannelAccount`, `ExternalListing`, `ExternalOrder`, and `SyncJob` keep marketplace concerns isolated from core storefront models.

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
6. Finish PopCustoms API work before enabling that connector in production.
