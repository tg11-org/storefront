from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import logging

from django.utils import timezone
from django.conf import settings

from catalog.models import StoreSettings
from orders.models import Order

from .adapters import ShippingProviderError, configured_shipping_adapter
from .alerts import alert_ops
from .models import Coupon, CouponRedemption, Promotion, PromotionScope, ShippingRateRule
from .services_math import money

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppliedRule:
    kind: str
    code: str
    label: str
    amount: Decimal
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ShippingQuote:
    quote_id: str
    method_id: int | None
    method_name: str
    carrier: str
    amount: Decimal
    estimated_min_days: int
    estimated_max_days: int
    rule_id: int | None
    fallback: bool = False
    provider: str = 'rules'
    external_rate_id: str = ''
    external_shipment_id: str = ''
    messages: tuple[str, ...] = ()

    def snapshot(self) -> dict:
        return {
            'method_id': self.method_id,
            'quote_id': self.quote_id,
            'method_name': self.method_name,
            'carrier': self.carrier,
            'amount': str(self.amount),
            'estimated_min_days': self.estimated_min_days,
            'estimated_max_days': self.estimated_max_days,
            'rule_id': self.rule_id,
            'fallback': self.fallback,
            'provider': self.provider,
            'external_rate_id': self.external_rate_id,
            'external_shipment_id': self.external_shipment_id,
            'messages': list(self.messages),
        }


def shipping_quote_from_snapshot(snapshot: dict) -> ShippingQuote:
    return ShippingQuote(
        quote_id=snapshot.get('quote_id', ''),
        method_id=snapshot.get('method_id'),
        method_name=snapshot.get('method_name', ''),
        carrier=snapshot.get('carrier', ''),
        amount=money(snapshot.get('amount', '0.00')),
        estimated_min_days=int(snapshot.get('estimated_min_days') or 0),
        estimated_max_days=int(snapshot.get('estimated_max_days') or 0),
        rule_id=snapshot.get('rule_id'),
        fallback=bool(snapshot.get('fallback', False)),
        provider=snapshot.get('provider', 'rules'),
        external_rate_id=snapshot.get('external_rate_id', ''),
        external_shipment_id=snapshot.get('external_shipment_id', ''),
        messages=tuple(snapshot.get('messages') or ()),
    )


@dataclass(frozen=True)
class PricingResult:
    subtotal: Decimal
    discount_total: Decimal
    shipping_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    applied_rules: list[AppliedRule]
    coupon: Coupon | None = None
    shipping_quote: ShippingQuote | None = None
    tax_snapshot: dict = field(default_factory=dict)

    def audit_snapshot(self) -> dict:
        return {
            'subtotal': str(self.subtotal),
            'discount_total': str(self.discount_total),
            'shipping_total': str(self.shipping_total),
            'tax_total': str(self.tax_total),
            'grand_total': str(self.grand_total),
            'coupon': self.coupon.code if self.coupon else '',
            'shipping_quote': self.shipping_quote.snapshot() if self.shipping_quote else None,
            'tax_snapshot': self.tax_snapshot,
            'applied_rules': [
                {'kind': rule.kind, 'code': rule.code, 'label': rule.label, 'amount': str(rule.amount), 'metadata': rule.metadata}
                for rule in self.applied_rules
            ],
        }


def _cart_items(cart):
    return cart.items.select_related('product', 'variant').prefetch_related('product__store_pages')


def _order_items(order):
    return order.items.select_related('product', 'variant')


def _line_total(item) -> Decimal:
    unit_price = getattr(item, 'unit_price', None)
    if unit_price is None:
        unit_price = item.variant.price
    return money(unit_price * item.quantity)


def _subtotal(items) -> Decimal:
    return money(sum((_line_total(item) for item in items), Decimal('0.00')))


def _csv_values(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split(',') if item.strip()}


def _active_time_window(queryset):
    now = timezone.now()
    return queryset.filter(active=True).filter(
        models_q_starts_before(now),
        models_q_ends_after(now),
    )


def models_q_starts_before(now):
    from django.db.models import Q

    return Q(starts_at__isnull=True) | Q(starts_at__lte=now)


def models_q_ends_after(now):
    from django.db.models import Q

    return Q(ends_at__isnull=True) | Q(ends_at__gte=now)


def scope_matches(scope: PromotionScope, item) -> bool:
    if scope.scope_type == PromotionScope.ScopeType.GLOBAL:
        return True
    if scope.scope_type == PromotionScope.ScopeType.PRODUCT:
        return bool(scope.product_id and scope.product_id == item.product_id)
    if scope.scope_type == PromotionScope.ScopeType.PRODUCTS:
        return scope.products.filter(pk=item.product_id).exists()
    if scope.scope_type == PromotionScope.ScopeType.SKU:
        return bool(scope.variant_id and scope.variant_id == item.variant_id)
    if scope.scope_type == PromotionScope.ScopeType.SKUS:
        sku = getattr(item.variant, 'sku', getattr(item, 'sku', '')).upper()
        return sku in _csv_values(scope.skus)
    if scope.scope_type == PromotionScope.ScopeType.PAGE:
        return bool(scope.page_id and item.product.store_pages.filter(pk=scope.page_id).exists())
    if scope.scope_type == PromotionScope.ScopeType.PAGES:
        return item.product.store_pages.filter(pk__in=scope.pages.values('pk')).exists()
    return False


