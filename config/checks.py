from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def required_env_keys_check(app_configs, **kwargs):
    errors = []
    for key in getattr(settings, 'REQUIRED_ENV_KEYS', []):
        value = getattr(settings, key, None)
        if not value or 'replace_me' in str(value) or str(value).startswith('replace-'):
            errors.append(
                Error(
                    f'{key} is required for production deployment.',
                    hint=f'Set {key} in the storefront .env file.',
                    id='tg11.E001',
                )
            )
    if getattr(settings, 'ENABLE_LIVE_SHIPPING_RATES', False):
        provider = getattr(settings, 'SHIPPING_RATE_PROVIDER', '')
        provider_key = {'easypost': 'EASYPOST_API_KEY', 'shippo': 'SHIPPO_API_TOKEN'}.get(provider)
        if not provider_key:
            errors.append(Error('Live shipping rates require SHIPPING_RATE_PROVIDER=easypost or shippo.', id='tg11.E002'))
        elif not getattr(settings, provider_key, ''):
            errors.append(Error(f'{provider_key} is required for live shipping rates.', hint=f'Set {provider_key} in .env or disable ENABLE_LIVE_SHIPPING_RATES.', id='tg11.E003'))
        for key in ['SHIP_FROM_LINE1', 'SHIP_FROM_CITY', 'SHIP_FROM_STATE', 'SHIP_FROM_POSTAL_CODE', 'SHIP_FROM_COUNTRY']:
            if not getattr(settings, key, ''):
                errors.append(Error(f'{key} is required for live shipping rates.', hint=f'Set {key} in the storefront .env file.', id='tg11.E004'))
    if getattr(settings, 'TAX_PROVIDER', 'none') == 'stripe_tax':
        if not getattr(settings, 'STRIPE_TAX_ENABLED', False):
            errors.append(Error('TAX_PROVIDER=stripe_tax requires STRIPE_TAX_ENABLED=1.', id='tg11.E005'))
        if not getattr(settings, 'STRIPE_SECRET_KEY', ''):
            errors.append(Error('STRIPE_SECRET_KEY is required for Stripe Tax.', id='tg11.E006'))
    return errors
