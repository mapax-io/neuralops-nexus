"""
python manage.py seed_avatars [--count N] [--force]

One-off fetch of a preset avatar pool from DiceBear (https://www.dicebear.com),
cached locally under MEDIA_ROOT/avatars/pool/<kind>/. Safe to re-run --
skips any file that already exists unless --force is passed. See #148.

Two styles are used so a user's identity type is visually distinguishable
at a glance, on top of the existing bubble-color distinction in the UI:
  - human   -> "avataaars" (friendly cartoon people)
  - persona -> "bottts"    (robot/bot avatars)

assign_avatar() (authn/services.py) picks a random file from the matching
pool at User-creation time (real users via auth_verify(), personas via
their identity_user shadow user in intelligence/services.py:create_persona()).
"""
import httpx
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

DICEBEAR_BASE = "https://api.dicebear.com/9.x"
# Personas only. The human pool was "avataaars" -- cartoon faces with hair --
# and assigning one at random put a face of the wrong apparent gender on real
# teammates. People now fall back to the initials the UI renders for an empty
# avatar, which is accurate by construction; see assign_avatar() in
# authn/services.py. A persona is a robot, so "bottts" claims nothing about
# anyone.
DICEBEAR_STYLES = {
    "persona": "bottts",
}


class Command(BaseCommand):
    help = "Fetch and cache a preset pool of DiceBear avatars for users/personas (#148)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=60,
            help="Avatars per style/kind (default: 60).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Re-fetch and overwrite even if a file already exists.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        force = options["force"]

        pool_root = Path(settings.MEDIA_ROOT) / "avatars" / "pool"
        fetched, skipped, failed = 0, 0, 0

        with httpx.Client(timeout=15.0) as client:
            for kind, dicebear_style in DICEBEAR_STYLES.items():
                out_dir = pool_root / kind
                out_dir.mkdir(parents=True, exist_ok=True)

                self.stdout.write(f"-- {kind} ({dicebear_style}) --")

                for i in range(1, count + 1):
                    out_path = out_dir / f"{i:03d}.png"
                    if out_path.exists() and not force:
                        skipped += 1
                        continue

                    # Deterministic seed -> same avatar every re-run, so
                    # --force reproduces the exact same pool, not a new one.
                    seed = f"{kind}-{i}"
                    url = f"{DICEBEAR_BASE}/{dicebear_style}/png"
                    try:
                        resp = client.get(url, params={"seed": seed, "size": 128})
                        resp.raise_for_status()
                    except httpx.HTTPError as exc:
                        failed += 1
                        self.stderr.write(self.style.WARNING(f"  {out_path.name}: {exc}"))
                        continue

                    out_path.write_bytes(resp.content)
                    fetched += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Fetched {fetched}, skipped {skipped} (already cached), failed {failed}."
        ))
        self.stdout.write(f"Pool location: {pool_root}")
