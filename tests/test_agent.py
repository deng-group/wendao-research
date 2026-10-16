import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from litgraph import literature
from litgraph.agent import Agent
from litgraph.server import create_app
from litgraph.store import GraphFile
from litgraph.workspace import Workspace

from tests.fake_anthropic import FakeAnthropic

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "md_coarse_graining"


def fake_search(query, limit=8, providers=None):
    return {"query": query, "provider": "fake", "failures": {}, "papers": [
        {"title": "Diffusion models for ion hops", "authors": ["A. Person", "B. Other"], "year": 2024, "venue": "J. Fake",
         "doi": "10.1000/fake", "url": "https://doi.org/10.1000/fake", "abstract": "We learn hop statistics.", "citations": 3, "provider": "fake"}]}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        for name in ("graph.json", "litgraph.toml", "AGENTS.md"):
            shutil.copy(EXAMPLE / name, self.folder)
        self.workspace = Workspace.load(self.folder)
        self.workspace.web_search = False
        self.workspace.provider = "anthropic"  # these tests use the fake Messages API
        self.graph_file = GraphFile(self.workspace.graph_path)

    def tearDown(self):
        shutil.rmtree(self.folder)

    def client_for(self, fake):
        import anthropic
        return anthropic.Anthropic(api_key="test", base_url=fake.base_url, max_retries=0)

    def test_tool_loop_searches_and_proposes(self):
        replies = [
            [{"text": "Let me look."}, {"tool": "search_literature", "input": {"query": "ion hop diffusion model", "limit": 3}}],
            # first proposal breaks the rules (no family, no technique, no fields): returned to the model, nothing written
            [{"tool": "propose_graph_changes", "input": {"reason": "A relevant generative model.", "nodes": [
                {"id": "paper:person2024-hops", "type": "paper", "label": "Diffusion models for ion hops", "summary": "Learns hop statistics.", "year": 2024, "doi": "10.1000/fake"}]}}],
            [{"tool": "propose_graph_changes", "input": {"reason": "A relevant generative model.", "nodes": [
                {"id": "paper:person2024-hops", "type": "paper", "label": "Diffusion models for ion hops", "summary": "Learns hop statistics.", "year": 2024, "doi": "10.1000/fake",
                 "authors": "A. Person, B. Other", "venue": "J. Fake", "learns": "hop statistics", "discards": "lattice motion", "validated_at": ["kinetic"]}],
                "edges": [{"source": "family:f", "target": "paper:person2024-hops", "type": "contains"},
                          {"source": "paper:person2024-hops", "target": "technique:flow-matching", "type": "uses"},
                          {"source": "paper:person2024-hops", "target": "LiFlow", "type": "contrasts", "label": "hops vs displacements"}]}}],
            [{"text": "Added one paper [paper:person2024-hops]."}],
        ]
        with FakeAnthropic(replies) as fake, mock.patch.object(literature, "search", fake_search):
            agent = Agent(self.workspace, self.graph_file, client=self.client_for(fake))
            events = list(agent.stream_answer("Find generative models of ion hops and add them", [], ["paper:nam2025-liflow"]))
        kinds = [event["type"] for event in events]
        self.assertEqual(kinds[0], "start")
        self.assertIn("proposal", kinds)
        self.assertEqual(kinds[-1], "done")
        done = events[-1]
        self.assertIn("Added one paper", done["answer"])
        self.assertEqual(done["proposals"][0]["added_nodes"], ["paper:person2024-hops"])
        graph = self.graph_file.graph
        self.assertEqual(graph.node("paper:person2024-hops")["status"], "proposed")
        self.assertTrue(graph.has_edge("paper:person2024-hops", "paper:nam2025-liflow", "contrasts"))
        # what the model saw: the graph in the system prompt, the selected node in the user turn, the tool results
        first = fake.requests[0]
        self.assertIn("paper:nam2025-liflow", first["system"][1]["text"])
        self.assertIn("(LiFlow) [paper:nam2025-liflow]", first["messages"][-1]["content"])
        self.assertEqual(first["output_config"], {"effort": "medium"})
        second = fake.requests[1]
        self.assertIn("Diffusion models for ion hops", second["messages"][-1]["content"][0]["content"])
        rejected = fake.requests[2]["messages"][-1]["content"][0]["content"]
        self.assertIn("Nothing was written", rejected)
        self.assertIn("exactly one `contains` edge", rejected)
        self.assertEqual(len(fake.requests), 4)
        self.assertEqual(len([e for e in events if e["type"] == "proposal"]), 1)

    def test_server_streams_and_decides_proposals(self):
        os.environ["ANTHROPIC_API_KEY"] = "test"
        replies = [
            [{"tool": "propose_graph_changes", "input": {"reason": "r", "nodes": [{"type": "claim", "label": "Brand new claim", "summary": "s", "claim_status": "open"}],
                                                       "edges": [{"source": "Brand new claim", "target": "technique:markov-state-model", "type": "about"}]}}],
            [{"text": "Done."}],
        ]
        with FakeAnthropic(replies) as fake:
            app = create_app(self.workspace, client=self.client_for(fake))
            client = app.test_client()
            self.assertEqual(client.get("/api/health").get_json()["nodes"], 75)
            response = client.post("/api/answer/stream", json={"query": "add it", "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]})
            lines = [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line.strip()]
            proposal = next(line["proposal"] for line in lines if line["type"] == "proposal")
            self.assertEqual(proposal["added_nodes"], ["claim:brand-new-claim"])
            self.assertEqual(client.get("/api/graph").get_json()["graph"]["nodes"][-1]["status"], "proposed")
            reply = client.post(f"/api/proposals/{proposal['id']}/discard").get_json()
            self.assertTrue(reply["ok"])
            self.assertIsNone(self.graph_file.graph.node("claim:brand-new-claim"))
            # manual editing
            reply = client.post("/api/graph/nodes", json={"type": "technique", "label": "My technique", "summary": "mine"}).get_json()
            self.assertTrue(reply["created"])
            reply = client.post("/api/graph/edges", json={"source": "family:e", "target": "technique:my-technique", "type": "contains"}).get_json()
            self.assertTrue(reply["ok"])
            self.assertEqual(client.delete("/api/graph/nodes/technique:my-technique").status_code, 200)
            self.assertEqual(client.delete("/api/graph/nodes/technique:my-technique").status_code, 404)
            page = client.get("/").get_data(as_text=True)
            self.assertIn("MD coarse-graining", page)

    def test_literature_formatting_without_network(self):
        text = literature.format_results(fake_search("q"))
        self.assertIn("Diffusion models for ion hops", text)
        self.assertIn("doi: 10.1000/fake", text)
        empty = literature.format_results({"query": "q", "provider": None, "papers": [], "failures": {"crossref": "timeout"}})
        self.assertIn("No papers found", empty)


if __name__ == "__main__":
    unittest.main()
