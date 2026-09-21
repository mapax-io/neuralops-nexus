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
MCP_CATALOG = [
    {
        "id": "github",
        "title": "GitHub",
        "description": "Issues, pull requests, code search and file contents in a repository.",
        "category": "Software",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-github",
        "url": None,
        "auth_type": "static_secrets",
        "needs": ["A GitHub personal access token with the scopes you want the persona to have"],
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/github",
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
        "docs": "https://support.atlassian.com/atlassian-rovo-mcp-server/",
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
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
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
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
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
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
    },
    {
        "id": "sentry",
        "title": "Sentry",
        "description": "Pull an issue's stack trace and context so a persona can work on the actual error.",
        "category": "Software",
        "server_type": "local",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-sentry",
        "url": None,
        "auth_type": "static_secrets",
        "needs": ["A Sentry auth token"],
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/sentry",
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
        "docs": "https://github.com/modelcontextprotocol/servers/tree/main/src/gdrive",
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
