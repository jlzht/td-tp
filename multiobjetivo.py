"""Entrega 2: Soma Ponderada e ε-restrito usando a mesma GVNS.

Execute python3 multiobjetivo.py --help. O README explica as rodadas,
normalização, retomada de lotes e arquivos de saída.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import multiprocessing
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from dataclasses import dataclass
from pathlib import Path

from figuras import write_projections
from mono_objetivo import (BASE_SEED, ITERATIONS, REPAIR_STEPS, RUNS, Case,
                          Criterion, Evaluation, NoFeasiblePlanError, evaluate,
                          load_case, solve_scalar)

ROOT = Path(__file__).resolve().parent
EPS_TOL = 1e-10
# Dominância: tolerância absoluta por unidade (R$, pp², pp²).
DOM_TOL = (1e-6, 1e-10, 1e-10)


@dataclass
class Normalization:
    """Referências congeladas; resultados fora de [0,1] não são cortados."""
    a: tuple[float, float, float]
    b: tuple[float, float, float]

    def __post_init__(self):
        if len(self.a) != 3 or len(self.b) != 3 or any(
                not math.isfinite(low) or not math.isfinite(high) or high <= low
                for low, high in zip(self.a, self.b)):
            raise ValueError("normalização exige três escalas finitas com b > a")

    def apply(self, objectives):
        return tuple((value - low) / (high - low)
                     for value, low, high in zip(objectives, self.a, self.b))


def plan_from_counts(case: Case, counts) -> list[list[int]]:
    """Converte a matriz x_ij em vetores; rejeita dados incompletos."""
    if len(counts) != len(case.trucks) or any(
            len(row) != len(case.ores) or
            any(type(n) is not int or n < 0 for n in row) for row in counts):
        raise ValueError("matriz de caminhões inválida")
    return [[j for j, count in enumerate(row) for _ in range(count)] for row in counts]


def load_normalization(path: Path, data_path: Path, case: Case):
    """Confere hash, receitas, objetivos e extremos da matriz de referência."""
    source = json.loads(path.read_text(encoding="utf-8"))
    if source["data_sha256"] != hashlib.sha256(data_path.read_bytes()).hexdigest():
        raise ValueError("normalização pertence a outro arquivo de dados")
    values, plans = [], []
    for q in ("f1", "f2", "f3"):
        reference = source["references"][q]
        plan = plan_from_counts(case, reference["caminhoes_por_pilha_e_minerio"])
        result = evaluate(case, plan)
        expected = [reference[k] for k in ("f1_rs", "f2_pp2", "f3_pp2")]
        if not result.feasible or any(abs(x-y) > tol for x, y, tol in
                                     zip(result.objectives, expected, DOM_TOL)):
            raise ValueError(f"receita ou objetivos de referência inválidos: {q}")
        values.append(expected)
        plans.append(plan)
    a = tuple(min(row[q] for row in values) for q in range(3))
    b = tuple(max(row[q] for row in values) for q in range(3))
    if list(a) != source["a"] or list(b) != source["b"]:
        raise ValueError("a e b não correspondem à matriz de referência")
    if [row["values"] for row in source["payoff_table"]] != values:
        raise ValueError("payoff_table diverge das receitas de referência")
    return Normalization(a, b), plans, source


def load_configurations(path: Path):
    """Pesos não negativos com soma 1; ε finitos e não negativos."""
    configs = json.loads(path.read_text(encoding="utf-8"))
    if set(configs) != {"soma", "epsilon"}:
        raise ValueError("configurações devem conter soma e epsilon")
    for method, entries in configs.items():
        ids = set()
        if not entries or len(entries) >= 1000:
            raise ValueError("cada abordagem precisa de 1 a 999 configurações")
        for item in entries:
            identifier = item["id"]
            if not identifier or not all(c.isascii() and (c.isalnum() or c == "_")
                                         for c in identifier) or identifier in ids:
                raise ValueError("IDs de configuração devem ser únicos e usar letras, números e _")
            ids.add(identifier)
            key, length = ("pesos", 3) if method == "soma" else ("epsilons", 2)
            values = item[key]
            if len(values) != length or any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError(f"valores inválidos em {identifier}")
            if method == "soma" and not math.isclose(sum(values), 1, rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"pesos devem somar 1 em {identifier}")
    return configs


def make_criterion(method: str, config: dict, normalization: Normalization) -> Criterion:
    """Restrição de ε entra na admissibilidade e na medida de reparo."""
    if method == "soma":
        weights = config["pesos"]
        return Criterion(config["id"],
                         lambda e: sum(w*f for w, f in
                                       zip(weights, normalization.apply(e.objectives))),
                         lambda e: e.violation)
    if method != "epsilon":
        raise ValueError("abordagem deve ser soma ou epsilon")
    eps2, eps3 = config["epsilons"]

    def violation(result: Evaluation) -> float:
        _, f2, f3 = normalization.apply(result.objectives)
        # Despreza apenas excesso numérico <= EPS_TOL em cada limite.
        extra = sum(excess for excess in (f2-eps2, f3-eps3) if excess > EPS_TOL)
        return result.violation + extra

    return Criterion(config["id"], lambda e: normalization.apply(e.objectives)[0], violation)


def dominates(a, b) -> bool:
    """Dominância nos TRÊS objetivos minimizados, antes de arredondar."""
    return (all(x <= y + tol for x, y, tol in zip(a, b, DOM_TOL)) and
            any(x < y - tol for x, y, tol in zip(a, b, DOM_TOL)))


def nondominated(records: list[dict]) -> list[dict]:
    """Une receitas idênticas e preserva origens; mantém empates de receitas distintas."""
    distinct = {}
    for record in records:
        if record["status"] != "ok":
            continue
        key = tuple(tuple(row) for row in record["caminhoes_por_pilha_e_minerio"])
        origin = {k: record[k] for k in ("rodada", "configuracao", "semente")}
        if key not in distinct:
            distinct[key] = {"objetivos": record["objetivos"],
                             "normalizados": record["normalizados"],
                             "caminhoes_por_pilha_e_minerio": record["caminhoes_por_pilha_e_minerio"],
                             "origens": []}
        distinct[key]["origens"].append(origin)
    points = list(distinct.values())
    return [point for point in points if not any(
        dominates(other["objetivos"], point["objetivos"]) for other in points)]


def execute_job(job) -> dict:
    """Uma configuração em uma rodada; sem alteração automática dos limites."""
    case, normalization, references, method, config, round_number, seed, iterations = job
    criterion = make_criterion(method, config, normalization)
    initial = None
    start = "construcao"
    # Política fixa: no ε-restrito, escolher a referência admissível mais barata.
    # Sem referência admissível, construir e reparar incluindo os ε.
    if method == "epsilon":
        admissible = [(evaluate(case, p).objectives[0], index, p)
                      for index, p in enumerate(references)
                      if criterion.feasible(evaluate(case, p))]
        if admissible:
            _, index, initial = min(admissible, key=lambda item: (item[0], item[1]))
            start = f"referencia_f{index+1}"
    record = {"metodo": method, "configuracao": config["id"], "parametros": config,
              "rodada": round_number, "semente": seed, "iteracoes": iterations,
              "partida": start}
    try:
        run = solve_scalar(case, criterion, seed, iterations, initial)
    except NoFeasiblePlanError as exc:
        return {**record, "status": "falha_reparo", "mensagem": str(exc),
                "avaliacoes": exc.evaluations, "segundos": exc.seconds}
    result = evaluate(case, run.best_plan)
    if not criterion.feasible(result):
        raise RuntimeError("GVNS retornou plano que viola as restrições ativas")
    return {**record, "status": "ok", "avaliacoes": run.evaluations,
            "segundos": run.seconds, "objetivos": result.objectives,
            "normalizados": normalization.apply(result.objectives),
            "valor_escalar": criterion.value(result), "violacao_fisica": result.violation,
            "si_por_pilha": result.si, "al_por_pilha": result.al,
            "caminhoes_por_pilha_e_minerio": [[row.count(j) for j in range(len(case.ores))]
                                             for row in run.best_plan],
            "convergencia": run.trace}


def write_json(path: Path, data) -> None:
    """Arquivo completo só substitui o anterior depois de gravado."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                         encoding="utf-8")
    temporary.replace(path)


