from __future__ import annotations

from django.db import OperationalError, ProgrammingError

from .models import StoreSettings


def store_settings(request):
    try:
        store = StoreSettings.current()
    except (OperationalError, ProgrammingError):
        store = None
    return {'store_settings': store}
