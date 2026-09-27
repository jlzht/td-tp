"""Checagens das fórmulas, da construção e da busca nos dados do anexo."""
import random
import unittest
from collections import Counter
from pathlib import Path

from mono_objetivo import construct, evaluate, load_case, neighbor, neighbors, solve


DATA = Path(__file__).with_name("dados_exemplo.json")


class MonoObjectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case(DATA)

    def test_formula_manual_do_exemplo_da_p1(self):
        ores = self.case.ores
        for ids, cost, si, al in (
            ([14] * 6 + [13] * 4, 3_080_000, 7.2, 2.06),
            ([14] * 6 + [10] * 2 + [12] * 2, 3_320_000, 6.16, 1.56),
        ):
            row = [ores[j - 1] for j in ids]
            self.assertEqual(sum(2000 * ore.price for ore in row), cost)
            self.assertAlmostEqual(sum(ore.si for ore in row) / 10, si)
            self.assertAlmostEqual(sum(ore.al for ore in row) / 10, al)

    def test_construcao_por_preco_respeita_estoque_e_elegibilidade(self):
        case = self.case
        plan = construct(case)
        result = evaluate(case, plan)
        self.assertEqual(tuple(map(len, plan)), case.trucks)
        self.assertEqual(Counter(j + 1 for j in plan[0]),
                         Counter({14: 6, 13: 1, 4: 1, 10: 1, 11: 1}))
        self.assertAlmostEqual(result.si[0], 6.47)
        self.assertFalse(result.feasible)  # inviabilidade inicial permitida
        for ore, count in zip(case.ores, result.usage):
            self.assertLessEqual(ore.minimum, count)
            self.assertLessEqual(count, ore.maximum)

    def test_vizinhos_preservam_massa_e_elegibilidade(self):
        case = self.case
        plan = construct(case)
        usage = evaluate(case, plan).usage
        for kind in (1, 2, 3):
            moved = neighbor(case, plan, kind, random.Random(kind))
            self.assertIsNotNone(moved)
            result = evaluate(case, moved)  # lança erro se massa/elegibilidade falhar
            if kind == 2:
                self.assertEqual(result.usage, usage)
            if kind == 3:
                changed = [p for p in range(len(plan))
                           if Counter(plan[p]) != Counter(moved[p])]
                self.assertEqual(len(changed), 1)
                p = changed[0]
                common = sum((Counter(plan[p]) & Counter(moved[p])).values())
                self.assertGreaterEqual(len(plan[p]) - common,
                                        (len(plan[p]) + 1) // 2)
                for ore, count in zip(case.ores, result.usage):
                    self.assertLessEqual(ore.minimum, count)
                    self.assertLessEqual(count, ore.maximum)
                group = case.sinters[case.groups[p]]
                self.assertLessEqual(group.si_min, result.si[p])
                self.assertLessEqual(result.si[p], group.si_max)
                self.assertLessEqual(group.al_min, result.al[p])
                self.assertLessEqual(result.al[p], group.al_max)

    def test_gvns_devolve_planos_viaveis(self):
        case = self.case
        for objective in range(3):
            run = solve(case, objective, 1, seconds=2)
            self.assertGreater(run.evaluations, 0)
            self.assertGreater(run.seconds, 0)
            self.assertIsNotNone(run.best_plan)
            self.assertTrue(evaluate(case, run.best_plan).feasible)
            if objective == 0:
                rebuilt = neighbor(case, run.best_plan, 3, random.Random(5))
                self.assertIsNotNone(rebuilt)
                self.assertTrue(evaluate(case, rebuilt).feasible)

    def test_parametros_do_experimento_sao_aplicados(self):
        run = solve(self.case, 0, 1, seconds=2, base_seed=314)
        self.assertEqual(run.seed, 315)
        self.assertGreater(run.evaluations, 0)
        self.assertTrue(evaluate(self.case, run.best_plan).feasible)

    def test_enumeracao_n1_nao_repete_composicoes(self):
        plan = construct(self.case)
        moves = list(neighbors(self.case, plan, 1, random.Random(42)))
        compositions = {tuple(tuple(sorted(Counter(row).items())) for row in move)
                        for move in moves}
        self.assertEqual(len(moves), len(compositions))


if __name__ == "__main__":
    unittest.main()