def export_results(directory: Path, records: list[dict], methods: list[str], rounds: int,
                   expected: int) -> None:
    """Exporta também falhas; gráficos usam apenas resultados admissíveis."""
    fields = ["metodo", "rodada", "configuracao", "status", "semente", "iteracoes",
              "partida", "avaliacoes", "segundos", "f1_rs", "f2_pp2", "f3_pp2",
              "f1_normalizado", "f2_normalizado", "f3_normalizado", "valor_escalar"]
    with (directory/"execucoes.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in fields}
            if record["status"] == "ok":
                row.update(zip(fields[9:12], record["objetivos"]))
                row.update(zip(fields[12:15], record["normalizados"]))
            writer.writerow(row)
    summary = {"completo": len(records) == expected, "chamadas_previstas": expected,
               "chamadas_concluidas": len(records), "abordagens": {}}
    for method in methods:
        selected = [r for r in records if r["metodo"] == method]
        points = nondominated(selected)
        by_round = {str(n): nondominated([r for r in selected if r["rodada"] == n])
                    for n in range(1, rounds+1)}
        write_json(directory/f"nao_dominadas_{method}.json", points)
        write_json(directory/f"nao_dominadas_rodadas_{method}.json", by_round)
        valid = [r for r in selected if r["status"] == "ok"]
        summary["abordagens"][method] = {
            "chamadas": len(selected), "viaveis": len(valid),
            "falhas_reparo": len(selected)-len(valid), "receitas_nao_dominadas": len(points),
            "avaliacoes": sum(r["avaliacoes"] for r in selected),
            "soma_segundos_das_chamadas": sum(r["segundos"] for r in selected),
            "por_rodada": {n: len(p) for n, p in by_round.items()},
            "minimos_observados": [min(r["objetivos"][q] for r in valid) for q in range(3)]
                                   if valid else None,
            "maximos_observados": [max(r["objetivos"][q] for r in valid) for q in range(3)]
                                   if valid else None}
        write_projections(directory, method, points, rounds)
    write_json(directory/"resumo.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=ROOT/"dados_exemplo.json")
    parser.add_argument("--normalizacao", type=Path, default=ROOT/"normalizacao.json")
    parser.add_argument("--configuracoes", type=Path, default=ROOT/"configuracoes_multi.json")
    parser.add_argument("--metodo", choices=("todos", "soma", "epsilon"), default="todos")
    parser.add_argument("--configuracao", action="append", help="ID para piloto; pode repetir a opção")
    parser.add_argument("--rodadas", type=int, default=RUNS, help="padrão: 5; piloto: 1")
    parser.add_argument("--iteracoes", type=int, default=ITERATIONS, help="ciclos globais, padrão: 50")
    parser.add_argument("--semente-base", type=int, default=BASE_SEED)
    parser.add_argument("--processos", type=int, default=1, help="chamadas simultâneas, padrão: 1")
    parser.add_argument("--saida", type=Path, default=ROOT/"resultados_multiobjetivo")
    args = parser.parse_args()
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    if not 1 <= args.rodadas < 100 or args.iteracoes < 1 or args.processos < 1:
        parser.error("rodadas deve ser 1–99; iterações e processos devem ser positivos")
    try:
        case = load_case(args.dados)
        normalization, references, normal_source = load_normalization(args.normalizacao, args.dados, case)
        configs = load_configurations(args.configuracoes)
        methods = ["soma", "epsilon"] if args.metodo == "todos" else [args.metodo]
        selected_ids = set(args.configuracao or [])
        available = {c["id"] for m in methods for c in configs[m]}
        if selected_ids - available:
            raise ValueError(f"configurações inexistentes na abordagem: {selected_ids-available}")
        jobs = []
        for method in methods:
            for n in range(1, args.rodadas+1):
                for index, config in enumerate(configs[method]):
                    if selected_ids and config["id"] not in selected_ids:
                        continue
                    seed = args.semente_base + (100000 if method == "soma" else 200000) + n*1000 + index+1
                    jobs.append((case, normalization, references, method, config, n, seed, args.iteracoes))
        methods = [m for m in methods if any(job[3] == m for job in jobs)]
        code_hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                       for name in ("mono_objetivo.py", "multiobjetivo.py", "figuras.py")}
        manifest = {"dados_sha256": normal_source["data_sha256"], "codigo_sha256": code_hashes,
                    "python": sys.version.split()[0], "matplotlib": version("matplotlib"),
                    "normalizacao": normal_source,
                    "configuracoes": configs, "rodadas": args.rodadas,
                    "iteracoes": args.iteracoes, "semente_base": args.semente_base,
                    "metodos": methods, "selecao": sorted(selected_ids),
                    "reparo_ciclos": REPAIR_STEPS, "teto_n3": None,
                    "tolerancia_epsilon": EPS_TOL, "tolerancias_dominancia": DOM_TOL,
                    "partida_epsilon": "referência admissível mais barata; caso contrário construção e reparo",
                    "semente": "base + 100000 (soma) ou 200000 (epsilon) + 1000*rodada + índice_configuração (1..n)"}
        directory = args.saida
        directory.mkdir(parents=True, exist_ok=True)
        manifest_path = directory/"configuracoes.json"
        # JSON normaliza tuplas em listas; permite comparar a retomada literalmente.
        manifest = json.loads(json.dumps(manifest))
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("pasta contém outro experimento/versão; escolha outra --saida")
        write_json(manifest_path, manifest)
        write_json(directory/"normalizacao.json", normal_source)
        checkpoints = directory/"chamadas"
        checkpoints.mkdir(exist_ok=True)
        records, pending = [], []
        for job in jobs:
            method, config, n, seed = job[3:7]
            path = checkpoints/f"{method}_r{n}_{config['id']}.json"
            if path.exists():
                record = json.loads(path.read_text())
                if (record["metodo"], record["configuracao"], record["rodada"], record["semente"]) != (method, config["id"], n, seed):
                    raise ValueError("checkpoint não corresponde à chamada planejada")
                if record["status"] == "ok":
                    result = evaluate(case, plan_from_counts(case, record["caminhoes_por_pilha_e_minerio"]))
                    if not make_criterion(method, config, normalization).feasible(result) or any(
                            abs(a-b)>tol for a, b, tol in zip(result.objectives, record["objetivos"], DOM_TOL)):
                        raise ValueError("checkpoint contém receita ou objetivos inválidos")
                elif record["status"] != "falha_reparo":
                    raise ValueError("status inválido no checkpoint")
                records.append(record)
            else:
                pending.append(job)
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"{len(jobs)} chamadas previstas; {len(records)} já salvas; {len(pending)} pendentes.", flush=True)

    def save_timing(interrupted: bool):
        path = directory/"historico_lote.json"
        history = json.loads(path.read_text()) if path.exists() else []
        history.append({"inicio_utc": started_at,
                        "segundos_relogio": time.perf_counter()-started,
                        "processos": args.processos, "chamadas_pendentes_no_inicio": len(pending),
                        "chamadas_salvas_no_fim": len(records), "interrompido": interrupted})
        write_json(path, history)

    def save(record):
        records.append(record)
        path = checkpoints/f"{record['metodo']}_r{record['rodada']}_{record['configuracao']}.json"
        write_json(path, record)
        print(f"[{len(records)}/{len(jobs)}] {path.stem}: {record['status']}, "
              f"{record['segundos']:.1f}s, {record['avaliacoes']} avaliações", flush=True)

    try:
        if args.processos == 1:
            for job in pending:
                save(execute_job(job))
        else:
            # Pool encerra os filhos ao interromper; só chamadas concluídas são retomadas.
            with multiprocessing.get_context("spawn").Pool(args.processos) as pool:
                for record in pool.imap_unordered(execute_job, pending):
                    save(record)
    except KeyboardInterrupt:
        records.sort(key=lambda r: (r["metodo"], r["rodada"], r["configuracao"]))
        export_results(directory, records, methods, args.rodadas, len(jobs))
        save_timing(True)
        parser.exit(130, "Lote interrompido. Repita o comando para retomar as chamadas pendentes.\n")
    records.sort(key=lambda r: (r["metodo"], r["rodada"], r["configuracao"]))
    export_results(directory, records, methods, args.rodadas, len(jobs))
    save_timing(False)
    print(f"Resultados em {directory.resolve()}", flush=True)


if __name__ == "__main__":
    main()
