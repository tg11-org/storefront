from __future__ import annotations

import requests
from django.conf import settings

from .base import BaseConnector


class PopCustomsConnector(BaseConnector):
    provider = 'popcustoms'

    def _config_value(self, key: str, setting_name: str, default: str = '') -> str:
        return self.channel_account.config.get(key) or getattr(settings, setting_name, default)

    @property
    def orders_endpoint(self) -> str:
        return self._config_value('orders_endpoint', 'POPCUSTOMS_ORDERS_ENDPOINT')

    @property
    def api_key(self) -> str:
        return self._config_value('api_key', 'POPCUSTOMS_API_KEY')

    @property
    def api_header(self) -> str:
        return self._config_value('api_header', 'POPCUSTOMS_API_HEADER', 'X-API-Key')

    @property
    def api_value_prefix(self) -> str:
        return self._config_value('api_value_prefix', 'POPCUSTOMS_API_VALUE_PREFIX')

    def _headers(self) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers[self.api_header] = f'{self.api_value_prefix}{self.api_key}'
        return headers

    def validate_configuration(self) -> None:
        missing = []
        if not self.orders_endpoint:
            missing.append('orders_endpoint')
        if not self.api_key:
            missing.append('api_key')
        if missing:
            raise ValueError(f'PopCustoms connector missing configuration: {", ".join(missing)}')

    def pull_orders(self) -> list[dict]:
        raise NotImplementedError('TODO: Implement PopCustoms order import.')

    def upsert_listing(self, listing) -> dict:
        raise NotImplementedError('TODO: Implement PopCustoms listing sync.')

    def push_inventory(self, listing, quantity: int) -> dict:
        raise NotImplementedError('TODO: Implement PopCustoms inventory sync.')

    def submit_order(self, order, items: list[dict]) -> dict:
        self.validate_configuration()
        payload = {
            'order': {
                'number': order.number,
                'email': order.email,
                'total': str(order.grand_total),
                'currency': settings.STRIPE_CURRENCY,
                'shipping_address': order.shipping_address,
                'billing_address': order.billing_address,
                'notes': order.notes,
            },
            'line_items': [
                {
                    'sku': item.get('sku', ''),
                    'name': item.get('title', ''),
                    'quantity': item.get('quantity', 1),
                    'unit_price': item.get('unit_price', ''),
                    'external_listing_id': item.get('external_listing_id', ''),
                    'external_product_id': item.get('external_product_id', ''),
                    'external_variant_id': item.get('external_variant_id', ''),
                    'custom_request': item.get('custom_request', ''),
                }
                for item in items
            ],
            'metadata': {
                'source': 'tg11-shop',
                'stripe_payment_intent_id': order.stripe_payment_intent_id,
            },
        }
        response = requests.post(self.orders_endpoint, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {'raw': response.text}
        return {'status': 'submitted', 'provider': self.provider, 'response': response_payload}
