# Otimização do Custo e Qualidade de Pilhas de Minério

Trabalho da disciplina Teoria da Decisão (Engenharia de Sistemas, UFMG, 2026/2), sobre o case da Cassotis Consulting.

- **Entrega 1:** resolve com **GVNS** os três problemas mono-objetivo: minimizar o custo (`f1`), o desvio quadrático de SiO₂ (`f2`) ou o desvio quadrático de Al₂O₃ (`f3`), sempre com as mesmas restrições de massa, qualidade, elegibilidade e disponibilidade.
- **Entrega 2:** reutiliza a mesma GVNS nas abordagens **Soma Ponderada** e **ε-restrito**, com normalização a partir da Entrega 1 e filtragem das soluções não dominadas nos três objetivos.
- **Entrega 3:** tomada de decisão multicritério sobre a união das frentes da Entrega 2, com quatro critérios (custo, desvio de SiO₂, desvio de Al₂O₃ e um critério extra), métodos de apoio à decisão plugáveis e análise de sensibilidade.

O relatório cumulativo das duas entregas está em [`relatorio/relatorio.tex`](relatorio/relatorio.tex).

## Estrutura do repositório

```text
dados/                     instância do case (dados_exemplo.json)
configuracoes/             grades de pesos e de ε (final e piloto); normalização gerada pela Entrega 1
src/pilhas_minerio/        código-fonte (pacote Python)
  gvns.py                    modelo, construção, vizinhanças, reparo e GVNS; execução da Entrega 1
  multiobjetivo.py           Soma Ponderada, ε-restrito, dominância e execução da Entrega 2
  normalizacao.py            gera configuracoes/normalizacao.json a partir da Entrega 1
  comparacao_abordagens.py   hipervolume, cobertura, variabilidade entre rodadas e figura 3D
  calibracao_n3.py           experimento da fração mínima de N3 e execuções longas
  criterio_parada.py         análise do critério de parada a partir das execuções longas
  referencia_gurobi.py       referência exata opcional com Gurobi
  figuras.py                 gráficos em PDF
  decisao/                   Entrega 3: união das frentes, critérios, ELECTRE I, AHP e sensibilidade
  caminhos.py                caminhos padrão do projeto
tests/                     testes automatizados (unittest)
relatorio/                 relatório em LaTeX e suas figuras
resultados/
  entrega_1/                 execução final mono-objetivo
  entrega_2/                 execução final multiobjetivo
  entrega_3/                 união das frentes com os quatro critérios e decisão final
  calibracao/                fração de N3, ciclos, critério de parada e piloto da grade de ε
  referencia_exata/          resultados do Gurobi
```

## Instalação

Python 3.10 ou superior. Na raiz do repositório:

```sh
python -m pip install -e .
python -m unittest discover -s tests -q
```

A instalação em modo editável deixa o pacote `pilhas_minerio` disponível para os comandos abaixo. As dependências são Matplotlib (figuras) e SciPy (testes estatísticos da calibração). O Gurobi só é necessário para a referência exata: `python -m pip install -e ".[gurobi]"`, com licença válida.

## Algoritmo

1. **Construção:** distribui os usos mínimos obrigatórios e completa as pilhas com os minérios elegíveis mais baratos, como sugere o enunciado. Pode violar a qualidade.
2. **Reparo:** perturbação seguida de VND, minimizando a violação normalizada até a primeira solução admissível. A cada **100 ciclos** sem solução admissível, recomeça da construção com a sequência de sorteios já avançada. Se o orçamento de ciclos acabar, a execução é registrada como `falha_reparo` e as demais continuam.
3. **GVNS:** perturba em `N_k` (até `k` movimentos), aplica VND em N1, N2 e N3 com primeira melhora e aceita só melhora estrita. Candidatos inviáveis são rejeitados.

| Vizinhança | Movimento |
| --- | --- |
| N1 | Substitui o minério de um caminhão numa pilha. |
| N2 | Troca caminhões de duas pilhas, respeitando a elegibilidade; a ordem dos pares de pilhas é sorteada. |
| N3 | Mantém nove pilhas e reconstrói a décima, alterando pelo menos `max(2, ceil(0,25 · n))` dos seus `n` caminhões. |

A N3 é enumerada por contagens de minérios, com limites de disponibilidade e de qualidade. Na VND, ramos que **não podem melhorar o critério ativo** são descartados por um limitante exato, o que permite examinar a vizinhança inteira, **sem teto** de candidatos. A avaliação é **incremental**: só as pilhas alteradas são recalculadas, com resultado idêntico ao da avaliação completa.

**Critério de parada:** orçamento de **300 ciclos** por execução, somando reparo e GVNS.

## Entrega 1 — execução final

```sh
python -m pilhas_minerio.gvns --processos 15
```

