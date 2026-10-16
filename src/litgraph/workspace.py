"""A workspace: a folder with litgraph.toml, graph.json, notes/, AGENTS.md and .env."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
STARTER_DIR = Path(__file__).parent / "starter"


def load_env_file(path: Path) -> None:
    """KEY=VALUE lines into the environment, without overriding variables that are already set."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Workspace:
    root: Path
    title: str = "Research knowledge graph"
    description: str = ""
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    max_tokens: int = 16000
    web_search: bool = True          # Anthropic's server-side web search and web fetch tools
    literature_search: bool = True   # Semantic Scholar / Crossref / arXiv lookups
    auto_apply: bool = False         # apply the model's graph proposals without asking
    fallbacks: bool = False          # Anthropic's server-side refusal fallback (beta)
    host: str = "127.0.0.1"
    port: int = 5058
    extra: dict = field(default_factory=dict)

    @property
    def graph_path(self) -> Path:
        return self.root / "graph.json"

    @property
    def notes_dir(self) -> Path:
        return self.root / "notes"

    @property
    def agents_path(self) -> Path:
        return self.root / "AGENTS.md"

    def instructions(self) -> str:
        return self.agents_path.read_text(encoding="utf-8") if self.agents_path.exists() else ""

    @classmethod
    def load(cls, root: Path | str | None = None) -> "Workspace":
        root = Path(root or os.environ.get("LITGRAPH_WORKSPACE") or Path.cwd()).resolve()
        config = {}
        toml_path = root / "litgraph.toml"
        if toml_path.exists():
            config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        load_env_file(root / ".env")
        project = config.get("project", {})
        model = config.get("model", {})
        server = config.get("server", {})
        agent = config.get("agent", {})
        workspace = cls(
            root=root,
            title=str(project.get("title", "Research knowledge graph")),
            description=str(project.get("description", "")),
            model=os.environ.get("ANTHROPIC_MODEL") or str(model.get("name", DEFAULT_MODEL)),
            effort=str(model.get("effort", "medium")),
            max_tokens=int(model.get("max_tokens", 16000)),
            fallbacks=bool(model.get("fallbacks", False)),
            web_search=bool(agent.get("web_search", True)),
            literature_search=bool(agent.get("literature_search", True)),
            auto_apply=bool(agent.get("auto_apply", False)),
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 5058)),
            extra=config,
        )
        return workspace

    def api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")


def init_workspace(target: Path, title: str = "My research graph") -> list[Path]:
    """Create a new workspace from the starter files. Returns the files written."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "notes").mkdir(exist_ok=True)
    written = []
    for name, dest in (("litgraph.toml", "litgraph.toml"), ("AGENTS.md", "AGENTS.md"),
                       ("env.example", ".env.example"), ("gitignore", ".gitignore"), ("graph.json", "graph.json")):
        path = target / dest
        if path.exists():
            continue
        text = (STARTER_DIR / name).read_text(encoding="utf-8").replace("{{TITLE}}", title)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
