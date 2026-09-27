"""Entrega 1: GVNS para os três objetivos mono-objetivo.

Execute: python3 mono_objetivo.py
Veja README.md para dados, resultados e escolhas do algoritmo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass
from itertools import combinations, islice, product
from pathlib import Path

from figuras import write_convergence, write_solution


# Cinco execuções são exigidas pelo PDF. Os demais valores são escolhas
# reproduzíveis desta implementação, não parâmetros fornecidos no case.
RUNS = 5
ITERATIONS = 50          # ciclos globais de perturbação + VND por execução
N3_CANDIDATES = 2000     # limite por visita à N3, cuja enumeração pode ser enorme
REPAIR_STEPS = 100       # evita laço infinito se o reparo não achar plano viável
BASE_SEED = 2026        # início da sequência de sementes aleatórias


@dataclass
class Ore:
    price: float          # R$/t
    si: float             # %
    al: float             # %
    minimum: int          # caminhões usados no plano inteiro
    maximum: int
    sinters: set[int]


@dataclass
class Sinter:
    si_min: float
    si_target: float
    si_max: float
    al_min: float
    al_target: float
    al_max: float


@dataclass
class Case:
    truck_kt: int
    trucks: tuple[int, ...]       # caminhões exigidos por pilha
    groups: tuple[int, ...]       # Sinter de cada pilha
    ores: tuple[Ore, ...]
    sinters: dict[int, Sinter]

@dataclass
class Evaluation:
    objectives: tuple[float, float, float]  # R$, pp² SiO2, pp² Al2O3
    violation: float
    si: tuple[float, ...]
    al: tuple[float, ...]
    usage: tuple[int, ...]

    @property
    def feasible(self) -> bool:
        return self.violation == 0.0


@dataclass
class Run:
    objective: int
    number: int
    seed: int
    evaluations: int
    iterations: int
    seconds: float
    best_plan: list[list[int]] | None
    best_evaluation: Evaluation | None
    trace: list[tuple[int, float]]


class NoFeasiblePlanError(RuntimeError):
    """Reparo terminou sem encontrar um plano viável."""


def load_case(path: Path) -> Case:
    """Lê o JSON e converte a massa das pilhas em número de caminhões."""
    data = json.loads(path.read_text(encoding="utf-8"))
    q = data["capacidade_caminhao_kt"]
    piles = sorted(data["pilhas"], key=lambda p: p["id"])
    ore_data = sorted(data["minerios"], key=lambda o: o["id"])
    if not isinstance(q, int) or q <= 0:
        raise ValueError("capacidade_caminhao_kt deve ser inteiro positivo")
    if [p["id"] for p in piles] != list(range(1, len(piles) + 1)):
        raise ValueError("IDs das pilhas devem começar em 1 e ser consecutivos")
    if [o["id"] for o in ore_data] != list(range(1, len(ore_data) + 1)):
        raise ValueError("IDs dos minérios devem começar em 1 e ser consecutivos")
    if any(p["massa_kt"] <= 0 or p["massa_kt"] % q for p in piles):
        raise ValueError("massas devem ser positivas e múltiplas do caminhão")
    sinters = {
        s["id"]: Sinter(s["si_min"], s["si_alvo"], s["si_max"],
                        s["al_min"], s["al_alvo"], s["al_max"])
        for s in data["sinteres"]
    }
    groups = tuple(p["sinter"] for p in piles)
    ores = tuple(
        Ore(o["preco_rs_t"], o["si"], o["al"], o["min"], o["max"],
            set(o["sinteres"]))
        for o in ore_data
    )
    if any(g not in sinters for g in groups):
        raise ValueError("pilha aponta para Sinter inexistente")
    if any(o.minimum < 0 or o.maximum < o.minimum or
           not o.sinters or not o.sinters <= sinters.keys() for o in ores):
        raise ValueError("mínimos, máximos ou elegibilidade inválidos")
    if any(not (s.si_min < s.si_max and s.al_min < s.al_max and
                s.si_min <= s.si_target <= s.si_max and
                s.al_min <= s.al_target <= s.al_max) for s in sinters.values()):
        raise ValueError("limites ou alvos de qualidade inválidos")
    trucks = tuple(p["massa_kt"] // q for p in piles)
    if not sum(o.minimum for o in ores) <= sum(trucks) <= sum(o.maximum for o in ores):
        raise ValueError("disponibilidade total incompatível com a massa")
    return Case(q, trucks, groups, ores, sinters)


def evaluate(case: Case, plan: list[list[int]]) -> Evaluation:
    """Calcula os três objetivos e as violações de qualidade/disponibilidade."""
    if len(plan) != len(case.trucks):
        raise ValueError("número incorreto de pilhas")
    usage = [0] * len(case.ores)
    si_values, al_values = [], []
    cost = si_error = al_error = violation = 0.0
    for p, row in enumerate(plan):
        if len(row) != case.trucks[p]:
            raise ValueError(f"massa incorreta na P{p + 1}")
        si_sum = al_sum = 0.0
        for j in row:
            if not isinstance(j, int) or not 0 <= j < len(case.ores):
                raise ValueError(f"minério inválido na P{p + 1}")
            ore = case.ores[j]
            if case.groups[p] not in ore.sinters:
                raise ValueError(f"minério inelegível na P{p + 1}")
            usage[j] += 1
            cost += 1000 * case.truck_kt * ore.price
            si_sum += ore.si
            al_sum += ore.al
        si, al = si_sum / len(row), al_sum / len(row)
        si_values.append(si)
        al_values.append(al)
        group = case.sinters[case.groups[p]]
        si_error += (si - group.si_target) ** 2
        al_error += (al - group.al_target) ** 2
        violation += (max(0.0, group.si_min - si) +
                      max(0.0, si - group.si_max)) / (group.si_max - group.si_min)
        violation += (max(0.0, group.al_min - al) +
                      max(0.0, al - group.al_max)) / (group.al_max - group.al_min)
    for ore, count in zip(case.ores, usage):
        violation += (max(0, ore.minimum - count) +
                      max(0, count - ore.maximum)) / max(1, ore.maximum - ore.minimum)
    if violation <= 1e-10:  # despreza apenas erro numérico de arredondamento
        violation = 0.0
    return Evaluation((cost, si_error, al_error), violation,
                      tuple(si_values), tuple(al_values), tuple(usage))


def capacity_possible(case: Case, plan: list[list[int]], usage: list[int]) -> bool:
    """Descarta escolhas que deixam capacidade insuficiente para completar pilhas."""
    remaining = {
        g: sum(case.trucks[p] - len(plan[p])
               for p in range(len(plan)) if case.groups[p] == g)
        for g in case.sinters
    }
    free = [ore.maximum - usage[j] for j, ore in enumerate(case.ores)]
    if any(amount < 0 for amount in free):
        return False
    if sum(remaining.values()) > sum(free):
        return False
    for group, needed in remaining.items():
        available = sum(free[j] for j, ore in enumerate(case.ores)
                        if group in ore.sinters)
        if needed > available:
            return False
    return True


def construct(case: Case) -> list[list[int]]:
    """Mínimos em rodízio; depois completa P1–P10 por preço crescente."""
    plan = [[] for _ in case.trucks]
    usage = [0] * len(case.ores)
    # Minérios exclusivos primeiro; os demais em ordem de ID.
    mandatory = sorted((j for j, ore in enumerate(case.ores) if ore.minimum),
                       key=lambda j: (len(case.ores[j].sinters), j))
    for j in mandatory:
        eligible = [p for p, g in enumerate(case.groups) if g in case.ores[j].sinters]
        cursor = 0
        for _ in range(case.ores[j].minimum):
            for offset in range(len(eligible)):
                position = (cursor + offset) % len(eligible)
                p = eligible[position]
                if len(plan[p]) == case.trucks[p]:
                    continue
                plan[p].append(j)
                usage[j] += 1
                if capacity_possible(case, plan, usage):
                    cursor = (position + 1) % len(eligible)
                    break
                plan[p].pop()
                usage[j] -= 1
            else:
                raise ValueError(f"não foi possível distribuir o mínimo de M{j + 1}")
    by_price = sorted(range(len(case.ores)),
                      key=lambda j: (case.ores[j].price, j))
    for p, row in enumerate(plan):
        while len(row) < case.trucks[p]:
            for j in by_price:
                ore = case.ores[j]
                if case.groups[p] not in ore.sinters or usage[j] == ore.maximum:
                    continue
                row.append(j)
                usage[j] += 1
                if capacity_possible(case, plan, usage):
                    break
                row.pop()
                usage[j] -= 1
            else:
                raise ValueError(f"não foi possível completar P{p + 1}")
    return plan  # a etapa de reparo verifica e corrige a qualidade


def neighbors(case: Case, plan: list[list[int]], kind: int,
              rng: random.Random):
    """Percorre vizinhos de N1, N2 ou N3 em ordem sorteada.

    Posições com o mesmo minério na mesma pilha são equivalentes: a composição,
    os objetivos e as restrições dependem das contagens, não da ordem do vetor.
    """
    piles = list(range(len(plan)))
    rng.shuffle(piles)
    positions = [{j: row.index(j) for j in set(row)} for row in plan]
    ore_ids = [list(found) for found in positions]
    for ids in ore_ids:
        rng.shuffle(ids)

    if kind == 1:
        for p in piles:
            choices = [j for j, ore in enumerate(case.ores)
                       if case.groups[p] in ore.sinters]
            rng.shuffle(choices)
            for old in ore_ids[p]:
                for new in choices:
                    if new == old:
                        continue
                    candidate = [row.copy() for row in plan]
                    candidate[p][positions[p][old]] = new
                    yield candidate
        return

    if kind == 3:
        # N3: fixa nove pilhas e reconstrói a composição INTEIRA da décima.
        # Busca por contagens de minérios (não por permutações de posições).
        global_usage = [sum(row.count(j) for row in plan)
                        for j in range(len(case.ores))]
        for p in piles:
            n = len(plan[p])
            group = case.sinters[case.groups[p]]
            eligible = [j for j, ore in enumerate(case.ores)
                        if case.groups[p] in ore.sinters]
            rng.shuffle(eligible)
            old_count = {j: plan[p].count(j) for j in eligible}
            lower, upper = [], []
            for j in eligible:
                used_elsewhere = global_usage[j] - old_count[j]
                ore = case.ores[j]
                lower.append(max(0, ore.minimum - used_elsewhere))
                upper.append(min(n, ore.maximum - used_elsewhere))
            if (any(high < low for low, high in zip(lower, upper)) or
                    sum(lower) > n or sum(upper) < n):
                continue
            min_si, max_si = n * group.si_min, n * group.si_max
            min_al, max_al = n * group.al_min, n * group.al_max
            si_values = [case.ores[j].si for j in eligible]
            al_values = [case.ores[j].al for j in eligible]
            counts = [0] * len(eligible)
            min_changes = (n + 1) // 2

            def quality_range(values: list[float], start: int, remaining: int):
                """Menor e maior teor ainda possíveis nas posições restantes."""
                base = sum(lower[t] * values[t]
                           for t in range(start, len(eligible)))
                free = remaining - sum(lower[start:])
                options = sorted((values[t], upper[t] - lower[t])
                                 for t in range(start, len(eligible)))
                bounds = []
                for order in (options, reversed(options)):
                    total, left = base, free
                    for value, capacity in order:
                        take = min(left, capacity)
                        total += take * value
                        left -= take
                        if left == 0:
                            break
                    bounds.append(total)
                return bounds[0], bounds[1]

            def rebuild(index: int, remaining: int, si: float, al: float):
                if not sum(lower[index:]) <= remaining <= sum(upper[index:]):
                    return
                si_low, si_high = quality_range(si_values, index, remaining)
                al_low, al_high = quality_range(al_values, index, remaining)
                if (si + si_low > max_si + 1e-10 or
                        si + si_high < min_si - 1e-10 or
                        al + al_low > max_al + 1e-10 or
                        al + al_high < min_al - 1e-10):
                    return
                if index == len(eligible):
                    changed = n - sum(min(counts[t], old_count[eligible[t]])
                                      for t in range(len(eligible)))
                    if changed >= min_changes:
                        candidate = [row.copy() for row in plan]
                        candidate[p] = [j for t, j in enumerate(eligible)
                                        for _ in range(counts[t])]
                        yield candidate
                    return
                j = eligible[index]
                choices = list(range(lower[index], min(upper[index], remaining) + 1))
                rng.shuffle(choices)
                for count in choices:
                    counts[index] = count
                    yield from rebuild(index + 1, remaining - count,
                                       si + count * case.ores[j].si,
                                       al + count * case.ores[j].al)
                counts[index] = 0

            yield from rebuild(0, n, 0.0, 0.0)
        return

    if kind != 2:
        raise ValueError("vizinhança deve ser N1, N2 ou N3")
    for p, q in combinations(piles, 2):
        for a, b in product(ore_ids[p], ore_ids[q]):
            if a == b or case.groups[q] not in case.ores[a].sinters or \
                    case.groups[p] not in case.ores[b].sinters:
                continue
            candidate = [row.copy() for row in plan]
            candidate[p][positions[p][a]] = b
            candidate[q][positions[q][b]] = a
            yield candidate


def neighbor(case: Case, plan: list[list[int]], kind: int,
             rng: random.Random) -> list[list[int]] | None:
    """Primeiro vizinho na ordem sorteada; útil para a perturbação inicial."""
    return next(neighbors(case, plan, kind, rng), None)


def solve(case: Case, objective: int, number: int, iterations: int = ITERATIONS,
          base_seed: int = BASE_SEED) -> Run:
    """Repara a construção e executa um número fixo de ciclos da GVNS."""
    if iterations <= 0:
        raise ValueError("iteracoes deve ser positivo")
    started = time.perf_counter()
    seed = base_seed + objective * 10000 + number
    rng = random.Random(seed)
    current = construct(case)
    current_result = evaluate(case, current)
    evaluations = 1
    best_plan = best_result = None
    trace = []

    def consider(plan: list[list[int]]) -> Evaluation:
        nonlocal evaluations, best_plan, best_result
        result = evaluate(case, plan)
        evaluations += 1
        if result.feasible and (best_result is None or
                result.objectives[objective] < best_result.objectives[objective] - 1e-10):
            best_plan = [row.copy() for row in plan]
            best_result = result
            trace.append((evaluations, result.objectives[objective]))
        return result

    def candidates(plan: list[list[int]], level: int):
        generated = neighbors(case, plan, level, rng)
        return islice(generated, N3_CANDIDATES) if level == 3 else generated

    def local_search(plan: list[list[int]], result: Evaluation, repairing: bool):
        level = 1
        # A busca local visita N1, N2 e N3; melhora reinicia em N1.
        last_level = 3
        while level <= last_level:
            improved = False
            for candidate in candidates(plan, level):
                candidate_result = consider(candidate)
                if repairing and candidate_result.feasible:
                    return candidate, candidate_result
                if not repairing and not candidate_result.feasible:
                    continue  # política da GVNS: rejeitar o movimento inviável
                before = result.violation if repairing else result.objectives[objective]
                after = (candidate_result.violation if repairing else
                         candidate_result.objectives[objective])
                if after < before - 1e-12:
                    plan, result = candidate, candidate_result
                    level = 1
                    improved = True
                    break  # primeira melhora
            if not improved:
                level += 1
        return plan, result

    if current_result.feasible:
        best_plan = [row.copy() for row in current]
        best_result = current_result
        trace.append((1, current_result.objectives[objective]))

    # A construção do PDF pode violar qualidade. O reparo procura uma
    # primeira solução factível; seus planos provisórios não entram na GVNS.
    level = 1
    for _ in range(REPAIR_STEPS):
        if best_plan is not None:
            break
        shaken = [row.copy() for row in current]
        for _ in range(level):
            moved = neighbor(case, shaken, level, rng)
            if moved is not None:
                shaken = moved
        shaken_result = consider(shaken)
        if best_plan is not None:
            break
        shaken, shaken_result = local_search(shaken, shaken_result, repairing=True)
        if best_plan is not None:
            break
        if shaken_result.violation < current_result.violation - 1e-12:
            current, current_result = shaken, shaken_result
            level = 1
        else:
            level = level % 3 + 1
    if best_plan is None:
        raise NoFeasiblePlanError("não foi possível reparar a construção")
    current = [row.copy() for row in best_plan]
    current_result = best_result
    assert current_result.feasible

    level = 1
    for _ in range(iterations):
        shaken = [row.copy() for row in current]
        for _ in range(level):
            for moved in candidates(shaken, level):
                moved_result = consider(moved)
                if moved_result.feasible:
                    shaken = moved
                    break
        shaken_result = consider(shaken)
        shaken, shaken_result = local_search(shaken, shaken_result, repairing=False)
        assert shaken_result.feasible
        if shaken_result.objectives[objective] < current_result.objectives[objective] - 1e-12:
            current, current_result = shaken, shaken_result
            level = 1
        else:
            level = level % 3 + 1
    return Run(objective, number, seed, evaluations, iterations,
               time.perf_counter() - started, best_plan, best_result, trace)


def write_outputs(case: Case, runs: list[Run], directory: Path,
                  data_path: Path, iterations: int = ITERATIONS,
                  base_seed: int = BASE_SEED) -> None:
    """Grava as 15 execuções, estatísticas, planos e figuras do relatório."""
    directory.mkdir(parents=True, exist_ok=True)
    config = {
        "metodo": "gvns", "dados": data_path.name,
        "sha256_dados": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "execucoes_por_objetivo": RUNS,
        "python": sys.version.split()[0],
        "limite_iteracoes_gvns": iterations,
        "limite_candidatos_n3_por_visita": N3_CANDIDATES,
        "limite_passos_reparo": REPAIR_STEPS,
        "politica_inviabilidade": "reparo inicial; rejeição de candidatos inviáveis na GVNS",
        "semente_base": base_seed,
        "construcao": "mínimos em rodízio; completar por preço crescente",
        "vizinhanças": "N1 substituição; N2 troca entre pilhas; N3 reconstrução integral de uma pilha, com ao menos metade dos caminhões alterados",
        "busca_local": "N1 e N2 até primeira melhora ou exaustão; N3 até primeira melhora ou 2000 candidatos por visita",
    }
    (directory / "configuracao.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    with (directory / "execucoes.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["objetivo", "execucao", "semente", "iteracoes_gvns",
                         "avaliacoes", "segundos_medidos",
                         "f1_rs", "f2_pp2", "f3_pp2", "violacao"])
        for run in runs:
            if run.best_evaluation is None:
                raise RuntimeError(f"f{run.objective + 1}, execução {run.number}: sem plano factível")
            result = run.best_evaluation
            writer.writerow([f"f{run.objective + 1}", run.number, run.seed,
                             run.iterations, run.evaluations, run.seconds,
                             *result.objectives, result.violation])
    summary, solutions = [], {}
    for objective in range(3):
        selected = [r for r in runs if r.objective == objective]
        values = [r.best_evaluation.objectives[objective] for r in selected]
        best = min(selected, key=lambda r: r.best_evaluation.objectives[objective])
        summary.append([f"f{objective + 1}", min(values), statistics.mean(values),
                        statistics.stdev(values), max(values)])
        result = best.best_evaluation
        solutions[f"f{objective + 1}"] = {
            "execucao": best.number, "semente": best.seed,
            "f1_rs": result.objectives[0], "f2_pp2": result.objectives[1],
            "f3_pp2": result.objectives[2], "si_por_pilha": result.si,
            "al_por_pilha": result.al,
            "caminhoes_por_pilha_e_minerio": [
                [row.count(j) for j in range(len(case.ores))]
                for row in best.best_plan
            ],
        }
        write_convergence(directory / f"convergencia_f{objective + 1}.pdf", selected)
        write_solution(directory / f"melhor_f{objective + 1}.pdf", case, best)
    with (directory / "resumo.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["objetivo", "minimo", "media", "desvio_padrao_amostral", "maximo"])
        writer.writerows(summary)
    (directory / "melhores_solucoes.json").write_text(
        json.dumps(solutions, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "convergencia.json").write_text(
        json.dumps({f"f{r.objective + 1}_exec{r.number}": r.trace for r in runs},
                   indent=2), encoding="utf-8")


def run_method(case: Case, iterations: int = ITERATIONS,
               base_seed: int = BASE_SEED) -> list[Run]:
    runs = []
    for objective in range(3):
        for number in range(1, RUNS + 1):
            run = solve(case, objective, number, iterations, base_seed)
            runs.append(run)
            value = run.best_evaluation.objectives[objective]
            print(f"GVNS, f{objective + 1}, execução {number}: {value}",
                  flush=True)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteracoes", type=int, default=ITERATIONS,
                        help="ciclos globais da GVNS por execução (padrão: 50)")
    parser.add_argument("--semente-base", type=int, default=BASE_SEED,
                        help="ponto de partida dos sorteios reproduzíveis")
    parser.add_argument("--dados", type=Path,
                        default=Path(__file__).with_name("dados_exemplo.json"))
    parser.add_argument("--saida", type=Path,
                        help="pasta de saída; padrão: resultados")
    args = parser.parse_args()
    if args.iteracoes <= 0:
        parser.error("--iteracoes deve ser positivo")
    case = load_case(args.dados)
    directory = args.saida or Path(__file__).with_name("resultados")
    runs = run_method(case, args.iteracoes, args.semente_base)
    write_outputs(case, runs, directory, args.dados,
                  args.iteracoes, args.semente_base)
    print(f"Resultados em {directory.resolve()}")


if __name__ == "__main__":
    main()
