"""
Built-in output type registrations.

Imported by apps/output_types/__init__.py to trigger registration.
To add a new output type, register a new OutputTypeSpec here — nothing else changes.
"""

from .registry import OutputTypeRegistry, OutputTypeSpec

# ── text ─────────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="text",
        render_as="text",
        label="Text",
        icon="align-left",
        system_instruction=(
            "Respond in clear, well-structured text or markdown. "
            "Use headings, lists, and code snippets where helpful. "
            "No special output wrapper needed."
        ),
        example_prompts=[
            "Explain how photosynthesis works",
            "What is the difference between TCP and UDP?",
            "Summarize this document",
            "Write a paragraph about climate change",
            "Tell me about machine learning",
            "What are the pros and cons of microservices?",
            "Help me understand recursion",
            "Describe the history of the internet",
        ],
    )
)



# ── html ─────────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="html",
        render_as="html",
        label="HTML Page",
        icon="globe",
        system_instruction=(
            "Respond with a complete, self-contained HTML page. "
            "Use this EXACT structure:\n\n"
            "<<<EMBED>>>\n"
            "One or two plain-English sentences describing what this page does (no HTML).\n"
            "<<<END_EMBED>>>\n"
            "<<<OUTPUT:html>>>\n"
            "<!DOCTYPE html>\n"
            "<html>...</html>\n"
            "<<<END_OUTPUT>>>\n\n"
            "You may import libraries from CDN (Chart.js, D3, etc.). "
            "The page runs in a sandboxed iframe — use inline CSS. No external fonts unless from CDN."
        ),
        example_prompts=[
            "Build an interactive web page",
            "Create an HTML dashboard",
            "Make a rich HTML report with styling",
            "Build a single-page HTML application",
        ],
    )
)

# ── chart ────────────────────────────────────────────────────────────────────
#
# The app renders this itself (ChartBlock, chart.js on a canvas): the model
# describes the chart, it never writes a page. A description is 5-10x fewer
# tokens than the HTML it replaced, follows the app's theme, and executes no
# script. The keys and limits below mirror the app's guard -- anything else is
# rejected there and shown as data, so the model must be told the shape exactly.

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="chart",
        render_as="chart",
        label="Chart",
        icon="bar-chart-2",
        system_instruction=(
            "OUTPUT FORMAT — your response must be exactly this structure, nothing else:\n\n"
            "<<<OUTPUT:chart>>>\n"
            "{ ...the chart description as JSON... }\n"
            "<<<END_OUTPUT>>>\n\n"
            "Begin your response with <<<OUTPUT:chart>>> on the very first line and end with "
            "<<<END_OUTPUT>>> on the very last line. No text before or after the markers, no "
            "markdown fences, no HTML — the app draws the chart itself.\n\n"
            "The description uses exactly these keys and no others:\n"
            "{\n"
            '  "type": "line" | "bar" | "pie" | "doughnut" | "polarArea" | "radar" | "scatter" | "bubble" | "mixed",  (doughnut, not donut)\n'
            '  "title": "short title, under 120 characters",\n'
            '  "subtitle": "what the encodings mean, e.g. bubble size = market cap · colour = sector",  (optional)\n'
            '  "labels": ["one x-axis category per data point"],\n'
            '  "groups": ["one group per point, e.g. its sector"],  (scatter, bubble only — optional; colour = group)\n'
            '  "datasets": [{ "label": "series name", "data": [numbers] }],\n'
            '  "axes": { "x": { "label": "Revenue", "prefix": "$", "suffix": "B", "scale": "time" }, "y": { "label": "Margin", "suffix": "%", "scale": "logarithmic", "min": 0, "max": 100 } },  (scale/min/max optional)\n'
            '  "legend": "top" | "bottom" | "left" | "right" | "none",  (optional)\n'
            '  "cutout": 60,     (doughnut only — hole size in percent, optional)\n'
            '  "gauge": true,    (doughnut only — a half ring, optional)\n'
            '  "stacked": true | false,      (bar, line, mixed only — optional)\n'
            '  "fill": true | false,         (line, radar, mixed only — optional; line becomes an area)\n'
            '  "orientation": "horizontal",  (bar, mixed only — optional)\n'
            '  "source": "where the figures come from",\n'
            '  "basis": "recalled" | "provided" | "tool"\n'
            "}\n\n"
            "Shapes by type:\n"
            "- line, bar, radar, pie, doughnut, polarArea: data is numbers, exactly one per label; null is a gap; "
            "a bar value may be [low, high] for a floating bar\n"
            '- a line, radar or mixed-line dataset may carry "smooth": true, "stepped": true, "dashed": true, and any series '
            'may carry "pointStyle": "circle" | "cross" | "crossRot" | "dash" | "line" | "rect" | "rectRounded" | "rectRot" | "star" | "triangle"\n'
            '- axes.x.scale "time" needs every label to be a date (YYYY-MM-DD); axes.y.scale "logarithmic" needs positive values\n'
            "- pie and doughnut take up to three datasets (rings); polarArea takes one\n"
            '- a series may carry "color": "#1baf7a" and a slice dataset "colors": ["#hex", ...] (one per slice); '
            "optional — the app keeps its own palette when a colour would not read on the theme\n"
            '- scatter: data is [{"x": number, "y": number}]; bubble: [{"x": number, "y": number, "r": number}] '
            "where r is the raw magnitude (the app scales it). For bubble, labels are REQUIRED: one name per "
            "bubble. For scatter they are optional point names — give them when the points are things "
            "(companies, countries). groups, when given, is one group per point and colour carries it\n"
            "- Units go on the axes as prefix/suffix, never inside the data\n"
            '- mixed: every dataset carries "type": "bar" or "line"\n'
            "- pie, doughnut, polarArea: exactly one dataset, non-negative values, at most 6 slices\n"
            "- radar: at least three labels (the axes)\n\n"
            "Rules:\n"
            "- At most 6 datasets — fold the rest into \"Other\"; at most 200 points per dataset\n"
            "- Plain numbers in data — no units, currency symbols or thousands separators\n"
            "- One y axis only. Two measures of different scale are two charts, not one\n"
            "- basis is required and must be honest: \"recalled\" for figures from your own knowledge, "
            "\"provided\" for figures the user gave you, \"tool\" for figures a tool returned\n"
            "- No markup (< or >) in any text\n"
            "- For a follow-up change, output the complete updated description again\n"
            '- More than one chart (different subjects, or measures of different scale): reply with '
            '{ "charts": [ description, description ] } — at most 4 — still inside the same single pair of markers'
        ),
        example_prompts=[
            "Show me a chart of sales over time",
            "Plot a bar graph of these numbers",
            "Visualise the data as a pie chart",
            "Create a line graph showing revenue trends",
            "Draw a comparison chart for these values",
            "Graph the population growth",
            "Chart the performance metrics",
            "Plot monthly statistics as a chart",
        ],
    )
)

