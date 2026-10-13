"""Teste de funcionamento com N3 LIMITADA; não é experimento oficial.

Execute: python3 teste_rapido.py
As duas travas valem apenas neste processo de teste e por chamada escalar.
"""
import argparse
import json
from itertools import islice
from pathlib import Path
from unittest.mock import patch

import mono_objetivo as mono
from multiobjetivo import execute_job, load_configurations, load_normalization, write_json

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visitas-n3", type=int, default=5,
                        help="máximo de visitas a N3 por chamada (padrão: 5)")
    parser.add_argument("--candidatos-n3", type=int, default=25,
                        help="máximo de candidatos completos por visita (padrão: 25)")
    parser.add_argument("--saida", type=Path, default=ROOT/"resultados_entrega2/teste_rapido_construcao_comum")
    args = parser.parse_args()
    if args.visitas_n3 < 0 or args.candidatos_n3 < 0:
        parser.error("limites devem ser não negativos")
    data = ROOT/"dados_exemplo.json"
    case = mono.load_case(data)
    normal, _, _ = load_normalization(ROOT/"normalizacao.json", data, case)
    configs = load_configurations(ROOT/"configuracoes_multi.json")
    original = mono.neighbors
    records = []
    # Só três chamadas de um ciclo, para verificar fluxo, ε e exportação.
    for method, identifier in (("soma", "equilibrada"), ("epsilon", "eps_100_100"),
                               ("epsilon", "eps_025_025")):
        visits = examined = 0

        def limited_neighbors(case, plan, kind, rng):
            nonlocal visits, examined
            if kind != 3:
                yield from original(case, plan, kind, rng)
                return
            visits += 1
            if visits > args.visitas_n3:
                return
            for candidate in islice(original(case, plan, kind, rng), args.candidatos_n3):
                examined += 1
                yield candidate

        index = next(i for i, c in enumerate(configs[method]) if c["id"] == identifier)
        config = configs[method][index]
        seed = mono.BASE_SEED + (100000 if method == "soma" else 200000) + 1000 + index+1
        with patch("mono_objetivo.neighbors", limited_neighbors):
            record = execute_job((case, normal, method, config, 1, seed, 1))
        record["teste_rapido_n3_limitada"] = True
        record["limite_visitas_n3"] = args.visitas_n3
        record["limite_candidatos_n3_por_visita"] = args.candidatos_n3
        record["visitas_n3_solicitadas"] = visits
        record["candidatos_n3_examinados"] = examined
        records.append(record)
        print(f"{identifier}: {record['status']}, {record['segundos']:.2f}s, "
              f"{examined} candidatos completos de N3", flush=True)
    args.saida.mkdir(parents=True, exist_ok=True)
    write_json(args.saida/"teste_rapido.json", records)
    print("Teste limitado: não usar estes resultados nas tabelas oficiais ou como ótimo local de N3.")


if __name__ == "__main__":
    main()
