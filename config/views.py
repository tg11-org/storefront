from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse


def healthcheck(request):
    return JsonResponse({'status': 'ok'})


def favicon(request, filename: str):
    path = settings.BASE_DIR / filename
    if filename not in {'favicon.ico', 'favicon.png'} or not path.exists():
        raise Http404
    content_type = 'image/x-icon' if filename.endswith('.ico') else 'image/png'
    return FileResponse(path.open('rb'), content_type=content_type)
