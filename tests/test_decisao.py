"""Checagens da Entrega 3: união das frentes, critérios, seleção e sensibilidade."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pilhas_minerio.caminhos import DATA_FILE, RESULTS_DIR
from pilhas_minerio.decisao.alternativas import Alternative, ParetoUnion
from pilhas_minerio.decisao.criterios import (EXTRA_CRITERIA, DecisionCriterion,
                                              RecipeHomogeneity, build_criteria)
from pilhas_minerio.decisao.metodos import (METHODS, DecisionMethod, MethodResult,
                                            ranking_from_scores, register_method)
from pilhas_minerio.decisao.preparar import Preparation
from pilhas_minerio.decisao.problema import DecisionProblem
from pilhas_minerio.decisao.selecao import SelectionRule
from pilhas_minerio.decisao.sensibilidade import (AlternativeCountVariants, DirichletWeights,
                                                  ParameterVariants, Scenario,
                                                  SensitivityAnalysis, WeightSweep)
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


class Dummy:
    """Critério sintético para problemas de teste."""

    def __init__(self, key, minimize=True):
        self.key, self.label, self.unit = key, key, "u"
        self.minimize, self.tolerance = minimize, 1e-10


def synthetic_problem(points, minimize=(True, True)):
    alternatives = tuple(Alternative(f"P{i}", (), (0.0, 0.0, 0.0), (), ())
                         for i in range(len(points)))
    criteria = tuple(Dummy(f"c{j}", m) for j, m in enumerate(minimize))
    return DecisionProblem(alternatives, criteria, np.array(points, dtype=float))


FRONT = [(0, 10), (1, 6), (3, 3), (7, 1), (10, 0)]


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


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT)

    def test_ancoras_ponto_ideal_e_cobertura(self):
        selection = SelectionRule(4).select(self.problem)
        self.assertEqual(selection.identifiers, ("P0", "P4", "P2", "P1"))
        self.assertIn("melhor em c0", selection.reasons["P0"])
        self.assertIn("ponto ideal", selection.reasons["P2"])
        self.assertIn("cobertura", selection.reasons["P1"])

    def test_conjunto_menor_cabe_no_maior(self):
        small = SelectionRule(3).select(self.problem).identifiers
        large = SelectionRule(5).select(self.problem).identifiers
        self.assertTrue(set(small) <= set(large))
        self.assertEqual(SelectionRule(5).select(self.problem).identifiers, large)

    def test_tamanho_impossivel(self):
        with self.assertRaises(ValueError):
            SelectionRule(2).select(self.problem)
        with self.assertRaises(ValueError):
            SelectionRule(6).select(self.problem)

    def test_ancora_repetida_conta_uma_vez(self):
        problem = synthetic_problem([(0, 0), (5, 9), (9, 5)])
        self.assertEqual(SelectionRule(2).select(problem).identifiers, ("P0", "P1"))


class MinMaxLoss(DecisionMethod):
    """Soma ponderada das perdas normalizadas, só para exercitar a interface."""
    name = "minmax"

    def __init__(self, shift=0.0):
        self.shift = shift

    def evaluate(self, problem, weights):
        scores = -(problem.losses() @ weights) + self.shift
        return MethodResult(scores, ranking_from_scores(scores))

    def parameters(self):
        return {"shift": self.shift}


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT)
        self.method = MinMaxLoss()
        self.base = np.array([0.5, 0.5])

    def test_varredura_de_peso_chega_ao_melhor_de_cada_criterio(self):
        scenarios = WeightSweep(3).scenarios(self.problem, self.method, self.base)
        self.assertEqual(len(scenarios), 6)
        for s in scenarios:
            self.assertAlmostEqual(s.weights.sum(), 1.0)
        result = SensitivityAnalysis(
            Scenario("base", self.problem, self.method, self.base), scenarios).run()
        winners = {o.name: o.winner for o in result.outcomes}
        self.assertEqual(winners["peso_c0=1.000"], "P0")
        self.assertEqual(winners["peso_c1=1.000"], "P4")

    def test_dirichlet_reprodutivel_e_pesos_validos(self):
        make = lambda seed: DirichletWeights(20, 50, seed).scenarios(
            self.problem, self.method, self.base)
        a, b, c = make(7), make(7), make(8)
        np.testing.assert_array_equal([s.weights for s in a], [s.weights for s in b])
        self.assertFalse(np.array_equal([s.weights for s in a], [s.weights for s in c]))
        self.assertTrue(all(abs(s.weights.sum() - 1) < 1e-9 and s.weights.min() >= 0 for s in a))
        with self.assertRaises(ValueError):
            DirichletWeights(20, 5, 1).scenarios(self.problem, self.method, np.array([1.0, 0.0]))

    def test_medidas_de_estabilidade(self):
        scenarios = DirichletWeights(20, 40, 1).scenarios(self.problem, self.method, self.base)
        result = SensitivityAnalysis(
            Scenario("base", self.problem, self.method, self.base), scenarios).run()
        self.assertAlmostEqual(sum(result.winner_frequency().values()), 1.0)
        ids, matrix = result.rank_acceptability()
        self.assertEqual(ids, self.problem.identifiers)
        np.testing.assert_allclose(matrix.sum(axis=1), 1.0)
        self.assertAlmostEqual(result.kendall_tau_to_base()[0], 1.0)

    def test_tau_de_rankings_opostos_e_conjuntos_diferentes(self):
        up = Scenario("a", self.problem, self.method, np.array([1.0, 0.0]))
        down = Scenario("b", self.problem, self.method, np.array([0.0, 1.0]))
        self.assertAlmostEqual(SensitivityAnalysis(up, [down]).run().kendall_tau_to_base()[1], -1.0)
        variants = AlternativeCountVariants([3, 5]).scenarios(self.problem, self.method, self.base)
        result = SensitivityAnalysis(variants[0], variants[1:]).run()
        self.assertEqual(len(result.base.ranked), 3)
        self.assertEqual(len(result.outcomes[1].ranked), 5)
        self.assertFalse(np.isnan(result.kendall_tau_to_base()[1]))

    def test_variantes_de_parametro_e_validacoes(self):
        variants = ParameterVariants({"a": MinMaxLoss(0), "b": MinMaxLoss(1)})
        scenarios = variants.scenarios(self.problem, self.base)
        self.assertEqual([s.name for s in scenarios], ["parametro_a", "parametro_b"])
        with self.assertRaises(ValueError):
            SensitivityAnalysis(scenarios[0], [scenarios[0]])
        with self.assertRaises(ValueError):
            Scenario("x", self.problem, self.method, np.array([0.7, 0.7]))

    def test_registro_de_metodos(self):
        register_method("teste_minmax")(MinMaxLoss)
        self.addCleanup(METHODS.pop, "teste_minmax")
        self.assertIsInstance(METHODS["teste_minmax"](), MinMaxLoss)
        with self.assertRaises(ValueError):
            register_method("teste_minmax")(MinMaxLoss)


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

    def test_resumo_traz_contagens_e_correlacoes(self):
        summary = self.preparation.summary()
        self.assertEqual(summary["uniao"]["finais"], len(self.preparation.union.alternatives))
        self.assertEqual(set(summary["spearman_do_criterio_extra"]),
                         {"custo", "desvio_sio2", "desvio_al2o3"})


if __name__ == "__main__":
    unittest.main()
