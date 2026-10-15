"""
Step 6 ruling 5 (docs/NUCLEUS-REVAMP.md) — the phone-home.

ONE value ever leaves the customer's server: the install's total token count,
identified by NEURALOPS_INSTALL_TOKEN, POSTed when the application opens and
when it closes — nothing else, not switchable, and it FAILS SILENTLY offline
(air-gapped installs are unharmed). All detailed usage rows stay local —
they are the customer's own budget view (Step 1); only this single total
leaves. No request traces ever leave the server.

The collector is a Supabase edge function (the portal's infrastructure, like
device-request/poll): default {SUPABASE_URL}/functions/v1/phone-home,
overridable via NEURALOPS_PHONE_HOME_URL. Its contract:

    POST {NEURALOPS_PHONE_HOME_URL}
    headers: apikey + Authorization: Bearer {SUPABASE_ANON_KEY}
    body: {"install_token": str, "event": "open" | "close",
           "total_tokens": int}
    Any 2xx = received. The function stores (install_token, event,
    total_tokens, received_at) — that is the whole job.

Wired in core/asgi.py — the ONLY entry that runs exclusively as the server
process, so manage.py commands, tests and the celery workers never fire it.
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def send(event: str) -> bool:
    """POST the one total. True when a 2xx came back; False otherwise —
    and failure is DEBUG-logged, never raised, never retried."""
    url = getattr(settings, "NEURALOPS_PHONE_HOME_URL", "")
    install_token = getattr(settings, "NEURALOPS_INSTALL_TOKEN", "")
    if not url or not install_token:
        return False
    try:
        from django.db.models import Sum
        from nucleus.models import UsageRecord

        totals = UsageRecord.objects.aggregate(
            t_in=Sum("input_tokens"), t_out=Sum("output_tokens"))
        total = int(totals["t_in"] or 0) + int(totals["t_out"] or 0)
        anon = getattr(settings, "SUPABASE_ANON_KEY", "")
        response = httpx.post(
            url,
            json={"install_token": install_token, "event": event, "total_tokens": total},
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            timeout=TIMEOUT_SECONDS,
        )
        ok = 200 <= response.status_code < 300
        if ok:
            logger.info("[phone-home] %s sent (total_tokens=%d)", event, total)
        else:
            logger.debug("[phone-home] %s not accepted: %s", event, response.status_code)
        return ok
    except Exception as exc:  # noqa: BLE001 — offline/misconfigured is a normal state
        logger.debug("[phone-home] %s not sent: %s", event, exc)
        return False


def wire_open_and_close() -> None:
    """Called from core/asgi.py: 'open' in a background thread (boot is never
    blocked, and the DB may still be warming up — send() just fails silently
    then), 'close' best-effort at interpreter exit."""
    import atexit
    import threading

    threading.Thread(target=send, args=("open",), daemon=True, name="phone-home-open").start()
    atexit.register(send, "close")
