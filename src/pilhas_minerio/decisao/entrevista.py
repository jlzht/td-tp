"""Entrega 3: leitura das respostas do formulário da entrevista com o decisor.

Execute: python -m pilhas_minerio.decisao.entrevista respostas.csv
O arquivo é a planilha de respostas do formulário criado por entrevista/criar_formulario.gs,
exportada em CSV. A saída mostra os julgamentos, os pesos, o quociente de consistência e os
limiares declarados; não altera configuracoes/decisao.json, cujos valores o grupo escolhe.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from ..caminhos import CONFIG_DIR
from .hiperparametros import Hyperparameters
from .metodos.ahp import CriteriaWeights

ASPECT_KEYS = {"custo": "custo", "sílica": "desvio_sio2", "alumina": "desvio_al2o3",
               "receita parecida": "homogeneidade"}
INTENSITY = re.compile(r"\((-|−)?(\d)\)\s*$")
PAIR_TITLE = re.compile(r"melhorar (?:o|a) (.+?) ou melhorar (?:o|a) (.+?)\?\s*$")
VETO = re.compile(r"Até (\d+)%")
SUPPORT = re.compile(r"Pelo menos (\d+)%")


@dataclass(frozen=True)
class InterviewAnswers:
    """Respostas de uma pessoa, já convertidas.

    Attributes:
        most_valuable: Critério da melhoria de maior valor.
        least_valuable: Critério da melhoria de menor valor.
        judgments: ``"a:b" -> intensidade`` de a sobre b, com a antes de b na ordem dos
            critérios; abaixo de 1 quando b vale mais.
        declared_veto: Maior piora tolerada, em fração da faixa (tau_d declarado).
        declared_support: Fração mínima da importância (tau_c declarado).
        comments: Observação livre, vazia se não houver.
    """
    most_valuable: str
    least_valuable: str
    judgments: dict[str, float]
    declared_veto: float
    declared_support: float
    comments: str


class ResponseSheet:
    """Planilha de respostas do formulário, uma linha por respondente."""

    def __init__(self, rows: Sequence[Mapping[str, str]], criteria: Sequence[str]) -> None:
        """Args: rows: Linhas, com os títulos das perguntas como chaves; criteria: Critérios, em ordem."""
        if set(criteria) != set(ASPECT_KEYS.values()):
            raise ValueError("o formulário cobre custo, sílica, alumina e receita parecida")
        self.rows = list(rows)
        self.criteria = tuple(criteria)

    @classmethod
    def from_csv(cls, path: Path, criteria: Sequence[str]) -> "ResponseSheet":
        """Lê o CSV exportado da planilha de respostas."""
        with path.open(newline="", encoding="utf-8-sig") as file:
            return cls(list(csv.DictReader(file)), criteria)

    def answers(self, row: int = -1) -> InterviewAnswers:
        """Converte as respostas de uma linha (por padrão, a última).

        Raises:
            ValueError: Planilha vazia, pergunta ausente ou resposta fora do formato.
        """
        if not self.rows:
            raise ValueError("a planilha não tem respostas")
        data = self.rows[row]
        judgments: dict[str, float] = {}
        for title, answer in data.items():
            pair = PAIR_TITLE.search(title) if title.startswith("Quanto vale mais melhorar") else None
            if pair:
                judgments.update(self._judgment(pair.group(1), pair.group(2), answer))
        expected = len(self.criteria) * (len(self.criteria) - 1) // 2
        if len(judgments) != expected:
            raise ValueError(f"esperados {expected} julgamentos, encontrados {len(judgments)}")
        return InterviewAnswers(
            most_valuable=self._aspect(self._answer(data, "Se você pudesse melhorar")),
            least_valuable=self._aspect(self._answer(data, "Qual dos quatro traria MENOS")),
            judgments=judgments,
            declared_veto=self._percent(self._answer(data, "Você aceita uma composição"), VETO),
            declared_support=self._percent(self._answer(data, "Para considerar que a composição A"),
                                           SUPPORT),
            comments=self._answer(data, "Há algum aspecto", required=False).strip())

    @staticmethod
    def _answer(data: Mapping[str, str], prefix: str, required: bool = True) -> str:
        for title, answer in data.items():
            if title.startswith(prefix):
                return answer
        if required:
            raise ValueError(f"pergunta ausente na planilha: {prefix}")
        return ""

    @staticmethod
    def _aspect(answer: str) -> str:
        label = answer.split(":")[0].strip().lower()
        if label not in ASPECT_KEYS:
            raise ValueError(f"critério não reconhecido na resposta: {answer}")
        return ASPECT_KEYS[label]

    @staticmethod
    def _percent(answer: str, pattern: re.Pattern) -> float:
        match = pattern.search(answer)
        if not match:
            raise ValueError(f"percentual não reconhecido na resposta: {answer}")
        return int(match.group(1)) / 100

    def _judgment(self, first: str, second: str, answer: str) -> dict[str, float]:
        match = INTENSITY.search(answer)
        if not match:
            raise ValueError(f"intensidade não reconhecida na resposta: {answer}")
        value = int(match.group(2))
        intensity = 1.0 / value if match.group(1) else float(value)
        a, b = ASPECT_KEYS[first.strip().lower()], ASPECT_KEYS[second.strip().lower()]
        if self.criteria.index(a) < self.criteria.index(b):
            return {f"{a}:{b}": intensity}
        return {f"{b}:{a}": 1.0 / intensity}


@dataclass(frozen=True)
class InterviewAnalysis:
    """Pesos e verificações de consistência de uma pessoa entrevistada.

    Attributes:
        weights: Critério -> peso (autovetor principal da matriz de julgamentos).
        consistency_ratio: Quociente de consistência da matriz.
        within_limit: Verdadeiro se o QC não passa do máximo.
        order_agrees: Verdadeiro se a melhoria de maior valor tem o maior peso e a de menor
            valor, o menor.
    """
    weights: dict[str, float]
    consistency_ratio: float
    within_limit: bool
    order_agrees: bool

    @classmethod
    def of(cls, answers: InterviewAnswers, criteria: Sequence[str],
           max_ratio: float) -> "InterviewAnalysis":
        """Calcula os pesos e confere as respostas de ordem contra eles."""
        matrix = CriteriaWeights(criteria, answers.judgments).matrix
        weights = dict(zip(criteria, (float(w) for w in matrix.priorities())))
        ratio = matrix.consistency_ratio()
        order = (max(weights, key=weights.get) == answers.most_valuable
                 and min(weights, key=weights.get) == answers.least_valuable)
        return cls(weights, float(ratio), ratio <= max_ratio, order)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("respostas", type=Path, help="CSV da planilha de respostas")
    parser.add_argument("--linha", type=int, default=-1, help="linha de respostas, padrão: a última")
    parser.add_argument("--hiperparametros", type=Path, default=CONFIG_DIR / "decisao.json")
    parser.add_argument("--saida", type=Path, help="grava o resultado em JSON")
    args = parser.parse_args()
    params = Hyperparameters.load(args.hiperparametros)
    answers = ResponseSheet.from_csv(args.respostas, params.criteria).answers(args.linha)
    analysis = InterviewAnalysis.of(answers, params.criteria, params.max_consistency_ratio)
    result = {"julgamentos": answers.judgments, "pesos": analysis.weights,
              "qc": analysis.consistency_ratio, "qc_dentro_do_limite": analysis.within_limit,
              "ordem_confere_com_os_pesos": analysis.order_agrees,
              "maior_valor": answers.most_valuable, "menor_valor": answers.least_valuable,
              "veto_declarado": answers.declared_veto, "apoio_declarado": answers.declared_support,
              "observacao": answers.comments}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.saida:
        args.saida.write_text(text + "\n", encoding="utf-8")
    if not (analysis.within_limit and analysis.order_agrees):
        raise SystemExit("atenção: QC acima do limite ou ordem incoerente com os pesos; "
                         "rever os julgamentos com o respondente")


if __name__ == "__main__":
    main()
