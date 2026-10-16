"""Look papers up on the open literature APIs: Semantic Scholar, Crossref, arXiv.

No API keys are needed. Semantic Scholar is tried first (best metadata and abstracts), then Crossref
(DOIs and venues), then arXiv (preprints). Each returns a list of paper dicts with the same keys.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from urllib import error, parse, request

TIMEOUT = 20
USER_AGENT = "litgraph/0.1 (+https://github.com/deng-group/wendao-research; research knowledge graph)"


def _get(url: str, headers: dict | None = None) -> bytes:
    req = request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with request.urlopen(req, timeout=TIMEOUT) as response:
        return response.read()


def _paper(**fields) -> dict:
    paper = {"title": "", "authors": [], "year": None, "venue": "", "doi": "", "url": "", "abstract": "",
             "citations": None, "provider": ""}
    paper.update({key: value for key, value in fields.items() if value not in (None, "", [])})
    return paper


def semantic_scholar(query: str, limit: int = 8) -> list[dict]:
    fields = "title,year,authors,venue,externalIds,abstract,citationCount,url"
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?"
           + parse.urlencode({"query": query, "limit": max(1, min(limit, 20)), "fields": fields}))
    headers = {}
    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    data = json.loads(_get(url, headers))
    papers = []
    for item in data.get("data", []) or []:
        ids = item.get("externalIds") or {}
        doi = ids.get("DOI", "")
        papers.append(_paper(
            title=item.get("title"), year=item.get("year"), venue=item.get("venue"),
            authors=[a.get("name", "") for a in item.get("authors") or []],
            doi=doi, url=item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
            abstract=(item.get("abstract") or "")[:1500], citations=item.get("citationCount"),
            arxiv=ids.get("ArXiv", ""), provider="semantic_scholar",
        ))
    return papers


def crossref(query: str, limit: int = 8) -> list[dict]:
    url = ("https://api.crossref.org/works?"
           + parse.urlencode({"query": query, "rows": max(1, min(limit, 20)),
                              "select": "DOI,title,author,issued,container-title,is-referenced-by-count,URL"}))
    data = json.loads(_get(url))
    papers = []
    for item in data.get("message", {}).get("items", []) or []:
        issued = (item.get("issued") or {}).get("date-parts") or [[None]]
        authors = [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in item.get("author") or []]
        papers.append(_paper(
            title=" ".join(item.get("title") or []), year=issued[0][0], venue=" ".join(item.get("container-title") or []),
            authors=authors, doi=item.get("DOI"), url=item.get("URL") or f"https://doi.org/{item.get('DOI', '')}",
            citations=item.get("is-referenced-by-count"), provider="crossref",
        ))
    return papers


def arxiv(query: str, limit: int = 8) -> list[dict]:
    url = "http://export.arxiv.org/api/query?" + parse.urlencode(
        {"search_query": f"all:{query}", "max_results": max(1, min(limit, 20))})
    root = ET.fromstring(_get(url))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    for entry in root.findall("a:entry", ns):
        link = entry.findtext("a:id", default="", namespaces=ns)
        published = entry.findtext("a:published", default="", namespaces=ns)
        papers.append(_paper(
            title=re.sub(r"\s+", " ", entry.findtext("a:title", default="", namespaces=ns)).strip(),
            year=int(published[:4]) if published[:4].isdigit() else None, venue="arXiv",
            authors=[a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)],
            url=link, abstract=re.sub(r"\s+", " ", entry.findtext("a:summary", default="", namespaces=ns)).strip()[:1500],
            arxiv=link.rsplit("/abs/", 1)[-1], provider="arxiv",
        ))
    return papers


PROVIDERS = {"semantic_scholar": semantic_scholar, "crossref": crossref, "arxiv": arxiv}


def search(query: str, limit: int = 8, providers: tuple[str, ...] = ("semantic_scholar", "crossref", "arxiv")) -> dict:
    """Papers from the first provider that answers, and which providers failed (and why)."""
    failures = {}
    for name in providers:
        try:
            papers = PROVIDERS[name](query, limit)
        except (error.URLError, error.HTTPError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
            failures[name] = str(exc)[:200]
            continue
        if papers:
            return {"query": query, "provider": name, "papers": papers, "failures": failures}
        failures[name] = "no results"
    return {"query": query, "provider": None, "papers": [], "failures": failures}


def format_results(result: dict) -> str:
    """Search results as text for the model."""
    if not result["papers"]:
        reasons = "; ".join(f"{name}: {why}" for name, why in result["failures"].items()) or "no providers tried"
        return f"No papers found for `{result['query']}` ({reasons})."
    lines = [f"Results for `{result['query']}` from {result['provider']}:"]
    for index, paper in enumerate(result["papers"], 1):
        authors = ", ".join(paper["authors"][:3]) + (" et al." if len(paper["authors"]) > 3 else "")
        head = f"{index}. {paper['title']} — {authors} ({paper['year'] or 'n.d.'}), {paper['venue'] or 'venue unknown'}"
        if paper.get("citations") is not None:
            head += f", {paper['citations']} citations"
        lines.append(head)
        if paper.get("doi"):
            lines.append(f"   doi: {paper['doi']}")
        elif paper.get("url"):
            lines.append(f"   url: {paper['url']}")
        if paper.get("abstract"):
            lines.append(f"   abstract: {paper['abstract'][:600]}")
    if result["failures"]:
        lines.append("(" + "; ".join(f"{name}: {why}" for name, why in result["failures"].items()) + ")")
    return "\n".join(lines)