# ── table ────────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="table",
        render_as="html",
        label="Table",
        icon="table",
        system_instruction=(
            "Respond with a complete, self-contained HTML page showing a styled data table. "
            "Wrap your entire response in output markers:\n\n"
            "<<<OUTPUT:table>>>\n"
            "<!DOCTYPE html>\n"
            "<html>...</html>\n"
            "<<<END_OUTPUT>>>\n\n"
            "Requirements:\n"
            "- Clean CSS with alternating row colours (zebra striping)\n"
            "- Sticky header row with distinct background\n"
            "- Responsive width, full-width table\n"
            "- body { margin: 8px; font-family: system-ui; }"
        ),
        example_prompts=[
            "Show me a table of countries and their GDP",
            "List the top programming languages in a table",
            "Tabulate this data for me",
            "Display these results in a structured table",
            "Create a comparison table",
            "Format this as a data table",
            "Show the records in tabular format",
        ],
    )
)

# ── diagram ──────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="diagram",
        render_as="text",
        label="Diagram",
        icon="git-branch",
        system_instruction=(
            "Respond with a Mermaid diagram. "
            "You MUST wrap your diagram in a standard markdown mermaid code block:\n\n"
            "```mermaid\n"
            "graph TD;\n"
            "  A-->B;\n"
            "```\n\n"
            "Supported diagram types: flowchart, sequenceDiagram, classDiagram, erDiagram, gantt, pie.\n"
            "CRITICAL: Do not output any HTML, even if previous messages in the chat history used HTML. Use ONLY plain text markdown mermaid blocks."
        ),
        example_prompts=[
            "Draw a flowchart of the user authentication process",
            "Create a sequence diagram for API calls",
            "Show the system architecture as a diagram",
            "Draw an entity relationship diagram",
            "Visualise the class hierarchy",
            "Create a flow diagram",
            "Show the state machine diagram",
            "Draw a process flow diagram",
        ],
    )
)

