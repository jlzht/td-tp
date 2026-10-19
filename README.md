# Trabalho de Teoria da Decisão — Entregas 1 e 2

A Entrega 1 resolve, com **GVNS**, os três problemas mono-objetivo do case de composição de pilhas: minimizar o custo (`f1`), o desvio quadrático de SiO₂ (`f2`) ou o desvio quadrático de Al₂O₃ (`f3`), sempre com as mesmas restrições de massa, qualidade, elegibilidade e disponibilidade.

A Entrega 2 reutiliza a mesma GVNS nas abordagens **Soma Ponderada** e **ε-restrito**, com normalização fixa a partir da Entrega 1 e filtragem das soluções não dominadas nos três objetivos. O relatório (`entrega-1.tex`) é cumulativo; não há apresentação oral na Entrega 2.

## Dados e representação

`dados_exemplo.json` transcreve o exemplo de dados do PDF do case: 20 minérios e 10 pilhas (P1–P5 no Sinter 1, P6–P10 no Sinter 2), com caminhões de 2 kt. Cada pilha é um vetor com uma posição por caminhão; uma pilha de 20 kt tem 10 posições e uma de 38 kt tem 19. O valor `x_ij` é o número de posições da pilha `i` com o minério `j`.

## Algoritmo

1. **Construção:** distribui os usos mínimos obrigatórios e completa as pilhas com os minérios elegíveis mais baratos (sugestão do enunciado). Pode violar a qualidade.
2. **Reparo:** perturbação + VND minimizando a violação normalizada, até a primeira solução admissível. A cada **100 ciclos** sem solução admissível, recomeça da construção com a sequência de sorteios já avançada. Se o orçamento de ciclos acabar, a execução é registrada como `falha_reparo` e o lote continua.
3. **GVNS:** perturba em `N_k` (até `k` movimentos), aplica VND em N1, N2, N3 com primeira melhora, aceita só melhora estrita. Candidatos inviáveis são rejeitados.

| Vizinhança | Movimento |
| --- | --- |
| N1 | Substitui o minério de um caminhão numa pilha. |
| N2 | Troca caminhões de duas pilhas, respeitando a elegibilidade; a ordem dos pares de pilhas é sorteada. |
| N3 | Mantém nove pilhas e reconstrói a décima, alterando pelo menos `max(2, ceil(0,25 · n))` dos seus `n` caminhões. |

A N3 é enumerada por contagens de minérios, com limites de disponibilidade e de qualidade. Na VND, ramos que **não podem melhorar o critério ativo** são descartados por um limitante exato (custo mínimo de completar a pilha e menor desvio possível na faixa de teor alcançável), o que permite examinar a vizinhança inteira, **sem teto** de candidatos. A avaliação é **incremental**: só as pilhas alteradas são recalculadas, com resultado idêntico ao da avaliação completa.

**Critério de parada:** orçamento de **C = 300 ciclos** por execução, somando reparo e GVNS. A escolha está em `resultados_criterio_parada/` (ver abaixo).

## Instalação

Python 3.10 ou superior.

```sh
python -m pip install -r requirements.txt
python -m unittest -q
```

`requirements.txt` traz Matplotlib (figuras) e SciPy (testes estatísticos dos experimentos de calibração). O Gurobi só é usado pela referência exata opcional em `solucao_exata/`.

## Entrega 1 — execução final

```sh
python mono_objetivo.py --processos 15 --saida resultados_entrega1
```

Faz 15 execuções (5 sementes × 3 objetivos), 300 ciclos cada. A semente da execução `r` de `f_k` é `2026 + 10000·(k−1) + r` e não depende do número de processos. Saída: `execucoes.csv`, `resumo.csv` (mínimo, média, desvio padrão, máximo), `melhores_solucoes.json`, `convergencia.json`, `convergencia_ciclos.json`, `configuracao.json`, `convergencia_f*.pdf` e `melhor_f*.pdf`.

## Entrega 2 — normalização e execução final

```sh
python gerar_normalizacao.py --lote resultados_entrega1
python multiobjetivo.py --processos 16 --saida resultados_entrega2/oficial_final
python comparar_abordagens.py --pasta resultados_entrega2/oficial_final
```

