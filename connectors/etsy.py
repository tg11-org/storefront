import requests
from django.conf import settings

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

    def _headers(self) -> dict[str, str]:
        access_token = self.channel_account.access_token
        return {
            'x-api-key': f'{self.api_key}:{self.shared_secret}',
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

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
        response = requests.get(f'{self.api_base}/shops/{self.shop_id}/receipts', headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get('results', [])

    def upsert_listing(self, listing) -> dict:
        self.validate_configuration()
        return {'status': 'todo', 'provider': self.provider, 'listing_id': getattr(listing, 'external_listing_id', '')}

    def push_inventory(self, listing, quantity: int) -> dict:
        self.validate_configuration()
        return {
            'status': 'todo',
            'provider': self.provider,
            'listing_id': getattr(listing, 'external_listing_id', ''),
            'quantity': quantity,
        }

    def submit_order(self, order, items: list[dict]) -> dict:
        self.validate_configuration()
        return {'status': 'todo', 'provider': self.provider, 'order_number': order.number, 'items': items}
