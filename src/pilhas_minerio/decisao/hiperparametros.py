"""Leitura dos hiperparâmetros da Entrega 3, todos em configuracoes/decisao.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .metodos.ahp import LOCAL_JUDGMENTS, CriteriaWeights
from .pipeline import PipelineSettings


def _range(spec: Mapping[str, float]) -> tuple[float, ...]:
    """Valores de ``inicio`` a ``fim``, inclusive, em passos de ``passo``."""
    values = np.arange(spec["inicio"], spec["fim"] + spec["passo"] / 2, spec["passo"])
    return tuple(float(x) for x in np.round(values, 10))


@dataclass(frozen=True)
class SensitivitySettings:
    """Variações da análise de sensibilidade.

    Attributes:
        levels: Números de níveis do ELECTRE I que seguem para o AHP.
        veto: Valores de tau_d, com o resto no valor base.
        support: Valores de tau_c, com o resto no valor base.
        heat_veto: Valores de tau_d do mapa de calor.
        heat_support: Valores de tau_c do mapa de calor.
        weight_sweep_steps: Valores por critério na varredura de cada peso.
        judgment_steps: Degraus aplicados a um julgamento por vez.
        judgment_samples: Sorteios com todos os julgamentos variando juntos.
        judgment_max_step: Maior degrau de cada julgamento nos sorteios.
        seed: Semente dos sorteios.
        local_judgments: Modos do AHP comparados.
    """
    levels: tuple[int, ...]
    veto: tuple[float, ...]
    support: tuple[float, ...]
    heat_veto: tuple[float, ...]
    heat_support: tuple[float, ...]
    weight_sweep_steps: int
    judgment_steps: tuple[int, ...]
    judgment_samples: int
    judgment_max_step: int
    seed: int
    local_judgments: tuple[str, ...]


@dataclass(frozen=True)
class Hyperparameters:
    """Valores escolhidos antes de rodar o modelo.

    Attributes:
        extra_criterion: Chave do critério extra em ``EXTRA_CRITERIA``.
        criteria: Chaves dos critérios, na ordem da matriz de julgamentos.
        judgments: Julgamentos par a par do decisor, ``"a:b" -> intensidade``.
        max_consistency_ratio: Maior QC aceito para os julgamentos do decisor.
        accept_above_limit: Verdadeiro se o grupo decidiu usar os julgamentos mesmo com QC acima
            do máximo; a decisão e o motivo ficam nas justificativas.
        pipeline: Limiares, modo do AHP e níveis do caso base.
        sensitivity: Variações da análise de sensibilidade.
        justifications: Parâmetro -> origem ou justificativa, para o relatório.
    """
    extra_criterion: str
    criteria: tuple[str, ...]
    judgments: dict[str, float]
    max_consistency_ratio: float
    accept_above_limit: bool
    pipeline: PipelineSettings
    sensitivity: SensitivitySettings
    justifications: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Hyperparameters":
        """Lê e valida o arquivo.

        Raises:
            ValueError: Valor fora do domínio.
            KeyError: Seção ou chave ausente.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        electre, sens = raw["electre1"], raw["sensibilidade"]
        judgments = sens["julgamentos"]
        params = cls(
            extra_criterion=raw["criterio_extra"],
            criteria=tuple(raw["pesos"]["criterios"]),
            judgments={k: float(v) for k, v in raw["pesos"]["julgamentos"].items()},
            max_consistency_ratio=float(raw["pesos"]["qc_maximo"]),
            accept_above_limit=bool(raw["pesos"].get("aceitar_qc_acima_do_maximo", False)),
            pipeline=PipelineSettings(float(electre["tau_c"]), float(electre["tau_d"]),
                                      raw["ahp"]["julgamento_local"], int(electre["niveis_para_ahp"]),
                                      float(raw["desempate"]["tolerancia_relativa"])),
            sensitivity=SensitivitySettings(
                levels=tuple(int(x) for x in sens["niveis_para_ahp"]),
                veto=_range(sens["veto"]), support=_range(sens["apoio"]),
                heat_veto=_range(sens["mapa_calor"]["veto"]),
                heat_support=_range(sens["mapa_calor"]["apoio"]),
                weight_sweep_steps=int(sens["varredura_pesos_passos"]),
                judgment_steps=tuple(int(x) for x in judgments["degraus"]),
                judgment_samples=int(judgments["sorteios"]),
                judgment_max_step=int(judgments["degrau_maximo_sorteio"]),
                seed=int(judgments["semente"]),
                local_judgments=tuple(sens["julgamento_local"])),
            justifications=dict(raw.get("justificativas", {})))
        params.validate()
        return params

    def validate(self) -> None:
        """Confere domínios; os julgamentos são conferidos ao calcular os pesos."""
        base, sens = self.pipeline, self.sensitivity
        if base.local_judgment not in LOCAL_JUDGMENTS or not set(
                sens.local_judgments) <= set(LOCAL_JUDGMENTS):
            raise ValueError(f"julgamento_local deve estar em {LOCAL_JUDGMENTS}")
        if not 0 < base.tau_c <= 1 or not 0 <= base.tau_d <= 1:
            raise ValueError("tau_c deve estar em (0, 1] e tau_d em [0, 1]")
        if not 0 <= base.tie_tolerance < 1:
            raise ValueError("a tolerância de empate deve estar em [0, 1)")
        if base.levels < 1 or any(n < 1 for n in sens.levels):
            raise ValueError("níveis para o AHP devem ser positivos")
        if any(not 0 < c <= 1 for c in (*sens.support, *sens.heat_support)) or any(
                not 0 <= d <= 1 for d in (*sens.veto, *sens.heat_veto)):
            raise ValueError("faixas de limiares fora do domínio")
        if sens.weight_sweep_steps < 2 or sens.judgment_samples < 1 or sens.judgment_max_step < 1:
            raise ValueError("passos, sorteios e degrau máximo devem ser positivos")

    def criteria_weights(self) -> np.ndarray:
        """Pesos dos critérios pelo AHP a partir dos julgamentos do decisor.

        Raises:
            ValueError: QC acima do máximo sem a decisão registrada de aceitá-lo.
        """
        return CriteriaWeights(self.criteria, self.judgments).weights(self.judgment_ratio_ceiling())

    def judgment_ratio_ceiling(self) -> float:
        """Maior QC admitido nos julgamentos: o máximo das aulas ou, se o grupo aceitou a matriz
        acima dele, o próprio QC dessa matriz, para que nenhuma variação seja mais inconsistente
        que a base."""
        if self.accept_above_limit:
            return max(self.max_consistency_ratio, self.judgments_consistency_ratio())
        return self.max_consistency_ratio

    def judgments_consistency_ratio(self) -> float:
        """QC da matriz de julgamentos do decisor."""
        return CriteriaWeights(self.criteria, self.judgments).matrix.consistency_ratio()