def _promotion_matches(promotion: Promotion, items, subtotal: Decimal) -> bool:
    if subtotal < promotion.min_subtotal:
        return False
    if promotion.max_uses is not None and promotion.usage_count >= promotion.max_uses:
        return False
    scopes = list(promotion.scopes.all())
    if not scopes:
        return True
    return any(scope_matches(scope, item) for scope in scopes for item in items)


def _promotion_discount(promotion: Promotion, subtotal: Decimal) -> Decimal:
    if promotion.promotion_type == Promotion.PromotionType.PERCENT_OFF:
        return money(subtotal * (promotion.value / Decimal('100')))
    if promotion.promotion_type == Promotion.PromotionType.FIXED_OFF:
        return money(min(subtotal, promotion.value))
    if promotion.promotion_type == Promotion.PromotionType.SALE_PRICE:
        return Decimal('0.00')
    return Decimal('0.00')


def _validate_coupon(coupon_code: str | None, subtotal: Decimal, customer=None) -> tuple[Coupon | None, str | None]:
    if not coupon_code:
        return None, None
    now = timezone.now()
    coupon = Coupon.objects.filter(code=coupon_code.strip().upper(), active=True).filter(
        models_q_starts_before(now),
        models_q_ends_after(now),
    ).first()
    if not coupon:
        return None, 'Coupon is not active.'
    if subtotal < coupon.min_subtotal:
        return None, f'Coupon requires at least ${coupon.min_subtotal}.'
    if coupon.max_total_uses is not None and coupon.usage_count >= coupon.max_total_uses:
        return None, 'Coupon usage limit has been reached.'
    if customer and coupon.max_uses_per_customer is not None:
        uses = CouponRedemption.objects.filter(coupon=coupon, user=customer).count()
        if uses >= coupon.max_uses_per_customer:
            return None, 'Coupon usage limit has been reached for this account.'
    if customer and coupon.first_order_only and Order.objects.filter(user=customer, status=Order.Status.PAID).exists():
        return None, 'Coupon is only valid on first orders.'
    return coupon, None


def quote_shipping_methods(destination: dict | None, cart_or_order, subtotal: Decimal | None = None) -> list[ShippingQuote]:
    if not getattr(settings, 'ENABLE_SHIPPING_ENGINE', True):
        return []
    destination = destination or {}
    country = (destination.get('country') or 'US').upper()
    items = list(_cart_items(cart_or_order) if hasattr(cart_or_order, 'items') and cart_or_order.__class__.__name__ == 'Cart' else _order_items(cart_or_order))
    subtotal = subtotal if subtotal is not None else _subtotal(items)
    weight = money(sum(((getattr(item.variant, 'weight_oz', Decimal('0.00')) or Decimal('0.00')) * item.quantity for item in items), Decimal('0.00')))
    quotes = []
    if getattr(settings, 'ENABLE_LIVE_SHIPPING_RATES', False):
        adapter = configured_shipping_adapter()
        if adapter:
            try:
                for rate in adapter.quote(destination, items):
                    days = rate.estimated_days or settings.LIVE_SHIPPING_DEFAULT_DAYS
                    quotes.append(
                        ShippingQuote(
                            quote_id=f'{rate.provider}:{rate.external_rate_id or rate.carrier + ":" + rate.service}',
                            method_id=None,
                            method_name=rate.service,
                            carrier=rate.carrier,
                            amount=money(rate.amount),
                            estimated_min_days=max(1, days),
                            estimated_max_days=max(1, days),
                            rule_id=None,
                            fallback=False,
                            provider=rate.provider,
                            external_rate_id=rate.external_rate_id,
                            external_shipment_id=rate.external_shipment_id,
                            messages=rate.messages,
                        )
                    )
            except ShippingProviderError as exc:
                alert_ops('Shipping quote provider failed', f'{settings.SHIPPING_RATE_PROVIDER}: {exc}')
                logger.warning('shipping_quote_provider_failed', extra={'provider': settings.SHIPPING_RATE_PROVIDER, 'error': str(exc)})
                if not getattr(settings, 'ENABLE_SHIPPING_FALLBACK_RATES', True):
                    return []

    rules = ShippingRateRule.objects.select_related('zone', 'method').filter(active=True, method__active=True, zone__active=True)
    if quotes and not getattr(settings, 'INCLUDE_FALLBACK_WITH_LIVE_RATES', False):
        logger.info('shipping_quotes_resolved', extra={'country': country, 'quote_count': len(quotes), 'subtotal': str(subtotal), 'weight_oz': str(weight), 'provider': settings.SHIPPING_RATE_PROVIDER})
        return sorted(quotes, key=lambda quote: quote.amount)

    for rule in rules:
        zone_countries = _csv_values(rule.zone.countries)
        unavailable = _csv_values(rule.zone.unavailable_countries)
        if country in unavailable:
            continue
        if '*' not in zone_countries and country not in zone_countries:
            continue
        if weight < rule.min_weight_oz or (rule.max_weight_oz is not None and weight > rule.max_weight_oz):
            continue
        if subtotal < rule.min_subtotal or (rule.max_subtotal is not None and subtotal > rule.max_subtotal):
            continue
        amount = Decimal('0.00') if rule.rate_type == ShippingRateRule.RateType.FREE_SHIPPING else rule.amount
        quotes.append(
            ShippingQuote(
                quote_id=f'rule:{rule.pk}',
                method_id=rule.method_id,
                method_name=rule.method.name,
                carrier=rule.method.carrier,
                amount=money(amount),
                estimated_min_days=rule.method.estimated_min_days,
                estimated_max_days=rule.method.estimated_max_days,
                rule_id=rule.pk,
                fallback=rule.fallback,
            )
        )
    logger.info('shipping_quotes_resolved', extra={'country': country, 'quote_count': len(quotes), 'subtotal': str(subtotal), 'weight_oz': str(weight)})
    return quotes


