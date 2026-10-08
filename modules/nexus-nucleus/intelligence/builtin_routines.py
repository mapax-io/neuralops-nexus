"""
The four routines every project starts with. Seeded by name
(intelligence/services.py seed_builtin_routines), so a project that already
has one keeps its edits -- built-ins are editable, never deletable.
"""
BUILTIN_ROUTINES = [
    {
        "name": "pr-description",
        "title": "PR description",
        "purpose": "Turn a branch's changes into a pull request description a reviewer can read in one pass.",
        "instructions": (
            "Write a pull request description for the changes you are given (a diff, a list of commits, or a summary).\n\n"
            "Structure it as: **What & why** (the problem and what the change does about it), **How** (the approach, and any "
            "alternative considered), **Files changed** (each significant file and its role), **Testing** (what was run and "
            "the result — only what you can see was run), **Breaking changes / migrations** (or \"None\"), **Reviewer focus** "
            "(where to look closely). Keep it factual: describe only what the changes show; never guess at intent you cannot see. "
            "Use the team's commit vocabulary (feat, fix, refactor, docs, test, chore) for the title."
        ),
    },
    {
        "name": "incident-summary",
        "title": "Incident summary",
        "purpose": "Write up an incident from the conversation and any logs, in the shape an on-call handover needs.",
        "instructions": (
            "Summarise the incident described in the conversation (and any logs or tool output you can read).\n\n"
            "Cover: **Impact** (who and what was affected, for how long), **Timeline** (timestamps as given, in order), "
            "**Cause** (only what the evidence supports — say \"unknown\" otherwise), **What fixed it**, **Follow-ups** "
            "(concrete actions with an owner where one is named). Separate facts from suspicions explicitly. Keep it under "
            "300 words unless the timeline needs more."
        ),
    },
    {
        "name": "weekly-digest",
        "title": "Weekly digest",
        "purpose": "Condense the period's discussion into decisions, progress, blockers and what needs a person.",
        "instructions": (
            "Write a digest of the period the person names (default: the last seven days) from this conversation and "
            "anything you are given.\n\n"
            "Sections: **Decisions made**, **Progress**, **Blockers and risks**, **Needs a decision** (questions still open, "
            "and who should answer). Attribute items to people by name where the conversation shows it. Bullet points, "
            "each one line; no preamble. If a section has nothing, say \"Nothing this period.\""
        ),
    },
    {
        "name": "meeting-notes",
        "title": "Meeting notes",
        "purpose": "Turn a transcript or a rough set of notes into clean notes with decisions and action items.",
        "instructions": (
            "Turn the notes or transcript you are given into meeting notes.\n\n"
            "Sections: **Attendees** (as given), **Summary** (three to five sentences), **Decisions**, **Action items** "
            "(one per line: owner — action — due date if said), **Open questions**. Keep the speakers' meaning; do not add "
            "conclusions nobody reached. If something is unclear in the source, mark it \"[unclear]\" rather than guessing."
        ),
    },
]
