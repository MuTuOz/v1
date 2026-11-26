"""Hand-derived cases, published examples and exhaustive author-code parity."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hcm_eval import Counts, TreeHCM, metrics, project_hierarchy


class TestRiehlHCM(unittest.TestCase):
    def setUp(self):
        self.tree = TreeHCM([("root", "benign"), ("root", "attack"),
                             ("attack", "A"), ("attack", "B"),
                             ("A", "a1"), ("A", "a2"),
                             ("B", "b1"), ("B", "b2"), ("B", "b3")])

    def test_exact_attack(self):
        self.assertEqual(self.tree.contribution("a1", "a1"), Counts(3, 3, 0, 0))

    def test_exact_benign_is_short_leaf(self):
        self.assertEqual(self.tree.contribution("benign", "benign"), Counts(1, 1, 0, 0))

    def test_wrong_subtype_within_family(self):
        self.assertEqual(self.tree.contribution("a1", "a2"), Counts(2, 2, 1, 1))

    def test_wrong_attack_family(self):
        self.assertEqual(self.tree.contribution("a1", "b1"), Counts(1, 1, 2, 2))

    def test_attack_predicted_benign(self):
        self.assertEqual(self.tree.contribution("a1", "benign"), Counts(0, 0, 1, 3))

    def test_benign_predicted_attack(self):
        self.assertEqual(self.tree.contribution("benign", "a1"), Counts(0, 0, 3, 1))

    def test_tn_is_not_every_off_path_node(self):
        c = self.tree.contribution("a1", "a1")
        self.assertNotEqual(c.tn, len(self.tree.children) - 1 - c.tp)
        self.assertEqual(self.tree.contribution("a1", "b1", transitive_sensitivity=True),
                         Counts(1, 4, 2, 2))

    def test_published_figure_4a(self):
        tree = TreeHCM([("root", "A"), ("root", "B"), ("A", "C"), ("A", "D"),
                        ("A", "E"), ("C", "H"), ("D", "I"), ("D", "J"), ("D", "K"),
                        ("E", "L"), ("E", "M"), ("B", "F"), ("B", "G")])
        for prediction, expected in [("I", Counts(3, 5, 0, 0)),
                                     ("J", Counts(2, 4, 1, 1)), ("L", Counts(1, 2, 2, 2))]:
            with self.subTest(prediction=prediction):
                self.assertEqual(tree.contribution("I", prediction), expected)

    def test_micro_formulas_and_undefined(self):
        combined = Counts(3, 3, 0, 0) + Counts(0, 0, 1, 3)
        m = metrics(combined)
        self.assertEqual(m["precision"], 3 / 4)
        self.assertEqual(m["recall"], 3 / 6)
        self.assertEqual(m["f1"], 6 / 10)
        self.assertEqual(m["false_negative_rate"], 3 / 6)
        self.assertTrue(all(v is None for v in metrics(Counts()).values()))

    def test_reject_unknown_and_internal_labels(self):
        for label in ["root", "A", "missing"]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.tree.contribution("a1", label)

    def test_invalid_tree(self):
        for edges in [[("root", "a"), ("root", "a")], [("root", "a"), ("a", "root")],
                      [("root", "a"), ("x", "y"), ("y", "x")]]:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                TreeHCM(edges)

    def test_full_84_by_84_author_reference_agreement(self):
        import networkx as nx
        schema = json.loads((ROOT / "flower_subtype_app/seniorfl_subtype/schema.json").read_text())
        tree, leaves = project_hierarchy(schema)
        source = ROOT / "results/formal_hcm_v1/sources/riehl_reference.py"
        spec = importlib.util.spec_from_file_location("riehl_author_reference", source)
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
        graph = nx.DiGraph((parent, node) for node, parent in tree.parents.items())
        self.assertEqual(len(tree.children), 93)
        self.assertEqual(len(leaves), 84)
        for true_leaf in leaves.values():
            for pred_leaf in leaves.values():
                actual = tree.contribution(true_leaf, pred_leaf)
                expected = ref.determineHierarchicalConfusionMatrix(
                    graph, [true_leaf], [list(tree.paths[pred_leaf])])
                self.assertEqual(actual.values(), tuple(expected), (true_leaf, pred_leaf))


if __name__ == "__main__":
    unittest.main()
