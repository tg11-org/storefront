from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from orders.models import Order
from payments.models import PaymentRecord


class Command(BaseCommand):
    help = 'Compare expected order totals against successful payment records.'

    def handle(self, *args, **options):
        mismatches = []
        for order in Order.objects.filter(status=Order.Status.PAID).prefetch_related('payment_records'):
            paid = sum(
                (payment.amount for payment in order.payment_records.filter(status=PaymentRecord.Status.SUCCEEDED)),
                Decimal('0.00'),
            )
            if paid != order.grand_total:
                mismatches.append((order.number, order.grand_total, paid))

        if mismatches:
            for number, expected, paid in mismatches:
                self.stderr.write(f'{number}: expected ${expected}, paid ${paid}')
            raise SystemExit(f'{len(mismatches)} payment reconciliation mismatch(es).')

        self.stdout.write(self.style.SUCCESS('Payment reconciliation passed.'))
