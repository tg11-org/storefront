from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .webhooks import parse_payload, record_shipping_webhook, verify_shared_secret


@csrf_exempt
@require_POST
def easypost_webhook(request):
    if not verify_shared_secret(request, settings.EASYPOST_WEBHOOK_SECRET):
        return HttpResponse(status=403)
    try:
        payload = parse_payload(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid json'}, status=400)
    event = record_shipping_webhook('easypost', payload)
    return JsonResponse({'received': True, 'processed': event.processed})


@csrf_exempt
@require_POST
def shippo_webhook(request):
    if not verify_shared_secret(request, settings.SHIPPO_WEBHOOK_SECRET):
        return HttpResponse(status=403)
    try:
        payload = parse_payload(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid json'}, status=400)
    event = record_shipping_webhook('shippo', payload)
    return JsonResponse({'received': True, 'processed': event.processed})
