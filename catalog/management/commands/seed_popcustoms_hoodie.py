from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import Product, ProductVariant


class Command(BaseCommand):
    help = 'Seed PopCustoms White Hoodie product with 10 size variants'

    def handle(self, *args, **options):
        try:
            product_defaults = {
                'slug': 'popcustoms-white-hoodie',
                'short_description': 'Premium velvet hoodie with drawstring hood, front pocket, and ribbed cuffs. Crafted from durable polyester, perfect for autumn/winter wear. Sizes XS-7XL. Machine wash 30C.',
                'description': '''Premium Velvet Hoodie - The Ultimate Casual Comfort Layer

Elevate your casual wardrobe with our ultra-soft PopCustoms White Hoodie. Engineered for comfort and durability, this premium piece features a modern silhouette perfect for layering or standalone wear.

**Material & Quality**
Crafted from premium polyester velvet, designed for softness and longevity. The durable construction withstands regular washing while maintaining its luxurious feel and vibrant white finish.

**Design & Fit**
- Drawstring hood for adjustable comfort
- Front kangaroo pocket with reinforced stitching
- Ribbed cuffs and hem for a polished look
- Modern relaxed fit suitable for all body types
- Unisex sizing for inclusive wear

**Sizing Guide**
Size XS-7XL available with international conversions:
- XS: Chest 32" (81cm), Length 26" (66cm)
- S: Chest 34" (86cm), Length 27" (69cm)
- M: Chest 38" (97cm), Length 28" (71cm)
- L: Chest 42" (107cm), Length 29" (74cm)
- XL: Chest 46" (117cm), Length 30" (76cm)
- 2XL: Chest 50" (127cm), Length 31" (79cm)
- 3XL: Chest 54" (137cm), Length 32" (81cm)
- 4XL: Chest 58" (147cm), Length 33" (84cm)
- 5XL: Chest 62" (157cm), Length 34" (86cm)
- 7XL: Chest 70" (178cm), Length 36" (91cm)

**Versatility**
Perfect for:
- Casual everyday wear
- Outdoor layering during cooler months
- Relaxed work-from-home comfort
- Travel and weekend adventures
- Beach cover-ups in warmer climates

**Care Instructions**
- Machine wash at 30C in cold water
- Do not bleach or tumble dry
- Lay flat or hang to dry
- Gentle press if needed; avoid direct heat
- Separate from darker colors to prevent dye transfer

**Shipping**
Standard and express shipping available to over 100 countries. Typical delivery:
- North America: 5-7 business days (standard), 2-3 days (express)
- Europe: 7-10 business days (standard), 3-5 days (express)
- Rest of World: 10-21 business days (standard), 5-10 days (express)

Ships from certified PopCustoms fulfillment center with tracking included.''',
                'product_type': Product.ProductType.EXTERNAL,
                'default_source': Product.Source.POPCUSTOMS,
                'is_active': True,
            }
            product, created = Product.objects.update_or_create(
                name='PopCustoms White Hoodie',
                defaults=product_defaults,
            )

            status_str = 'Created' if created else 'Already exists'
            self.stdout.write(f'{status_str}: {product.name}')

            # Define variants (size, sku, price, sort_order, chest, body, sleeve)
            variants_data = [
                ('XS', 'NGZO816W-1', Decimal('17.49'), 0, Decimal('32.00'), Decimal('26.00'), Decimal('24.00')),
                ('S', 'NGZO816W-2', Decimal('17.49'), 1, Decimal('34.00'), Decimal('27.00'), Decimal('25.00')),
                ('M', 'NGZO816W-3', Decimal('17.49'), 2, Decimal('38.00'), Decimal('28.00'), Decimal('26.00')),
                ('L', 'NGZO816W-4', Decimal('17.49'), 3, Decimal('42.00'), Decimal('29.00'), Decimal('27.00')),
                ('XL', 'NGZO816W-5', Decimal('17.49'), 4, Decimal('46.00'), Decimal('30.00'), Decimal('28.00')),
                ('2XL', 'NGZO816W-6', Decimal('20.49'), 5, Decimal('50.00'), Decimal('31.00'), Decimal('29.00')),
                ('3XL', 'NGZO816W-7', Decimal('20.49'), 6, Decimal('54.00'), Decimal('32.00'), Decimal('30.00')),
                ('4XL', 'NGZO816W-8', Decimal('20.49'), 7, Decimal('58.00'), Decimal('33.00'), Decimal('31.00')),
                ('5XL', 'NGZO816W-9', Decimal('20.49'), 8, Decimal('62.00'), Decimal('34.00'), Decimal('32.00')),
                ('7XL', 'NGZO816W-10', Decimal('20.49'), 9, Decimal('70.00'), Decimal('36.00'), Decimal('34.00')),
            ]

            for size, sku, price, sort_order, chest, body, sleeve in variants_data:
                variant, v_created = ProductVariant.objects.update_or_create(
                    sku=sku,
                    defaults={
                        'product': product,
                        'title': size,
                        'size_label': size,
                        'sort_order': sort_order,
                        'price': price,
                        'supplier_price': price,
                        'is_default': (size == 'M'),  # M as default size
                        'is_active': True,
                        'stock_quantity': 0,  # PopCustoms handles inventory
                        'chest_width_in': chest,
                        'body_length_in': body,
                        'sleeve_length_in': sleeve,
                    }
                )
                v_status = 'Created' if v_created else 'Already exists'
                self.stdout.write(
                    f'  {v_status}: {size} ({sku}) - ${price} - Chest {chest}" / Length {body}" / Sleeve {sleeve}"'
                )

            self.stdout.write(f'\n✓ PopCustoms White Hoodie product fully seeded!')

        except Exception as exc:
            self.stderr.write(f'Error seeding product: {exc}')
