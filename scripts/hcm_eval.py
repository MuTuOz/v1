"""Riehl HCM for a tree, single path and mandatory leaf predictions.

Source: Riehl et al. (2023), doi:10.1093/jrsssc/qlad057, Eq. (4).
Operational TN semantics match the authors' implementation at commit
2256f4c24b813ffb752a53e20a8092ec7b1e3ac3: neighbours are siblings and
getDescendants returns immediate children, not a transitive closure.
This module deliberately does not claim DAG/multilabel/internal-node support.
"""
from dataclasses import asdict, dataclass
from math import sqrt


@dataclass(frozen=True)
class Counts:
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    def __add__(self, other):
        return Counts(*(a + b for a, b in zip(self.values(), other.values())))

    def values(self):
        return self.tp, self.tn, self.fp, self.fn

    def to_dict(self):
        return asdict(self)


def metrics(counts):
    """Binary formulas applied after summing HCM contributions (micro).

    Undefined ratios are None/JSON null, never silently perfect or zero.
    HCM FNR uses FN/(TP+FN), correcting the paper Table 2's FP typo.
    """
    tp, tn, fp, fn = counts.values()
    ratio = lambda a, b: a / b if b else None
    return {
        "accuracy": ratio(tp + tn, tp + tn + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "specificity": ratio(tn, tn + fp),
        "false_positive_rate": ratio(fp, fp + tn),
        "false_negative_rate": ratio(fn, fn + tp),
        "mcc": ratio(tp * tn - fp * fn,
                     sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))),
    }


class TreeHCM:
    def __init__(self, edges, root="root"):
        self.root = root
        self.parents = {}
        self.children = {root: set()}
        for parent, child in edges:
            if child == root or child in self.parents or parent == child:
                raise ValueError("Expected unique-parent rooted tree; repeated edge/node parent")
            self.parents[child] = parent
            self.children.setdefault(parent, set()).add(child)
            self.children.setdefault(child, set())
        self.paths = {}
        for node in self.children:
            path = [node]
            while path[-1] != root:
                if path[-1] not in self.parents or self.parents[path[-1]] in path:
                    raise ValueError("Disconnected node or cycle")
                path.append(self.parents[path[-1]])
            self.paths[node] = tuple(reversed(path))
        self.leaves = frozenset(n for n, children in self.children.items() if not children)
        if root in self.leaves:
            raise ValueError("Tree requires at least one non-root node")

    def siblings(self, node):
        return self.children[self.parents[node]] - {node} if node != self.root else set()

    def descendants(self, node):
        found = set()
        frontier = list(self.children[node])
        while frontier:
            child = frontier.pop()
            found.add(child)
            frontier.extend(self.children[child])
        return found

    def contribution(self, true_leaf, predicted_leaf, *, transitive_sensitivity=False):
        if true_leaf not in self.leaves or predicted_leaf not in self.leaves:
            raise ValueError("Labels must be known leaves; internal-node predictions are out of scope")
        true_path = self.paths[true_leaf]
        pred_path = self.paths[predicted_leaf]
        common = []
        for a, b in zip(true_path, pred_path):
            if a != b:
                break
            common.append(a)
        t, p = set(true_path), set(pred_path)
        neighbours = set().union(*(self.siblings(n) for n in common)) - t
        # Authors' getDescendants(graph, node) enumerates graph.neighbors(node).
        candidates = (self.descendants(common[-1]) if transitive_sensitivity
                      else self.children[common[-1]])
        negatives_below = candidates - (t | p)
        return Counts(tp=len((t & p) - {self.root}),
                      tn=len(neighbours) + len(negatives_below),
                      fp=len(p - t), fn=len(t - p))


def project_hierarchy(schema):
    """All 84 training-derived leaves; benign is a depth-1 leaf, not padded."""
    classes, mapping = schema["classes"], schema["family_of"]
    if len(classes) != len(set(classes)) or set(classes) != set(mapping):
        raise ValueError("Class/mapping mismatch")
    if classes[0] != "benign" or mapping["benign"] != "benign":
        raise ValueError("Expected benign ID zero")
    families = sorted(set(mapping.values()) - {"benign"})
    edges = [("root", "benign"), ("root", "attack")]
    edges += [("attack", f"family:{f}") for f in families]
    leaves = {"benign": "benign"}
    for subtype in classes[1:]:
        family = mapping[subtype]
        if family == "benign":
            raise ValueError("Only benign can map to benign")
        leaves[subtype] = f"subtype:{subtype}"
        edges.append((f"family:{family}", leaves[subtype]))
    tree = TreeHCM(edges)
    if tree.leaves != set(leaves.values()):
        raise ValueError("Every training class must be exactly one leaf")
    return tree, leaves
