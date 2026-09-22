"""
The tool catalog (W11): tool servers a team is likely to want, as content.

Not a registry and not a marketplace — a hand-kept list whose only job is to
save someone reading a README to learn which URL to paste and which secret to
have ready. Nothing here is a credential, and nothing is fetched at runtime:
picking an entry pre-fills the create dialog the person already uses, and the
server row is created exactly as a typed one would be.

Keeping it current is a maintenance job; it is listed in docs/OPEN-ITEMS.md so
it does not quietly rot.
"""

# id: stable, referenced by the app. url: what goes in the create dialog, with
# {placeholders} the person must replace. needs: what they should have ready
# BEFORE clicking add -- a token, a workspace name -- never the secret itself.
# The docs links are checked by hand when this file changes -- they 404 silently
# otherwise, which is how every card but Git pointed at folders that had moved
# (2026-09-22). The reference servers for Postgres, SQLite, Slack and Google
# Drive now live in modelcontextprotocol/servers-archived: still installable,
# no longer maintained, and the link says so. GitHub and Sentry run official
# hosted servers with a sign-in, so those entries point there instead.
MCP_CATALOG = [
    {
        "id": "github",
        "title": "GitHub",
        "description": "GitHub's hosted server: issues, pull requests, code search and file contents, through your own GitHub sign-in.",
        "category": "Software",
        "server_type": "hosted",
        "transport": "http",
        "command": None,
        "url": "https://api.githubcopilot.com/mcp/",
        "auth_type": "oauth2",
        "needs": ["A GitHub account with access to the repositories you want the persona to reach"],
        "docs": "https://github.com/github/github-mcp-server",
    },
    {
        "id": "atlassian",
        "title": "Jira & Confluence",
        "description": "Atlassian's hosted server: issues, sprints and pages, through your own Atlassian sign-in.",
        "category": "Software",
        "server_type": "hosted",
        "transport": "http",
        "command": None,
        "url": "https://mcp.atlassian.com/v1/mcp",
        "auth_type": "oauth2",
        "needs": ["An Atlassian account with access to the site you want to reach"],
        "docs": "https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/",
    },
    {
        "id": "postgres",
        "title": "PostgreSQL",
        "description": "Read-only SQL against a database, with the schema exposed so a persona can write queries.",
        "category": "Data",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-postgres {connection-url}",
        "url": None,
        "auth_type": "static_secrets",
        "needs": ["A connection URL for a role that may only read"],
        "docs": "https://github.com/modelcontextprotocol/servers-archived/tree/main/src/postgres",
    },
    {
        "id": "sqlite",
        "title": "SQLite",
        "description": "A single database file on the server — useful for a project's own small store.",
        "category": "Data",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-sqlite --db-path {path-to.db}",
        "url": None,
        "auth_type": "none",
        "needs": ["A path the server can read, inside the project folder"],
        "docs": "https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite",
    },
    {
        "id": "slack",
        "title": "Slack",
        "description": "Read channels and post messages as an app you install in your workspace.",
        "category": "Communication",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-slack",
        "url": None,
        "auth_type": "static_secrets",
        "needs": ["A Slack bot token", "The workspace (team) id"],
        "docs": "https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack",
    },
    {
        "id": "sentry",
        "title": "Sentry",
        "description": "Sentry's hosted server: pull an issue's stack trace and context so a persona can work on the actual error, through your own Sentry sign-in.",
        "category": "Software",
        "server_type": "hosted",
        "transport": "http",
        "command": None,
        "url": "https://mcp.sentry.dev/mcp",
        "auth_type": "oauth2",
        "needs": ["A Sentry account with access to the organisation you want to reach"],
        "docs": "https://docs.sentry.io/product/sentry-mcp/",
    },
    {
        "id": "google-drive",
        "title": "Google Drive",
        "description": "Search and read documents and sheets a persona has been given access to.",
        "category": "Documents",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-gdrive",
        "url": None,
        "auth_type": "oauth2",
        "needs": ["A Google Cloud project with the Drive API on, and its OAuth client"],
        "docs": "https://github.com/modelcontextprotocol/servers-archived/tree/main/src/gdrive",
    },
    {
        "id": "git",
        "title": "Git",
        "description": "History, diffs and blame for a repository already on the server.",
        "category": "Software",
        "server_type": "local",
        "transport": "stdio",
        "command": "mcp-server-git --repository {path-to-repo}",
        "url": None,
        "auth_type": "none",
        "needs": ["A repository inside the project folder"],
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/git",
    },
]

CATEGORIES = ["Software", "Data", "Communication", "Documents"]


def catalog() -> list[dict]:
    """The catalog as the app reads it. A copy, so a caller cannot edit the module."""
    return [dict(entry) for entry in MCP_CATALOG]


def entry(entry_id: str) -> dict | None:
    return next((dict(e) for e in MCP_CATALOG if e["id"] == entry_id), None)
