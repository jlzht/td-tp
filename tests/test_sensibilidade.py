"""Checagens da análise de sensibilidade da Entrega 3."""
import unittest

import numpy as np

from auxiliar import FRONT, synthetic_problem
from pilhas_minerio.decisao.metodos import (METHODS, DecisionMethod, MethodResult,
                                            ranking_from_scores, register_method)
from pilhas_minerio.decisao.pipeline import ElectreThenAhp, PipelineSettings
from pilhas_minerio.decisao.sensibilidade import (CriticalWeight, JudgmentPerturbation,
                                                  LevelVariants, LocalJudgmentVariants, Scenario,
                                                  SensitivityAnalysis, ThresholdGrid,
                                                  ThresholdLine, WeightSweep)


class MinMaxLoss(DecisionMethod):
    """Soma ponderada das perdas normalizadas, só para exercitar a interface."""
    name = "minmax"

    def evaluate(self, problem, weights):
        scores = -(problem.losses() @ weights)
        return MethodResult(scores, ranking_from_scores(scores))

    def parameters(self):
        return {}


class ResultMeasuresTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT)
        self.method = MinMaxLoss()

    def scenario(self, name, weights):
        return Scenario(name, self.problem, self.method, np.array(weights))

    def test_frequencia_e_taxa_contam_so_as_variacoes(self):
        base = self.scenario("base", [0.5, 0.5])
        variations = [self.scenario("a", [1.0, 0.0]), self.scenario("b", [0.5, 0.5]),
                      self.scenario("c", [0.0, 1.0]), self.scenario("d", [0.5, 0.5])]
        result = SensitivityAnalysis(base, variations).run()
        self.assertEqual(result.base.winner, "P2")
        self.assertAlmostEqual(result.base_win_rate(), 0.5)
        self.assertEqual(result.winner_frequency(), {"P2": 0.5, "P0": 0.25, "P4": 0.25})
        self.assertEqual(result.base_winner_positions(), [1, 3, 1, 3, 1])

    def test_tau_de_rankings_opostos(self):
        up, down = self.scenario("a", [1.0, 0.0]), self.scenario("b", [0.0, 1.0])
        result = SensitivityAnalysis(up, [down]).run()
        self.assertAlmostEqual(result.kendall_tau_to_base()[0], 1.0)
        self.assertAlmostEqual(result.kendall_tau_to_base()[1], -1.0)

    def test_tabela_traz_posicao_tamanho_e_pesos(self):
        base = self.scenario("base", [0.5, 0.5])
        row = SensitivityAnalysis(base, [self.scenario("a", [1.0, 0.0])]).run().table()[1]
        self.assertEqual((row["cenario"], row["vencedora"], row["mudou"]), ("a", "P0", True))
        self.assertEqual((row["posicao_da_base"], row["alternativas_no_ahp"]), (3, 5))
        self.assertEqual(row["pesos"], [1.0, 0.0])

    def test_validacoes_de_cenario_e_analise(self):
        base = self.scenario("base", [0.5, 0.5])
        with self.assertRaises(ValueError):
            self.scenario("x", [0.7, 0.7])
        with self.assertRaises(ValueError):
            SensitivityAnalysis(base, [base])

    def test_registro_de_metodos(self):
        register_method("teste_minmax")(MinMaxLoss)
        self.addCleanup(METHODS.pop, "teste_minmax")
        self.assertIsInstance(METHODS["teste_minmax"](), MinMaxLoss)
        with self.assertRaises(ValueError):
            register_method("teste_minmax")(MinMaxLoss)


class WeightTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT)
        self.method = MinMaxLoss()
        self.base = np.array([0.5, 0.5])

    def test_pesos_do_criterio_variado_e_proporcao_dos_outros(self):
        weights = WeightSweep.weights_at(np.array([0.5, 0.3, 0.2]), 0, 0.2)
        np.testing.assert_allclose(weights, [0.2, 0.48, 0.32])
        np.testing.assert_allclose(WeightSweep.weights_at(np.array([0.5, 0.5]), 1, 1.0), [0, 1])

    def test_varredura_chega_ao_melhor_de_cada_criterio(self):
        scenarios = WeightSweep(3).scenarios(self.problem, self.method, self.base)
        self.assertEqual(len(scenarios), 6)
        winners = {s.name: SensitivityAnalysis(s, []).run().base.winner for s in scenarios}
        self.assertEqual(winners["peso_c0=1.000"], "P0")
        self.assertEqual(winners["peso_c1=1.000"], "P4")

    def test_peso_critico_confere_com_a_conta_a_mao(self):
        # Com perdas x/10 e y/10, P2 custa 3 e vence entre t = 1/3 (P3) e t = 0,6 (P1).
        below, above = CriticalWeight(self.problem, self.method, self.base).find(0)
        self.assertAlmostEqual(below, 1 / 3, delta=2e-3)
        self.assertAlmostEqual(above, 0.6, delta=2e-3)

    def test_peso_critico_nulo_quando_a_vencedora_nunca_muda(self):
        problem = synthetic_problem([(0, 0), (5, 5)])
        below, above = CriticalWeight(problem, self.method, self.base).find(0)
        self.assertIsNone(below)
        self.assertIsNone(above)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT + [(9, 9), (10, 10)])
        self.settings = PipelineSettings(0.5, 0.3, "faixa_linear", 1)
        self.weights = np.array([0.5, 0.5])

    def test_linha_de_limiar_varia_so_um_parametro(self):
        scenarios = ThresholdLine("tau_d", [0.1, 0.3]).scenarios(
            self.problem, self.settings, self.weights)
        self.assertEqual([s.name for s in scenarios], ["veto=0.10", "veto=0.30"])
        self.assertEqual([s.method.settings.tau_d for s in scenarios], [0.1, 0.3])
        self.assertEqual({s.method.settings.tau_c for s in scenarios}, {0.5})
        support = ThresholdLine("tau_c", [0.6]).scenarios(self.problem, self.settings, self.weights)
        self.assertEqual((support[0].name, support[0].method.settings.tau_d), ("apoio=0.60", 0.3))
        with self.assertRaises(ValueError):
            ThresholdLine("outro", [0.1])

    def test_grade_niveis_e_modos(self):
        grid = ThresholdGrid([0.5, 0.6], [0.1, 0.2, 0.3]).scenarios(
            self.problem, self.settings, self.weights)
        self.assertEqual(len(grid), 6)
        levels = LevelVariants([1, 2]).scenarios(self.problem, self.settings, self.weights)
        self.assertEqual([s.method.settings.levels for s in levels], [1, 2])
        modes = LocalJudgmentVariants(["faixa_linear", "razao"]).scenarios(
            self.problem, self.settings, self.weights)
        self.assertEqual([s.method.settings.local_judgment for s in modes],
                         ["faixa_linear", "razao"])

    def test_variacao_roda_o_encadeamento(self):
        base = Scenario("base", self.problem, ElectreThenAhp(self.settings), self.weights)
        variations = LevelVariants([1, 2, 3]).scenarios(self.problem, self.settings, self.weights)
        result = SensitivityAnalysis(base, variations).run()
        sizes = [row["alternativas_no_ahp"] for row in result.table()]
        self.assertEqual(sizes[1], sizes[0])
        self.assertLess(sizes[1], sizes[2])


class JudgmentPerturbationTests(unittest.TestCase):
    def setUp(self):
        self.problem = synthetic_problem(FRONT)
        self.settings = PipelineSettings(0.5, 0.3, "faixa_linear", 1)
        self.keys = ["a", "b", "c"]
        self.judgments = {"a:b": 2, "a:c": 6, "b:c": 3}

    def test_degrau_da_escala_de_saaty(self):
        self.assertEqual(JudgmentPerturbation.shifted(5, 1), 6)
        self.assertEqual(JudgmentPerturbation.shifted(1, -1), 1 / 2)
        self.assertAlmostEqual(JudgmentPerturbation.shifted(1 / 3, 1), 1 / 2)
        self.assertIsNone(JudgmentPerturbation.shifted(9, 1))
        self.assertIsNone(JudgmentPerturbation.shifted(1 / 9, -1))

    def test_um_por_vez_descarta_fora_da_escala_e_qc_alto(self):
        perturbation = JudgmentPerturbation(self.keys, self.judgments, 0.10)
        problem = synthetic_problem([(0, 10, 5), (10, 0, 5), (5, 5, 0)])
        scenarios, skipped = perturbation.one_at_a_time(problem, self.settings, [1])
        self.assertEqual(len(scenarios) + len(skipped), 6)
        for s in scenarios:
            self.assertAlmostEqual(s.weights.sum(), 1.0)
        strict = JudgmentPerturbation(self.keys, self.judgments, 0.0)
        accepted, rejected = strict.one_at_a_time(problem, self.settings, [1])
        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(rejected), 6)

    def test_sorteios_reprodutiveis_e_contagem_de_descartes(self):
        perturbation = JudgmentPerturbation(self.keys, self.judgments, 0.10)
        problem = synthetic_problem([(0, 10, 5), (10, 0, 5), (5, 5, 0)])
        first, skipped_first = perturbation.random(problem, self.settings, 50, 1, 7)
        second, skipped_second = perturbation.random(problem, self.settings, 50, 1, 7)
        self.assertEqual(skipped_first, skipped_second)
        np.testing.assert_array_equal([s.weights for s in first], [s.weights for s in second])
        self.assertEqual(len(first) + skipped_first, 50)


if __name__ == "__main__":
    unittest.main()
