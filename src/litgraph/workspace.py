"""A workspace: a folder with litgraph.toml, graph.json, notes/, AGENTS.md and .env."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
# Shell variables that redirect Claude Code away from its own sign-in: a relay (base URL), its token, a model.
ANTHROPIC_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                 "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                 "ANTHROPIC_SMALL_FAST_MODEL")
STARTER_DIR = Path(__file__).parent / "starter"


def topic_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:80]


@dataclass
class Topic:
    """One topic of a workspace: a folder with graph.json, review.md and notes/."""

    slug: str
    folder: Path

    @property
    def graph_path(self) -> Path:
        return self.folder / "graph.json"

    @property
    def review_path(self) -> Path:
        return self.folder / "review.md"

    @property
    def notes_dir(self) -> Path:
        return self.folder / "notes"

    @property
    def title(self) -> str:
        try:
            return str(json.loads(self.graph_path.read_text(encoding="utf-8")).get("title") or self.slug)
        except (OSError, ValueError):
            return self.slug

    def describe(self) -> dict:
        try:
            data = json.loads(self.graph_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        nodes = data.get("nodes") or []
        return {"slug": self.slug, "title": str(data.get("title") or self.slug), "description": str(data.get("description") or ""),
                "nodes": len(nodes), "edges": len(data.get("edges") or []), "proposed": sum(1 for n in nodes if n.get("status") == "proposed"),
                "has_review": self.review_path.exists(),
                "updated": datetime.fromtimestamp(self.graph_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds") if self.graph_path.exists() else ""}


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
    provider: str = "claude-code"    # "claude-code" (your Claude Code sign-in) or "anthropic" (an API key)
    model: str = DEFAULT_MODEL
    model_configured: bool = False   # a model named in litgraph.toml (else the provider's default)
    cli_path: str = ""               # claude-code: path to the Claude Code CLI, if not the bundled one
    ignore_anthropic_env: bool = False  # claude-code: drop ANTHROPIC_* variables so Claude Code uses its own sign-in
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
        """The first topic's graph (kept for single-topic commands)."""
        topics = self.topics()
        return topics[0].graph_path if topics else self.topics_dir / "main" / "graph.json"

    @property
    def topics_dir(self) -> Path:
        return self.root / "topics"

    def topics(self) -> list["Topic"]:
        """Every topic: a root graph.json (slug `main`) and each topics/<slug>/graph.json."""
        found = []
        if (self.root / "graph.json").exists():
            found.append(Topic("main", self.root))
        if self.topics_dir.exists():
            for folder in sorted(self.topics_dir.iterdir()):
                if (folder / "graph.json").exists():
                    found.append(Topic(folder.name, folder))
        return found

    def topic(self, slug: str | None) -> "Topic | None":
        topics = self.topics()
        if not slug:
            return topics[0] if topics else None
        return next((t for t in topics if t.slug == slug), None)

    def find_topic(self, text: str) -> "Topic | None":
        """A topic whose slug or title matches the text (case-insensitive, ignoring punctuation)."""
        key = topic_slug(text)
        if not key:
            return None
        for topic in self.topics():
            if topic.slug == key or topic_slug(topic.title) == key:
                return topic
        # Looser: the same words, ignoring order and small words ("MD coarse graining & acceleration" opens
        # "MD coarse-graining and acceleration for ion transport ...").
        stop = {"a", "an", "the", "and", "or", "of", "for", "in", "on", "to", "with", "by", "vs", "versus"}
        words = lambda text: {w for w in topic_slug(text).split("-") if w and w not in stop}  # noqa: E731
        asked = words(text)
        best, score = None, 0.0
        for topic in self.topics():
            have = words(topic.title) | words(topic.slug)
            if not asked or not have:
                continue
            overlap = len(asked & have) / min(len(asked), len(have))
            if overlap > score:
                best, score = topic, overlap
        return best if score >= 0.75 and len(asked) >= 2 else None

    def create_topic(self, title: str, description: str = "") -> "Topic":
        slug = topic_slug(title)
        if not slug:
            raise ValueError("A topic needs a name.")
        folder = self.topics_dir / slug
        if (folder / "graph.json").exists():
            return Topic(slug, folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "notes").mkdir(exist_ok=True)
        graph = {"schema": "2.0", "title": title.strip(), "description": description.strip(), "nodes": [], "edges": []}
        (folder / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return Topic(slug, folder)

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
            provider=str(model.get("provider", "claude-code")).strip().lower().replace("_", "-"),
            model=os.environ.get("ANTHROPIC_MODEL") or str(model.get("name") or DEFAULT_MODEL),
            model_configured=bool(os.environ.get("ANTHROPIC_MODEL") or model.get("name")),
            cli_path=str(model.get("cli_path", "")),
            ignore_anthropic_env=bool(model.get("ignore_anthropic_env", False)),
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
        if workspace.provider not in ("claude-code", "anthropic"):
            raise ValueError(f"[model] provider must be `claude-code` or `anthropic`, not `{workspace.provider}`.")
        if workspace.provider == "claude-code" and workspace.ignore_anthropic_env:
            for key in ANTHROPIC_ENV:
                os.environ.pop(key, None)
            workspace.model = str(model.get("name") or DEFAULT_MODEL)
            workspace.model_configured = bool(model.get("name"))
        return workspace

    def inherited_anthropic_env(self) -> list[str]:
        """ANTHROPIC_* variables from the shell that Claude Code would follow (a relay, another model, a key)."""
        return [key for key in ANTHROPIC_ENV if os.environ.get(key)]

    def api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")

    def ai_ready(self) -> tuple[bool, str]:
        """Whether the chat can run, and why not if it can't."""
        if self.provider == "claude-code":
            try:
                import claude_agent_sdk  # noqa: F401
            except ImportError:
                return False, "The claude-agent-sdk package is not installed: `pip install claude-agent-sdk`."
            return True, ""
        if not self.api_key():
            return False, "No ANTHROPIC_API_KEY: put it in the workspace's .env file (or set [model] provider = \"claude-code\")."
        return True, ""

    def model_label(self) -> str:
        if self.provider == "claude-code":
            return self.model if self.model_configured else "Claude Code (default model)"
        return self.model


def init_workspace(target: Path, title: str = "My research graph") -> list[Path]:
    """Create a new workspace from the starter files. Returns the files written."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "topics").mkdir(exist_ok=True)
    written = []
    for name, dest in (("litgraph.toml", "litgraph.toml"), ("AGENTS.md", "AGENTS.md"),
                       ("env.example", ".env.example"), ("gitignore", ".gitignore")):
        path = target / dest
        if path.exists():
            continue
        text = (STARTER_DIR / name).read_text(encoding="utf-8").replace("{{TITLE}}", title)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
