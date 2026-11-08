"""Checagens da leitura das respostas do formulário da entrevista."""
import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pilhas_minerio.caminhos import CONFIG_DIR, PROJECT_ROOT as PROJECT
from pilhas_minerio.decisao.entrevista import InterviewAnalysis, ResponseSheet
from pilhas_minerio.decisao.hiperparametros import Hyperparameters

CRITERIA = ("custo", "desvio_sio2", "desvio_al2o3", "homogeneidade")
MOST = "Se você pudesse melhorar SÓ UM aspecto, do pior para o melhor valor, qual traria MAIS valor para a usina?"
LEAST = "Qual dos quatro traria MENOS valor, ou seja, qual você abriria mão primeiro?"
VETO = ("Você aceita uma composição que seja pior em um aspecto desde que compense nos outros. "
        "Qual a maior piora que você toleraria em QUALQUER aspecto isolado?")
SUPPORT = ('Para considerar que a composição A é "pelo menos tão boa quanto" a B e descartar a B, os '
           "aspectos em que A é melhor ou igual a B precisam somar quanto da importância total?")
COMMENTS = "Há algum aspecto importante para a usina que ficou de fora, ou alguma observação sobre as suas respostas?"
PAIRS = {("o custo", "a sílica"): "custo:desvio_sio2", ("o custo", "a alumina"): "custo:desvio_al2o3",
         ("o custo", "a receita parecida"): "custo:homogeneidade",
         ("a sílica", "a alumina"): "desvio_sio2:desvio_al2o3",
         ("a sílica", "a receita parecida"): "desvio_sio2:homogeneidade",
         ("a alumina", "a receita parecida"): "desvio_al2o3:homogeneidade"}
LABELS = {9: "extremamente", 7: "muito fortemente", 5: "fortemente", 3: "moderadamente"}


def pair_answer(first, second, value):
    if value == 1:
        return "As duas melhorias valem o mesmo (1)"
    winner, loser = (first, second) if value > 0 else (second, first)
    return f"Melhorar {winner} vale {LABELS[abs(value)]} mais que melhorar {loser} ({value})"


def row(values, most="Custo: a compra de minério cai", least="Receita parecida: a receita de cada pilha",
        veto="Até 10% da faixa: quase não aceito", support="Pelo menos 80%: exijo que quase toda", comments=""):
    data = {"Carimbo de data/hora": "05/11/2026 10:00:00", MOST: most, LEAST: least}
    for (first, second), key in PAIRS.items():
        data[f"Quanto vale mais melhorar {first} ou melhorar {second}?"] = pair_answer(
            first, second, values[key])
    data.update({VETO: veto, SUPPORT: support, COMMENTS: comments})
    return data


# Julgamentos perfeitamente consistentes: 3 x 3 = 9.
INTERVIEW = {"custo:desvio_sio2": 3, "custo:desvio_al2o3": 3, "custo:homogeneidade": 9,
             "desvio_sio2:desvio_al2o3": 1, "desvio_sio2:homogeneidade": 3,
             "desvio_al2o3:homogeneidade": 3}


class ResponseSheetTests(unittest.TestCase):
    def test_respostas_viram_julgamentos_e_pesos(self):
        answers = ResponseSheet([row(INTERVIEW)], CRITERIA).answers()
        self.assertEqual(answers.judgments, {k: float(v) for k, v in INTERVIEW.items()})
        self.assertEqual((answers.most_valuable, answers.least_valuable), ("custo", "homogeneidade"))
        self.assertEqual((answers.declared_veto, answers.declared_support), (0.10, 0.80))
        analysis = InterviewAnalysis.of(answers, CRITERIA, 0.10)
        np.testing.assert_allclose(list(analysis.weights.values()), [9 / 16, 3 / 16, 3 / 16, 1 / 16])
        self.assertAlmostEqual(analysis.consistency_ratio, 0.0)
        self.assertTrue(analysis.within_limit and analysis.order_agrees)

    def test_planilha_da_cassotis_reproduz_os_julgamentos_adotados(self):
        params = Hyperparameters.load(CONFIG_DIR / "decisao.json")
        sheet = ResponseSheet.from_csv(PROJECT / "entrevista" / "respostas_cassotis.csv", CRITERIA)
        answers = sheet.answers()
        self.assertEqual(answers.judgments, params.judgments)
        analysis = InterviewAnalysis.of(answers, CRITERIA, params.max_consistency_ratio)
        np.testing.assert_allclose(list(analysis.weights.values()), params.criteria_weights())
        self.assertAlmostEqual(analysis.consistency_ratio, params.judgments_consistency_ratio())
        self.assertFalse(analysis.within_limit)
        self.assertTrue(analysis.order_agrees)

    def test_valor_negativo_significa_que_o_segundo_criterio_vale_mais(self):
        values = {**INTERVIEW, "custo:desvio_sio2": -3}
        judgments = ResponseSheet([row(values)], CRITERIA).answers().judgments
        self.assertAlmostEqual(judgments["custo:desvio_sio2"], 1 / 3)

    def test_ultima_linha_e_a_padrao_e_csv_com_acentos(self):
        rows = [row(INTERVIEW, comments="primeira"), row({**INTERVIEW, "custo:desvio_sio2": 7},
                                                          comments="segunda, com acento: é")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "respostas.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            sheet = ResponseSheet.from_csv(path, CRITERIA)
        self.assertEqual(sheet.answers().judgments["custo:desvio_sio2"], 7.0)
        self.assertEqual(sheet.answers().comments, "segunda, com acento: é")
        self.assertEqual(sheet.answers(0).judgments["custo:desvio_sio2"], 3.0)

    def test_julgamentos_circulares_passam_do_limite_de_consistencia(self):
        circular = {"custo:desvio_sio2": 9, "custo:desvio_al2o3": -9, "custo:homogeneidade": 1,
                    "desvio_sio2:desvio_al2o3": 9, "desvio_sio2:homogeneidade": 1,
                    "desvio_al2o3:homogeneidade": 1}
        analysis = InterviewAnalysis.of(ResponseSheet([row(circular)], CRITERIA).answers(), CRITERIA, 0.10)
        self.assertFalse(analysis.within_limit)

    def test_ordem_incoerente_com_os_pesos_e_detectada(self):
        answers = ResponseSheet([row(INTERVIEW, most="Alumina: o desvio típico")], CRITERIA).answers()
        self.assertFalse(InterviewAnalysis.of(answers, CRITERIA, 0.10).order_agrees)

    def test_erros_de_formato(self):
        with self.assertRaises(ValueError):
            ResponseSheet([], CRITERIA).answers()
        broken = row(INTERVIEW)
        del broken[VETO]
        with self.assertRaises(ValueError):
            ResponseSheet([broken], CRITERIA).answers()
        no_number = row(INTERVIEW)
        no_number["Quanto vale mais melhorar o custo ou melhorar a sílica?"] = "Sem número"
        with self.assertRaises(ValueError):
            ResponseSheet([no_number], CRITERIA).answers()
        with self.assertRaises(ValueError):
            ResponseSheet([row(INTERVIEW)], ("custo", "outro")).answers()


if __name__ == "__main__":
    unittest.main()
