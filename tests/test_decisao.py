"""Checagens da Entrega 3: união das frentes e critérios de decisão."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from auxiliar import FRONT, synthetic_problem
from pilhas_minerio.caminhos import DATA_FILE, RESULTS_DIR
from pilhas_minerio.decisao.alternativas import ParetoUnion
from pilhas_minerio.decisao.criterios import EXTRA_CRITERIA, RecipeHomogeneity, build_criteria
from pilhas_minerio.decisao.preparar import Preparation
from pilhas_minerio.gvns import Case, Ore, Sinter, evaluate
from pilhas_minerio.multiobjetivo import dominates, plan_from_counts


def two_ore_case(trucks, groups):
    sinters = {g: Sinter(0, 5, 100, 0, 1, 100) for g in set(groups)}
    ores = (Ore(100, 5, 1, 0, 100, set(sinters)), Ore(100, 5, 1, 0, 100, set(sinters)))
    return Case(2, tuple(trucks), tuple(groups), ores, sinters)


def homogeneity(case, counts):
    evaluation = evaluate(case, plan_from_counts(case, counts))
    return RecipeHomogeneity().evaluate(case, counts, evaluation)


class HomogeneityTests(unittest.TestCase):
    def test_pilhas_com_mesma_proporcao_dao_zero(self):
        case = two_ore_case((2, 4), (1, 1))
        self.assertAlmostEqual(homogeneity(case, [[1, 1], [2, 2]]), 0.0)

    def test_receita_comum_pondera_pela_massa(self):
        # Receita comum (1/4, 3/4); distâncias L1 1,5 e 0,5; média 1,0.
        case = two_ore_case((1, 3), (1, 1))
        self.assertAlmostEqual(homogeneity(case, [[1, 0], [0, 3]]), 1.0)

    def test_media_entre_equipamentos(self):
        case = two_ore_case((2, 2, 2, 2), (1, 1, 2, 2))
        counts = [[2, 0], [0, 2], [1, 1], [1, 1]]
        self.assertAlmostEqual(homogeneity(case, counts), 0.5)

    def test_criterio_extra_trocavel_por_nome(self):
        self.assertEqual([c.key for c in build_criteria("homogeneidade")],
                         ["custo", "desvio_sio2", "desvio_al2o3", "homogeneidade"])
        with self.assertRaises(ValueError):
            build_criteria("inexistente")
        self.assertIn("homogeneidade", EXTRA_CRITERIA)


def union_case():
    """Uma pilha de 2 caminhões; A barato e longe do alvo, B no alvo, C é A mais caro."""
    sinters = {1: Sinter(4, 5, 8, 0.5, 1, 2)}
    ores = (Ore(100, 7, 1, 0, 2, {1}), Ore(200, 5, 1, 0, 2, {1}), Ore(300, 7, 1, 0, 2, {1}))
    return Case(2, (2,), (1,), ores, sinters)


def record(case, counts):
    objectives = evaluate(case, plan_from_counts(case, counts)).objectives
    return {"objetivos": list(objectives), "caminhoes_por_pilha_e_minerio": counts,
            "origens": [{"rodada": 1, "configuracao": "x", "semente": 1}]}


class UnionTests(unittest.TestCase):
    def setUp(self):
        self.case = union_case()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def write(self, soma, epsilon):
        for name, records in (("soma", soma), ("epsilon", epsilon)):
            (self.directory / f"nao_dominadas_{name}.json").write_text(
                json.dumps(records), encoding="utf-8")

    def test_filtra_dominancia_global_e_une_receitas_repetidas(self):
        aa, ab, bb = [[2, 0, 0]], [[1, 1, 0]], [[0, 2, 0]]
        cc, bc = [[0, 0, 2]], [[0, 1, 1]]
        self.write([record(self.case, c) for c in (aa, ab, cc)],
                   [record(self.case, c) for c in (ab, bb, bc)])
        result = ParetoUnion.from_directory(self.case, self.directory).build()
        self.assertEqual(result.report.distinct_recipes, 5)
        self.assertEqual(result.report.dominated_removed, 2)
        self.assertEqual([a.counts for a in result.alternatives],
                         [((2, 0, 0),), ((1, 1, 0),), ((0, 2, 0),)])
        self.assertEqual([a.identifier for a in result.alternatives], ["A01", "A02", "A03"])
        middle = result.alternatives[1]
        self.assertEqual(middle.approaches, ("soma", "epsilon"))
        self.assertEqual(len(middle.origins), 2)

    def test_rejeita_objetivos_que_divergem_da_reavaliacao(self):
        broken = record(self.case, [[2, 0, 0]])
        broken["objetivos"][0] += 1000
        self.write([broken], [record(self.case, [[0, 2, 0]])])
        with self.assertRaises(ValueError):
            ParetoUnion.from_directory(self.case, self.directory).build()


class ProblemTests(unittest.TestCase):
    def test_perdas_orientam_0_melhor_1_pior(self):
        problem = synthetic_problem([(0, 4), (10, 8)], minimize=(True, False))
        np.testing.assert_allclose(problem.losses(), [[0, 1], [1, 0]])

    def test_criterio_sem_variacao_vira_zero(self):
        np.testing.assert_allclose(synthetic_problem([(1, 5), (1, 7)]).losses()[:, 0], [0, 0])

    def test_dominancia_considera_sentido_de_cada_criterio(self):
        problem = synthetic_problem([(1, 5), (2, 4), (2, 6)], minimize=(True, False))
        self.assertEqual(problem.nondominated_mask().tolist(), [True, False, True])

    def test_subset_mantem_ordem_e_rejeita_desconhecidas(self):
        problem = synthetic_problem(FRONT)
        self.assertEqual(problem.subset(["P3", "P1"]).identifiers, ("P1", "P3"))
        with self.assertRaises(ValueError):
            problem.subset(["P9"])


@unittest.skipUnless((RESULTS_DIR / "entrega_2" / "nao_dominadas_soma.json").exists(),
                     "resultados da Entrega 2 ausentes")
class RealFrontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preparation = Preparation(DATA_FILE, RESULTS_DIR / "entrega_2", "homogeneidade")

    def test_uniao_sem_dominancia_entre_os_tres_objetivos(self):
        alternatives = self.preparation.union.alternatives
        for a, b in itertools.permutations(alternatives, 2):
            self.assertFalse(dominates(a.objectives, b.objectives))
        self.assertEqual(len({a.counts for a in alternatives}), len(alternatives))

    def test_criterios_finitos_e_homogeneidade_no_intervalo(self):
        values = self.preparation.problem.values
        self.assertTrue(np.isfinite(values).all())
        self.assertTrue(((values[:, 3] >= 0) & (values[:, 3] <= 2)).all())

    def test_objetivos_da_matriz_coincidem_com_os_da_alternativa(self):
        problem = self.preparation.problem
        for alternative, row in zip(problem.alternatives, problem.values):
            for expected, got in zip(alternative.objectives, row[:3]):
                self.assertAlmostEqual(expected, got, places=6)

    def test_resumo_traz_contagens_e_faixas(self):
        summary = self.preparation.summary()
        self.assertEqual(summary["uniao"]["finais"], len(self.preparation.union.alternatives))
        self.assertEqual(set(summary["criterios"]),
                         {"custo", "desvio_sio2", "desvio_al2o3", "homogeneidade"})


if __name__ == "__main__":
    unittest.main()
