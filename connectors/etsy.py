import requests

from .base import BaseConnector


class EtsyConnector(BaseConnector):
    provider = 'etsy'
    api_base = 'https://openapi.etsy.com/v3/application'

    def _headers(self) -> dict[str, str]:
        api_key = self.channel_account.config.get('api_key', '')
        access_token = self.channel_account.access_token
        return {
            'x-api-key': api_key,
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

    def validate_configuration(self) -> None:
        missing = [key for key in ('api_key', 'shop_id') if not self.channel_account.config.get(key)]
        if not self.channel_account.access_token:
            missing.append('access_token')
        if missing:
            raise ValueError(f'Etsy connector missing configuration: {", ".join(sorted(set(missing)))}')

    def pull_orders(self) -> list[dict]:
        self.validate_configuration()
        shop_id = self.channel_account.config['shop_id']
        response = requests.get(f'{self.api_base}/shops/{shop_id}/receipts', headers=self._headers(), timeout=30)
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
