"""Gera normalizacao.json a partir da execução final mono-objetivo da Entrega 1.

As referências são as melhores soluções de cada objetivo (melhores_solucoes.json
gravado por gvns.py). A matriz cruzada dá a = mínimo e b = máximo de
cada coluna. O arquivo gerado é conferido por load_normalization antes de ser
gravado, com as mesmas verificações usadas pelo lote multiobjetivo.

Execute: python -m pilhas_minerio.normalizacao
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from .gvns import load_case
from .multiobjetivo import data_digest, load_normalization, write_json
KEYS = ("f1_rs", "f2_pp2", "f3_pp2")


class NormalizationBuilder:
    """Monta a matriz cruzada e as escalas a partir de um lote mono-objetivo.

    Args:
        batch: Pasta de saída de gvns.py.
        data_path: Instância usada no lote.
    """

    def __init__(self, batch: Path, data_path: Path) -> None:
        self.batch = batch
        self.data_path = data_path
        self.best = json.loads((batch / "melhores_solucoes.json").read_text(encoding="utf-8"))
        self.config = json.loads((batch / "configuracao.json").read_text(encoding="utf-8"))

    def build(self) -> dict:
        """Devolve o conteúdo de normalizacao.json.

        Raises:
            ValueError: Se o lote foi gerado com outro arquivo de dados.
        """
        if self.config.get("dados") != self.data_path.name:
            raise ValueError("o lote foi executado com outro arquivo de dados")
        references = {q: self.best[q] for q in ("f1", "f2", "f3")}
        payoff = [{"objective_optimized": q, "run": ref["execucao"], "seed": ref["semente"],
                   "values": [ref[k] for k in KEYS]} for q, ref in references.items()]
        return {
            "status": "referencias_fixas_entrega2",
            "payoff_table": payoff,
            "a": [min(row["values"][c] for row in payoff) for c in range(3)],
            "b": [max(row["values"][c] for row in payoff) for c in range(3)],
            "normalization": "(f_q-a_q)/(b_q-a_q); sem clipping",
            "source": f"{self.batch.name}: melhor execução de cada objetivo do lote oficial",
            "data_sha256": data_digest(self.data_path),
            "iterations": self.config.get("limite_iteracoes_gvns"),
            "n3_min_fraction": self.config.get("n3_fracao_minima_alterada"),
            "n3_candidate_limit": None,
            "references": references,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lote", type=Path, default=RESULTS_DIR / "entrega_1",
                        help="pasta de saída da execução final de gvns.py")
    parser.add_argument("--dados", type=Path, default=DATA_FILE)
    parser.add_argument("--saida", type=Path, default=CONFIG_DIR / "normalizacao.json")
    args = parser.parse_args()
    content = NormalizationBuilder(args.lote, args.dados).build()
    # Conferir num arquivo temporário evita substituir o atual por um inválido.
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder) / "normalizacao.json"
        write_json(candidate, content)
        load_normalization(candidate, args.dados, load_case(args.dados))
    write_json(args.saida, content)
    print(f"a = {content['a']}\nb = {content['b']}\nGravado em {args.saida}")


if __name__ == "__main__":
    main()
