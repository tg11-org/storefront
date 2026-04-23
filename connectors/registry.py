from .etsy import EtsyConnector
from .popcustoms import PopCustomsConnector

CONNECTOR_REGISTRY = {
    'etsy': EtsyConnector,
    'popcustoms': PopCustomsConnector,
}


def get_connector(channel_account):
    connector_class = CONNECTOR_REGISTRY[channel_account.provider]
    return connector_class(channel_account)
