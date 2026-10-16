import json
import tempfile
import unittest
from pathlib import Path

from litgraph.store import Graph, GraphError, GraphFile

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "md_coarse_graining" / "graph.json"


class StoreTests(unittest.TestCase):
    def test_example_graph_is_valid(self):
        graph = Graph.load(EXAMPLE)
        self.assertGreater(len(graph.nodes), 40)
        self.assertGreater(len(graph.edges), 90)
        for node in graph.nodes:  # every node is connected
            self.assertTrue(graph.edges_of(node["id"]), node["id"])
        self.assertIn("paper:nam2025-liflow", graph.outline())

    def test_apply_resolves_labels_and_reports(self):
        graph = Graph.load(EXAMPLE)
        report = graph.apply({
            "nodes": [{"type": "paper", "label": "A new paper", "summary": "s", "year": "2024", "doi": "10.1/x"}],
            "edges": [{"source": "category:f", "target": "A new paper", "type": "contains"},
                      {"source": "A new paper", "target": "LiFlow", "type": "extends", "label": "builds on"},
                      {"source": "A new paper", "target": "nope", "type": "uses"}],
        }, status="proposed", source="chat")
        self.assertEqual(report["added_nodes"], ["paper:a-new-paper"])
        self.assertEqual(len(report["added_edges"]), 2)
        self.assertEqual(len(report["errors"]), 1)
        node = graph.node("paper:a-new-paper")
        self.assertEqual(node["status"], "proposed")
        self.assertEqual(node["year"], 2024)
        self.assertTrue(graph.has_edge("paper:a-new-paper", "paper:nam2025-liflow", "extends"))

    def test_upsert_merges_same_label(self):
        graph = Graph.load(EXAMPLE)
        node, created = graph.upsert_node({"type": "paper", "label": "LiFlow: flow matching for accelerated simulation of atomic transport", "summary": "", "venue": "NMI"})
        self.assertFalse(created)
        self.assertEqual(node["id"], "paper:nam2025-liflow")
        self.assertEqual(node["venue"], "NMI")
        self.assertTrue(node["summary"])  # an empty summary doesn't erase the old one

    def test_bad_input_raises(self):
        graph = Graph()
        with self.assertRaises(GraphError):
            graph.upsert_node({"label": "", "type": "paper"})
        with self.assertRaises(GraphError):
            graph.add_edge({"source": "a", "target": "b", "type": "uses"})

    def test_graph_file_saves_and_reloads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.json"
            path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            store = GraphFile(path)
            store.edit(lambda g: g.set_status(["paper:nam2025-liflow"], "proposed"))
            self.assertEqual(json.loads(path.read_text())["nodes"][0]["id"], "question:main")
            self.assertEqual(Graph.load(path).node("paper:nam2025-liflow")["status"], "proposed")
            self.assertTrue((Path(folder) / "graph.backup.json").exists())


if __name__ == "__main__":
    unittest.main()
