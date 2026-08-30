"""
Jarvis MCP server — read-only status/visibility tools over the MGEQuant trading fleet.

Scope, deliberately: this exposes what's actually on disk — git history, changelogs,
roadmaps, dev logs, screenshots, and Claude's own memory notes about backtest verdicts
and fleet topology. There is no live P&L or dashboard state file anywhere in these repos
(NinjaTrader only renders the dashboard on-chart), so this server does not and cannot
expose live trading state. It is read-only: no tool here can place, modify, or cancel
a trade, or write into any project file.

Run with: python jarvis_server.py
Registered with Claude Code / Claude Desktop over stdio.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("jarvis")

TRADING_ROOT = Path("F:/Trading Software")
MEMORY_DIR = Path(
    r"C:\Users\maric\.claude\projects\f--Trading-Software-MGEQuant\memory"
)

TEXT_EXTENSIONS = {".md", ".txt", ".py", ".cs", ".json", ".yaml", ".yml", ".csv"}
MAX_FILE_BYTES = 200_000


@dataclass(frozen=True)
class Project:
    path: Path
    is_git_repo: bool


PROJECTS: dict[str, Project] = {
    "mgequant": Project(TRADING_ROOT / "MGEQuant", True),
    "qax": Project(TRADING_ROOT / "QAX", True),
    "marketcoach": Project(TRADING_ROOT / "MarketCoach", True),
    "tradepilot": Project(TRADING_ROOT / "TradePilot", True),
    "exhaustionfade": Project(TRADING_ROOT / "Releases" / "ExhaustionFade", False),
    "renkopullbackdoji": Project(TRADING_ROOT / "Releases" / "RenkoPullbackDoji", False),
}


def _project(name: str) -> Project:
    proj = PROJECTS.get(name.lower())
    if proj is None:
        known = ", ".join(sorted(PROJECTS))
        raise ValueError(f"Unknown project '{name}'. Known projects: {known}")
    return proj


def _resolve_within(root: Path, relpath: str) -> Path:
    candidate = (root / relpath).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise ValueError(f"Path '{relpath}' escapes project root")
    return candidate


@mcp.tool()
def list_projects() -> list[dict]:
    """List the trading-fleet projects Jarvis knows about, with their paths and
    whether each is a standalone git repo."""
    return [
        {"name": name, "path": str(proj.path), "is_git_repo": proj.is_git_repo}
        for name, proj in sorted(PROJECTS.items())
    ]


@mcp.tool()
def list_memory_notes() -> list[dict]:
    """List Claude's persistent memory notes about this fleet (backtest verdicts,
    fleet topology, rollout decisions, etc.), parsed from MEMORY.md's index."""
    index = MEMORY_DIR / "MEMORY.md"
    if not index.exists():
        return []
    entries = []
    pattern = re.compile(r"^-\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)\s*—\s*(?P<hook>.+)$")
    for line in index.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            entries.append(m.groupdict())
    return entries


@mcp.tool()
def read_memory_note(name: str) -> str:
    """Read the full content of one memory note. `name` may be the memory's slug
    (filename without .md, e.g. 'project_fleet_machine_topology') or a fragment of
    its title/filename — the closest match is returned. Raises if nothing matches
    or the match is ambiguous."""
    needle = name.lower().strip()
    candidates = sorted(p for p in MEMORY_DIR.glob("*.md") if p.name != "MEMORY.md")

    exact = [p for p in candidates if p.stem.lower() == needle]
    if len(exact) == 1:
        return exact[0].read_text(encoding="utf-8")

    fuzzy = [p for p in candidates if needle in p.stem.lower()]
    if len(fuzzy) == 1:
        return fuzzy[0].read_text(encoding="utf-8")
    if len(fuzzy) > 1:
        names = ", ".join(p.stem for p in fuzzy)
        raise ValueError(f"'{name}' is ambiguous, matches: {names}")
    raise ValueError(f"No memory note matches '{name}'")


@mcp.tool()
def read_project_doc(project: str, relpath: str) -> str:
    """Read a text file (docs, changelogs, roadmaps, source — .md/.txt/.py/.cs/
    .json/.yaml/.csv only, capped at 200KB) from within one project's repo.
    `project` is one of list_projects()'s names; `relpath` is relative to that
    project's root, e.g. 'CHANGELOG.md' or 'Documentation/Roadmap.md'."""
    proj = _project(project)
    target = _resolve_within(proj.path, relpath)
    if not target.exists() or not target.is_file():
        raise ValueError(f"No such file: {relpath}")
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"Refusing to read non-text extension '{target.suffix}'")
    data = target.read_bytes()[:MAX_FILE_BYTES]
    return data.decode("utf-8", errors="replace")


@mcp.tool()
def git_log(project: str, count: int = 10) -> str:
    """Recent commit history for a project (oneline, dated). `count` caps how many
    commits to show (default 10)."""
    proj = _project(project)
    if not proj.is_git_repo:
        raise ValueError(f"'{project}' is not a git repo")
    result = subprocess.run(
        ["git", "log", f"-n{max(1, min(count, 200))}", "--date=short",
         "--pretty=format:%h %ad %s"],
        cwd=proj.path, capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


@mcp.tool()
def git_status(project: str) -> dict:
    """Current branch and working-tree status (clean or list of changed paths)
    for a project."""
    proj = _project(project)
    if not proj.is_git_repo:
        raise ValueError(f"'{project}' is not a git repo")
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=proj.path, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=proj.path, capture_output=True, text=True, timeout=15,
    ).stdout
    changes = [line for line in porcelain.splitlines() if line.strip()]
    return {"branch": branch, "clean": not changes, "changed_paths": changes}


@mcp.tool()
def list_screenshots(project: str, subdir: str = "", limit: int = 20) -> list[dict]:
    """List the most recently modified screenshots under a project's Screenshots
    folder (optionally a subfolder), newest first. Screenshot timestamps are the
    only on-disk evidence of when a strategy/indicator was last confirmed live,
    since NinjaTrader dashboards aren't written to any state file."""
    proj = _project(project)
    root = proj.path / "Screenshots"
    if subdir:
        root = _resolve_within(proj.path / "Screenshots", subdir)
    if not root.exists():
        return []
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[: max(1, min(limit, 200))]:
        stat = p.stat()
        out.append({
            "relpath": str(p.relative_to(proj.path)),
            "modified": __import__("datetime").datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat(timespec="seconds"),
            "size_bytes": stat.st_size,
        })
    return out


@mcp.tool()
def search_dev_logs(project: str, query: str, max_results: int = 20) -> list[dict]:
    """Case-insensitive substring search across a project's development logs
    (Documentation/DevelopmentLogs or DevelopmentLogs). Returns matching lines
    with file path and line number."""
    proj = _project(project)
    for candidate in ("Documentation/DevelopmentLogs", "DevelopmentLogs"):
        log_root = proj.path / candidate
        if log_root.exists():
            break
    else:
        return []

    needle = query.lower()
    hits = []
    for path in sorted(log_root.rglob("*.md")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if needle in line.lower():
                hits.append({
                    "file": str(path.relative_to(proj.path)),
                    "line": i,
                    "text": line.strip(),
                })
                if len(hits) >= max_results:
                    return hits
    return hits


if __name__ == "__main__":
    mcp.run(transport="stdio")
