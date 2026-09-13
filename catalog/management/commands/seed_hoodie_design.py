"""Seed an all-over-print hoodie design as a PopCustoms product.

Generalises catalog/management/commands/seed_popcustoms_hoodie.py so that adding
a new design is a matter of adding one entry to DESIGNS below and dropping its
mockup images into product-image-staging/.

Usage:
    python manage.py seed_hoodie_design neon-lynx
    python manage.py seed_hoodie_design --all
    python manage.py seed_hoodie_design --all --dry-run
    python manage.py seed_hoodie_design neon-lynx --skip-images

Blank specs, supplier costs and size charts were taken from the PopCustoms
listings on 2026-09-13. Re-check them if PopCustoms changes pricing.

Note: PopCustoms renames blanks. All four current designs were created on a blank
then called "Men's All Over Print Hoodie", now listed as "Men's All Over Print
Warm Velvets Pair Of Hoodie". Match a design to its blank by comparing the size
chart PopCustoms attaches to the design, not by the name shown in My Designs.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Product, ProductImage, ProductVariant


# PopCustoms reports 1/2 chest width (garment laid flat). The catalog stores
# chest_width_in as a full circumference to match the existing seed command, so
# half-chest values below are doubled on the way in. Flip this to False to store
# the flat measurement instead.
CHEST_AS_CIRCUMFERENCE = True

# PopCustoms ships US orders free but bills US customs duty per item at checkout
# ($3.50 on a 2-item order = $1.75/item, observed 2026-09-13). supplier_price below
# is the garment cost only; set POPCUSTOMS_PRICING_OVERHEAD to this to make the
# retail-floor maths use true landed cost - see the note in seed_variants().
CUSTOMS_DUTY_PER_ITEM = Decimal('1.75')

STAGING_DIRNAME = 'product-image-staging'

# Alt-text suffixes for the five PopCustoms mockup renders, in im1of5..im5of5 order.
MOCKUP_ROLES = ['Front 1', 'Back 1', 'Front 2', 'Back 2', 'Both Sides']


# --------------------------------------------------------------------------
# Blanks
# --------------------------------------------------------------------------
# size rows: (title, size_label, sort_order, weight_oz, shoulder, length, half_chest, sleeve)

BLANKS = {
    # Not currently used by any design. Kept for designs created on this blank
    # in future - note it tops out at 4XL, unlike the one below.
    'lightweight': {
        'label': "Men's Lightweight All Over Print Hoodie",
        'product_code': 'JS_C5',
        # PopCustoms charges more for the bigger sizes; confirm per size before use.
        'costs': {
            'Small': Decimal('17.89'), 'Medium': Decimal('17.89'), 'Large': Decimal('17.89'),
            'XL': Decimal('17.89'), '2XL': Decimal('17.89'),
            '3XL': Decimal('17.89'), '4XL': Decimal('17.89'),
        },
        'material': 'Air layer fabric (100% polyester)',
        'fulfillment': 'Made to order: average 5-7 days in production before it ships',
        'sizing_chart_image': 'mens-lightweight-all-over-print-hoodie-sizing-chart.webp',
        'sizes': [
            ('Small', 'Small', 1, Decimal('20.00'), Decimal('18.5'), Decimal('26.8'), Decimal('22.1'), Decimal('23.6')),
            ('Medium', 'Medium', 2, Decimal('20.50'), Decimal('19.3'), Decimal('28.0'), Decimal('23.2'), Decimal('25.6')),
            ('Large', 'Large', 3, Decimal('22.00'), Decimal('20.9'), Decimal('29.1'), Decimal('24.4'), Decimal('25.8')),
            ('XLarge', 'XL', 4, Decimal('23.25'), Decimal('22.1'), Decimal('30.3'), Decimal('25.6'), Decimal('25.8')),
            ('2XLarge', '2XL', 5, Decimal('24.50'), Decimal('22.8'), Decimal('31.5'), Decimal('26.8'), Decimal('26.0')),
            ('3XLarge', '3XL', 6, Decimal('25.75'), Decimal('23.6'), Decimal('32.7'), Decimal('28.0'), Decimal('26.2')),
            ('4XLarge', '4XL', 7, Decimal('27.00'), Decimal('24.8'), Decimal('33.5'), Decimal('29.1'), Decimal('26.4')),
        ],
    },
    # This is the blank all four current products sit on. PopCustoms listed it as
    # "Men's All Over Print Hoodie" when the older designs were made and has since
    # renamed it; the size chart it attaches to those older designs is identical to
    # the Warm Velvets chart, which is how the match was confirmed.
    # Chart gives LENGTH and CHEST WIDTH only - no shoulder or sleeve columns.
    'warm_velvets': {
        'label': "Men's All Over Print Warm Velvets Pair Of Hoodie",
        'aka': "Men's All Over Print Hoodie (pre-rename)",
        'product_code': '',
        # Per-size supplier cost, read off the PopCustoms order page 2026-09-13.
        'costs': {
            'Small': Decimal('17.49'), 'Medium': Decimal('17.49'), 'Large': Decimal('17.49'),
            'XL': Decimal('17.49'), '2XL': Decimal('17.49'),
            '3XL': Decimal('18.49'), '4XL': Decimal('18.49'),
            '5XL': Decimal('19.49'),
            '6XL': Decimal('20.49'), '7XL': Decimal('20.49'),
        },
        'material': 'Premium polyester velvet',
        'fulfillment': 'Made to order: average 5-7 days in production before it ships',
        'sizing_chart_image': 'mens-all-over-print-warm-velvets-hoodie-sizing-chart.webp',
        'sizes': [
            ('Small', 'Small', 1, Decimal('20.00'), None, Decimal('27.1'), Decimal('22.0'), None),
            ('Medium', 'Medium', 2, Decimal('20.50'), None, Decimal('28.0'), Decimal('23.2'), None),
            ('Large', 'Large', 3, Decimal('22.00'), None, Decimal('28.7'), Decimal('24.4'), None),
            ('XLarge', 'XL', 4, Decimal('23.25'), None, Decimal('29.5'), Decimal('25.6'), None),
            ('2XLarge', '2XL', 5, Decimal('24.50'), None, Decimal('30.3'), Decimal('26.8'), None),
            ('3XLarge', '3XL', 6, Decimal('25.75'), None, Decimal('31.0'), Decimal('28.0'), None),
            ('4XLarge', '4XL', 7, Decimal('27.00'), None, Decimal('31.9'), Decimal('29.2'), None),
            ('5XLarge', '5XL', 8, Decimal('28.25'), None, Decimal('32.7'), Decimal('30.3'), None),
            ('6XLarge', '6XL', 9, Decimal('29.25'), None, Decimal('33.5'), Decimal('31.5'), None),
            ('7XLarge', '7XL', 10, Decimal('30.50'), None, Decimal('34.3'), Decimal('32.7'), None),
        ],
    },
}


# --------------------------------------------------------------------------
# Designs
# --------------------------------------------------------------------------
# To add a design: copy a block, set the key/name/slug/sku_base/image_prefix,
# write the two description fields, drop the five im1of5..im5of5 webp files into
# product-image-staging/, then run the command with the new key.
#
# IMPORTANT: 'sizes' is the list of size labels PopCustoms will actually let you
# ORDER for that design. It is fixed when the design is created over there and it
# is not always the blank's full range, so copy it off the PopCustoms listing for
# each design rather than assuming. Any size left out of this list is a size you
# cannot fulfil, so it must not appear on the storefront. SKUs are numbered
# sequentially over this list, matching how the existing products are numbered.

DESIGNS = {
    'neon-fox': {
        'name': 'Neon Fox Hoodie',
        'slug': 'neon-fox-hoodie',
        'blank': 'warm_velvets',
        'sku_base': 'GY5XLGLW',
        'sizes': ['Small', 'Medium', 'Large', 'XL', '2XL', '3XL', '4XL'],
        'image_prefix': '145067-Ai-SynthwaveFox',
        'price': Decimal('26.75'),
        'short_description': (
            'All-over-print synthwave fox hoodie in electric magenta and cyan. '
            'Velvet-finish polyester, sizes S-4XL, printed and shipped on demand.'
        ),
        'blurb': (
            'A synthwave fox stares out of a grid-lined neon sunset, rendered edge to edge '
            'across the front, back and sleeves. Magenta, cyan and deep violet carry the whole '
            'garment, so there is no blank space and no seam where the artwork stops.'
        ),
    },
    'neon-bandit': {
        'name': 'Neon Bandit Hoodie',
        'slug': 'neon-bandit-hoodie',
        'blank': 'warm_velvets',
        'sku_base': 'ZNR3MG1Y',
        'sizes': ['Small', 'Medium', 'Large', 'XL', '2XL', '3XL', '4XL'],
        'image_prefix': '145072-Ai-TrashPanda',
        'price': Decimal('26.75'),
        'short_description': (
            'All-over-print neon raccoon hoodie in acid green and violet. '
            'Velvet-finish polyester, sizes S-4XL, printed and shipped on demand.'
        ),
        'blurb': (
            'A raccoon in full neon warpaint, printed edge to edge in acid green, violet and '
            'hot pink. The masked face lands across the chest and the pattern runs unbroken '
            'over the hood, sleeves and back.'
        ),
    },
    'neon-citrus': {
        'name': 'Neon Citrus Hoodie',
        'slug': 'neon-citrus-hoodie',
        'blank': 'warm_velvets',
        'sku_base': '5WX3G7KN',
        'sizes': ['Small', 'Medium', 'Large', 'XL', '2XL', '3XL', '4XL'],
        'image_prefix': '145064-Ai-OrangeSlice',
        'price': Decimal('26.75'),
        'short_description': (
            'All-over-print neon citrus hoodie in glowing orange and teal. '
            'Velvet-finish polyester, sizes S-4XL, printed and shipped on demand.'
        ),
        'blurb': (
            'Backlit orange slices scattered across a deep teal ground, printed edge to edge. '
            'The citrus pattern wraps the hood, sleeves and back with no repeat seam and no '
            'blank panels.'
        ),
    },
    'neon-driver': {
        'name': 'Neon Driver Pullover',
        'slug': 'neon-driver-pullover',
        'blank': 'warm_velvets',
        'sku_base': 'NGZO816W',
        'sizes': ['Small', 'Medium', 'Large', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL', '7XL'],
        'image_prefix': '786995-AI-Retro-Car',
        'price': Decimal('26.75'),
        'short_description': (
            'All-over-print retro car pullover in sunset orange and chrome blue. '
            'Velvet-finish polyester, sizes S-7XL, printed and shipped on demand.'
        ),
        'blurb': (
            'A retro coupe cutting through a chrome-and-sunset horizon, printed edge to edge '
            'across the garment. Runs S through 7XL - the widest size range in the shop.'
        ),
    },
}


def enabled_sizes(design: dict, blank: dict) -> list[tuple]:
    """Blank size rows filtered to the sizes this design can actually be ordered in.

    PopCustoms fixes the orderable size range per design at creation time, so a
    design is often narrower than its blank. Order follows the blank; SKU numbers
    are assigned sequentially over the result by the caller.
    """
    wanted = design.get('sizes')
    if not wanted:
        return list(blank['sizes'])

    by_label = {row[1]: row for row in blank['sizes']}
    unknown = [label for label in wanted if label not in by_label]
    if unknown:
        raise ValueError(
            f"{design['name']}: size(s) {', '.join(unknown)} are not in the "
            f"{blank['label']} size table. Fix the design's 'sizes' list or add the "
            f"row to BLANKS."
        )
    missing_cost = [label for label in wanted if label not in blank.get('costs', {})]
    if missing_cost:
        raise ValueError(
            f"{design['name']}: no supplier cost recorded for size(s) "
            f"{', '.join(missing_cost)} in the {blank['label']} cost table."
        )
    return [row for row in blank['sizes'] if row[1] in set(wanted)]


def build_description(design: dict, blank: dict) -> str:
    sizes = enabled_sizes(design, blank)
    size_run = f"{sizes[0][1]} through {sizes[-1][1]}"
    measured = [row for row in sizes if row[5] is not None]

    lines = [
        design['blurb'],
        '',
        '**Material & Print**',
        f"- {blank['material']}",
        '- All-over sublimation print: front, back, hood and sleeves',
        '- Drawstring hood, front kangaroo pocket, ribbed cuffs and hem',
        '- Unisex relaxed fit',
        '',
        '**Sizing**',
        f'- Available {size_run}',
    ]

    if measured:
        lines.append('- Garment measurements (inches):')
        for title, label, _sort, _weight, shoulder, length, half_chest, sleeve in measured:
            chest = half_chest * 2 if CHEST_AS_CIRCUMFERENCE else half_chest
            chest_word = 'Chest' if CHEST_AS_CIRCUMFERENCE else 'Chest (flat)'
            lines.append(
                f'  - {label}: Shoulder {shoulder}" / Length {length}" / '
                f'{chest_word} {chest}" / Sleeve {sleeve}"'
            )
        lines.append('- Allow 1-3cm variance; these are hand measurements.')
    else:
        lines.append('- See the sizing chart image for full measurements.')

    lines += [
        '',
        '**Care**',
        '- Machine wash cold, inside out',
        '- Do not bleach, do not tumble dry',
        '- Hang or lay flat to dry; cool iron on the reverse only',
        '',
        '**Made to order**',
        f"- {blank['fulfillment']}",
        '- Printed for you after you order, so nothing is warehoused and nothing is wasted',
    ]
    return '\n'.join(lines)


class Command(BaseCommand):
    help = 'Create or update an all-over-print hoodie product from the DESIGNS table.'

    def add_arguments(self, parser):
        parser.add_argument('design', nargs='?', help='Design key from DESIGNS.')
        parser.add_argument('--all', action='store_true', help='Seed every design in DESIGNS.')
        parser.add_argument('--skip-images', action='store_true', help='Do not touch ProductImage rows.')
        parser.add_argument('--dry-run', action='store_true', help='Roll back instead of committing.')
        parser.add_argument(
            '--deactivate-unlisted',
            action='store_true',
            help="Set is_active=False on existing variants that are not in the design's orderable size list.",
        )
        parser.add_argument(
            '--staging-dir',
            default='',
            help=f'Where the mockup files live. Defaults to <BASE_DIR>/{STAGING_DIRNAME}.',
        )

    def handle(self, *args, **options):
        if options['all']:
            keys = list(DESIGNS)
        elif options['design']:
            if options['design'] not in DESIGNS:
                raise CommandError(
                    f"Unknown design '{options['design']}'. Known: {', '.join(DESIGNS)}"
                )
            keys = [options['design']]
        else:
            raise CommandError('Give a design key, or --all. Known: ' + ', '.join(DESIGNS))

        staging = Path(options['staging_dir']) if options['staging_dir'] else Path(settings.BASE_DIR) / STAGING_DIRNAME

        try:
            with transaction.atomic():
                for key in keys:
                    self.seed_design(
                        key,
                        staging,
                        skip_images=options['skip_images'],
                        deactivate_unlisted=options['deactivate_unlisted'],
                    )
                if options['dry_run']:
                    self.stdout.write(self.style.WARNING('\n--dry-run: rolling back.'))
                    transaction.set_rollback(True)
        except Exception as exc:
            raise CommandError(f'Seeding failed, nothing committed: {exc}') from exc

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS('\nDone.'))

    # ----------------------------------------------------------------------

    def seed_design(self, key: str, staging: Path, *, skip_images: bool, deactivate_unlisted: bool) -> None:
        design = DESIGNS[key]
        blank = BLANKS[design['blank']]

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{design['name']} ({key})"))

        product, created = Product.objects.update_or_create(
            slug=design['slug'],
            defaults={
                'name': design['name'],
                'short_description': design['short_description'],
                'description': build_description(design, blank),
                'product_type': Product.ProductType.EXTERNAL,
                'default_source': Product.Source.POPCUSTOMS,
                'is_active': True,
            },
        )
        self.stdout.write(f"  product: {'created' if created else 'updated'}")

        self.seed_variants(product, design, blank, deactivate_unlisted=deactivate_unlisted)
        if not skip_images:
            self.seed_images(product, design, blank, staging)

    def seed_variants(self, product: Product, design: dict, blank: dict, *, deactivate_unlisted: bool) -> None:
        seen = []
        rows = enabled_sizes(design, blank)
        for position, row in enumerate(rows, start=1):
            title, label, _blank_order, weight, shoulder, length, half_chest, sleeve = row
            sort_order = position
            sku = f"{design['sku_base']}-{position}"
            chest = None
            if half_chest is not None:
                chest = half_chest * 2 if CHEST_AS_CIRCUMFERENCE else half_chest

            _variant, created = ProductVariant.objects.update_or_create(
                sku=sku,
                defaults={
                    'product': product,
                    'title': title,
                    'size_label': label,
                    'sort_order': sort_order,
                    'price': design['price'],
                    'supplier_price': blank['costs'][label],
                    'stock_quantity': 999,
                    'max_order_quantity': 100,
                    'weight_oz': weight,
                    'chest_width_in': chest,
                    'body_length_in': length,
                    'sleeve_length_in': sleeve,
                    'origin_country': 'US',
                    'is_active': True,
                },
            )
            seen.append(sku)
            cost = blank['costs'][label]
            landed = cost + CUSTOMS_DUTY_PER_ITEM
            margin = design['price'] - landed
            flag = '' if margin > 0 else '  <-- SELLING AT A LOSS'
            self.stdout.write(
                f"    {'+' if created else '='} {sku:<14} {label:<6} "
                f"retail ${design['price']}  landed ${landed}  margin ${margin}{flag}"
            )

        # Anything left over is a size this design can no longer be ordered in.
        # Leaving it buyable means taking money for something PopCustoms will not make.
        stale = product.variants.exclude(sku__in=seen)
        if stale.exists():
            skus = ', '.join(stale.values_list('sku', flat=True))
            if deactivate_unlisted:
                count = stale.update(is_active=False)
                self.stdout.write(self.style.WARNING(
                    f'    deactivated {count} unorderable variant(s): {skus}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"    WARNING: {stale.count()} variant(s) are live but not in this design's "
                    f'orderable size list: {skus}\n'
                    f'             Re-run with --deactivate-unlisted to take them off the storefront.'
                ))

    def seed_images(self, product: Product, design: dict, blank: dict, staging: Path) -> None:
        if not staging.is_dir():
            self.stdout.write(self.style.WARNING(f'    images: staging dir not found ({staging}), skipped'))
            return

        media_products = Path(settings.MEDIA_ROOT) / 'products'
        media_products.mkdir(parents=True, exist_ok=True)

        wanted = [
            (f"{design['image_prefix']}-im{n}of5.webp", f"{design['name']} {role}", n)
            for n, role in enumerate(MOCKUP_ROLES, start=1)
        ]
        chart = blank.get('sizing_chart_image')
        if chart:
            wanted.append((chart, f"{design['name']} sizing chart", len(MOCKUP_ROLES) + 1))

        for filename, alt_text, sort_order in wanted:
            source = staging / filename
            if not source.is_file():
                self.stdout.write(self.style.WARNING(f'    image missing, skipped: {filename}'))
                continue

            target = media_products / filename
            if not target.exists():
                shutil.copy2(source, target)

            _image, created = ProductImage.objects.update_or_create(
                product=product,
                image=f'products/{filename}',
                defaults={'alt_text': alt_text, 'sort_order': sort_order},
            )
            self.stdout.write(f"    {'+' if created else '='} image {filename}")
