import json

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .demo import demo_groups, demo_keys, demo_mode_enabled
from .groups import delete_group, get_group, list_groups, save_group
from .keycafe import (
    KeycafeError,
    fetch_inventory,
    fetch_keys,
    has_server_credentials,
    resolve_auth,
)


@require_GET
@never_cache
def config(request):
    demo_mode = demo_mode_enabled()
    return JsonResponse(
        {
            "csrfToken": get_token(request),
            "keycafeConfigured": has_server_credentials(),
            "demoMode": demo_mode,
            "ready": demo_mode or has_server_credentials(),
        }
    )


@require_http_methods(["GET", "POST"])
@never_cache
def groups(request):
    if request.method == "GET":
        if demo_mode_enabled():
            return JsonResponse({"groups": demo_groups()})
        return _local_response(lambda: {"groups": list_groups()})
    return _local_response(lambda: {"group": save_group(_json_body(request))})


@require_http_methods(["PUT", "DELETE"])
@never_cache
def group_detail(request, group_id):
    def handler():
        if request.method == "DELETE":
            delete_group(group_id)
            return {"deleted": True}
        return {"group": save_group(_json_body(request), group_id)}
    return _local_response(handler)


@require_GET
@never_cache
def inventory(request):
    def picker_rows(rows):
        return {"keys": [{"id": key["id"], "name": key.get("name") or f"Schlüssel {key['id']}",
                          "serialNumber": key.get("serialNumber") or ""}
                         for key in rows if key.get("id") is not None]}

    if demo_mode_enabled():
        return JsonResponse(picker_rows(demo_keys()["keys"]))
    return _keycafe_response(lambda auth: picker_rows(fetch_inventory(auth)))


@require_GET
@never_cache
def keys(request):
    if demo_mode_enabled():
        return JsonResponse(demo_keys(group=request.GET.get("group")))
    def handler(auth):
        group_id = request.GET.get("group")
        group = get_group(group_id) if group_id else None
        return fetch_keys(auth, key_ids=group["keyIds"] if group else None)
    return _keycafe_response(handler)


def _json_body(request):
    try:
        return json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise KeycafeError(400, "Ungültige JSON-Daten.") from None


def _local_response(handler):
    try:
        if demo_mode_enabled():
            raise KeycafeError(400, "Gruppen können nur im Livebetrieb bearbeitet werden.")
        return JsonResponse(handler())
    except KeycafeError as error:
        return JsonResponse({"error": str(error)}, status=error.status)


@require_GET
@never_cache
def frontend_index(_request):
    index_path = settings.BASE_DIR / "frontend" / "dist" / "index.html"
    if index_path.exists():
        return FileResponse(index_path.open("rb"), content_type="text/html; charset=utf-8")

    return HttpResponse(
        "Die Svelte-Anwendung wurde noch nicht gebaut. Bitte `npm run build` ausführen oder Vite mit `npm run dev` starten.",
        content_type="text/plain; charset=utf-8",
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
