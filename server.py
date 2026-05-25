import os
import asyncio
import json
import httpx
from fastmcp import FastMCP

mcp = FastMCP("github-ranker")

GITHUB_API = "https://api.github.com"


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if tok := os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {tok}"
    return h


async def _fetch_github(client: httpx.AsyncClient, username: str) -> dict | None:
    profile_r, repos_r = await asyncio.gather(
        client.get(f"{GITHUB_API}/users/{username}", headers=_gh_headers()),
        client.get(
            f"{GITHUB_API}/users/{username}/repos",
            headers=_gh_headers(),
            params={"per_page": 100, "sort": "updated"},
        ),
    )
    if profile_r.status_code == 404:
        return None
    if profile_r.status_code == 429:
        return {"error": "rate_limited", "username": username}

    p     = profile_r.json()
    repos = repos_r.json() if repos_r.status_code == 200 else []

    lang_counts: dict[str, int] = {}
    total_stars = 0
    for r in repos:
        total_stars += r.get("stargazers_count", 0)
        if lang := r.get("language"):
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return {
        "username":      p["login"],
        "name":          p.get("name") or "",
        "bio":           p.get("bio") or "",
        "public_repos":  p.get("public_repos", 0),
        "followers":     p.get("followers", 0),
        "total_stars":   total_stars,
        "top_languages": sorted(lang_counts, key=lang_counts.__getitem__, reverse=True)[:5],
        "recent_repos": [
            {
                "name":   r["name"],
                "lang":   r.get("language") or "",
                "topics": r.get("topics", []),
            }
            for r in repos[:10]
            if not r.get("fork")
        ],
    }


def _score(candidate: dict, skills: list[str]) -> tuple[int, list[str]]:
    required = {s.strip().lower() for s in skills}
    signals: set[str] = set()
    for lang in candidate.get("top_languages") or []:
        signals.add(lang.lower())
    for repo in candidate.get("recent_repos") or []:
        if lang := repo.get("lang"):
            signals.add(lang.lower())
        for topic in repo.get("topics", []):
            signals.add(topic.lower())
    matched = required & signals
    return len(matched), [s.strip() for s in skills if s.strip().lower() in matched]


@mcp.tool()
async def rank_candidates(usernames: list[str], job_title: str, skills: str) -> str:
    """
    Fetch GitHub profiles for the given usernames and score each against
    the required skills. Returns structured candidate data as a JSON string
    — pass this output directly into the ranking_report prompt.

    usernames:  GitHub usernames, e.g. ["torvalds", "gvanrossum"]
    job_title:  role being hired for, e.g. "Backend Engineer"
    skills:     comma-separated — GitHub language names (Python, Go, TypeScript)
                and lowercase repo topic keywords (docker, fastapi, kubernetes)
    """
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch_github(client, u) for u in usernames])

    skill_list = [s.strip() for s in skills.split(",")]
    valid      = [r for r in results if r and "error" not in r]
    not_found  = [u for u, r in zip(usernames, results) if r is None]
    rate_lim   = [r["username"] for r in results if r and "error" in r]

    if not valid:
        return json.dumps({"error": "No valid profiles fetched.", "not_found": not_found})

    scored = sorted(
        [(*_score(c, skill_list), c) for c in valid],
        key=lambda x: (x[0], x[2].get("total_stars", 0)),
        reverse=True,
    )

    return json.dumps({
        "job_title":   job_title,
        "skills":      skills,
        "not_found":   not_found,
        "rate_limited": rate_lim,
        "ranking": [
            {
                "rank":          i + 1,
                "username":      c["username"],
                "name":          c.get("name", ""),
                "bio":           c.get("bio", ""),
                "score":         f"{score}/{len(skill_list)}",
                "matched":       matched,
                "top_languages": c.get("top_languages", []),
                "total_stars":   c.get("total_stars", 0),
                "public_repos":  c.get("public_repos", 0),
                "followers":     c.get("followers", 0),
            }
            for i, (score, matched, c) in enumerate(scored)
        ],
    }, indent=2)


@mcp.prompt()
def ranking_report(candidate_data: str) -> str:
    """
    Takes the JSON output from rank_candidates and returns a prompt
    that instructs the LLM to produce a clean markdown ranking report.

    candidate_data: the raw JSON string returned by the rank_candidates tool
    """
    return f"""You are a technical recruiter assistant.

Below is structured candidate data from GitHub. Generate a clean, concise markdown report with:
- A heading with the job title and required skills
- A ranked table: | Rank | Username | Score | Matched Skills | Stars |
- A 1-2 sentence technical assessment per candidate
- A final "Recommended Hire" section naming the top candidate with reasoning

Candidate data:
{candidate_data}

Output only the markdown report. No preamble."""


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)