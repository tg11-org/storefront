from __future__ import annotations

import requests
from django.conf import settings
from django.utils import timezone

from .base import BaseConnector


class PopCustomsConnector(BaseConnector):
    provider = 'popcustoms'

    def _config_value(self, key: str, setting_name: str, default: str = '') -> str:
        return self.channel_account.config.get(key) or getattr(settings, setting_name, default)

    @property
    def orders_endpoint(self) -> str:
        return self._config_value('orders_endpoint', 'POPCUSTOMS_ORDERS_ENDPOINT')

    @property
    def listings_endpoint(self) -> str:
        return self._config_value('listings_endpoint', 'POPCUSTOMS_LISTINGS_ENDPOINT')

    @property
    def inventory_endpoint(self) -> str:
        return self._config_value('inventory_endpoint', 'POPCUSTOMS_INVENTORY_ENDPOINT')

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

    def _listing_url(self, listing_id: str = '') -> str:
        endpoint = self.listings_endpoint.rstrip('/')
        if not endpoint:
            return ''
        detail_template = self.channel_account.config.get('listing_detail_endpoint_template', '')
        if listing_id and detail_template:
            return detail_template.format(listing_id=listing_id, product_id=listing_id)
        if listing_id:
            return f'{endpoint}/{listing_id}'
        return endpoint

    def _inventory_url(self, listing_id: str = '') -> str:
        endpoint = (self.inventory_endpoint or self.listings_endpoint).rstrip('/')
        if not endpoint:
            return ''
        inventory_template = self.channel_account.config.get('inventory_endpoint_template', '')
        if inventory_template:
            return inventory_template.format(listing_id=listing_id, product_id=listing_id)
        if listing_id:
            return f'{endpoint}/{listing_id}/inventory'
        return endpoint

    def _request_json(self, method: str, url: str, **kwargs) -> dict | list:
        response = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {'raw': response.text}

    def _listing_payload(self, listing) -> dict:
        product = listing.product
        variant = listing.variant or product.primary_variant
        if not variant:
            raise ValueError(f'{product.name} does not have a variant to sync.')
        return {
            'listing_id': listing.external_listing_id,
            'external_product_id': listing.external_product_id,
            'external_variant_id': listing.external_variant_id,
            'title': product.name,
            'description': product.description or product.short_description,
            'short_description': product.short_description,
            'product_type': product.product_type,
            'source': product.default_source,
            'is_active': product.is_active and variant.is_active,
            'sku': variant.sku,
            'variant_title': variant.title,
            'price': str(variant.price),
            'compare_at_price': str(variant.compare_at_price) if variant.compare_at_price is not None else '',
            'quantity': variant.stock_quantity,
            'weight_oz': str(variant.weight_oz),
            'dimensions_in': {
                'length': str(variant.length_in),
                'width': str(variant.width_in),
                'height': str(variant.height_in),
            },
            'origin_country': variant.origin_country,
            'hs_code': variant.hs_code,
            'supplier': {
                'price': str(variant.supplier_price) if variant.supplier_price is not None else '',
                'compare_at': str(variant.supplier_compare_at) if variant.supplier_compare_at is not None else '',
                'sale_price': str(variant.supplier_sale_price) if variant.supplier_sale_price is not None else '',
                'sale_start': variant.supplier_sale_start.isoformat() if variant.supplier_sale_start else '',
                'sale_end': variant.supplier_sale_end.isoformat() if variant.supplier_sale_end else '',
            },
            'metadata': {
                'local_product_id': product.pk,
                'local_variant_id': variant.pk,
                'channel_account': self.channel_account.account_identifier,
            },
        }

    def _coerce_listings(self, payload: dict | list) -> list[dict]:
        if isinstance(payload, list):
            return payload
        for key in ('listings', 'products', 'items', 'data', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def validate_configuration(self) -> None:
        missing = []
        if not self.api_key:
            missing.append('api_key')
        if missing:
            raise ValueError(f'PopCustoms connector missing configuration: {", ".join(missing)}')

    def validate_order_configuration(self) -> None:
        self.validate_configuration()
        if not self.orders_endpoint:
            raise ValueError('PopCustoms connector missing configuration: orders_endpoint')

    def validate_listing_configuration(self) -> None:
        self.validate_configuration()
        if not self.listings_endpoint:
            raise ValueError('PopCustoms connector missing configuration: listings_endpoint')

    def pull_orders(self) -> list[dict]:
        orders_endpoint = self.channel_account.config.get('pull_orders_endpoint', '')
        if not orders_endpoint:
            return []
        self.validate_configuration()
        payload = self._request_json('get', orders_endpoint)
        if isinstance(payload, list):
            return payload
        for key in ('orders', 'data', 'results', 'items'):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def pull_listings(self) -> list[dict]:
        self.validate_listing_configuration()
        return self._coerce_listings(self._request_json('get', self.listings_endpoint))

    def upsert_listing(self, listing) -> dict:
        self.validate_listing_configuration()
        payload = self._listing_payload(listing)
        listing_id = listing.external_listing_id
        method = 'put' if listing_id else 'post'
        result = self._request_json(method, self._listing_url(listing_id), json=payload)
        response_listing = result.get('listing', result) if isinstance(result, dict) else {}
        external_id = str(
            response_listing.get('id')
            or response_listing.get('listing_id')
            or response_listing.get('product_id')
            or listing.external_listing_id
        )
        if external_id:
            listing.external_listing_id = external_id
        listing.external_product_id = str(response_listing.get('product_id') or listing.external_product_id or external_id)
        listing.external_variant_id = str(response_listing.get('variant_id') or response_listing.get('sku') or listing.external_variant_id)
        listing.listing_url = response_listing.get('url') or response_listing.get('listing_url') or listing.listing_url
        listing.metadata = {**listing.metadata, 'last_push_payload': payload, 'last_push_response': result}
        listing.sync_state = listing.SyncState.SYNCED
        listing.last_synced_at = timezone.now()
        listing.save(update_fields=[
            'external_listing_id',
            'external_product_id',
            'external_variant_id',
            'listing_url',
            'metadata',
            'sync_state',
            'last_synced_at',
        ])
        return {'status': 'synced', 'provider': self.provider, 'listing_id': listing.external_listing_id, 'response': result}

    def push_inventory(self, listing, quantity: int) -> dict:
        self.validate_listing_configuration()
        if not listing.external_listing_id:
            raise ValueError('Cannot push PopCustoms inventory before the listing has an external_listing_id.')
        payload = {
            'listing_id': listing.external_listing_id,
            'product_id': listing.external_product_id,
            'variant_id': listing.external_variant_id,
            'sku': getattr(listing.variant, 'sku', ''),
            'quantity': int(quantity),
        }
        result = self._request_json('put', self._inventory_url(listing.external_listing_id), json=payload)
        listing.metadata = {**listing.metadata, 'last_inventory_payload': payload, 'last_inventory_response': result}
        listing.sync_state = listing.SyncState.SYNCED
        listing.last_synced_at = timezone.now()
        listing.save(update_fields=['metadata', 'sync_state', 'last_synced_at'])
        if listing.variant:
            listing.variant.stock_quantity = max(0, int(quantity))
            listing.variant.last_sync_at = timezone.now()
            listing.variant.save(update_fields=['stock_quantity', 'last_sync_at'])
        return {'status': 'inventory_synced', 'provider': self.provider, 'listing_id': listing.external_listing_id, 'response': result}

    def submit_order(self, order, items: list[dict]) -> dict:
        self.validate_order_configuration()
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