def calculate_cart_totals(cart, customer=None, shipping_address: dict | None = None, coupon_code: str | None = None, shipping_quote_id: str | int | None = None, shipping_quotes: list[ShippingQuote] | None = None) -> PricingResult:
    items = list(_cart_items(cart))
    subtotal = _subtotal(items)
    applied_rules = []
    coupon, coupon_error = _validate_coupon(coupon_code, subtotal, customer) if getattr(settings, 'ENABLE_PROMOTIONS', True) else (None, None)
    if coupon_error:
        applied_rules.append(AppliedRule('coupon_rejected', coupon_code or '', coupon_error, Decimal('0.00')))

    promotions = _active_time_window(Promotion.objects.prefetch_related('scopes', 'scopes__products', 'scopes__pages').all()) if getattr(settings, 'ENABLE_PROMOTIONS', True) else Promotion.objects.none()
    if coupon:
        promotions = promotions.filter(id__in=coupon.promotions.values('id')) if coupon.promotions.exists() else promotions.none()

    discount_total = Decimal('0.00')
    free_shipping = False
    for promotion in promotions:
        if not _promotion_matches(promotion, items, subtotal):
            continue
        if applied_rules and not promotion.combinable and not (coupon and coupon.combinable):
            continue
        if promotion.promotion_type == Promotion.PromotionType.FREE_SHIPPING:
            free_shipping = True
            applied_rules.append(AppliedRule('promotion', promotion.name, promotion.name, Decimal('0.00'), {'type': promotion.promotion_type}))
            continue
        discount = _promotion_discount(promotion, subtotal - discount_total)
        if discount > 0:
            discount_total = money(discount_total + discount)
            applied_rules.append(AppliedRule('promotion', promotion.name, promotion.name, discount, {'type': promotion.promotion_type}))

    quotes = shipping_quotes if shipping_quotes is not None else (quote_shipping_methods(shipping_address, cart, subtotal=subtotal) if shipping_address else [])
    shipping_quote = None
    if quotes:
        shipping_quote = next((quote for quote in quotes if quote.quote_id == str(shipping_quote_id) or str(quote.rule_id) == str(shipping_quote_id)), None) or quotes[0]
    shipping_total = Decimal('0.00') if free_shipping else (shipping_quote.amount if shipping_quote else Decimal('0.00'))
    if free_shipping and shipping_quote:
        applied_rules.append(AppliedRule('shipping', 'free_shipping', 'Free shipping', shipping_quote.amount))

    tax_total = Decimal('0.00')
    tax_snapshot = {}
    if shipping_address and getattr(settings, 'TAX_PROVIDER', 'none') == 'stripe_tax':
        from .tax import TaxProviderError, stripe_tax_calculation

        try:
            tax_total, tax_snapshot = stripe_tax_calculation(items, max(Decimal('0.00'), subtotal - discount_total), shipping_total, shipping_address)
        except TaxProviderError as exc:
            alert_ops('Tax provider failed', str(exc))
            logger.warning('tax_provider_failed', extra={'provider': settings.TAX_PROVIDER, 'error': str(exc)})
            if getattr(settings, 'TAX_PROVIDER_REQUIRED', False):
                raise
    grand_total = money(max(Decimal('0.00'), subtotal - discount_total) + shipping_total + tax_total)
    logger.info('cart_totals_calculated', extra={'cart_id': cart.pk, 'subtotal': str(subtotal), 'discount_total': str(discount_total), 'shipping_total': str(shipping_total), 'tax_total': str(tax_total), 'grand_total': str(grand_total)})
    return PricingResult(subtotal, discount_total, shipping_total, tax_total, grand_total, applied_rules, coupon, shipping_quote, tax_snapshot)


def calculate_order_totals(order: Order) -> PricingResult:
    class OrderCartAdapter:
        pk = order.pk
        items = order.items

    result = calculate_cart_totals(OrderCartAdapter(), customer=order.user, shipping_address=order.shipping_address)
    return result


def default_store_settings() -> StoreSettings:
    return StoreSettings.current()
