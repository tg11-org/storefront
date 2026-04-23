from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from connectors.models import SyncJob
from orders.models import Order
from payments.models import PaymentRecord


@staff_member_required
def dashboard_home(request):
    paid_orders = Order.objects.filter(status=Order.Status.PAID)
    gross_sales = sum((order.grand_total for order in paid_orders), Decimal('0.00'))
    metrics = {
        'order_count': Order.objects.count(),
        'gross_sales': gross_sales,
        'connector_jobs': SyncJob.objects.count(),
        'successful_payments': PaymentRecord.objects.filter(status=PaymentRecord.Status.SUCCEEDED).count(),
    }
    return render(request, 'dashboard/home.html', {'metrics': metrics, 'recent_orders': Order.objects.all()[:10], 'recent_jobs': SyncJob.objects.all()[:10]})
