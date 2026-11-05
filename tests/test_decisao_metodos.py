"""Checagens de ELECTRE I, AHP, do encadeamento dos dois e dos hiperparâmetros."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pilhas_minerio.caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from pilhas_minerio.decisao.alternativas import Alternative
from pilhas_minerio.decisao.executar import FinalDecision
from pilhas_minerio.decisao.hiperparametros import Hyperparameters
from pilhas_minerio.decisao.metodos.ahp import (Ahp, ComparisonMatrix, CriteriaWeights,
                                                RandomIndex)
from pilhas_minerio.decisao.metodos.electre1 import ElectreI
from pilhas_minerio.decisao.pipeline import ElectreThenAhp
from pilhas_minerio.decisao.preparar import Preparation
from pilhas_minerio.decisao.problema import DecisionProblem


class Dummy:
    """Critério sintético para problemas de teste."""

    def __init__(self, key, minimize=True):
        self.key, self.label, self.unit = key, key, "u"
        self.minimize, self.tolerance = minimize, 1e-10


def synthetic_problem(points, minimize=None):
    minimize = minimize or (True,) * len(points[0])
    alternatives = tuple(Alternative(f"P{i}", (), (0.0, 0.0, 0.0), (), ())
                         for i in range(len(points)))
    criteria = tuple(Dummy(f"c{j}", m) for j, m in enumerate(minimize))
    return DecisionProblem(alternatives, criteria, np.array(points, dtype=float))


FRONT = [(0, 10), (1, 6), (3, 3), (7, 1), (10, 0)]


class ElectreITests(unittest.TestCase):
    """Reproduz os exemplos numéricos dos slides da aula de ELECTRE I."""

    def test_concordancia_e_discordancia_do_exemplo_custo_qualidade_prazo(self):
        # Amplitudes 10 (custo) e 8 (prazo), como no slide; A=(83, 9, 12), B=(80, 6, 10).
        problem = synthetic_problem([(83, 9, 12), (80, 6, 10), (90, 7, 18)],
                                    minimize=(True, False, True))
        concordance, discordance = ElectreI(0.75, 0.25).concordance_discordance(
            problem, np.array([0.15, 0.7, 0.15]))
        self.assertAlmostEqual(concordance[0, 1], 0.7)
        self.assertAlmostEqual(discordance[0, 1], 0.30)

    def test_relacao_e_ordem_parcial_do_exemplo_de_cinco_acoes(self):
        # Matrizes C e D do slide; tau_c = 0,75 e tau_d = 0,25.
        c = np.array([[1, 0, 1, 0, .5], [1, 1, 1, .25, 1], [.25, 0, 1, 0, .5],
                      [1, 1, 1, 1, 1], [.5, .25, 1, .25, 1]])
        d = np.array([[0, 1, 0, 1, 1], [0, 0, 0, .870, 0], [.804, 1, 0, 1, 1],
                      [0, 0, 0, 0, 0], [.043, .130, 0, 1, 0]])
        relation = ElectreI(0.75, 0.25).outranking(c, d)
        arcs = {(i + 1, k + 1) for i, k in zip(*np.nonzero(relation))}
        self.assertEqual(arcs, {(1, 3), (2, 1), (2, 3), (2, 5), (4, 1), (4, 2), (4, 3),
                                (4, 5), (5, 3)})
        levels, _ = ElectreI.levels(relation)
        self.assertEqual(levels, [[3], [1], [0, 4], [2]])

    def test_circuito_vira_uma_classe(self):
        relation = np.zeros((3, 3), dtype=bool)
        relation[0, 1] = relation[1, 0] = relation[0, 2] = True
        levels, label = ElectreI.levels(relation)
        self.assertEqual(levels, [[0, 1], [2]])
        self.assertEqual(label[0], label[1])

    def test_nucleo_e_calibracao_do_veto(self):
        problem = synthetic_problem(FRONT)
        weights = np.array([0.5, 0.5])
        method = ElectreI(0.5, 0.0)
        result = method.evaluate(problem, weights)
        self.assertEqual(len(ElectreI.kernel(result)), 5)
        calibration = method.calibrate_tau_d(problem, weights, 2, np.linspace(0, 1, 11))
        self.assertAlmostEqual(calibration.kernel_size, 2, delta=1)
        self.assertEqual(len(calibration.grid), len(calibration.sizes))
        with self.assertRaises(ValueError):
            ElectreI(0.0, 0.5)


class AhpTests(unittest.TestCase):
    def test_matriz_consistente_dos_slides(self):
        matrix = ComparisonMatrix(np.array([[1, 2, 6], [1 / 2, 1, 3], [1 / 6, 1 / 3, 1]]))
        np.testing.assert_allclose(matrix.priorities(), [0.6, 0.3, 0.1], atol=1e-9)
        self.assertAlmostEqual(matrix.principal_eigenpair()[0], 3.0)
        self.assertAlmostEqual(matrix.consistency_index(), 0.0)

    def test_matriz_experiencia_dos_slides(self):
        matrix = ComparisonMatrix(np.array([[1, 1 / 4, 4], [4, 1, 9], [1 / 4, 1 / 9, 1]]))
        np.testing.assert_allclose(matrix.priorities(), [0.217, 0.717, 0.066], atol=2e-3)

    def test_matriz_inconsistente_tem_qc_positivo_e_matriz_invalida_falha(self):
        matrix = ComparisonMatrix(np.array([[1, 2, 9], [1 / 2, 1, 3], [1 / 9, 1 / 3, 1]]))
        self.assertGreater(matrix.consistency_ratio(), 0.0)
        with self.assertRaises(ValueError):
            ComparisonMatrix(np.array([[1, 2], [2, 1]]))

    def test_ica_simulado_reproduz_a_tabela_dos_slides(self):
        self.assertAlmostEqual(RandomIndex.simulate(5, 4000, 1), RandomIndex.value(5), delta=0.05)
        self.assertEqual(RandomIndex.value(2), 0.0)

    def test_pesos_dos_criterios_exigem_qc_e_todos_os_pares(self):
        keys = ["a", "b", "c"]
        ok = CriteriaWeights(keys, {"a:b": 2, "a:c": 6, "b:c": 3})
        np.testing.assert_allclose(ok.weights(0.10), [0.6, 0.3, 0.1], atol=1e-9)
        contradictory = CriteriaWeights(keys, {"a:b": 9, "b:c": 9, "a:c": 1 / 9})
        with self.assertRaises(ValueError):
            contradictory.weights(0.10)
        with self.assertRaises(ValueError):
            CriteriaWeights(keys, {"a:b": 2, "a:c": 6})
        with self.assertRaises(ValueError):
            CriteriaWeights(keys, {"a:b": 2, "a:c": 6, "b:c": 12})

    def test_faixa_linear_da_extremo_a_extremo_nove(self):
        problem = synthetic_problem([(1.0,), (3.0,)])
        result = Ahp("faixa_linear").evaluate(problem, np.array([1.0]))
        np.testing.assert_allclose(result.scores, [0.9, 0.1])
        self.assertEqual(result.best, 0)

    def test_modo_razao_e_modo_desconhecido(self):
        problem = synthetic_problem([(1.0,), (4.0,)])
        np.testing.assert_allclose(Ahp("razao").evaluate(problem, np.array([1.0])).scores,
                                   [0.8, 0.2])
        with self.assertRaises(ValueError):
            Ahp("outro")

    def test_sintese_global_pondera_prioridades_locais(self):
        problem = synthetic_problem([(0, 10), (10, 0)])
        scores = Ahp("faixa_linear").evaluate(problem, np.array([0.75, 0.25])).scores
        np.testing.assert_allclose(scores, [0.75 * 0.9 + 0.25 * 0.1, 0.75 * 0.1 + 0.25 * 0.9])


class PipelineTests(unittest.TestCase):
    def test_nucleo_vai_a_frente_e_ahp_ordena_dentro_dele(self):
        problem = synthetic_problem(FRONT + [(9, 9)])
        result = ElectreThenAhp(0.5, 0.2, "faixa_linear").evaluate(problem, np.array([0.5, 0.5]))
        kernel = set(result.details["nucleo"])
        self.assertNotIn(5, kernel)
        self.assertEqual(set(result.ranking[:len(kernel)]), kernel)
        self.assertIn(result.best, kernel)
        self.assertEqual(sorted(result.ranking), list(range(6)))
        self.assertAlmostEqual(sum(result.details["resumo"]["prioridade_global"].values()), 1.0)


class HyperparameterTests(unittest.TestCase):
    def test_arquivo_do_projeto(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        weights = params.criteria_weights()
        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertLessEqual(params.judgments_consistency_ratio(), params.max_consistency_ratio)
        self.assertEqual(len(weights), len(params.criteria))
        self.assertGreaterEqual(params.tau_d_search[-1], 1.0 - 1e-9)

    def test_valor_fora_do_dominio_e_recusado(self):
        raw = json.loads((CONFIG_DIR / "decisao.json").read_text(encoding="utf-8"))
        raw["electre1"]["tau_c"] = 1.5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisao.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                Hyperparameters.load(path)


@unittest.skipUnless((RESULTS_DIR / "entrega_2" / "nao_dominadas_soma.json").exists(),
                     "resultados da Entrega 2 ausentes")
class FinalDecisionTests(unittest.TestCase):
    def test_decisao_final_escolhe_uma_do_nucleo_com_os_pesos_do_arquivo(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        preparation = Preparation(DATA_FILE, RESULTS_DIR / "entrega_2", params.extra_criterion)
        record = FinalDecision(preparation, params).run()
        self.assertIn(record["escolhida"]["id"], record["electre1"]["nucleo"])
        self.assertAlmostEqual(sum(record["pesos"]["valores"]), 1.0)
        self.assertEqual(record["ranking_final"][0], record["escolhida"]["id"])
        self.assertAlmostEqual(sum(record["ahp"]["prioridade_global"].values()), 1.0)
        self.assertIn(round(record["limiares"]["tau_d"], 6), [round(x, 6) for x in params.tau_d_search])


if __name__ == "__main__":
    unittest.main()
