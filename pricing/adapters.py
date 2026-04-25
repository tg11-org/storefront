from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import base64
import json
import logging
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)


class ShippingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRate:
    provider: str
    carrier: str
    service: str
    amount: Decimal
    currency: str
    external_rate_id: str = ''
    external_shipment_id: str = ''
    estimated_days: int | None = None
    messages: tuple[str, ...] = ()


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json', **headers}, method='POST')
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise ShippingProviderError(f'{url} returned {exc.code}: {body[:500]}') from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ShippingProviderError(str(exc)) from exc


def _origin_address() -> dict:
    return {
        'name': settings.SHIP_FROM_NAME,
        'company': settings.SHIP_FROM_COMPANY,
        'street1': settings.SHIP_FROM_LINE1,
        'street2': settings.SHIP_FROM_LINE2,
        'city': settings.SHIP_FROM_CITY,
        'state': settings.SHIP_FROM_STATE,
        'zip': settings.SHIP_FROM_POSTAL_CODE,
        'postal_code': settings.SHIP_FROM_POSTAL_CODE,
        'country': settings.SHIP_FROM_COUNTRY,
        'phone': settings.SHIP_FROM_PHONE,
        'email': settings.SHIP_FROM_EMAIL,
    }


def _destination_address(destination: dict) -> dict:
    return {
        'name': destination.get('full_name') or destination.get('name') or 'Customer',
        'company': destination.get('company_name', ''),
        'street1': destination.get('line1', ''),
        'street2': destination.get('line2', ''),
        'city': destination.get('city', ''),
        'state': destination.get('state', ''),
        'zip': destination.get('postal_code', ''),
        'postal_code': destination.get('postal_code', ''),
        'country': destination.get('country', 'US'),
        'phone': destination.get('phone_number', ''),
        'email': destination.get('email', ''),
    }


def _parcel(items) -> dict:
    weight = sum((Decimal(str(item.variant.weight_oz or '0.00')) * item.quantity for item in items), Decimal('0.00'))
    max_length = max((Decimal(str(item.variant.length_in or '0.00')) for item in items), default=Decimal('0.00'))
    max_width = max((Decimal(str(item.variant.width_in or '0.00')) for item in items), default=Decimal('0.00'))
    total_height = sum((Decimal(str(item.variant.height_in or '0.00')) * item.quantity for item in items), Decimal('0.00'))
    return {
        'length': str(max(max_length, Decimal('1.00'))),
        'width': str(max(max_width, Decimal('1.00'))),
        'height': str(max(total_height, Decimal('1.00'))),
        'weight': str(max(weight, Decimal('1.00'))),
    }


class EasyPostAdapter:
    provider = 'easypost'

    def enabled(self) -> bool:
        return bool(settings.EASYPOST_API_KEY)

    def quote(self, destination: dict, items) -> list[ProviderRate]:
        if not self.enabled():
            return []
        origin = _origin_address()
        dest = _destination_address(destination)
        parcel = _parcel(items)
        auth = base64.b64encode(f'{settings.EASYPOST_API_KEY}:'.encode('utf-8')).decode('ascii')
        payload = {
            'shipment': {
                'to_address': {
                    'name': dest['name'],
                    'company': dest['company'],
                    'street1': dest['street1'],
                    'street2': dest['street2'],
                    'city': dest['city'],
                    'state': dest['state'],
                    'zip': dest['zip'],
                    'country': dest['country'],
                    'phone': dest['phone'],
                    'email': dest['email'],
                },
                'from_address': {
                    'name': origin['name'],
                    'company': origin['company'],
                    'street1': origin['street1'],
                    'street2': origin['street2'],
                    'city': origin['city'],
                    'state': origin['state'],
                    'zip': origin['zip'],
                    'country': origin['country'],
                    'phone': origin['phone'],
                    'email': origin['email'],
                },
                'parcel': parcel,
                'options': {'currency': settings.STRIPE_CURRENCY.upper()},
            }
        }
        response = _post_json(
            settings.EASYPOST_API_URL.rstrip('/') + '/shipments',
            payload,
            {'Authorization': f'Basic {auth}'},
            settings.SHIPPING_PROVIDER_TIMEOUT_SECONDS,
        )
        rates = []
        for rate in response.get('rates', []):
            if rate.get('currency', '').lower() != settings.STRIPE_CURRENCY.lower():
                continue
            rates.append(
                ProviderRate(
                    provider=self.provider,
                    carrier=rate.get('carrier', 'EasyPost'),
                    service=rate.get('service', 'Carrier rate'),
                    amount=Decimal(str(rate.get('rate', '0.00'))),
                    currency=rate.get('currency', settings.STRIPE_CURRENCY).lower(),
                    external_rate_id=rate.get('id', ''),
                    external_shipment_id=response.get('id', ''),
                    estimated_days=rate.get('delivery_days') or rate.get('est_delivery_days'),
                    messages=tuple(message.get('message', '') for message in response.get('messages', []) if message.get('message')),
                )
            )
        return rates


class ShippoAdapter:
    provider = 'shippo'

    def enabled(self) -> bool:
        return bool(settings.SHIPPO_API_TOKEN)

    def quote(self, destination: dict, items) -> list[ProviderRate]:
        if not self.enabled():
            return []
        origin = _origin_address()
        dest = _destination_address(destination)
        parcel = _parcel(items)
        payload = {
            'address_from': {
                'name': origin['name'],
                'company': origin['company'],
                'street1': origin['street1'],
                'street2': origin['street2'],
                'city': origin['city'],
                'state': origin['state'],
                'zip': origin['zip'],
                'country': origin['country'],
                'phone': origin['phone'],
                'email': origin['email'],
            },
            'address_to': {
                'name': dest['name'],
                'company': dest['company'],
                'street1': dest['street1'],
                'street2': dest['street2'],
                'city': dest['city'],
                'state': dest['state'],
                'zip': dest['zip'],
                'country': dest['country'],
                'phone': dest['phone'],
                'email': dest['email'],
            },
            'parcels': [{**parcel, 'distance_unit': 'in', 'mass_unit': 'oz'}],
            'async': False,
        }
        response = _post_json(
            settings.SHIPPO_API_URL.rstrip('/') + '/shipments/',
            payload,
            {'Authorization': f'ShippoToken {settings.SHIPPO_API_TOKEN}'},
            settings.SHIPPING_PROVIDER_TIMEOUT_SECONDS,
        )
        rates = []
        for rate in response.get('rates', []):
            currency = rate.get('currency') or rate.get('currency_local') or settings.STRIPE_CURRENCY
            if currency.lower() != settings.STRIPE_CURRENCY.lower():
                continue
            rates.append(
                ProviderRate(
                    provider=self.provider,
                    carrier=rate.get('provider', 'Shippo'),
                    service=rate.get('servicelevel', {}).get('name') or rate.get('servicelevel', {}).get('token') or 'Carrier rate',
                    amount=Decimal(str(rate.get('amount') or rate.get('amount_local') or '0.00')),
                    currency=currency.lower(),
                    external_rate_id=rate.get('object_id', ''),
                    external_shipment_id=response.get('object_id', ''),
                    estimated_days=rate.get('estimated_days'),
                    messages=tuple(message.get('text', '') for message in response.get('messages', []) if message.get('text')),
                )
            )
        return rates


def configured_shipping_adapter():
    provider = settings.SHIPPING_RATE_PROVIDER.lower()
    adapters = {
        'easypost': EasyPostAdapter(),
        'shippo': ShippoAdapter(),
    }
    return adapters.get(provider)
