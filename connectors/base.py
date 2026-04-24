from abc import ABC, abstractmethod


class BaseConnector(ABC):
    provider = 'base'

    def __init__(self, channel_account):
        self.channel_account = channel_account

    @abstractmethod
    def validate_configuration(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def pull_orders(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def upsert_listing(self, listing) -> dict:
        raise NotImplementedError

    @abstractmethod
    def push_inventory(self, listing, quantity: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order, items: list[dict]) -> dict:
        raise NotImplementedError