# ── form ─────────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="form",
        render_as="html",
        label="Form",
        icon="clipboard-list",
        system_instruction=(
            "Respond with a complete, self-contained HTML page containing a styled interactive form. "
            "Use this EXACT structure:\n\n"
            "<<<EMBED>>>\n"
            "One or two plain-English sentences describing the form's purpose and fields.\n"
            "<<<END_EMBED>>>\n"
            "<<<OUTPUT:form>>>\n"
            "<!DOCTYPE html>\n"
            "<html>...</html>\n"
            "<<<END_OUTPUT>>>\n\n"
            "Requirements:\n"
            "- Accessible form with proper labels and input types\n"
            "- Inline CSS for clean look\n"
            "- On submit: prevent default, validate required fields, show a success/summary message\n"
            "- No actual backend calls — handle everything client-side\n"
            "- body { max-width: 520px; margin: 24px auto; font-family: system-ui; }"
        ),
        example_prompts=[
            "Create a contact form",
            "Build a user registration form",
            "Make a survey form",
            "Design a feedback form",
            "Create a booking form",
            "Build an order form",
            "Create a sign-up form with validation",
        ],
    )
)

# ── terminal ─────────────────────────────────────────────────────────────────

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="terminal",
        render_as="terminal",
        label="Terminal",
        icon="terminal",
        system_instruction=(
            "Respond as terminal/shell output. "
            "Use this EXACT structure:\n\n"
            "<<<EMBED>>>\n"
            "One plain-English sentence summarising what commands were run and what they achieved.\n"
            "<<<END_EMBED>>>\n"
            "<<<OUTPUT:terminal>>>\n"
            "$ command-here\n"
            "output here\n"
            "$ next-command\n"
            "output here\n"
            "<<<END_OUTPUT>>>\n\n"
            "Rules:\n"
            "- Prefix every command with $ (dollar space)\n"
            "- Show realistic output after each command\n"
            "- No markdown — plain text only\n"
            "- Use correct UNIX/Windows conventions depending on context"
        ),
        example_prompts=[
            "Show me how to deploy with docker",
            "Run these shell commands and show the output",
            "Show git log output",
            "Set up a Python virtual environment in the terminal",
            "Show npm install output",
            "Run kubectl to check pod status",
            "Show docker ps output",
            "Install and configure nginx on Ubuntu",
        ],
    )
)

# ── code ─────────────────────────────────────────────────────────────────────
#
# Explicit-only: no example_prompts, so the classifier builds no centroid and
# never picks this on its own. The app renders this type as a bare <pre> -- the
# whole reply becomes a code block with no prose -- which is what someone who
# typed @code wants, and the wrong answer to an ordinary "how do I ..." question.

OutputTypeRegistry.register(
    OutputTypeSpec(
        name="code",
        render_as="code",
        label="Code",
        icon="code",
        system_instruction=(
            "Respond with source code only. "
            "Use this EXACT structure:\n\n"
            "<<<EMBED>>>\n"
            "One plain-English sentence describing what the code does.\n"
            "<<<END_EMBED>>>\n"
            "<<<OUTPUT:code>>>\n"
            "the code, exactly as it should be pasted into a file\n"
            "<<<END_OUTPUT>>>\n\n"
            "Rules:\n"
            "- Raw source only. No markdown, no fences -- the renderer shows the "
            "content verbatim, so backticks would appear literally\n"
            "- No prose before or after the code; explain inside it as comments\n"
            "- Complete and runnable as given, not a fragment with ellipses\n"
            "- For a follow-up change, output the complete updated file again"
        ),
    )
)


# Preflight: what a gated persona would do, as a plan for a person to approve,
# adjust or decline before any tool runs. The app renders it as a card with
# the decision controls; the keys mirror what the app reads.
OutputTypeRegistry.register(
    OutputTypeSpec(
        name="preflight",
        render_as="preflight",
        label="Preflight",
        icon="clipboard-check",
        system_instruction=(
            "You are proposing, not doing. No tool is available on this turn; do not pretend to run one. "
            "Lay out exactly what you would do so a person can approve, adjust or decline it.\n\n"
            "OUTPUT FORMAT — your response must be exactly this structure, nothing else:\n\n"
            "<<<OUTPUT:preflight>>>\n"
            "{ ...the plan as JSON... }\n"
            "<<<END_OUTPUT>>>\n\n"
            "Begin with <<<OUTPUT:preflight>>> on the very first line and end with <<<END_OUTPUT>>> on the very "
            "last line. No text before or after the markers, no markdown fences.\n\n"
            "The plan uses exactly these keys and no others:\n"
            "{\n"
            '  "summary": "one or two sentences: what you will achieve and how",\n'
            '  "steps": [ { "title": "one step, in the order you would take it", "tools": ["tool names this step uses, if any"], "writes": true | false } ],  (at most 12 steps; writes = the step changes files, systems or data outside this conversation)\n'
            '  "risks": ["anything the approver should weigh: irreversible effects, cost, uncertainty"]  (may be empty)\n'
            "}\n"
        ),
        example_prompts=[],
    )
)
