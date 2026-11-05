"""Leitura dos hiperparâmetros da Entrega 3, todos em configuracoes/decisao.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .metodos.ahp import LOCAL_JUDGMENTS, CriteriaWeights


@dataclass(frozen=True)
class DirichletSettings:
    """Sorteio de pesos da análise de sensibilidade; ``concentration`` nulo até ser calibrada."""
    concentration: float | None
    samples: int
    seed: int


@dataclass(frozen=True)
class SensitivitySettings:
    """Variações da análise de sensibilidade."""
    targets: tuple[int, ...]
    weight_sweep_steps: int
    dirichlet: DirichletSettings
    tau_c_grid: tuple[float, ...]
    tau_d_grid: tuple[float, ...]
    local_judgments: tuple[str, ...]


@dataclass(frozen=True)
class Hyperparameters:
    """Valores escolhidos antes de rodar o modelo.

    Attributes:
        extra_criterion: Chave do critério extra em ``EXTRA_CRITERIA``.
        criteria: Chaves dos critérios, na ordem da matriz de julgamentos.
        judgments: Julgamentos par a par do decisor, ``"a:b" -> intensidade``.
        max_consistency_ratio: Maior QC aceito para os julgamentos do decisor.
        tau_c: Limiar mínimo de concordância do ELECTRE I.
        tau_d: Limiar máximo de discordância, ou ``None`` para calibrá-lo ao alvo.
        target: Tamanho do núcleo que o ELECTRE I deve entregar ao AHP.
        tau_d_search: Valores de tau_d percorridos na calibração.
        local_judgment: Modo dos julgamentos entre alternativas no AHP.
        sensitivity: Variações da análise de sensibilidade.
        justifications: Parâmetro -> origem ou justificativa, para o relatório.
    """
    extra_criterion: str
    criteria: tuple[str, ...]
    judgments: dict[str, float]
    max_consistency_ratio: float
    tau_c: float
    tau_d: float | None
    target: int
    tau_d_search: np.ndarray
    local_judgment: str
    sensitivity: SensitivitySettings
    justifications: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Hyperparameters":
        """Lê e valida o arquivo.

        Raises:
            ValueError: Valor fora do domínio ou julgamentos incompletos.
            KeyError: Seção ou chave ausente.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        electre, ahp, sens = raw["electre1"], raw["ahp"], raw["sensibilidade"]
        search = electre["busca_tau_d"]
        dirichlet = sens["dirichlet"]
        params = cls(
            extra_criterion=raw["criterio_extra"],
            criteria=tuple(raw["pesos"]["criterios"]),
            judgments={k: float(v) for k, v in raw["pesos"]["julgamentos"].items()},
            max_consistency_ratio=float(raw["pesos"]["qc_maximo"]),
            tau_c=float(electre["tau_c"]),
            tau_d=None if electre["tau_d"] is None else float(electre["tau_d"]),
            target=int(electre["alternativas_alvo"]),
            tau_d_search=np.round(np.arange(search["inicio"], search["fim"] + search["passo"] / 2,
                                            search["passo"]), 10),
            local_judgment=ahp["julgamento_local"],
            sensitivity=SensitivitySettings(
                targets=tuple(int(x) for x in sens["alternativas_alvo"]),
                weight_sweep_steps=int(sens["varredura_pesos_passos"]),
                dirichlet=DirichletSettings(
                    None if dirichlet["concentracao"] is None else float(dirichlet["concentracao"]),
                    int(dirichlet["sorteios"]), int(dirichlet["semente"])),
                tau_c_grid=tuple(float(x) for x in sens["grade_tau_c"]),
                tau_d_grid=tuple(float(x) for x in sens["grade_tau_d"]),
                local_judgments=tuple(sens["julgamento_local"])),
            justifications=dict(raw.get("justificativas", {})))
        params.validate()
        return params

    def validate(self) -> None:
        """Confere domínios; os julgamentos são conferidos ao calcular os pesos."""
        if self.local_judgment not in LOCAL_JUDGMENTS or not set(
                self.sensitivity.local_judgments) <= set(LOCAL_JUDGMENTS):
            raise ValueError(f"julgamento_local deve estar em {LOCAL_JUDGMENTS}")
        if not 0 < self.tau_c <= 1 or (self.tau_d is not None and not 0 <= self.tau_d <= 1):
            raise ValueError("tau_c deve estar em (0, 1] e tau_d em [0, 1]")
        if self.target < 1 or any(t < 1 for t in self.sensitivity.targets):
            raise ValueError("alternativas_alvo deve ser positivo")

    def criteria_weights(self) -> np.ndarray:
        """Pesos dos critérios pelo AHP a partir dos julgamentos do decisor."""
        return CriteriaWeights(self.criteria, self.judgments).weights(self.max_consistency_ratio)

    def judgments_consistency_ratio(self) -> float:
        """QC da matriz de julgamentos do decisor."""
        return CriteriaWeights(self.criteria, self.judgments).matrix.consistency_ratio()
