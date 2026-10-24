# Release 1.0.0 — UI verification walkthrough (TC-R1..R10, detailed steps)

**Written 2026-10-23.** Click-by-click steps for the owner's live pass over
everything changed since the Oct 21/22 acceptance pass: the Stage 2
removals, viewer-can-post, supervisor pass-unless-broken, the memory-pass
hardening, and the 1.0.0 version stamp. The short case list lives in
TEST-CASES.md (§ RELEASE 1.0.0 UI VERIFICATION PASS). Run on the DEV stack.
**Hard-reload the frontend first (Ctrl+Shift+R).** Record one line per id:
`TC-R1 PASS` / `TC-R6 FAIL — <what you saw>`.

---

## TC-R1 — Four panes

1. Open any project → any topic.
2. Look at the right-side pane rail.

PASS if: exactly **Topics, Context, Schedules, Project** — no Recall, no
Deliverables, no blank button or broken icon. Click each of the four once;
each opens.

## TC-R2 — Keep is gone

1. In an OLD topic where a reply was once kept as a deliverable, hover a
   persona reply → open its actions (hover buttons / "…" menu).
2. Repeat on a NEW persona reply in any topic.

PASS if: no "Keep" action anywhere, no way to reach the keep dialog, and
the old topic's messages all render normally.

## TC-R3 — Remembered chip is gone

1. Open the old topic where replies showed "Remembered N things" (the one
   from the Oct 22 session is ideal).
2. Scroll the whole history slowly.

PASS if: no "Remembered" chip on any message, and no gap/error where the
chip used to sit.

## TC-R4 — Persona dialogs lost the Recall toggle

1. `/add-persona` in any topic (or project Personas tab → Add).
2. Scroll the whole dialog top to bottom.
3. Check: no Recall checkbox/switch; seats in order **Model → Router →
   Deep → Fallbacks → Advisor**. Cancel.
4. EDIT an existing persona (Personas tab → click one → Edit). Scroll
   fully.
5. Check: no Recall toggle. Change something trivial (add a space to the
   prompt) and **Save**.

PASS if: both dialogs clean, and the save succeeds without error.

## TC-R5 — A viewer can post

Setup: a viewer-only member in one topic. If none exists:
`/invite someone@example.com` in a single topic (topic-only invite =
viewer there); open the app as that user in a second browser or private
window.

1. As the viewer, open that topic.
2. Check: the composer (message box) is visible — no read-only banner.
3. Send a plain message ("hello from viewer").
4. Check: it posts; the owner window sees it too (realtime).
5. As the viewer, send a message that @mentions a persona.
6. Check: the persona call is REFUSED with a worded error (not silence,
   not a crash).
7. As the viewer, send one more plain message.
8. Check: it still posts normally after the refusal.

PASS if all of 2–8 hold.

## TC-R6 — Supervisor passes decent work

Setup: a chain with ≥2 persona steps and a supervisor persona assigned.

Part A — style is not a defect:
1. Make step 1 open-ended ("write a short summary of X") where any
   competent answer passes but wording could vary.
2. Run the chain in a topic; watch the supervisor's verdict after the
   stage.
3. Expect **APPROVE**, even if the wording/structure isn't what the
   supervisor model would have produced. A REDO purely over tone,
   structure or "could be clearer" = FAIL.

Part B — a real defect still gets caught:
4. Edit a step to demand a strict format ("answer ONLY as a JSON object
   with keys a, b") and arrange for it to miss (weak model, or phrase the
   task so prose is likely).
5. Run again.
6. Expect **REDO** with a note naming the concrete, fixable problem
   ("output was prose, not the required JSON") — not a vague "improve
   quality". FAIL only when it did not do its job at all.

## TC-R7 — Transcripts are never stored as memory (the big one)

1. In a topic, ask a persona with the shell capability: "run `ls -la` in
   the project folder and show me what's there". Approve the tool card.
2. Sanity: a real tool row appears and the output matches reality.
3. Let the reply fully finish (the memory pass runs at the end). Wait
   about a minute.
4. Open a NEW topic, same project, same persona. Ask: "what command did
   we run earlier today and what did it show?"
5. PASS if the reply: speaks in SUMMARY form ("earlier we listed the
   project folder; it contained …"), SAYS it's remembered material ("from
   our earlier work" or similar), shows NO `$`-prefixed transcript, and
   does NOT present the old output as a freshly run command (no tool row
   = no fresh-run claim).
6. FAIL if a verbatim terminal transcript appears, or the output is
   framed as a fresh run — that is the Oct 22 fabricated-date pattern and
   must be impossible now.
7. Extra: ask about a FACT from the first topic ("what files did it
   find?") — the useful fact should survive in memory; only the raw
   transcript form must be gone.

## TC-R8 — Retrieval announces itself

1. Take a long-running topic with real work in its history (the
   date-ranges topic qualifies).
2. Ask: "based on everything we did earlier in this topic, what were the
   key results?"
3. PASS if it uses remembered material but ATTRIBUTES it ("from our
   earlier work…", "as we found before…") and never frames old tool
   output as something it just executed in this reply.

## TC-R9 — Version 1.0.0 everywhere

1. Find the app's version display (footer / about / settings).
2. Check: shows **1.0.0**.
3. Check the server connection screen (or wherever server version/compat
   surfaces).
4. PASS if the server reports 1.0.0 and NO "server too old / update"
   warning appears anywhere during the whole pass.

## TC-R10 — Regression sweep (10 minutes)

In one topic, back to back:
1. Plain message → appears instantly (realtime works).
2. `@persona show me something @chart` → tool/approval card if needed →
   a chart renders.
3. Same with `@table` on a small ask → table renders.
4. Schedules pane → an existing schedule lists; open one.
5. Project pane → files list; open/preview one file.
6. The topic's running cost line updates after the persona replies.
7. `@session` → a follow-up without re-mentioning → persona answers →
   `@session close`.

PASS if everything behaves exactly as in the Oct 21–22 pass — nothing new
broken.

---

## Results (owner fills in)

| TC | Result | Note |
|---|---|---|
| TC-R1 | | |
| TC-R2 | | |
| TC-R3 | | |
| TC-R4 | | |
| TC-R5 | | |
| TC-R6 | | |
| TC-R7 | | |
| TC-R8 | | |
| TC-R9 | | |
| TC-R10 | | |
