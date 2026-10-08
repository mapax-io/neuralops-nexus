"""
scheduling/hooks_api.py -- the public side of inbound hooks (W12).

Mounted WITHOUT auth (the router sets none, and the API has no global default),
so this is the one public write path in nucleus: whoever holds a hook's token
can make its persona answer in its topic, as the person who created it. Every
rule that keeps that safe lives in scheduling/hooks.py; this module is HTTP
only -- read the body, call fire(), turn a HookError into its status.

Answers are deliberately thin. An unknown token is a flat 404 with no hint that
a hook ever existed there, and no response says anything about the topic, the
persona or the company behind it.
"""
import logging

from django.http import JsonResponse
from ninja import Router

from scheduling import hooks as hook_svc
from scheduling.hooks import HookError
from scheduling.schema import HookFireIn

logger = logging.getLogger(__name__)

# No auth= : the token in the path is the credential.
router = Router(tags=["Inbound hooks"])


def _answer(status: int, detail: str) -> JsonResponse:
    response = JsonResponse({"detail": detail}, status=status)
    if status == 429:
        response["Retry-After"] = str(hook_svc.RATE_WINDOW_SECONDS)
    return response


@router.post("/{token}/")
async def fire_hook(request, token: str, payload: HookFireIn):
    """POST /api/v1/hooks/{token}/ -- the persona answers in the hook's chat."""
    from asgiref.sync import sync_to_async

    # The lookup is inside the try as well: an error raised there would otherwise
    # reach Django's debug 500 page, which prints this frame's locals -- the token
    # among them -- straight into the response (audit, 2026-09-21).
    hook = None
    try:
        hook = await sync_to_async(hook_svc.hook_for_token)(token)
        if hook is None:
            return _answer(404, "No such hook.")
        await hook_svc.fire(hook, payload.text, payload.data)
    except HookError as e:
        return _answer(e.status, e.detail)
    except Exception:  # noqa: BLE001 -- a sender learns nothing about our internals
        logger.exception("[hook] fire failed for %s", hook.id if hook else "an unknown token")
        if hook is not None:
            await sync_to_async(hook_svc._record)(hook, ok=False, error="The server could not post this fire.")
        return _answer(500, "The server could not post this fire.")
    return JsonResponse({"ok": True})
