from .base import BaseConnector


class PopCustomsConnector(BaseConnector):
    provider = 'popcustoms'

    def validate_configuration(self) -> None:
        raise NotImplementedError('TODO: Add PopCustoms API credentials validation once the API contract is confirmed.')

    def pull_orders(self) -> list[dict]:
        raise NotImplementedError('TODO: Implement PopCustoms order import.')

    def upsert_listing(self, listing) -> dict:
        raise NotImplementedError('TODO: Implement PopCustoms listing sync.')

    def push_inventory(self, listing, quantity: int) -> dict:
        raise NotImplementedError('TODO: Implement PopCustoms inventory sync.')
