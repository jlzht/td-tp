# """Leitura e avaliação dos resultados já produzidos pelo projeto."""
# from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return re.sub(r"[^a-z0-9]+", "_", "".join(c for c in normalized if not unicodedata.combining(c)).lower()).strip("_")


def field(obj: Any, *aliases: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    indexed = {key(k): v for k, v in obj.items()}
    for alias in aliases:
        if key(alias) in indexed and indexed[key(alias)] is not None:
            return indexed[key(alias)]
    return default


def number(value: Any, default: float = float("nan")) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return default


def list_of(obj: Any, *names: str) -> list:
    if isinstance(obj, list):
        return obj
    result = field(obj, *names)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return list(result.values())
    return []


def read_json(path: Path, mandatory: bool = True) -> Any:
    if not path.exists():
        if mandatory:
            raise FileNotFoundError(f"Arquivo de resultados não encontrado: {path.relative_to(ROOT)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Não foi possível ler {path.name}: {exc}") from exc


def alternative_id(value: Any) -> str:
    if isinstance(value, dict):
        value = field(value, "id", "alternativa", "identificador", "codigo", "nome", default="")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"A{int(value):02d}"
    s = str(value or "").strip().upper()
    if re.fullmatch(r"\d+", s):
        return f"A{int(s):02d}"
    if re.fullmatch(r"A\d+", s):
        return f"A{int(s[1:]):02d}"
    return s


def _objectives(record: dict) -> dict:
    nested = field(record, "criterios", "objetivos", "valores_objetivos", "funcoes_objetivo", default={})
    values = [record, nested] if isinstance(nested, dict) else [record]
    out: dict[str, float] = {}
    for label, aliases in {
        "f1": ("f1", "custo", "custo_total", "valor_f1", "objetivo_1"),
        "f2": ("f2", "sio2", "desvio_sio2", "desvio_si_o2", "valor_f2", "objetivo_2"),
        "f3": ("f3", "al2o3", "desvio_al2o3", "desvio_al_o3", "valor_f3", "objetivo_3"),
        "h": ("h", "homogeneidade", "homogeneidade_receita", "f4"),
    }.items():
        for obj in values:
            v = field(obj, *aliases)
            if v is not None:
                out[label] = number(v)
                break
    if isinstance(nested, (tuple, list)) and len(nested) >= 3:
        for name, val in zip(("f1", "f2", "f3", "h"), nested):
            out.setdefault(name, number(val))
    return out


def _record_list(obj: Any) -> list:
    if isinstance(obj, list):
        return obj
    for k in ("alternativas", "solucoes", "solucoes_nao_dominadas", "nao_dominadas", "uniao", "resultados"):
        got = field(obj, k)
        if isinstance(got, list):
            return got
        if isinstance(got, dict):
            candidate = _record_list(got)
            if candidate:
                return candidate
    if isinstance(obj, dict) and all(re.fullmatch(r"A\d+", str(k), re.I) for k in obj):
        return [{"id": k, **(v if isinstance(v, dict) else {"receita": v})} for k, v in obj.items()]
    return []


RECIPE_KEYS = ("receita", "plano", "solucao", "composicao", "matriz", "contagens",
               "x", "xij", "x_ij", "caminhoes", "pilhas", "vetores", "receitas",
               "matriz_contagens", "contagens_por_pilha", "caminhoes_por_pilha",
               "composicao_por_pilha", "matriz_caminhoes", "alocacao", "alocacoes",
               "matriz_alocacao", "plano_caminhoes", "mistura")


def _recipe_raw(obj: Any) -> Any:
    for k in RECIPE_KEYS:
        v = field(obj, k)
        if v is not None:
            return v
    return None


def _truck_index(value: Any, size: int, zero_based: bool) -> int:
    if isinstance(value, dict):
        value = field(value, "minerio", "mineral", "produto", "id", "indice", default=value)
    if isinstance(value, str):
        v = value.strip().upper()
        if re.fullmatch(r"M\d+", v):
            return int(v[1:]) - 1
        if not re.fullmatch(r"\d+", v):
            raise ValueError(f"Minério desconhecido: {value}")
        value = int(v)
    n = int(value)
    return n if zero_based else n - 1


def _matrix_from_recipe(raw: Any, mineral_count: int, pile_count: int,
                        expected_trucks: list[int] | None = None) -> np.ndarray | None:
    """Decode truck vectors or count matrices; never infer composition from objectives.

    The project's truck vectors can use 0-based mineral indices. Matrices and
    dictionaries keyed by M1, M2, ... always represent counts, not truck indices.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        # Explicit nested containers take precedence over unrelated metadata.
        deeper = _recipe_raw(raw)
        if deeper is not None and deeper is not raw:
            candidate = _matrix_from_recipe(deeper, mineral_count, pile_count, expected_trucks)
            if candidate is not None:
                return candidate
        pile_keys = [k for k in raw if re.fullmatch(r"(?:P|PILHA[_ ]?)?\d+", str(k), re.I)]
        if len(pile_keys) == pile_count:
            pile_keys.sort(key=lambda k: int(re.search(r"\d+", str(k)).group()))
            raw = [raw[k] for k in pile_keys]
        elif len(raw) == 2 and all(isinstance(v, (list, tuple)) for v in raw.values()):
            groups = sorted(raw, key=lambda k: int(re.search(r"\d+", str(k)).group())
                            if re.search(r"\d+", str(k)) else 999)
            raw = [pile for k in groups for pile in raw[k]]
        else:
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    # Flat count matrix (a JSON-serializable 10x20 array).
    if (len(raw) == pile_count * mineral_count and
            all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                np.isfinite(v) and v >= 0 and float(v).is_integer() for v in raw)):
        return np.asarray(raw, dtype=int).reshape(pile_count, mineral_count)
    if (expected_trucks is not None and len(raw) == sum(expected_trucks) and
            all(isinstance(v, (int, str)) for v in raw)):
        # Flat sequence of trucks, one consecutive block for each pile.
        lengths = np.cumsum([0, *expected_trucks])
        raw = [raw[lengths[i]:lengths[i+1]] for i in range(pile_count)]
    if len(raw) != pile_count:
        return None
    if all(isinstance(row, (list, tuple)) and len(row) == mineral_count and
           all(isinstance(n, (int, float)) and not isinstance(n, bool) and
               np.isfinite(n) and n >= 0 and float(n).is_integer() for n in row)
           for row in raw):
        return np.asarray(raw, dtype=int)

    matrix = np.zeros((pile_count, mineral_count), dtype=int)
    all_trucks = []
    for row in raw:
        if isinstance(row, (list, tuple)):
            all_trucks.extend(row)
    integer_trucks = [int(v) for v in all_trucks if isinstance(v, (int, float))]
    # The project's computational vectors use internal IDs 0..19 (see report,
    # section III); a literal M1 or M20 always uses external 1-based indexing.
    zero_based = bool(integer_trucks) and max(integer_trucks) < mineral_count
    for i, row in enumerate(raw):
        if isinstance(row, dict):
            inner = field(row, "caminhoes", "minerios", "contagens", "vetor", "receita",
                          "composicao", "x", "xij", "alocacao")
            if inner is not None:
                row = inner
        if isinstance(row, dict):
            for label, count in row.items():
                j = _truck_index(label, mineral_count, False)
                if not 0 <= j < mineral_count:
                    raise ValueError(f"Minério fora da faixa: {label}")
                if not np.isfinite(number(count)) or number(count) < 0 or not number(count).is_integer():
                    raise ValueError(f"Quantidade de caminhões inválida: {count}")
                matrix[i, j] = int(count)
        elif isinstance(row, (list, tuple)):
            if (len(row) == mineral_count and
                    all(isinstance(v, (int, float)) and v >= 0 and float(v).is_integer() for v in row)):
                matrix[i, :] = np.asarray(row, dtype=int)
            elif row and all(isinstance(v, dict) for v in row):
                for entry in row:
                    label = field(entry, "minerio", "id", "produto", "mineral")
                    n = number(field(entry, "caminhoes", "quantidade", "contagem", "qtd"))
                    if label is None or not np.isfinite(n) or n < 0 or not n.is_integer():
                        raise ValueError(f"Entrada inválida da receita: {entry}")
                    j = _truck_index(label, mineral_count, False)
                    if not 0 <= j < mineral_count:
                        raise ValueError(f"Índice de minério fora da faixa: {label}")
                    matrix[i, j] += int(n)
            elif row and all(isinstance(v, (list, tuple)) and len(v) == 2 for v in row):
                for label, count in row:
                    j = _truck_index(label, mineral_count, False)
                    n = number(count)
                    if not 0 <= j < mineral_count or not np.isfinite(n) or n < 0 or not n.is_integer():
                        raise ValueError("Par minério/quantidade inválido.")
                    matrix[i, j] += int(n)
            else:
                for truck in row:
                    j = _truck_index(truck, mineral_count, zero_based)
                    if not 0 <= j < mineral_count:
                        raise ValueError(f"Índice de minério fora da faixa: {truck}")
                    matrix[i, j] += 1
        else:
            return None
    return matrix


def _recipe_candidates(node: Any, depth: int = 0):
    """Yield recipe-shaped substructures without confusing objectives with recipes."""
    if depth > 7:
        return
    if isinstance(node, dict):
        yield node
        raw = _recipe_raw(node)
        if raw is not None:
            yield raw
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from _recipe_candidates(child, depth + 1)
    elif isinstance(node, list):
        yield node
        for child in node:
            if isinstance(child, (dict, list)):
                yield from _recipe_candidates(child, depth + 1)


def _recipe_for_record(obj: Any, ore_count: int, pile_count: int,
                       expected_trucks: list[int]) -> np.ndarray | None:
    """Return an actual 10-pile plan only if masses match the case instance."""
    if not isinstance(obj, (dict, list)):
        return None
    for raw in _recipe_candidates(obj):
        try:
            matrix = _matrix_from_recipe(raw, ore_count, pile_count, expected_trucks)
        except (ValueError, TypeError, OverflowError):
            continue
        if (matrix is not None and matrix.shape == (pile_count, ore_count) and
                np.array_equal(matrix.sum(axis=1), expected_trucks)):
            return matrix
    return None


def _extra_recipe_sources(source: Path):
    """Try explicit recipe exports in the result directories, not random data files."""
    patterns = ("receit", "compos", "plano", "nao_dominad", "alternativ", "soluc", "uniao")
    locations = [source, source.parent / "entrega_2"]
    for folder in locations:
        if folder.is_dir():
            for path in sorted(folder.rglob("*.json")):
                if path == source / "uniao_nao_dominadas.json":
                    continue
                if not any(part in key(path.stem) for part in patterns):
                    continue
                # Avoid traversing enormous unrelated traces when only plans are needed.
                if path.stat().st_size <= 75_000_000:
                    yield path


def _collect_recipes(union: Any, records: list, source: Path, ores: pd.DataFrame,
                     piles: pd.DataFrame, limits: pd.DataFrame,
                     truck_kt: float) -> dict[str, np.ndarray]:
    """Look up recipes by stable Axx identifier across known optimization exports."""
    ore_count, pile_count = len(ores), len(piles)
    expected = [round(float(m) / truck_kt) for m in piles.massa_kt]
    if any(abs(n * truck_kt - m) > 1e-8 for n, m in zip(expected, piles.massa_kt)):
        raise ValueError("Massas das pilhas não são múltiplos da capacidade do caminhão.")
    identifiers = [alternative_id(field(r, "id", "alternativa", "identificador", "nome", default=i + 1))
                   for i, r in enumerate(records)]
    recipes = {}
    for aid, record in zip(identifiers, records):
        candidate = _recipe_for_record(record, ore_count, pile_count, expected)
        if candidate is not None:
            recipes[aid] = candidate

    def add_from_mapping(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        # Never associate recipes by position unless the enclosing union explicitly
        # declares an ordered array of recipes for all alternatives.
        for name, value in obj.items():
            if re.fullmatch(r"A\d+", str(name), re.I):
                aid = alternative_id(name)
                if aid in identifiers and aid not in recipes:
                    mat = _recipe_for_record(value, ore_count, pile_count, expected)
                    if mat is not None:
                        recipes[aid] = mat
        for k in ("receitas", "composicoes", "planos", "alternativas", "solucoes"):
            container = field(obj, k)
            if isinstance(container, dict):
                add_from_mapping(container)
            if isinstance(container, list):
                for entry in container:
                    if isinstance(entry, dict):
                        aid = alternative_id(field(entry, "id", "alternativa", "identificador", default=""))
                        if aid in identifiers and aid not in recipes:
                            mat = _recipe_for_record(entry, ore_count, pile_count, expected)
                            if mat is not None:
                                recipes[aid] = mat
                # Only a recipe array in the *same union document* has guaranteed
                # positional correspondence with its alternative list.
                if obj is union and key(k) in ("receitas", "composicoes", "planos") and len(container) == len(records):
                    for aid, entry in zip(identifiers, container):
                        if aid not in recipes:
                            mat = _recipe_for_record(entry, ore_count, pile_count, expected)
                            if mat is not None:
                                recipes[aid] = mat

    add_from_mapping(union)
    def objective_values(matrix: np.ndarray) -> dict[str, float]:
        masses = matrix.sum(axis=1)
        results = {
            "f1": float((matrix.sum(axis=0) * ores.preco.to_numpy()).sum()
                        * truck_kt * 1000 / 1_000_000),
            "h": homogeneity(matrix, piles),
        }
        for chemical, goal in (("sio2", "f2"), ("al2o3", "f3")):
            blend = matrix @ ores[chemical].to_numpy() / masses
            targets = [float(limits.loc[(limits.sinter == int(sid)) &
                                        (limits.criterio == chemical), "alvo"].iloc[0])
                       for sid in piles.sinter]
            results[goal] = float(np.square(blend - targets).sum())
        return results

    # Exports from the earlier multiobjective stage might lack the Axx IDs
    # assigned by Entrega 3. In that case, only associate recipes whose four
    # recomputed criteria identify exactly one alternative in the union.
    def add_by_objectives(obj: Any) -> None:
        if len(recipes) == len(records):
            return
        remaining = {aid: _objectives(rec) for aid, rec in zip(identifiers, records)
                    if aid not in recipes}
        # Avoid scanning every scalar as a candidate.
        for raw in _recipe_candidates(obj):
            try:
                matrix = _matrix_from_recipe(raw, ore_count, pile_count,
                                             expected_trucks=expected)
            except (ValueError, TypeError, OverflowError):
                continue
            if matrix is None or not np.array_equal(matrix.sum(axis=1), expected):
                continue
            actual = objective_values(matrix)
            matches = []
            for aid, values in remaining.items():
                if not all(k in values and np.isfinite(values[k]) for k in ("f1", "f2", "f3", "h")):
                    continue
                ref_cost = values["f1"] / 1_000_000 if values["f1"] > 1e5 else values["f1"]
                if (abs(actual["f1"] - ref_cost) <= 0.015 and
                    abs(actual["f2"] - values["f2"]) <= 0.001 and
                    abs(actual["f3"] - values["f3"]) <= 0.001 and
                    abs(actual["h"] - values["h"]) <= 0.001):
                    matches.append(aid)
            if len(matches) == 1:
                aid = matches[0]
                recipes[aid] = matrix
                remaining.pop(aid)
                if not remaining:
                    break

    if len(recipes) < len(records):
        # A record of the union may have a valid recipe but use an unfamiliar
        # field name. The recomputed criteria provide an unambiguous fallback.
        add_by_objectives(union)
    if len(recipes) < len(records):
        for path in _extra_recipe_sources(source):
            try:
                obj = read_json(path)
            except (ValueError, OSError):
                continue
            add_from_mapping(obj)
            if len(recipes) < len(records):
                add_by_objectives(obj)
            if len(recipes) == len(records):
                break
    return recipes


def _load_ores(data: dict) -> pd.DataFrame:
    ores = list_of(data, "minerios", "produtos")
    if not ores:
        raise ValueError("A instância não contém a lista 'minerios'.")
    result = []
    for i, item in enumerate(ores):
        if not isinstance(item, dict):
            raise ValueError("Dados dos minérios devem ser objetos com preço e teores.")
        identification = field(item, "id", "nome", "minerio", "codigo", default=f"M{i+1}")
        availability = field(item, "disponibilidade", default={})
        if not isinstance(availability, dict):
            availability = {}
        eligibility = field(item, "sinteres", "elegibilidade", "compativel", "equipamentos", default=None)
        if isinstance(eligibility, dict):
            eligibility = [n for n, v in eligibility.items() if v]
        result.append({
            "id": (f"M{int(identification)}" if str(identification).isdigit() else str(identification).upper()), "preco": number(field(item, "preco", "preco_rs_t", "custo")),
            "sio2": number(field(item, "sio2", "si_o2", "silica", "si")),
            "al2o3": number(field(item, "al2o3", "al_o3", "alumina", "al")),
            "fet": number(field(item, "fet", "fe", "ferro_total")),
            "min": number(field(item, "disp_min", "disponibilidade_minima", "disponibilidade_min", "minimo", "min", default=field(availability, "min", "minimo")), 0),
            "max": number(field(item, "disp_max", "disponibilidade_maxima", "disponibilidade_max", "maximo", "max", default=field(availability, "max", "maximo"))),
            "elegibilidade": eligibility,
        })
    return pd.DataFrame(result)


def _load_piles(data: dict) -> pd.DataFrame:
    values = list_of(data, "pilhas")
    if not values:
        raise ValueError("A instância não contém a lista 'pilhas'.")
    result = []
    for i, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError("O registro de cada pilha deve ser um objeto.")
        sid = field(item, "sinter", "equipamento", "grupo", "sinter_id", default=1 if i < 5 else 2)
        sid = int(re.search(r"\d+", str(sid)).group()) if re.search(r"\d+", str(sid)) else int(sid)
        pile_id = field(item, "id", "nome", "pilha", default=f"P{i+1}")
        pile_id = f"P{int(pile_id)}" if str(pile_id).isdigit() else str(pile_id).upper()
        result.append({"id": pile_id,
                       "sinter": sid, "massa_kt": number(field(item, "massa_kt", "massa", "massa_final"))})
    return pd.DataFrame(result)


def _load_limits(data: dict) -> pd.DataFrame:
    """Converte especificações de qualidade dos Sinters para uma tabela única.

    Suporta teores aninhados (sio2: {min, alvo, max}), limites/alvos em
    objetos separados e propriedades planas (sio2_min, alvo_sio2). Nenhum
    limite é estimado: campos ausentes provocam um erro descritivo.
    """
    raw = field(data, "sinteres", "equipamentos", "sinters")
    if isinstance(raw, list):
        sinters = [(None, item) for item in raw]
    elif isinstance(raw, dict):
        sinters = list(raw.items())
    else:
        sinters = []

    criteria = {
        "sio2": ("sio2", "si_o2", "silica", "si"),
        "al2o3": ("al2o3", "al_o3", "alumina", "al"),
    }
    measures = {
        "min": ("min", "minimo", "minima", "limite_min", "limite_minimo",
                "limite_inferior", "inferior", "lower"),
        "alvo": ("alvo", "alvos", "meta", "metas", "target", "referencia",
                 "valor_alvo"),
        "max": ("max", "maximo", "maxima", "limite_max", "limite_maximo",
                "limite_superior", "superior", "upper"),
    }

    def contains_alias(label: str, aliases: tuple[str, ...]) -> bool:
        """Recognize standalone and compound keys; never match unrelated fields."""
        normalized = key(label)
        compact = normalized.replace("_", "")
        for alias in aliases:
            candidate = key(alias)
            if normalized == candidate or compact == candidate.replace("_", ""):
                return True
            if f"_{candidate}_" in f"_{normalized}_":
                return True
            # Variants such as Si_O2_min and al_2_o_3_alvo.
            compact_alias = candidate.replace("_", "")
            if compact.startswith(compact_alias) and compact[len(compact_alias):] in (
                "min", "minimo", "max", "maximo", "alvo", "meta", "target"
            ):
                return True
            if compact.endswith(compact_alias) and compact[:-len(compact_alias)] in (
                "min", "minimo", "max", "maximo", "alvo", "meta", "target"
            ):
                return True
        return False

    def extract(item: dict, criterion: str, measure: str) -> float:
        """Find a numeric value only if its path identifies both attributes."""
        found: list[float] = []

        def visit(node: Any, has_criterion: bool = False,
                  has_measure: bool = False, depth: int = 0) -> None:
            if depth > 9:
                return
            if isinstance(node, dict):
                # Schemas with a list of records: {criterio: "sio2", minimo: ...}.
                label = field(node, "criterio", "indicador", "substancia", "componente")
                record_criterion = has_criterion or (
                    label is not None and contains_alias(str(label), criteria[criterion])
                )
                for name, value in node.items():
                    is_criterion = contains_alias(str(name), criteria[criterion])
                    is_measure = contains_alias(str(name), measures[measure])
                    visit(value, record_criterion or is_criterion,
                          has_measure or is_measure, depth + 1)
            elif isinstance(node, list):
                for value in node:
                    visit(value, has_criterion, has_measure, depth + 1)
            elif has_criterion and has_measure:
                val = number(node)
                if np.isfinite(val):
                    found.append(val)

        visit(item)
        if found:
            # Multiple representations of the same limit are allowed only if
            # they agree. Prefer reporting conflicting data to guessing.
            if any(not np.isclose(v, found[0], rtol=0, atol=1e-9) for v in found[1:]):
                raise ValueError(
                    f"Valores conflitantes para {criterion}/{measure} em um Sinter: {found}"
                )
            return found[0]
        return float("nan")

    result = []
    for i, (name, item) in enumerate(sinters):
        if not isinstance(item, dict):
            continue
        label = field(item, "id", "sinter", "nome", default=name or f"Sinter {i + 1}")
        match = re.search(r"\d+", str(label))
        if match is None:
            raise ValueError(f"Identificador de Sinter inválido: {label!r}")
        sid = int(match.group())
        for criterion in criteria:
            result.append({
                "sinter": sid,
                "criterio": criterion,
                **{measure: extract(item, criterion, measure) for measure in measures},
            })
    frame = pd.DataFrame(result, columns=["sinter", "criterio", "min", "alvo", "max"])
    expected = {(sid, criterion) for sid in (1, 2) for criterion in criteria}
    actual = list(zip(frame.sinter, frame.criterio))
    missing = sorted(expected - set(actual))
    duplicates = sorted({entry for entry in actual if actual.count(entry) > 1})
    undefined = [f"Sinter {int(r.sinter)}/{r.criterio}: " + ", ".join(
        name for name in ("min", "alvo", "max") if not np.isfinite(r[name]))
        for _, r in frame.iterrows() if not all(np.isfinite(r[name]) for name in ("min", "alvo", "max"))]
    if missing or duplicates or undefined:
        details = []
        if missing:
            details.append("ausentes: " + ", ".join(f"Sinter {s}/{c}" for s, c in missing))
        if duplicates:
            details.append("duplicados: " + ", ".join(f"Sinter {s}/{c}" for s, c in duplicates))
        if undefined:
            details.append("campos não reconhecidos: " + "; ".join(undefined))
        available = list(raw.keys()) if isinstance(raw, dict) else [
            list(item.keys()) for _, item in sinters if isinstance(item, dict)]
        raise ValueError("Especificações de qualidade dos Sinters incompletas (" +
                         " | ".join(details) + "). Estrutura encontrada: " + repr(available))
    for _, r in frame.iterrows():
        if not r["min"] <= r["alvo"] <= r["max"]:
            raise ValueError(f"Limites inconsistentes para Sinter {int(r.sinter)}/{r.criterio}: "
                             f"min={r['min']}, alvo={r['alvo']}, max={r['max']}")
    return frame.sort_values(["sinter", "criterio"]).reset_index(drop=True)


def _walk(root: Any, depth: int = 0):
    if depth > 8:
        return
    yield root
    if isinstance(root, dict):
        for v in root.values():
            yield from _walk(v, depth + 1)
    elif isinstance(root, list):
        for v in root:
            yield from _walk(v, depth + 1)


def _decision_info(obj: dict, tab: pd.DataFrame) -> tuple[list[str], pd.DataFrame, str, dict]:
    electre: list[str] = []
    ranking: list[dict] = []
    selected = ""
    weights: dict[str, float] = {}
    for node in _walk(obj):
        if not isinstance(node, dict):
            continue
        if not selected:
            v = field(node, "escolhida", "alternativa_escolhida", "vencedora", "vencedor", "recomendada", "melhor_alternativa", "alternativa_final")
            if isinstance(v, (str, int)):
                selected = alternative_id(v)
        if not electre:
            for name in ("primeiro_nivel", "nivel_1", "selecionadas_electre", "alternativas_selecionadas", "selecionadas", "conjunto_escolha"):
                v = field(node, name)
                if isinstance(v, list):
                    electre = [alternative_id(a) for a in v]
                    break
        levels = field(node, "niveis", "niveis_electre", "camadas")
        if not electre and isinstance(levels, list) and levels:
            first = levels[0]
            if isinstance(first, list):
                electre = [alternative_id(a) for a in first]
            elif isinstance(first, dict):
                group = field(first, "alternativas", "ids", "solucoes")
                if isinstance(group, list):
                    electre = [alternative_id(a) for a in group]
        if not ranking:
            names = field(node, "alternativas", "ids", "alternativas_ahp", "ids_alternativas")
            scores = field(node, "prioridades_globais", "prioridades", "pesos_alternativas")
            if (isinstance(names, list) and isinstance(scores, list) and
                    len(names) == len(scores) and all(np.isfinite(number(p)) for p in scores)):
                ranking = [{"id": alternative_id(a), "prioridade": number(p)} for a, p in zip(names, scores)]
        if not ranking:
            for name in ("ranking", "ranking_ahp", "prioridades_globais", "prioridades", "classificacao"):
                v = field(node, name)
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    rows = []
                    for entry in v:
                        a = alternative_id(entry)
                        p = number(field(entry, "prioridade", "prioridade_global", "g", "peso_global", "score"))
                        if re.fullmatch(r"A\d+", a) and np.isfinite(p):
                            rows.append({"id": a, "prioridade": p})
                    if rows:
                        ranking = rows
                        break
                if isinstance(v, dict) and v and all(re.fullmatch(r"A\d+", str(k), re.I) for k in v):
                    ranking = [{"id": alternative_id(k), "prioridade": number(val)} for k, val in v.items()]
                    break
        if not weights:
            w = field(node, "pesos_criterios", "pesos", "vetor_pesos")
            if isinstance(w, dict):
                candidates = {k: number(field(w, k)) for k in ("f1", "f2", "f3", "h")}
                candidates = {k: v for k, v in candidates.items() if np.isfinite(v)}
                if len(candidates) == 4:
                    weights = candidates
                else:
                    # Schema real da Entrega 3: pesos.criterios + pesos.valores.
                    # Evite mapear pesos pela posição sem verificar os nomes.
                    names = field(w, "criterios", "atributos")
                    values = field(w, "valores", "vetor")
                    aliases = {"custo": "f1", "f1": "f1",
                               "desvio_sio2": "f2", "sio2": "f2", "f2": "f2",
                               "desvio_al2o3": "f3", "al2o3": "f3", "f3": "f3",
                               "homogeneidade": "h", "h": "h"}
                    if (isinstance(names, list) and isinstance(values, list)
                            and len(names) == len(values)):
                        parsed = {aliases.get(key(name)): number(value)
                                  for name, value in zip(names, values)
                                  if key(name) in aliases}
                        if (set(parsed) == {"f1", "f2", "f3", "h"}
                                and all(np.isfinite(v) and v >= 0 for v in parsed.values())):
                            weights = parsed
            elif isinstance(w, list) and len(w) == 4 and all(isinstance(x, (float, int)) for x in w):
                weights = dict(zip(("f1", "f2", "f3", "h"), map(float, w)))
    if not electre and "nivel" in tab:
        electre = tab.loc[tab["nivel"] == 1, "id"].tolist()
    if not ranking and "prioridade" in tab:
        ranking = tab.loc[tab["prioridade"].notna(), ["id", "prioridade"]].to_dict("records")
    df = pd.DataFrame(ranking, columns=["id", "prioridade"])
    if not df.empty:
        df = df.drop_duplicates("id").sort_values("prioridade", ascending=False).reset_index(drop=True)
        if not selected:
            selected = str(df.iloc[0]["id"])
    return list(dict.fromkeys(electre)), df, selected, weights


@dataclass
class Data:
    alternatives: pd.DataFrame
    recipes: dict[str, np.ndarray]
    ores: pd.DataFrame
    piles: pd.DataFrame
    limits: pd.DataFrame
    truck_kt: float
    electre: list[str]
    ranking: pd.DataFrame
    winner: str
    weights: dict[str, float]
    sensitivity: Any
    notices: list[str]


def load(root: Path = ROOT) -> Data:
    root = Path(root)
    source = root / "resultados" / "entrega_3"
    union = read_json(source / "uniao_nao_dominadas.json")
    decision = read_json(source / "decisao.json")
    instance = read_json(root / "dados" / "dados_exemplo.json")
    ores = _load_ores(instance)
    piles = _load_piles(instance)
    limits = _load_limits(instance)
    truck_kt = number(field(instance, "capacidade_caminhao_kt", "capacidade_caminhao", "capacidade_kt", "t"), 2.0)
    if not np.isfinite(truck_kt) or truck_kt <= 0:
        raise ValueError("Capacidade do caminhão inválida.")
    records = _record_list(union)
    if not records:
        raise ValueError("Não foram encontradas alternativas em uniao_nao_dominadas.json.")
    merged: dict[str, dict] = {}
    recipes: dict[str, np.ndarray] = {}
    for i, obj in enumerate(records):
        if not isinstance(obj, dict):
            raise ValueError("Registro de alternativa inválido na união não dominada.")
        aid = alternative_id(field(obj, "id", "alternativa", "identificador", "nome", default=i+1))
        if aid in merged:
            raise ValueError(f"Identificador duplicado: {aid}")
        row = {"id": aid, **_objectives(obj)}
        orig = field(obj, "origens", "origem", "abordagens", "metodos", default="")
        row["origem"] = ", ".join(map(str, orig)) if isinstance(orig, (list, tuple)) else str(orig)
        merged[aid] = row
    # A union record can contain only objectives and an identifier. In that case
    # search the explicitly associated recipe exports without fabricating plans.
    recipes = _collect_recipes(union, records, source, ores, piles, limits, truck_kt)
    notices = []
    csv_file = source / "tabela_alternativas.csv"
    if csv_file.exists():
        table = pd.read_csv(csv_file)
        table.columns = [key(c) for c in table.columns]
        if "id" not in table:
            col = next((c for c in ("alternativa", "identificador", "alt", "codigo") if c in table), None)
            if col:
                table = table.rename(columns={col: "id"})
        if "id" in table:
            table["id"] = table["id"].map(alternative_id)
            for _, r in table.iterrows():
                aid = r["id"]
                if aid not in merged:
                    continue
                vals = _objectives(r.to_dict())
                for n, v in vals.items():
                    if np.isfinite(v):
                        if n in merged[aid] and np.isfinite(merged[aid][n]) and abs(merged[aid][n] - v) > max(1e-6, abs(v)*1e-6):
                            notices.append(f"Valores divergentes entre união e CSV para {aid}/{n}; mantido o da união.")
                        else:
                            merged[aid][n] = v
                for alias, name in (("nivel_electre", "nivel"), ("nivel", "nivel"), ("prioridade_ahp", "prioridade"), ("prioridade_global", "prioridade"), ("g", "prioridade")):
                    if alias in r and pd.notna(r[alias]):
                        merged[aid][name] = number(r[alias])
    df = pd.DataFrame(list(merged.values()))
    df["_order"] = df.id.map(lambda a: int(a[1:]) if re.fullmatch(r"A\d+", a) else 10**9)
    df = df.sort_values(["_order", "id"]).drop(columns="_order").reset_index(drop=True)
    for name in ("f1", "f2", "f3"):
        if name not in df or df[name].isna().any():
            raise ValueError(f"Critério obrigatório '{name}' incompleto nos resultados.")
    if df["f1"].median() > 1e5:
        df["f1"] /= 1_000_000
    # Homogeneidade: pode ser calculada diretamente a partir das receitas, se não estiver na tabela.
    if "h" not in df:
        df["h"] = np.nan
    for index, row in df[df["h"].isna()].iterrows():
        if row["id"] in recipes:
            df.loc[index, "h"] = homogeneity(recipes[row["id"]], piles)
    if df["h"].isna().any():
        raise ValueError("Homogeneidade H ausente para alternativas sem receita disponível.")
    if limits.empty or not all((limits.criterio == c).sum() == 2 for c in ("sio2", "al2o3")) or limits[["min", "alvo", "max"]].isna().any().any():
        raise ValueError("Os limites e alvos de SiO₂ e Al₂O₃ dos dois Sinters não foram reconhecidos nos dados.")
    if ores[["preco", "sio2", "al2o3"]].isna().any().any():
        raise ValueError("Preço e teores de SiO₂/Al₂O₃ devem estar definidos para todos os minérios.")
    if len(df) != len(records):
        raise ValueError("A quantidade de alternativas carregadas não confere com a união.")
    electre, ranking, winner, weights = _decision_info(decision, df)
    if not winner or winner not in merged:
        raise ValueError("Resultado de AHP sem alternativa vencedora identificável.")
    electre = [a for a in electre if a in merged]
    if not electre and not ranking.empty:
        electre = ranking["id"].tolist()
    if not electre:
        raise ValueError("Não foi possível identificar o conjunto selecionado pelo ELECTRE I.")
    if winner not in electre:
        notices.append("A vencedora do AHP não aparece no conjunto ELECTRE I; verifique a configuração da decisão.")
    if not ranking.empty and set(ranking["id"]) != set(electre):
        notices.append("O ranking AHP e o conjunto ELECTRE I não coincidem; verifique a sincronização dos resultados.")
    return Data(df, recipes, ores, piles, limits, truck_kt, electre, ranking, winner, weights,
                read_json(source / "sensibilidade.json", mandatory=False), list(dict.fromkeys(notices)))


def homogeneity(matrix: np.ndarray, piles: pd.DataFrame) -> float:
    values = []
    for _, subset in piles.reset_index().groupby("sinter", sort=True):
        section = matrix[subset["index"].to_numpy()]
        totals = section.sum(axis=1)
        if np.any(totals <= 0):
            raise ValueError("Há pilha vazia na receita.")
        common = section.sum(axis=0)/section.sum()
        values.append(float(np.abs(section/totals[:, None]-common).sum(axis=1).mean()))
    return float(np.mean(values))


def evaluate_recipe(data: Data, aid: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    matrix = data.recipes.get(aid)
    if matrix is None:
        raise ValueError(
            f"A composição de {aid} não foi localizada em um arquivo de receitas com "
            "identificador compatível. Confira se uniao_nao_dominadas.json ou as "
            "exportações da otimização incluem o plano em caminhões (10 pilhas × 20 minérios)."
        )
    if matrix.shape != (len(data.piles), len(data.ores)):
        raise ValueError("Dimensões da matriz de composição incompatíveis com a instância.")
    if not np.issubdtype(matrix.dtype, np.integer) or (matrix < 0).any():
        raise ValueError("A composição deve conter quantidades inteiras não negativas.")
    rows = []
    used = matrix.sum(axis=0)
    for i, counts in enumerate(matrix):
        base = data.piles.iloc[i]
        n = int(counts.sum())
        if n == 0:
            raise ValueError(f"Pilha {base['id']} sem caminhões.")
        row = {"pilha": base["id"], "sinter": int(base["sinter"]), "caminhoes": n,
               "massa_kt": n * data.truck_kt,
               "massa_valida": bool(np.isclose(n*data.truck_kt, base["massa_kt"]))}
        for chem in ("sio2", "al2o3", "fet"):
            if data.ores[chem].notna().all():
                row[chem] = float(np.dot(counts, data.ores[chem])/n)
        for chem in ("sio2", "al2o3"):
            selected = data.limits.loc[(data.limits.sinter == int(base["sinter"])) & (data.limits.criterio == chem)]
            if not selected.empty and np.isfinite(selected.iloc[0][["min", "max"]].to_numpy(dtype=float)).all():
                lim = selected.iloc[0]
                row[f"{chem}_valida"] = bool(lim["min"] - 1e-9 <= row[chem] <= lim["max"] + 1e-9)
                row[f"{chem}_folga"] = min(row[chem]-lim["min"], lim["max"]-row[chem])
        rows.append(row)
    piles = pd.DataFrame(rows)
    by_ore = pd.DataFrame({"minerio": data.ores["id"], "sinter_1": matrix[data.piles.sinter == 1].sum(axis=0),
                           "sinter_2": matrix[data.piles.sinter == 2].sum(axis=0),
                           "total": used, "min": data.ores["min"], "max": data.ores["max"]})
    by_ore["disponibilidade_valida"] = ((by_ore["total"] >= by_ore["min"]) &
                                          (by_ore["max"].isna() | (by_ore["total"] <= by_ore["max"])))
    if data.ores.elegibilidade.notna().all():
        valid = []
        for i, counts in enumerate(matrix):
            sinter = int(data.piles.iloc[i].sinter)
            for j, n in enumerate(counts):
                if n == 0:
                    continue
                allowed = data.ores.iloc[j].elegibilidade
                if isinstance(allowed, (list, tuple)):
                    groups = {int(match.group()) for v in allowed if (match := re.search(r"\d+", str(v)))}
                    valid.append(sinter in groups)
        piles["elegibilidade_valida"] = all(valid)
    return piles, by_ore
