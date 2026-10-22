"""
seed_catalog — push the BUNDLED default catalog into the DB (owner's ruling
2026-10-21: "while setting up server will include this command to push this
data into db"). A fresh or offline install is born with sensible defaults —
model list, context windows, max outputs, rates — instead of waiting for the
daily online refresh.

Two modes:

  manage.py seed_catalog
      Load intelligence/data/model_prices_seed.json and FILL MISSING rows
      only — a row the daily online refresh already wrote is fresher than a
      release snapshot and is never touched. Safe to run any number of times;
      part of the standard setup sequence, right after migrate.

  manage.py seed_catalog --regenerate
      RELEASE-TIME ONLY (needs network): fetch the live litellm catalog, trim
      it to our providers and the keys our parser reads, and REWRITE the
      bundled seed file. Run inside the dev container (the repo is mounted),
      review the diff, commit. This is how "default data is updated on every
      release" happens.

The seed file keeps litellm's own shape so intelligence/tasks.upsert_catalog
is the ONE parser for both the seed and the online refresh — shapes can never
drift apart.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "model_prices_seed.json"

# What --regenerate keeps from the live catalog: only providers our
# _PROVIDER_MAP knows, only keys upsert_catalog reads.
_KEEP_KEYS = (
    "litellm_provider",
    "input_cost_per_token", "output_cost_per_token", "cache_read_input_token_cost",
    "max_input_tokens", "max_tokens", "max_output_tokens",
)


class Command(BaseCommand):
    help = "Load the bundled model catalog into the DB (setup), or --regenerate the bundled file (release)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--regenerate", action="store_true",
            help="Fetch the live litellm catalog and rewrite the bundled seed file (release-time, needs network).",
        )

    def handle(self, *args, **options):
        if options["regenerate"]:
            self._regenerate()
        else:
            self._seed()

    def _seed(self):
        from intelligence.tasks import upsert_catalog

        if not SEED_PATH.exists():
            raise CommandError(
                f"Bundled seed not found at {SEED_PATH} — run `manage.py seed_catalog --regenerate` "
                "on a machine with network and commit the file."
            )
        try:
            data = json.loads(SEED_PATH.read_text())
        except ValueError as exc:
            raise CommandError(f"Bundled seed is not valid JSON: {exc}")
        # only_missing: the seed is a release snapshot — the daily online
        # refresh is always fresher and must never be downgraded by setup.
        saved = upsert_catalog(data, source="bundled-seed", only_missing=True)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {saved} new catalog rows from the bundle ({len(data)} in the file; "
            "existing rows left untouched)."
        ))

    def _regenerate(self):
        import httpx
        from django.conf import settings

        from intelligence.tasks import _PROVIDER_MAP

        url = getattr(settings, "MODEL_PRICES_URL", "")
        if not url:
            raise CommandError("MODEL_PRICES_URL is not set — nothing to fetch from.")
        self.stdout.write(f"Fetching {url} …")
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()

        trimmed = {}
        for raw_id, row in sorted(data.items()):
            if not isinstance(row, dict):
                continue
            if str(row.get("litellm_provider") or "") not in _PROVIDER_MAP:
                continue
            kept = {k: row[k] for k in _KEEP_KEYS if k in row}
            if len(kept) <= 1:
                continue  # litellm_provider alone (image-model rows) feeds the parser nothing
            trimmed[raw_id] = kept
        if not trimmed:
            raise CommandError("The live catalog yielded no rows for our providers — not overwriting the seed.")

        SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
        # One model per line: a release-to-release diff reads like a changelog.
        lines = ",\n".join(f" {json.dumps(k)}: {json.dumps(v, sort_keys=True)}" for k, v in trimmed.items())
        SEED_PATH.write_text("{\n" + lines + "\n}\n")
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(trimmed)} rows to {SEED_PATH} — review the diff and commit it with the release."
        ))