Faz 15 execuções (5 sementes × 3 objetivos), com 300 ciclos cada, e grava em `resultados/entrega_1/`. A semente da execução `r` de `f_k` é `2026 + 10000·(k−1) + r` e não depende do número de processos. Saída: `execucoes.csv`, `resumo.csv` (mínimo, média, desvio padrão, máximo), `melhores_solucoes.json`, `convergencia.json`, `convergencia_ciclos.json`, `configuracao.json`, `convergencia_f*.pdf` e `melhor_f*.pdf`.

## Entrega 2 — normalização e execução final

```sh
python -m pilhas_minerio.normalizacao
python -m pilhas_minerio.multiobjetivo --processos 16
python -m pilhas_minerio.comparacao_abordagens
```

1. **Normalização:** monta a matriz cruzada com as melhores soluções de cada objetivo da Entrega 1; `a` e `b` são o mínimo e o máximo de cada coluna, e `f̄ = (f − a)/(b − a)`, sem cortar valores fora de [0, 1]. O arquivo `configuracoes/normalizacao.json` é conferido (hash dos dados, receitas e objetivos) antes de ser gravado.
2. **Soma Ponderada:** minimiza `Σ w_q f̄_q` com 7 vetores de pesos (`configuracoes/grade_multiobjetivo.json`, na ordem custo, sílica, alumina).
3. **ε-restrito:** minimiza `f̄_1` com `f̄_2 ≤ ε₂` e `f̄_3 ≤ ε₃`, na grade `{0,10; 0,25; 0,50; 1,00}²` (16 pares). No reparo, a violação inclui o excesso sobre cada ε.
4. **Rodadas:** 5 rodadas de cada grade, com 35 chamadas de Soma Ponderada e 80 de ε-restrito. Semente: `2026 + d + 1000·rodada + índice`, com `d = 100000` (soma) ou `200000` (ε).
5. **Saída** (`resultados/entrega_2/`): uma receita por chamada em `chamadas/`, `execucoes.csv`, `resumo.json`, conjuntos não dominados por abordagem e por rodada, as seis projeções `soma_f*_f*.pdf` e `epsilon_f*_f*.pdf`, com cores por rodada, e, após `comparacao_abordagens`, as métricas de comparação e a figura `frente_3d.pdf`.

Repetir o comando de `multiobjetivo` retoma só as chamadas pendentes; mudanças nos dados, no código, na normalização ou nos parâmetros exigem outra pasta de saída (`--saida`).

## Calibração

| Pasta em `resultados/calibracao/` | Conteúdo | Comando |
| --- | --- | --- |
| `fracao_n3/` | 8 regras de mínimo da N3, 30 execuções × 3 objetivos, 50 ciclos | `python -m pilhas_minerio.calibracao_n3 --execucoes 30 --processos 8 --iteracoes 50` |
| `ciclos_n3/` | 200 contra 50 ciclos para N3 com 25%, 30% e 50% | `python -m pilhas_minerio.calibracao_n3 --fracoes 0.25 0.3 0.5 --execucoes 10 --iteracoes 200 --saida resultados/calibracao/ciclos_n3` |
| `criterio_parada/` | 30 execuções × 3 objetivos com 500 ciclos; curvas por ciclo | `python -m pilhas_minerio.calibracao_n3 --fracoes 0.25 --execucoes 30 --iteracoes 500 --saida resultados/calibracao/criterio_parada` e `python -m pilhas_minerio.criterio_parada` |
| `piloto_grade_epsilon/` | Piloto de 1 rodada, 100 ciclos, com ε em {0,05; 0,10; 0,25; 0,50; 1,00} e normalização preliminar; guarda as chamadas e o manifesto | `python -m pilhas_minerio.multiobjetivo --rodadas 1 --iteracoes 100 --configuracoes configuracoes/grade_piloto_epsilon.json --normalizacao resultados/calibracao/piloto_grade_epsilon/normalizacao.json --saida <pasta nova>` |

O experimento de `fracao_n3/` usou, em N2, a exploração dos pares a partir de uma pilha sorteada; as execuções atuais sorteiam os pares diretamente, então os valores por semente podem diferir ligeiramente.

## Referência exata (opcional)

```sh
python -m pilhas_minerio.referencia_gurobi --objetivo 2 --tempo-limite 21600
```

Resolve f1 (programa linear inteiro) e f2, f3 (programas quadráticos inteiros) com Gurobi, só para medir a distância entre a GVNS e o ótimo. Os resultados ficam em `resultados/referencia_exata/` e não são usados em nenhuma outra etapa.

## Entrega 3: tomada de decisão multicritério

```sh
python -m pilhas_minerio.decisao.preparar
python -m pilhas_minerio.decisao.executar
python -m pilhas_minerio.decisao.analise
python -m pilhas_minerio.decisao.candidatos
```

