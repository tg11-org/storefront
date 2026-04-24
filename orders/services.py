"""Order fulfillment and notification services."""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.urls import reverse

from .models import Order, FulfillmentUpdate


def get_order_absolute_url(order: Order) -> str:
    """Get absolute URL for an order."""
    site_url = getattr(settings, 'SITE_URL', 'https://shop.tg11.org').rstrip('/')
    return f"{site_url}/orders/{order.number}/"


def send_fulfillment_notification(fulfillment_update: FulfillmentUpdate) -> bool:
    """
    Send customer email notification for fulfillment status update.
    
    Returns True if email was sent successfully, False otherwise.
    """
    if fulfillment_update.email_sent:
        return True  # Already sent
    
    order = fulfillment_update.order
    recipient_email = order.email
    
    # Prepare email template context
    context = {
        'order_number': order.number,
        'customer_name': order.user.get_full_name() if order.user else 'Valued Customer',
        'status': fulfillment_update.get_status_display(),
        'status_slug': fulfillment_update.status,
        'tracking_number': fulfillment_update.tracking_number or '',
        'carrier': fulfillment_update.get_carrier_display() if fulfillment_update.carrier else '',
        'tracking_url': fulfillment_update.get_tracking_url_display(),
        'estimated_delivery': fulfillment_update.estimated_delivery,
        'notes': fulfillment_update.notes or '',
        'items': order.items.all(),
        'order': order,
        'order_url': get_order_absolute_url(order),
        'shipping_address': order.shipping_address,
        'site_name': 'TG11 Shop',
    }
    
    # Render email subject and body
    try:
        subject = render_to_string(
            f'emails/fulfillment_{fulfillment_update.status}_subject.txt',
            context
        ).strip()
        
        html_body = render_to_string(
            f'emails/fulfillment_{fulfillment_update.status}_email.html',
            context
        )
        
        text_body = render_to_string(
            f'emails/fulfillment_{fulfillment_update.status}_email.txt',
            context
        )
    except Exception as e:
        print(f"Failed to render email templates for {order.number}: {e}")
        return False
    
    try:
        send_mail(
            subject=subject,
            message=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_body,
            fail_silently=False,
        )
        fulfillment_update.email_sent = True
        fulfillment_update.save(update_fields=['email_sent'])
        return True
    except Exception as e:
        print(f"Failed to send fulfillment email for {order.number}: {e}")
        return False


def create_fulfillment_update(
    order: Order,
    status: str,
    tracking_number: str = '',
    carrier: str = '',
    tracking_url: str = '',
    estimated_delivery=None,
    notes: str = '',
    created_by=None,
    send_email: bool = True
) -> FulfillmentUpdate:
    """
    Create a fulfillment update and optionally send notification email.
    
    Args:
        order: The Order to update
        status: New fulfillment status (from Order.FulfillmentStatus choices)
        tracking_number: Carrier tracking number
        carrier: Shipping carrier (ups, fedex, usps, dhl, other)
        tracking_url: Custom tracking URL
        estimated_delivery: Expected delivery date
        notes: Additional notes for customer
        created_by: User making the update
        send_email: Whether to send notification email immediately
    
    Returns:
        The created FulfillmentUpdate instance
    """
    fulfillment_update = FulfillmentUpdate.objects.create(
        order=order,
        status=status,
        tracking_number=tracking_number,
        carrier=carrier,
        tracking_url=tracking_url,
        estimated_delivery=estimated_delivery,
        notes=notes,
        created_by=created_by,
    )
    
    # Update order fulfillment_status
    order.fulfillment_status = status
    order.save(update_fields=['fulfillment_status', 'updated_at'])
    
    # Send email notification if requested
    if send_email:
        send_fulfillment_notification(fulfillment_update)
    
    return fulfillment_update


def mark_order_refunded(order: Order, reason: str = '', created_by=None) -> FulfillmentUpdate:
    """
    Mark an order as refunded. Updates order status and creates fulfillment update.
    """
    # Update order status to CANCELLED
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    
    # Create fulfillment update for refund
    return FulfillmentUpdate.objects.create(
        order=order,
        status=Order.FulfillmentStatus.UNSUBMITTED,  # Reset fulfillment
        notes=f'Order refunded. Reason: {reason}' if reason else 'Order refunded',
        created_by=created_by,
    )


def mark_order_return_requested(order: Order, reason: str = '', created_by=None) -> FulfillmentUpdate:
    """
    Create a return request fulfillment update.
    """
    return FulfillmentUpdate.objects.create(
        order=order,
        status=Order.FulfillmentStatus.UNSUBMITTED,
        notes=f'Return requested by customer. Reason: {reason}' if reason else 'Return requested by customer.',
        created_by=created_by,
    )
