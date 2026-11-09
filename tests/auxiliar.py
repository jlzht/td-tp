"""Problemas de decisão sintéticos, compartilhados pelos testes da Entrega 3."""
import numpy as np

from pilhas_minerio.decisao.alternativas import Alternative
from pilhas_minerio.decisao.problema import DecisionProblem

FRONT = [(0, 10), (1, 6), (3, 3), (7, 1), (10, 0)]


class Dummy:
    """Critério sintético para problemas de teste."""

    def __init__(self, key, minimize=True):
        self.key, self.label, self.unit = key, key, "u"
        self.minimize, self.tolerance = minimize, 1e-10


def synthetic_problem(points, minimize=None):
    """Problema com uma alternativa P0, P1, ... por linha de ``points``; critérios c0, c1, ..."""
    minimize = minimize or (True,) * len(points[0])
    alternatives = tuple(Alternative(f"P{i}", (), (0.0, 0.0, 0.0), (), ())
                         for i in range(len(points)))
    criteria = tuple(Dummy(f"c{j}", m) for j, m in enumerate(minimize))
    return DecisionProblem(alternatives, criteria, np.array(points, dtype=float))
