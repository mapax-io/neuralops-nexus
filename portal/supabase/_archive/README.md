# Legacy portal functions (archived 2026-10-18)

The three edge functions that were live in the Supabase project from the
0.8.0 era ("device login": permanent device_id, 30-day sessions, revocation,
auto-verify after login, shared X-NeuralOps-Token install secret). Replaced
by the Step 4 claim-code flow (../functions/) on the owner's installer-only
ruling: a typed code from the install's own screen, token-based proof the
install verifies itself, no shared secret, one claim ever.

Copied here verbatim from the dashboard before overwriting, per the
don't-overwrite-what-you-haven't-read rule. The old `device_codes` table may
still exist in the project — it is unused by the new flow (which uses
`device_requests`) and can be dropped after the new flow is verified
(owner's test-check-then-remove policy).
