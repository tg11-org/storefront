from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from pricing.models import ShippingMethod, ShippingRateRule, ShippingZone


class Command(BaseCommand):
    help = 'Create baseline domestic and international shipping zones and fallback rules.'

    def handle(self, *args, **options):
        domestic, _ = ShippingZone.objects.get_or_create(name='Domestic US', defaults={'countries': 'US'})
        international, _ = ShippingZone.objects.get_or_create(name='International', defaults={'countries': '*', 'unavailable_countries': ''})
        standard, _ = ShippingMethod.objects.get_or_create(
            name='Standard',
            defaults={'carrier': ShippingMethod.Carrier.CUSTOM, 'estimated_min_days': 3, 'estimated_max_days': 7},
        )
        intl_standard, _ = ShippingMethod.objects.get_or_create(
            name='International Standard',
            defaults={'carrier': ShippingMethod.Carrier.CUSTOM, 'estimated_min_days': 7, 'estimated_max_days': 21},
        )
        ShippingRateRule.objects.get_or_create(
            zone=domestic,
            method=standard,
            rate_type=ShippingRateRule.RateType.FLAT,
            defaults={'amount': Decimal('6.95'), 'fallback': True, 'priority': 100},
        )
        ShippingRateRule.objects.get_or_create(
            zone=international,
            method=intl_standard,
            rate_type=ShippingRateRule.RateType.FLAT,
            defaults={'amount': Decimal('24.95'), 'fallback': True, 'priority': 200},
        )
        self.stdout.write(self.style.SUCCESS('Baseline shipping zones and fallback rates are ready.'))
