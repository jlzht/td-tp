"""Checagens de ELECTRE I, AHP, do encadeamento dos dois e dos hiperparâmetros."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from auxiliar import FRONT, synthetic_problem
from pilhas_minerio.caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from pilhas_minerio.decisao.executar import FinalDecision, write_table
from pilhas_minerio.decisao.figuras_escolha import ChoiceFigures
from pilhas_minerio.decisao.hiperparametros import Hyperparameters
from pilhas_minerio.decisao.metodos.ahp import (Ahp, ComparisonMatrix, CriteriaWeights,
                                                RandomIndex)
from pilhas_minerio.decisao.metodos.electre1 import ElectreI
from pilhas_minerio.decisao.pipeline import ElectreThenAhp, PipelineSettings
from pilhas_minerio.decisao.preparar import Preparation


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

    def test_primeiros_niveis_acumulam_sem_partir_nenhum(self):
        problem = synthetic_problem(FRONT + [(9, 9), (10, 10)])
        result = ElectreI(0.5, 0.3).evaluate(problem, np.array([0.5, 0.5]))
        levels = result.details["niveis"]
        self.assertGreaterEqual(len(levels), 2)
        self.assertEqual(set(ElectreI.top_levels(result, 1)), set(levels[0]))
        self.assertEqual(set(ElectreI.top_levels(result, 2)), set(levels[0]) | set(levels[1]))
        self.assertEqual(len(ElectreI.top_levels(result, 99)), len(problem.alternatives))
        with self.assertRaises(ValueError):
            ElectreI.top_levels(result, 0)

    def test_limiares_fora_do_dominio(self):
        with self.assertRaises(ValueError):
            ElectreI(0.0, 0.5)
        with self.assertRaises(ValueError):
            ElectreI(0.5, 1.5)


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
    def test_conjunto_do_ahp_vai_a_frente_e_o_ahp_ordena_dentro_dele(self):
        problem = synthetic_problem(FRONT + [(9, 9)])
        method = ElectreThenAhp(PipelineSettings(0.5, 0.2, "faixa_linear", 1))
        result = method.evaluate(problem, np.array([0.5, 0.5]))
        chosen = set(result.details["conjunto_ahp"])
        self.assertNotIn(5, chosen)
        self.assertEqual(set(result.ranking[:len(chosen)]), chosen)
        self.assertIn(result.best, chosen)
        self.assertEqual(sorted(result.ranking), list(range(6)))
        self.assertAlmostEqual(sum(result.details["resumo"]["prioridade_global"].values()), 1.0)

    def test_mais_niveis_levam_mais_alternativas_ao_ahp(self):
        problem = synthetic_problem(FRONT + [(9, 9), (10, 10)])
        weights = np.array([0.5, 0.5])
        sizes = [ElectreThenAhp(PipelineSettings(0.5, 0.3, "faixa_linear", n)).evaluate(
            problem, weights).details["resumo"]["tamanho_ahp"] for n in (1, 2, 3)]
        self.assertLess(sizes[0], sizes[1])
        self.assertLessEqual(sizes[1], sizes[2])

    def test_niveis_invalidos(self):
        problem = synthetic_problem(FRONT)
        with self.assertRaises(ValueError):
            ElectreThenAhp(PipelineSettings(0.5, 0.3, "faixa_linear", 0)).evaluate(
                problem, np.array([0.5, 0.5]))


class HyperparameterTests(unittest.TestCase):
    def test_arquivo_do_projeto(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        weights = params.criteria_weights()
        self.assertAlmostEqual(weights.sum(), 1.0)
        if params.accept_above_limit:
            self.assertEqual(params.judgment_ratio_ceiling(), max(
                params.max_consistency_ratio, params.judgments_consistency_ratio()))
        else:
            self.assertLessEqual(params.judgments_consistency_ratio(), params.max_consistency_ratio)
        self.assertEqual(len(weights), len(params.criteria))
        self.assertIn(params.pipeline.tau_d, params.sensitivity.veto)
        self.assertIn(params.pipeline.tau_c, params.sensitivity.support)
        self.assertIn(params.pipeline.levels, params.sensitivity.levels)

    def test_qc_acima_do_maximo_exige_decisao_registrada(self):
        raw = json.loads((CONFIG_DIR / "decisao.json").read_text(encoding="utf-8"))
        raw["pesos"]["julgamentos"] = {"custo:desvio_sio2": 7, "custo:desvio_al2o3": 7,
                                       "custo:homogeneidade": 9, "desvio_sio2:desvio_al2o3": 3,
                                       "desvio_sio2:homogeneidade": 7, "desvio_al2o3:homogeneidade": 7}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisao.json"
            raw["pesos"]["aceitar_qc_acima_do_maximo"] = False
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                Hyperparameters.load(path).criteria_weights()
            raw["pesos"]["aceitar_qc_acima_do_maximo"] = True
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertAlmostEqual(Hyperparameters.load(path).criteria_weights().sum(), 1.0)

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
    def test_decisao_final_escolhe_uma_das_alternativas_do_ahp_com_os_pesos_do_arquivo(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        preparation = Preparation(DATA_FILE, RESULTS_DIR / "entrega_2", params.extra_criterion)
        record = FinalDecision(preparation, params).run()
        self.assertIn(record["escolhida"]["id"], record["electre1"]["conjunto_ahp"])
        self.assertAlmostEqual(sum(record["pesos"]["valores"]), 1.0)
        self.assertEqual(record["ranking_final"][0], record["escolhida"]["id"])
        self.assertAlmostEqual(sum(record["ahp"]["prioridade_global"].values()), 1.0)
        self.assertEqual(record["limiares"]["tau_d"], params.pipeline.tau_d)

    def test_tabela_compromissos_e_figuras(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        preparation = Preparation(DATA_FILE, RESULTS_DIR / "entrega_2", params.extra_criterion)
        record = FinalDecision(preparation, params).run()
        table = record["tabela"]
        self.assertEqual(len(table), len(preparation.problem.alternatives))
        self.assertEqual(sum(row["no_ahp"] for row in table), len(record["electre1"]["conjunto_ahp"]))
        winner = [row for row in table if row["posicao_final"] == 1]
        self.assertEqual([row["id"] for row in winner], [record["escolhida"]["id"]])
        self.assertEqual(set(record["compromissos"]), set(params.criteria))
        for key, item in record["compromissos"].items():
            self.assertTrue(0.0 <= item["posicao_na_faixa"] <= 1.0)
            self.assertEqual(item["ao_trocar_pela_melhor"][key]["variacao"],
                             item["melhor_valor"] - item["valor_da_escolhida"])
        with tempfile.TemporaryDirectory() as tmp:
            ChoiceFigures(preparation, record).write(Path(tmp))
            write_table(Path(tmp) / "tabela.csv", table, params.criteria)
            for name in ("projecoes_escolha.pdf", "solucao_final.pdf", "tabela.csv"):
                self.assertGreater((Path(tmp) / name).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
