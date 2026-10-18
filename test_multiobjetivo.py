"""Checagens multiobjetivo em instância pequena e nas referências reais."""
import contextlib
import hashlib
import io
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import multiobjetivo as multi
from mono_objetivo import (Case, Ore, Sinter, evaluate,
                          construct, load_case, neighbors, solve_scalar)

ROOT = Path(__file__).resolve().parent


def small_case():
    return Case(2, (2,), (1,),
                (Ore(100, 5.8, 1.8, 0, 2, {1}),
                 Ore(200, 5, 1, 0, 2, {1}),
                 Ore(150, 5.4, 1.8, 0, 2, {1})),
                {1: Sinter(4, 5, 6, .5, 1, 2.2)})


class MultiObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.case = small_case()
        self.normal = multi.Normalization((400000, 0, 0), (800000, .64, .64))
        self.config = {"id": "eps_test", "epsilons": [.1, .1]}
        self.criterion = multi.make_criterion("epsilon", self.config, self.normal)

    def test_normalizacao_fixa_sem_corte(self):
        self.assertEqual(self.normal.apply((400000, 0, 0)), (0, 0, 0))
        self.assertEqual(self.normal.apply((800000, .64, .64)), (1, 1, 1))
        self.assertEqual(self.normal.apply((200000, 1.28, .32)), (-.5, 2, .5))
        with self.assertRaises(ValueError):
            multi.Normalization((0, 0, 0), (0, 1, 1))

    def test_referencias_reais_conferidas(self):
        case = load_case(ROOT/"dados_exemplo.json")
        normal, plans, source = multi.load_normalization(ROOT/"normalizacao.json",
                                                       ROOT/"dados_exemplo.json", case)
        self.assertEqual(len(plans), 3)
        self.assertEqual(normal.a[0], 59860000)
        self.assertEqual(source["n3_candidate_limit"], None)

    def test_soma_ponderada_manual(self):
        criterion = multi.make_criterion("soma", {"id": "w", "pesos": [.5, .25, .25]}, self.normal)
        result = evaluate(self.case, [[1, 1]])
        self.assertTrue(criterion.feasible(result))
        self.assertAlmostEqual(criterion.value(result), .5)

    def test_epsilon_rejeita_plano_fisicamente_viavel(self):
        result = evaluate(self.case, [[0, 0]])
        self.assertTrue(result.feasible)
        self.assertFalse(self.criterion.feasible(result))
        self.assertAlmostEqual(self.criterion.violation(result), 1.8)
        rebuilt = list(neighbors(self.case, [[1, 1]], 3, random.Random(1)))
        self.assertTrue(any(evaluate(self.case, p).feasible and
                            not self.criterion.feasible(evaluate(self.case, p)) for p in rebuilt))

    def test_reparo_inclui_epsilon_e_nao_soma_penalidade_ao_custo(self):
        run = solve_scalar(self.case, self.criterion, 42, iterations=2)
        self.assertTrue(self.criterion.feasible(run.best_evaluation))
        self.assertEqual(run.best_plan, [[1, 1]])
        self.assertAlmostEqual(self.criterion.value(run.best_evaluation), 1)
        self.assertTrue(all(abs(value-1) < 1e-10 for _, value in run.trace))

    def test_ambas_abordagens_chamam_construcao_original(self):
        # Mesmo vetor bruto, sem seleção de referência como partida.
        configs = {"soma": {"id": "w", "pesos": [1/3]*3},
                   "epsilon": {"id": "eps", "epsilons": [1, 1]}}
        for method, config in configs.items():
            with self.subTest(method=method), \
                 patch("mono_objetivo.construct", wraps=construct) as builder, \
                 patch("mono_objetivo.neighbors", return_value=iter(())):
                record = multi.execute_job((self.case, self.normal, method, config, 1, 42, 1))
            builder.assert_called_once_with(self.case)
            self.assertEqual(record["status"], "ok")
            self.assertEqual(record["partida"], "construcao")
            self.assertEqual(record["caminhoes_por_pilha_e_minerio"], [[2, 0, 0]])

    def test_epsilon_sem_solucao_pode_ser_interrompido(self):
        # A configuração não admite as receitas disponíveis: não exportar ponto inválido.
        case = small_case()
        case.ores = (case.ores[0], case.ores[2])
        with patch("mono_objetivo.neighbor", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                multi.execute_job((case, self.normal, "epsilon", self.config, 1, 42, 1))

    def test_dominancia_em_tres_objetivos(self):
        self.assertTrue(multi.dominates((60, 3, 2), (61, 4, 2)))
        self.assertFalse(multi.dominates((60, 3, 2), (59, 4, 2)))
        self.assertFalse(multi.dominates((60, 3, 2), (60, 3, 2)))
        # Parece pior nos eixos custo/Si, mas melhora Al: deve permanecer.
        self.assertFalse(multi.dominates((60, 3, 2), (61, 4, 1)))

    def test_duplicatas_por_receita_preservam_origens_e_empates(self):
        def record(round_number, counts, objectives):
            return {"status": "ok", "rodada": round_number, "configuracao": "w", "semente": round_number,
                    "objetivos": objectives, "normalizados": objectives,
                    "caminhoes_por_pilha_e_minerio": [counts]}
        records = [record(1, [2, 0], [60, 3, 2]), record(2, [2, 0], [60, 3, 2]),
                   record(3, [1, 1], [60, 3, 2]), record(1, [0, 2], [61, 4, 2])]
        points = multi.nondominated(records)
        self.assertEqual(len(points), 2)
        self.assertEqual(len(points[0]["origens"]), 2)

    def test_grade_tem_16_configuracoes_e_valores_validos(self):
        configs = multi.load_configurations(ROOT/"configuracoes_multi.json")
        self.assertEqual(len(configs["soma"]), 7)
        self.assertEqual(len(configs["epsilon"]), 9)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"bad.json"
            configs["soma"][0]["pesos"] = [1, 1, 1]
            path.write_text(json.dumps(configs))
            with self.assertRaises(ValueError):
                multi.load_configurations(path)

    def test_pipeline_cli_e_retomada_em_instancia_pequena(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = {"capacidade_caminhao_kt": 2, "pilhas": [{"id": 1, "massa_kt": 4, "sinter": 1}],
                    "sinteres": [{"id": 1, "si_min": 4, "si_alvo": 5, "si_max": 6,
                                  "al_min": .5, "al_alvo": 1, "al_max": 2.2}],
                    "minerios": [{"id": j+1, "preco_rs_t": o.price, "si": o.si, "al": o.al,
                                  "min": 0, "max": 2, "sinteres": [1]} for j, o in enumerate(self.case.ores)]}
            data_path = root/"dados.json"
            data_path.write_text(json.dumps(data))
            references, payoff = {}, []
            for q, plan in enumerate(([[0, 0]], [[1, 1]], [[2, 2]])):
                e = evaluate(self.case, plan)
                references[f"f{q+1}"] = {"f1_rs": e.objectives[0], "f2_pp2": e.objectives[1],
                                       "f3_pp2": e.objectives[2], "caminhoes_por_pilha_e_minerio":
                                       [[plan[0].count(j) for j in range(3)]]}
                payoff.append({"values": e.objectives})
            normal_source = {"data_sha256": multi.data_digest(data_path),
                             "references": references, "payoff_table": payoff,
                             "a": [min(p["values"][q] for p in payoff) for q in range(3)],
                             "b": [max(p["values"][q] for p in payoff) for q in range(3)]}
            normal_path = root/"normal.json"
            normal_path.write_text(json.dumps(normal_source))
            config_path = root/"configs.json"
            config_path.write_text(json.dumps({"soma": [{"id": "w", "pesos": [1/3]*3}],
                                               "epsilon": [self.config]}))
            output = root/"saida"
            command = ["multiobjetivo.py", "--dados", str(data_path), "--normalizacao", str(normal_path),
                       "--configuracoes", str(config_path), "--saida", str(output),
                       "--iteracoes", "1", "--rodadas", "1"]
            with patch.object(sys, "argv", command), contextlib.redirect_stdout(io.StringIO()):
                multi.main()
            self.assertEqual(len(list(output.glob("*.pdf"))), 6)
            self.assertTrue(json.loads((output/"resumo.json").read_text())["completo"])
            with patch.object(sys, "argv", command), patch("multiobjetivo.execute_job") as execute, contextlib.redirect_stdout(io.StringIO()):
                multi.main()
                execute.assert_not_called()
            # A pasta não pode misturar lotes com parâmetros diferentes.
            with patch.object(sys, "argv", command + ["--iteracoes", "2"]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    multi.main()
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
