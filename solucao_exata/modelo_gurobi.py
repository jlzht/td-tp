"""Ótimos exatos de f1, f2 e f3 com Gurobi, apenas como referência visual.

Este módulo é independente da GVNS: lê os dados diretamente do JSON, não
importa nada de mono_objetivo.py e seus resultados não alimentam nenhuma outra
etapa do projeto. Serve só para medir a distância entre a metaheurística e o
ótimo global.

Requer gurobipy e uma licença Gurobi válida (não faz parte do requirements.txt).

Execute: python solucao_exata/modelo_gurobi.py --objetivo 2 --tempo-limite 21600

Para cada objetivo otimizado, grava em --saida:
    f{k}_resumo.csv       status, valores, limitante, gap, tempo, nós e parâmetros
    f{k}_pilhas.csv       teores, desvios, folgas de qualidade e custo por pilha
    f{k}_composicao.csv   caminhões de cada minério em cada pilha
    f{k}_disponibilidade.csv  uso total de cada minério contra mínimo e máximo
    f{k}_evolucao.csv     cada nova solução incumbente e o limitante ao longo do tempo
    f{k}_gurobi.log       log completo do Gurobi
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB

STATUS_NAMES = {GRB.OPTIMAL: "otimo", GRB.TIME_LIMIT: "limite_tempo",
                GRB.INTERRUPTED: "interrompido", GRB.INFEASIBLE: "inviavel"}
BOUND_SAMPLE_SECONDS = 60.0


@dataclass
class ExactResult:
    """Resultado de uma otimização exata.

    Attributes:
        objective: Índice do objetivo otimizado (0, 1 ou 2).
        status: Nome do status final do Gurobi.
        objective_value: Valor da melhor solução encontrada.
        bound: Melhor limitante inferior provado.
        gap: Gap relativo final entre solução e limitante.
        seconds: Tempo de execução do Gurobi.
        nodes: Nós explorados no branch-and-bound.
        simplex_iterations: Iterações simplex/barreira acumuladas.
        solution_count: Soluções guardadas pelo Gurobi.
        values: f1, f2 e f3 da melhor solução.
        trucks: Caminhões por pilha e minério.
        progress: Linhas (tempo, evento, incumbente, limitante) registradas na busca.
    """

    objective: int
    status: str
    objective_value: float
    bound: float
    gap: float
    seconds: float
    nodes: float
    simplex_iterations: float
    solution_count: int
    values: tuple[float, float, float]
    trucks: list[list[int]]
    progress: list[tuple[float, str, float, float]] = field(default_factory=list)


class ExactModel:
    """Modelo inteiro do case, com custo linear e desvios quadráticos convexos.

    Args:
        data_path: Arquivo JSON da instância, no formato de dados_exemplo.json.
    """

    def __init__(self, data_path: Path) -> None:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.truck_kt: int = data["capacidade_caminhao_kt"]
        self.piles = sorted(data["pilhas"], key=lambda p: p["id"])
        self.ores = sorted(data["minerios"], key=lambda o: o["id"])
        self.sinters = {s["id"]: s for s in data["sinteres"]}

    def trucks_in(self, pile: dict) -> int:
        """Número de caminhões que fecham a massa da pilha."""
        return pile["massa_kt"] // self.truck_kt

    def solve(self, objective: int, time_limit: float | None, threads: int,
              log_path: Path) -> ExactResult:
        """Otimiza um único objetivo sujeito a todas as restrições do case.

        Args:
            objective: 0 para custo, 1 para desvio de SiO2, 2 para desvio de Al2O3.
            time_limit: Limite de tempo em segundos; None deixa o Gurobi provar o ótimo.
            threads: Threads do Gurobi; 0 usa todas.
            log_path: Arquivo onde o Gurobi grava o log completo.

        Returns:
            Status, limitante, gap, esforço, valores dos três objetivos e composição.

        Raises:
            RuntimeError: Se o Gurobi terminar sem nenhuma solução viável.
        """
        model = gp.Model(f"f{objective + 1}")
        model.Params.MIPGap = 0.0
        model.Params.Threads = threads
        if time_limit is not None:
            model.Params.TimeLimit = time_limit

        # Criar variável só para pares elegíveis já impõe a compatibilidade.
        x = {
            (i, j): model.addVar(vtype=GRB.INTEGER, lb=0, name=f"x_P{i + 1}_M{j + 1}")
            for i, pile in enumerate(self.piles)
            for j, ore in enumerate(self.ores)
            if pile["sinter"] in ore["sinteres"]
        }
        cost = gp.quicksum(1000 * self.truck_kt * self.ores[j]["preco_rs_t"] * var
                           for (i, j), var in x.items())
        deviation = {"si": gp.QuadExpr(), "al": gp.QuadExpr()}
        for i, pile in enumerate(self.piles):
            n = self.trucks_in(pile)
            sinter = self.sinters[pile["sinter"]]
            row = [(j, var) for (p, j), var in x.items() if p == i]
            model.addConstr(gp.quicksum(var for _, var in row) == n, name=f"massa_P{i + 1}")
            for key in ("si", "al"):
                total = gp.quicksum(self.ores[j][key] * var for j, var in row)
                # Limites multiplicados por n mantêm a restrição linear.
                model.addConstr(total >= n * sinter[f"{key}_min"], name=f"{key}_min_P{i + 1}")
                model.addConstr(total <= n * sinter[f"{key}_max"], name=f"{key}_max_P{i + 1}")
                error = total / n - sinter[f"{key}_alvo"]
                deviation[key] += error * error
        for j, ore in enumerate(self.ores):
            used = gp.quicksum(var for (_, k), var in x.items() if k == j)
            model.addConstr(used >= ore["min"], name=f"disp_min_M{j + 1}")
            model.addConstr(used <= ore["max"], name=f"disp_max_M{j + 1}")

        expressions = (cost, deviation["si"], deviation["al"])
        model.setObjective(expressions[objective], GRB.MINIMIZE)

        progress: list[tuple[float, str, float, float]] = []
        last_sample = [-BOUND_SAMPLE_SECONDS]

        # O Gurobi não abre LogFile em caminho com acento ("Decisão"), então o
        # log é copiado pelo callback de mensagens.
        log = log_path.open("w", encoding="utf-8")

        def record(cb_model: gp.Model, where: int) -> None:
            if where == GRB.Callback.MESSAGE:
                log.write(cb_model.cbGet(GRB.Callback.MSG_STRING))
                log.flush()
            elif where == GRB.Callback.MIPSOL:
                progress.append((cb_model.cbGet(GRB.Callback.RUNTIME), "nova_incumbente",
                                 cb_model.cbGet(GRB.Callback.MIPSOL_OBJ),
                                 cb_model.cbGet(GRB.Callback.MIPSOL_OBJBND)))
            elif where == GRB.Callback.MIP:
                now = cb_model.cbGet(GRB.Callback.RUNTIME)
                # Amostrar o limitante evita um CSV com milhões de linhas em 6 h.
                if now - last_sample[0] >= BOUND_SAMPLE_SECONDS:
                    last_sample[0] = now
                    progress.append((now, "amostra_limitante",
                                     cb_model.cbGet(GRB.Callback.MIP_OBJBST),
                                     cb_model.cbGet(GRB.Callback.MIP_OBJBND)))

        try:
            model.optimize(record)
        finally:
            log.close()
        if model.SolCount == 0:
            raise RuntimeError(f"f{objective + 1}: Gurobi terminou sem solução viável "
                               f"(status {model.Status})")

        trucks = [[0] * len(self.ores) for _ in self.piles]
        for (i, j), var in x.items():
            trucks[i][j] = round(var.X)
        progress.append((model.Runtime, "final", model.ObjVal, model.ObjBound))
        return ExactResult(
            objective=objective,
            status=STATUS_NAMES.get(model.Status, str(model.Status)),
            objective_value=model.ObjVal, bound=model.ObjBound, gap=model.MIPGap,
            seconds=model.Runtime, nodes=model.NodeCount,
            simplex_iterations=model.IterCount, solution_count=model.SolCount,
            values=tuple(float(expr.getValue()) for expr in expressions),
            trucks=trucks, progress=progress)


class ResultWriter:
    """Grava em CSV tudo o que vale guardar de uma otimização exata.

    Args:
        model: Modelo usado, para recuperar dados de pilhas e minérios.
        directory: Pasta de saída.
    """

    def __init__(self, model: ExactModel, directory: Path) -> None:
        self.model = model
        self.directory = directory

    def write(self, result: ExactResult, settings: dict[str, object]) -> None:
        """Grava os cinco CSVs do objetivo otimizado.

        Args:
            result: Resultado devolvido por ExactModel.solve.
            settings: Parâmetros da execução, repetidos no resumo.
        """
        prefix = f"f{result.objective + 1}"
        self._write_summary(self.directory / f"{prefix}_resumo.csv", result, settings)
        self._write_piles(self.directory / f"{prefix}_pilhas.csv", result)
        self._write_composition(self.directory / f"{prefix}_composicao.csv", result)
        self._write_availability(self.directory / f"{prefix}_disponibilidade.csv", result)
        self._write_rows(self.directory / f"{prefix}_evolucao.csv",
                         ["segundos", "evento", "incumbente", "limitante"],
                         result.progress)

    @staticmethod
    def _write_rows(path: Path, header: list[str], rows: list) -> None:
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)

    def _write_summary(self, path: Path, result: ExactResult,
                       settings: dict[str, object]) -> None:
        row = {
            "objetivo_otimizado": f"f{result.objective + 1}",
            "status": result.status,
            "valor_objetivo": result.objective_value,
            "limitante_inferior": result.bound,
            "gap_relativo": result.gap,
            "gap_absoluto": result.objective_value - result.bound,
            "segundos": result.seconds,
            "nos_explorados": result.nodes,
            "iteracoes_simplex": result.simplex_iterations,
            "solucoes_encontradas": result.solution_count,
            "f1_rs": result.values[0],
            "f2_pp2": result.values[1],
            "f3_pp2": result.values[2],
            **settings,
        }
        self._write_rows(path, list(row), [list(row.values())])

    def _write_piles(self, path: Path, result: ExactResult) -> None:
        rows = []
        for i, pile in enumerate(self.model.piles):
            n = self.model.trucks_in(pile)
            sinter = self.model.sinters[pile["sinter"]]
            counts = result.trucks[i]
            si = sum(c * o["si"] for c, o in zip(counts, self.model.ores)) / n
            al = sum(c * o["al"] for c, o in zip(counts, self.model.ores)) / n
            cost = sum(c * o["preco_rs_t"] for c, o in zip(counts, self.model.ores))
            rows.append([
                f"P{pile['id']}", pile["sinter"], pile["massa_kt"], n,
                sum(1 for c in counts if c), round(1000 * self.model.truck_kt * cost),
                si, sinter["si_alvo"], (si - sinter["si_alvo"]) ** 2,
                si - sinter["si_min"], sinter["si_max"] - si,
                al, sinter["al_alvo"], (al - sinter["al_alvo"]) ** 2,
                al - sinter["al_min"], sinter["al_max"] - al,
            ])
        self._write_rows(path, [
            "pilha", "sinter", "massa_kt", "caminhoes", "minerios_distintos", "custo_rs",
            "si_pct", "si_alvo", "si_desvio2", "si_folga_min", "si_folga_max",
            "al_pct", "al_alvo", "al_desvio2", "al_folga_min", "al_folga_max",
        ], rows)

    def _write_composition(self, path: Path, result: ExactResult) -> None:
        names = [f"M{o['id']}" for o in self.model.ores]
        rows = [[f"P{pile['id']}", pile["sinter"], *result.trucks[i]]
                for i, pile in enumerate(self.model.piles)]
        self._write_rows(path, ["pilha", "sinter", *names], rows)

    def _write_availability(self, path: Path, result: ExactResult) -> None:
        rows = []
        for j, ore in enumerate(self.model.ores):
            used = sum(row[j] for row in result.trucks)
            rows.append([f"M{ore['id']}", ore["preco_rs_t"], ore["si"], ore["al"],
                         ore["min"], used, ore["max"], used == ore["min"],
                         used == ore["max"]])
        self._write_rows(path, ["minerio", "preco_rs_t", "si_pct", "al_pct", "disp_min",
                                "usado", "disp_max", "no_minimo", "no_maximo"], rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(__file__).resolve().parent
    parser.add_argument("--dados", type=Path, default=root.parent / "dados_exemplo.json")
    parser.add_argument("--saida", type=Path, default=root / "resultados")
    parser.add_argument("--objetivo", type=int, choices=(1, 2, 3), action="append",
                        help="objetivo a otimizar; pode repetir (padrão: 1, 2 e 3)")
    parser.add_argument("--tempo-limite", type=float, default=None,
                        help="segundos por objetivo; sem valor, prova o ótimo")
    parser.add_argument("--threads", type=int, default=0,
                        help="threads do Gurobi (padrão 0: todas)")
    args = parser.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    exact = ExactModel(args.dados)
    writer = ResultWriter(exact, args.saida)
    for objective in sorted(set(args.objetivo or (1, 2, 3))):
        started = datetime.now()
        result = exact.solve(objective - 1, args.tempo_limite, args.threads,
                             args.saida / f"f{objective}_gurobi.log")
        writer.write(result, {
            "inicio": started.isoformat(timespec="seconds"),
            "fim": datetime.now().isoformat(timespec="seconds"),
            "tempo_limite_s": args.tempo_limite,
            "mip_gap_alvo": 0.0,
            "threads": args.threads,
            "gurobi": ".".join(map(str, gp.gurobi.version())),
            "cpu": platform.processor(),
            "dados": args.dados.name,
        })
        print(f"f{objective}: {result.status}, valor {result.objective_value:.6g}, "
              f"limitante {result.bound:.6g}, gap {result.gap:.2e}, "
              f"{result.seconds:.0f} s", flush=True)
    print(f"Resultados em {args.saida}")


if __name__ == "__main__":
    main()
