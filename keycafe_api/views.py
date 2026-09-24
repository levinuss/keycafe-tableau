from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from .keycafe import (
    KeycafeError,
    fetch_groups,
    fetch_keys,
    has_server_credentials,
    resolve_auth,
)
from .demo import demo_groups, demo_keys, demo_mode_enabled


@require_GET
@never_cache
def config(request):
    demo_mode = demo_mode_enabled()
    return JsonResponse(
        {
            "keycafeConfigured": has_server_credentials(),
            "demoMode": demo_mode,
            "ready": demo_mode or has_server_credentials(),
        }
    )


@require_GET
@never_cache
def groups(request):
    if demo_mode_enabled():
        return JsonResponse({"groups": demo_groups()})

    return _keycafe_response(
        lambda auth: {
            "groups": fetch_groups(auth, request.GET.get("organization")),
        },
    )


@require_GET
@never_cache
def keys(request):
    if demo_mode_enabled():
        return JsonResponse(demo_keys(group=request.GET.get("group")))

    return _keycafe_response(
        lambda auth: fetch_keys(
            auth,
            group=request.GET.get("group"),
            organization=request.GET.get("organization"),
        ),
    )


@never_cache
def frontend_index(_request):
    index_path = settings.BASE_DIR / "frontend" / "dist" / "index.html"
    if index_path.exists():
        return FileResponse(index_path.open("rb"), content_type="text/html")

    return HttpResponse(
        "Die Svelte-Anwendung wurde noch nicht gebaut. Bitte `npm run build` ausführen oder Vite mit `npm run dev` starten.",
        content_type="text/plain",
        status=503,
    )


@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


def _keycafe_response(handler):
    try:
        auth = resolve_auth()
        return JsonResponse(handler(auth))
    except KeycafeError as error:
        return JsonResponse(
            {"error": str(error)},
            status=error.status,
        )