Todos os hiperparâmetros (julgamentos do decisor, limiares, níveis do ELECTRE I enviados ao AHP, variações da sensibilidade) ficam em [`configuracoes/decisao.json`](configuracoes/decisao.json), com a justificativa de cada um; o código só lê esse arquivo. A entrevista que originou os julgamentos e os limiares está em [`configuracoes/entrevista_decisor.json`](configuracoes/entrevista_decisor.json). Para repetir a entrevista com outra pessoa, [`entrevista/criar_formulario.gs`](entrevista/criar_formulario.gs) é um script do Google Apps Script que cria o formulário com as mesmas perguntas e a planilha de respostas. Com a planilha exportada em CSV, `python -m pilhas_minerio.decisao.entrevista respostas.csv` converte as respostas em julgamentos par a par, calcula os pesos, o QC e confere a ordem declarada contra os pesos, e mostra o veto e o apoio declarados. Os valores só entram em `configuracoes/decisao.json` por decisão do grupo.

1. **União** (`decisao/alternativas.py`): reúne `nao_dominadas_soma.json` e `nao_dominadas_epsilon.json`, reavalia cada receita na instância (os objetivos gravados precisam coincidir), une receitas idênticas e remove as dominadas entre as duas abordagens. Cada alternativa recebe um código (`A01`, ...) pela ordem crescente dos objetivos.
2. **Critérios** (`decisao/criterios.py`): os três objetivos mais um critério extra escolhido em `criterio_extra`. Hoje, `homogeneidade`: para cada equipamento, média da distância L1 entre a receita de cada pilha e a receita comum do grupo (total de caminhões de cada minério dividido pelo total de caminhões do grupo), e média entre os equipamentos; 0 é receita igual em todas as pilhas. Outro critério entra como subclasse de `DecisionCriterion` registrada em `EXTRA_CRITERIA`.
3. **Pesos** (`decisao/metodos/ahp.py`): o decisor julga os critérios par a par na escala de Saaty (`pesos.julgamentos`); os pesos são o autovetor principal da matriz, aceita com quociente de consistência (QC) até 0,10.
4. **ELECTRE I** (`decisao/metodos/electre1.py`), com a notação das aulas: conjuntos J+, J= e J-, índices de concordância C e de discordância D (fator de escala `1/amplitude`), relação S por `tau_c` (apoio) e `tau_d` (veto), circuitos reduzidos a uma classe e ordenação por níveis. As alternativas do primeiro nível, que empatam por serem incomparáveis entre si, seguem para o AHP; `niveis_para_ahp` acrescenta o segundo nível, o terceiro e assim por diante, sempre inteiros.
5. **AHP** (`decisao/metodos/ahp.py`): prioridades por autovetor principal, índice e quociente de consistência com a tabela de ICA das aulas (simulação acima de n = 10) e síntese global `g = P w`. As matrizes entre alternativas saem dos valores medidos, pelo modo de `ahp.julgamento_local`.
6. **Encadeamento** (`decisao/pipeline.py`): `ElectreThenAhp` aplica o AHP às alternativas dos primeiros níveis do ELECTRE I; a de maior prioridade global é a escolhida.
7. **Métodos plugáveis** (`decisao/metodos/base.py`): cada método implementa `DecisionMethod.evaluate(problema, pesos)` e se registra em `METHODS`.
8. **Sensibilidade** (`decisao/sensibilidade.py`, `decisao/analise.py`): em torno do caso base, variam-se, um grupo por vez: o veto, o apoio, o número de níveis enviados ao AHP, o modo do AHP, cada peso de 0 a 1 (com o peso crítico em que a escolha muda), cada julgamento do decisor em 1 e 2 degraus da escala de Saaty e todos juntos em sorteios, e o par apoio e veto em um mapa de calor. Há ainda um caso de referência com o AHP sobre todas as alternativas, sem o ELECTRE I. Medem-se a vencedora, a fração de variações em que a vencedora do caso base se mantém, sua posição e o tau de Kendall com o ranking-base.

Saída em `resultados/entrega_3/`: `uniao_nao_dominadas.json` (contagens, faixas dos critérios, correlação de Spearman do critério extra e uma linha por alternativa), `decisao.json` (pesos, limiares, conjunto enviado ao AHP, prioridades, ranking, alternativa escolhida e seus compromissos), `tabela_alternativas.csv` e `.tex` (critérios, nível no ELECTRE I e prioridade do AHP das 73 alternativas), `sensibilidade.json`, `criterios_candidatos.json` (correlação de Spearman de atributos candidatos a critério extra, de `candidatos`) e as figuras `projecoes_escolha.pdf`, `solucao_final.pdf`, `mapa_calor_limiares.pdf`, `sensibilidade_limiares.pdf`, `sensibilidade_pesos.pdf` e `sensibilidade_julgamentos.pdf`. As figuras e a tabela em `.tex` usadas no relatório são cópias dessas, em `relatorio/`.
