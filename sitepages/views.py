"""The pages a shop owes its customers: what it is, what it promises, what it
keeps, how it behaves and whether it is up.

Plain renders, except /status/, which asks the database one question. They stay
independent of the catalogue and checkout so they answer even when an order
cannot be placed.
"""
from django.db import connection
from django.shortcuts import render
from django.views.decorators.http import require_GET

# One place to bump when the policies change; every policy page shows it.
POLICY = {'effective': '2026-09-14', 'updated': '2026-09-14', 'version': '1.0'}


def _page(request, name, extra=None):
    return render(request, f'sitepages/{name}.html', {'policy': POLICY, **(extra or {})})


@require_GET
def about(request):
    return _page(request, 'about')


@require_GET
def terms(request):
    return _page(request, 'terms')


@require_GET
def privacy(request):
    return _page(request, 'privacy')


@require_GET
def guidelines(request):
    return _page(request, 'guidelines')


@require_GET
def faq(request):
    return _page(request, 'faq')


@require_GET
def support(request):
    return _page(request, 'support')


@require_GET
def changelog(request):
    return _page(request, 'changelog')


@require_GET
def status(request):
    """A summary, not a diagnostic: the shop is serving and its database
    answers. Detail that would help someone map the deployment stays out."""
    database = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        database = False
    return _page(request, 'status', {'overall': 'ok' if database else 'degraded', 'database': database})
