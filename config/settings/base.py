from __future__ import annotations

import os
import sys
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parents[2]


def load_env_file() -> None:
    if 'test' in sys.argv:
        return
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(name, value)


load_env_file()


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]


def unique_values(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def host_without_port(value: str | None) -> str:
    if not value:
        return ''
    host = value.strip()
    if '://' in host:
        host = host.split('://', 1)[1]
    host = host.split('/', 1)[0]
    if host.startswith('['):
        return host.strip('[]')
    return host.rsplit(':', 1)[0] if ':' in host else host


SECRET_KEY = env('DJANGO_SECRET_KEY', 'django-insecure-change-me')
DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = unique_values(
    env_list('DJANGO_ALLOWED_HOSTS', ['shop.tg11.org', 'localhost', '127.0.0.1'])
    + [
        host_without_port(env('APP_HOST', '127.6.0.10')),
        host_without_port(env('GUNICORN_BIND', '127.6.0.10:8000')),
    ]
)
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', ['https://shop.tg11.org'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',
    'allauth',
    'allauth.account',
    'accounts',
    'catalog',
    'cart',
    'checkout',
    'orders',
    'payments',
    'pricing',
    'connectors',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cart.context_processors.cart_summary',
                'catalog.context_processors.store_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = env('DB_ENGINE', 'django.db.backends.sqlite3')
if DB_ENGINE == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': env('POSTGRES_DB', 'tg11_shop'),
            'USER': env('POSTGRES_USER', 'tg11_shop'),
            'PASSWORD': env('POSTGRES_PASSWORD', 'change-me'),
            'HOST': env('DB_HOST', '127.6.0.11'),
            'PORT': env('DB_PORT', '55432'),
            'CONN_MAX_AGE': int(env('DB_CONN_MAX_AGE', '60')),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('DJANGO_TIME_ZONE', 'America/New_York')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
SERVE_MEDIA = env_bool('SERVE_MEDIA', True)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.CustomUser'
SITE_ID = int(env('SITE_ID', '1'))
LOGIN_REDIRECT_URL = 'accounts:dashboard'
LOGOUT_REDIRECT_URL = 'catalog:home'
LOGIN_URL = 'account_login'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'first_name', 'last_name', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[TG11 Shop] '
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_SESSION_REMEMBER = True

EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'TG11 Shop <no-reply@shop.tg11.org>')
SERVER_EMAIL = env('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(env('EMAIL_PORT', '25'))
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
FULFILLMENT_EMAIL_RECIPIENTS = env_list('FULFILLMENT_EMAIL_RECIPIENTS', [SERVER_EMAIL])

STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', '')
STRIPE_CURRENCY = env('STRIPE_CURRENCY', 'usd')
STRIPE_ACCOUNT_ID = env('STRIPE_ACCOUNT_ID', '')
PAYMENT_PROVIDER = env('PAYMENT_PROVIDER', 'stripe')
FOXPAY_API_KEY = env('FOXPAY_API_KEY', '')
FOXPAY_WEBHOOK_SECRET = env('FOXPAY_WEBHOOK_SECRET', '')
FOXPAY_CHECKOUT_ENDPOINT = env('FOXPAY_CHECKOUT_ENDPOINT', '')
POPCUSTOMS_API_KEY = env('POPCUSTOMS_API_KEY', '')
POPCUSTOMS_ORDERS_ENDPOINT = env('POPCUSTOMS_ORDERS_ENDPOINT', '')
POPCUSTOMS_LISTINGS_ENDPOINT = env('POPCUSTOMS_LISTINGS_ENDPOINT', '')
POPCUSTOMS_INVENTORY_ENDPOINT = env('POPCUSTOMS_INVENTORY_ENDPOINT', '')
POPCUSTOMS_API_HEADER = env('POPCUSTOMS_API_HEADER', 'X-API-Key')
POPCUSTOMS_API_VALUE_PREFIX = env('POPCUSTOMS_API_VALUE_PREFIX', '')
ETSY_API_KEY = env('ETSY_API_KEY', '')
ETSY_SHARED_SECRET = env('ETSY_SHARED_SECRET', '')
SITE_URL = env('SITE_URL', 'https://shop.tg11.org')

REQUIRED_ENV_KEYS = env_list(
    'REQUIRED_ENV_KEYS',
    [
        'SITE_URL',
        'STRIPE_SECRET_KEY',
        'STRIPE_PUBLISHABLE_KEY',
        'STRIPE_WEBHOOK_SECRET',
        'DEFAULT_FROM_EMAIL',
        'EMAIL_BACKEND',
    ],
)
ENABLE_PROMOTIONS = env_bool('ENABLE_PROMOTIONS', True)
ENABLE_SHIPPING_ENGINE = env_bool('ENABLE_SHIPPING_ENGINE', True)
ENABLE_LIVE_SHIPPING_RATES = env_bool('ENABLE_LIVE_SHIPPING_RATES', False)
ENABLE_SHIPPING_FALLBACK_RATES = env_bool('ENABLE_SHIPPING_FALLBACK_RATES', True)
INCLUDE_FALLBACK_WITH_LIVE_RATES = env_bool('INCLUDE_FALLBACK_WITH_LIVE_RATES', False)
ENABLE_EMERGENCY_SHIPPING_FALLBACK = env_bool('ENABLE_EMERGENCY_SHIPPING_FALLBACK', True)
EMERGENCY_DOMESTIC_SHIPPING_AMOUNT = env('EMERGENCY_DOMESTIC_SHIPPING_AMOUNT', '6.95')
EMERGENCY_INTERNATIONAL_SHIPPING_AMOUNT = env('EMERGENCY_INTERNATIONAL_SHIPPING_AMOUNT', '24.95')
POPCUSTOMS_FALLBACK_DOMESTIC_SHIPPING_AMOUNT = env('POPCUSTOMS_FALLBACK_DOMESTIC_SHIPPING_AMOUNT', '0.00')
POPCUSTOMS_FALLBACK_DOMESTIC_MIN_DAYS = int(env('POPCUSTOMS_FALLBACK_DOMESTIC_MIN_DAYS', '7'))
POPCUSTOMS_FALLBACK_DOMESTIC_MAX_DAYS = int(env('POPCUSTOMS_FALLBACK_DOMESTIC_MAX_DAYS', '21'))
POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_AMOUNT = env('POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_AMOUNT', '12.95')
POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_MIN_DAYS = int(env('POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_MIN_DAYS', '3'))
POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_MAX_DAYS = int(env('POPCUSTOMS_FALLBACK_DOMESTIC_EXPRESS_MAX_DAYS', '7'))
POPCUSTOMS_FALLBACK_INTERNATIONAL_SHIPPING_AMOUNT = env('POPCUSTOMS_FALLBACK_INTERNATIONAL_SHIPPING_AMOUNT', '24.95')
POPCUSTOMS_FALLBACK_INTERNATIONAL_MIN_DAYS = int(env('POPCUSTOMS_FALLBACK_INTERNATIONAL_MIN_DAYS', '10'))
POPCUSTOMS_FALLBACK_INTERNATIONAL_MAX_DAYS = int(env('POPCUSTOMS_FALLBACK_INTERNATIONAL_MAX_DAYS', '28'))
POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_AMOUNT = env('POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_AMOUNT', '')
POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_MIN_DAYS = int(env('POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_MIN_DAYS', '0'))
POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_MAX_DAYS = int(env('POPCUSTOMS_FALLBACK_INTERNATIONAL_EXPRESS_MAX_DAYS', '0'))
POPCUSTOMS_PRICING_OVERHEAD = env('POPCUSTOMS_PRICING_OVERHEAD', '0.00')
AUTO_ENFORCE_EXTERNAL_RETAIL_FLOOR = env_bool('AUTO_ENFORCE_EXTERNAL_RETAIL_FLOOR', True)
EXTERNAL_RETAIL_MARKUP_PERCENT = env('EXTERNAL_RETAIL_MARKUP_PERCENT', '35')
EXTERNAL_RETAIL_ROUND_TO = env('EXTERNAL_RETAIL_ROUND_TO', '1.00')
EXTERNAL_RETAIL_PRICE_ENDING = env('EXTERNAL_RETAIL_PRICE_ENDING', '0.99')
SHIPPING_RATE_PROVIDER = env('SHIPPING_RATE_PROVIDER', 'rules')
SHIPPING_PROVIDER_TIMEOUT_SECONDS = int(env('SHIPPING_PROVIDER_TIMEOUT_SECONDS', '8'))
LIVE_SHIPPING_DEFAULT_DAYS = int(env('LIVE_SHIPPING_DEFAULT_DAYS', '5'))
EASYPOST_API_KEY = env('EASYPOST_API_KEY', '')
EASYPOST_API_URL = env('EASYPOST_API_URL', 'https://api.easypost.com/v2')
EASYPOST_TRACKING_URL = env('EASYPOST_TRACKING_URL', '')
EASYPOST_WEBHOOK_URL = env('EASYPOST_WEBHOOK_URL', '')
EASYPOST_WEBHOOK_SECRET = env('EASYPOST_WEBHOOK_SECRET', '')
SHIPPO_API_TOKEN = env('SHIPPO_API_TOKEN', '')
SHIPPO_API_URL = env('SHIPPO_API_URL', 'https://api.goshippo.com')
SHIPPO_WEBHOOK_URL = env('SHIPPO_WEBHOOK_URL', '')
SHIPPO_WEBHOOK_SECRET = env('SHIPPO_WEBHOOK_SECRET', '')
SHIP_FROM_NAME = env('SHIP_FROM_NAME', 'TG11 Shop')
SHIP_FROM_COMPANY = env('SHIP_FROM_COMPANY', 'TG11 LLC')
SHIP_FROM_LINE1 = env('SHIP_FROM_LINE1', '')
SHIP_FROM_LINE2 = env('SHIP_FROM_LINE2', '')
SHIP_FROM_CITY = env('SHIP_FROM_CITY', '')
SHIP_FROM_STATE = env('SHIP_FROM_STATE', '')
SHIP_FROM_POSTAL_CODE = env('SHIP_FROM_POSTAL_CODE', '')
SHIP_FROM_COUNTRY = env('SHIP_FROM_COUNTRY', 'US')
SHIP_FROM_PHONE = env('SHIP_FROM_PHONE', '')
SHIP_FROM_EMAIL = env('SHIP_FROM_EMAIL', SERVER_EMAIL)
TAX_PROVIDER = env('TAX_PROVIDER', 'none')
TAX_PROVIDER_REQUIRED = env_bool('TAX_PROVIDER_REQUIRED', False)
STRIPE_TAX_ENABLED = env_bool('STRIPE_TAX_ENABLED', False)
STRIPE_TAX_BEHAVIOR = env('STRIPE_TAX_BEHAVIOR', 'exclusive')
PRICING_ALERT_EMAILS_ENABLED = env_bool('PRICING_ALERT_EMAILS_ENABLED', False)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = int(env('SECURE_HSTS_SECONDS', '31536000' if not DEBUG else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', 'INFO')},
}

SENTRY_DSN = env('SENTRY_DSN', '')
SENTRY_ENVIRONMENT = env('SENTRY_ENVIRONMENT', 'production' if not DEBUG else 'development')
SENTRY_RELEASE = env('SENTRY_RELEASE', '')
SENTRY_TRACES_SAMPLE_RATE = float(env('SENTRY_TRACES_SAMPLE_RATE', '0.0'))
SENTRY_PROFILES_SAMPLE_RATE = float(env('SENTRY_PROFILES_SAMPLE_RATE', '0.0'))
SENTRY_SEND_DEFAULT_PII = env_bool('SENTRY_SEND_DEFAULT_PII', False)

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            environment=SENTRY_ENVIRONMENT,
            release=SENTRY_RELEASE or None,
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
            send_default_pii=SENTRY_SEND_DEFAULT_PII,
        )
    except ImportError:
        logging.getLogger(__name__).warning('SENTRY_DSN is set but sentry-sdk is not installed.')
