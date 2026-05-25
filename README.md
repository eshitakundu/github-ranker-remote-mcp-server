# github-ranker-remote-mcp-server

A remote MCP server built with FastMCP that ranks GitHub candidates against a job's required skills.

## What it does

Give it a list of GitHub usernames, a job title, and required skills — it fetches each profile from the GitHub API, scores them by skill match (languages + repo topics), and returns ranked candidate data. A prompt primitive is included for the MCP client's LLM to format the output as a markdown report.

## Tools & Primitives

| Primitive | Name | Description |
|---|---|---|
| `@mcp.tool` | `rank_candidates` | Fetches GitHub profiles, scores each against required skills, returns ranked JSON |
| `@mcp.prompt` | `ranking_report` | Takes the tool output and returns a prompt for the client LLM to generate a markdown report |

## Usage

**Tool call:**
```json
{
  "usernames": ["torvalds", "gvanrossum", "antirez"],
  "job_title": "Backend Engineer",
  "skills": "Python, C, Go, docker, redis"
}
```

Skills matching checks:
- GitHub-reported top languages (e.g. `Python`, `TypeScript`, `Go`)
- Repo topic tags (e.g. `docker`, `fastapi`, `kubernetes`) — must be lowercase

**Prompt call:**
Pass the raw JSON string from `rank_candidates` into `ranking_report`. The MCP client's LLM generates the final markdown report — no external API call is made from this server.

## Stack

- [FastMCP](https://gofastmcp.com) — MCP server framework
- [httpx](https://www.python-httpx.org) — async GitHub API calls
- Python 3.11+

## Setup

```bash
uv init
uv add fastmcp httpx
```

Create a `.env` file in the project root:
```
GITHUB_TOKEN=your_token_here
```

`GITHUB_TOKEN` is optional but recommended — unauthenticated requests are rate-limited to 60/hour.

## Running locally

```bash
uv run python server.py
```

Server starts on `http://0.0.0.0:8000/mcp` using the `streamable-http` transport.

## Development / testing

```bash
uv run fastmcp dev inspector --server-spec server.py
```

Opens the MCP Inspector UI in the browser for interactive tool testing.

## Transport

Uses `streamable-http` — suitable for remote deployment. Clients must include:
```
Accept: application/json, text/event-stream
```

## Connecting to Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "github-ranker": {
      "type": "streamable-http",
      "url": "https://github-mcp-server-opoq.onrender.com/mcp"
    }
  }
}
```

`claude_desktop_config.json` is located at:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

## Deploying

Works on any platform that supports Python and persistent processes (Render, Railway, Fly.io).

Set `GITHUB_TOKEN` as an environment variable in your deployment dashboard.