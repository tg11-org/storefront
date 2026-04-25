from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from .base import BaseConnector


class EtsyConnector(BaseConnector):
    provider = 'etsy'
    api_base = 'https://openapi.etsy.com/v3/application'

    def _config_value(self, key: str, setting_name: str) -> str:
        return self.channel_account.config.get(key) or getattr(settings, setting_name, '')

    @property
    def api_key(self) -> str:
        return self._config_value('api_key', 'ETSY_API_KEY')

    @property
    def shared_secret(self) -> str:
        return self._config_value('shared_secret', 'ETSY_SHARED_SECRET')

    @property
    def shop_id(self) -> str:
        return self.channel_account.config.get('shop_id', self.channel_account.account_identifier)

    def _headers(self, *, json_body: bool = True) -> dict[str, str]:
        access_token = self.channel_account.access_token
        headers = {
            'x-api-key': f'{self.api_key}:{self.shared_secret}',
            'Authorization': f'Bearer {access_token}',
        }
        headers['Content-Type'] = 'application/json' if json_body else 'application/x-www-form-urlencoded'
        return headers

    def _request_json(self, method: str, url: str, *, json_body: dict | None = None, form_data: dict | None = None) -> dict | list:
        headers = self._headers(json_body=form_data is None)
        kwargs = {'headers': headers, 'timeout': 30}
        if form_data is not None:
            kwargs['data'] = form_data
        elif json_body is not None:
            kwargs['json'] = json_body
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {'raw': response.text}

    def validate_configuration(self) -> None:
        missing = []
        if not self.api_key:
            missing.append('api_key')
        if not self.shared_secret:
            missing.append('shared_secret')
        if not self.shop_id:
            missing.append('shop_id')
        if not self.channel_account.access_token:
            missing.append('access_token')
        if missing:
            raise ValueError(f'Etsy connector missing configuration: {", ".join(sorted(set(missing)))}')

    def pull_orders(self) -> list[dict]:
        self.validate_configuration()
        payload = self._request_json('get', f'{self.api_base}/shops/{self.shop_id}/receipts')
        return payload.get('results', []) if isinstance(payload, dict) else []

    def pull_listings(self) -> list[dict]:
        self.validate_configuration()
        payload = self._request_json('get', f'{self.api_base}/shops/{self.shop_id}/listings')
        return payload.get('results', []) if isinstance(payload, dict) else []

    def _listing_payload(self, listing) -> dict:
        product = listing.product
        variant = listing.variant or product.primary_variant
        if not variant:
            raise ValueError(f'{product.name} does not have a variant to sync.')

        payload = {
            'title': product.name[:140],
            'description': product.description or product.short_description or product.name,
            'quantity': max(0, int(variant.stock_quantity)),
            'price': str(variant.price),
            'who_made': self.channel_account.config.get('who_made', 'i_did'),
            'when_made': self.channel_account.config.get('when_made', 'made_to_order'),
            'taxonomy_id': self.channel_account.config.get('taxonomy_id'),
            'shipping_profile_id': self.channel_account.config.get('shipping_profile_id'),
            'readiness_state_id': self.channel_account.config.get('readiness_state_id'),
            'sku': variant.sku,
            'state': self.channel_account.config.get('listing_state', 'draft'),
        }
        optional_keys = [
            'type',
            'materials',
            'shop_section_id',
            'processing_min',
            'processing_max',
            'return_policy_id',
        ]
        for key in optional_keys:
            if self.channel_account.config.get(key) not in (None, ''):
                payload[key] = self.channel_account.config[key]
        missing = [key for key in ('taxonomy_id', 'shipping_profile_id') if not payload.get(key)]
        if missing:
            raise ValueError(
                'Etsy listing sync needs channel config values: '
                + ', '.join(missing)
                + '. Add them to the channel config JSON before pushing listings.'
            )
        return {key: value for key, value in payload.items() if value not in (None, '')}

    def _inventory_payload(self, listing, quantity: int) -> dict:
        variant = listing.variant or listing.product.primary_variant
        if not variant:
            raise ValueError(f'{listing.product.name} does not have a variant to sync.')
        readiness_state_id = self.channel_account.config.get('readiness_state_id')
        offering = {
            'price': float(Decimal(variant.price)),
            'quantity': max(0, int(quantity)),
            'is_enabled': variant.is_active,
        }
        if readiness_state_id:
            offering['readiness_state_id'] = readiness_state_id
        product = {
            'sku': variant.sku,
            'property_values': listing.metadata.get('etsy_property_values', []),
            'offerings': [offering],
        }
        return {
            'products': listing.metadata.get('etsy_inventory_products') or [product],
            'price_on_property': listing.metadata.get('etsy_price_on_property', []),
            'quantity_on_property': listing.metadata.get('etsy_quantity_on_property', []),
            'sku_on_property': listing.metadata.get('etsy_sku_on_property', []),
        }

    def upsert_listing(self, listing) -> dict:
        self.validate_configuration()
        payload = self._listing_payload(listing)
        if listing.external_listing_id:
            result = self._request_json(
                'patch',
                f'{self.api_base}/shops/{self.shop_id}/listings/{listing.external_listing_id}',
                form_data=payload,
            )
        else:
            result = self._request_json(
                'post',
                f'{self.api_base}/shops/{self.shop_id}/listings',
                form_data=payload,
            )
        response_listing = result.get('listing', result) if isinstance(result, dict) else {}
        external_id = str(response_listing.get('listing_id') or response_listing.get('id') or listing.external_listing_id)
        if external_id:
            listing.external_listing_id = external_id
        listing.external_product_id = str(response_listing.get('listing_id') or listing.external_product_id or external_id)
        listing.listing_url = response_listing.get('url') or listing.listing_url
        listing.metadata = {**listing.metadata, 'last_push_payload': payload, 'last_push_response': result}
        listing.sync_state = listing.SyncState.SYNCED
        listing.last_synced_at = timezone.now()
        listing.save(update_fields=[
            'external_listing_id',
            'external_product_id',
            'listing_url',
            'metadata',
            'sync_state',
            'last_synced_at',
        ])
        if listing.external_listing_id and listing.variant:
            self.push_inventory(listing, listing.variant.stock_quantity)
        return {'status': 'synced', 'provider': self.provider, 'listing_id': listing.external_listing_id, 'response': result}

    def push_inventory(self, listing, quantity: int) -> dict:
        self.validate_configuration()
        if not listing.external_listing_id:
            raise ValueError('Cannot push Etsy inventory before the listing has an external_listing_id.')
        payload = self._inventory_payload(listing, quantity)
        result = self._request_json(
            'put',
            f'{self.api_base}/listings/{listing.external_listing_id}/inventory',
            json_body=payload,
        )
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
        self.validate_configuration()
        raise ValueError('Etsy does not expose an API for creating marketplace customer orders from this storefront. Use Etsy for listing/inventory sync and import Etsy receipts instead.')