1. **Normalização:** `gerar_normalizacao.py` monta a matriz cruzada com as melhores soluções de cada objetivo do lote da Entrega 1; `a` e `b` são o mínimo e o máximo de cada coluna, e `f̄ = (f − a)/(b − a)`, sem cortar valores fora de [0, 1]. O arquivo é conferido (hash dos dados, receitas e objetivos) antes de ser gravado.
2. **Soma Ponderada:** minimiza `Σ w_q f̄_q` com 7 vetores de pesos (`configuracoes_multi.json`, ordem custo, sílica, alumina).
3. **ε-restrito:** minimiza `f̄_1` com `f̄_2 ≤ ε₂` e `f̄_3 ≤ ε₃`, grade `{0,10; 0,25; 0,50; 1,00}²` (16 pares). No reparo, a violação inclui o excesso sobre cada ε.
4. **Rodadas:** 5 rodadas de cada grade: 35 chamadas de Soma Ponderada e 80 de ε-restrito. Semente: `2026 + d + 1000·rodada + índice`, com `d = 100000` (soma) ou `200000` (ε).
5. **Saída:** uma receita por chamada em `chamadas/`, `execucoes.csv`, `resumo.json`, conjuntos não dominados por abordagem e por rodada, e as seis projeções `soma_f*_f*.pdf` e `epsilon_f*_f*.pdf`, com cores por rodada.
6. **Comparação:** `comparar_abordagens.py` grava número de não dominadas, faixas, hipervolume normalizado (referência 1,1 em cada eixo), cobertura entre as abordagens e hipervolume por rodada.

Repetir o comando de `multiobjetivo.py` retoma só as chamadas pendentes; mudanças nos dados, no código, na normalização ou nos parâmetros exigem outra pasta de saída.

## Experimentos de calibração

| Pasta | Conteúdo | Comando |
| --- | --- | --- |
| `resultados_experimento_n3/` | 8 regras de mínimo da N3, 30 execuções × 3 objetivos, 50 ciclos | `python experimento_n3.py --execucoes 30 --processos 8 --iteracoes 50 --saida resultados_experimento_n3` |
| `resultados_ciclos_n3/` | 200 contra 50 ciclos para N3 com 25%, 30% e 50% | `python experimento_n3.py --fracoes 0.25 0.3 0.5 --execucoes 10 --iteracoes 200 --saida resultados_ciclos_n3` |
| `resultados_criterio_parada/` | 30 execuções × 3 objetivos com 500 ciclos; curvas por ciclo | `python experimento_n3.py --fracoes 0.25 --execucoes 30 --iteracoes 500 --saida resultados_criterio_parada` e `python analise_criterio_parada.py --pasta resultados_criterio_parada` |
| `resultados_entrega2/piloto_grade/` | Piloto de 1 rodada, 100 ciclos, grade de ε ampliada | — |

Os experimentos de N3 foram feitos antes do sorteio uniforme dos pares da N2; os resultados por semente podem diferir ligeiramente na versão atual.

## Referência exata (opcional)

`solucao_exata/modelo_gurobi.py` resolve f1 (programa linear inteiro) e f2, f3 (programas quadráticos inteiros) com Gurobi, só para medir a distância entre a GVNS e o ótimo. Os resultados ficam em `solucao_exata/resultados/` e não são usados em nenhuma outra etapa.

## Arquivos principais

| Arquivo | Função |
| --- | --- |
| `mono_objetivo.py` | Modelo, construção, vizinhanças, avaliação incremental e a GVNS única (`solve` e `solve_scalar`). |
| `multiobjetivo.py` | Critérios escalares, rodadas, dominância, retomada e exportação multiobjetivo. |
| `gerar_normalizacao.py` | Gera `normalizacao.json` a partir do lote da Entrega 1. |
| `comparar_abordagens.py` | Métricas de comparação entre Soma Ponderada e ε-restrito. |
| `experimento_n3.py`, `analise_criterio_parada.py` | Calibração da N3 e do critério de parada. |
| `figuras.py` | Gráficos em PDF com Matplotlib. |
| `test_mono_objetivo.py`, `test_multiobjetivo.py` | Testes automatizados. |
| `entrega-1.tex` | Relatório cumulativo das duas entregas. |
