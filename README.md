# Trabalho de Teoria da Decisão — Entrega 1

Este repositório implementa **GVNS** para três problemas mono-objetivo do case de composição de pilhas: minimizar o custo (`f1`), o desvio quadrático de SiO₂ (`f2`) ou o desvio quadrático de Al₂O₃ (`f3`). Cada objetivo é resolvido separadamente, sempre com as mesmas restrições de massa, qualidade, elegibilidade e disponibilidade dos minérios.

## Dados e representação

O arquivo `dados_exemplo.json` transcreve o **exemplo de formato dos dados** do PDF do case. Há 10 pilhas: P1–P5 alimentam o Sinter 1 e P6–P10, o Sinter 2. Cada caminhão transporta 2 kt de um único minério. Uma pilha de 20 kt ocupa 10 posições na solução; uma de 38 kt ocupa 19. O valor `x_ij` é o número de posições da pilha `i` ocupadas pelo minério `j`. O FeT consta dos dados, mas os objetivos e limites desta entrega envolvem SiO₂ e Al₂O₃.

## Como o algoritmo trabalha

1. A **construção** distribui os usos mínimos obrigatórios dos minérios e completa as pilhas, em ordem, com os minérios elegíveis mais baratos. Ela pode gerar uma mistura fora dos limites de qualidade.
2. O **reparo** busca uma primeira solução viável. Só nessa fase a soma normalizada das violações guia a busca; ela não é somada a `f1`, `f2` ou `f3`.
3. A **GVNS** começa pela solução viável, perturba uma vizinhança e faz busca local VND em N1, N2 e N3. Candidatos inviáveis são rejeitados. Se houver melhora no objetivo escolhido, a busca volta a N1; caso contrário, passa à próxima vizinhança.

| Vizinhança | Movimento |
| --- | --- |
| N1 | Substitui o minério de um caminhão numa pilha. |
| N2 | Troca caminhões de duas pilhas, respeitando a elegibilidade de ambos. |
| N3 | Mantém nove pilhas e **reconstrói a composição inteira** da décima, mudando o minério de pelo menos metade dos seus caminhões. |

A N3 procura uma nova receita da pilha por contagens de minérios, em vez de permutar posições equivalentes. Ela verifica massa, elegibilidade, disponibilidade e qualidade. Por exemplo, numa pilha de 10 caminhões, pode substituir cinco caminhões de uma vez enquanto as outras nove pilhas ficam fixas. Isso difere de N1 (uma substituição) e N2 (troca entre pilhas sem alterar o uso total de minérios). A regra de mudar pelo menos metade é uma escolha da implementação; o PDF pede uma terceira vizinhança, mas não determina essa regra.

```text
para cada objetivo f1, f2, f3:
    repetir 5 vezes, com sementes diferentes:
        construir uma solução e repará-la até encontrar uma solução viável
        k = 1
        repetir ITERACOES vezes:              # ciclos globais da GVNS
            perturbar a solução corrente usando Nk
            fazer VND: visitar N1, N2, N3; melhoria reinicia em N1
            se a solução melhorou o objetivo escolhido:
                aceitá-la; k = 1
            senão:
                k = próxima vizinhança, voltando a N1 depois de N3
        salvar o melhor plano viável encontrado
```

`--iteracoes` limita os **ciclos globais** por execução, e não 50 visitas a cada vizinhança. O valor padrão é **50**, escolhido para os experimentos; o PDF não fixa esse número. Cada ciclo pode visitar as três vizinhanças durante a VND. **N1, N2 e N3 são examinadas até a primeira melhora ou o esgotamento dos vizinhos distintos, sem teto de candidatos e sem limite de tempo.** O reparo tem limite de 100 ciclos e avisa se não encontrar uma solução viável. O tempo em segundos é apenas medido e registrado; ele não encerra a busca.

### N3 sem teto de candidatos

A versão atual **retirou o antigo teto de 2.000 candidatos**. Durante a VND, uma visita a N3 continua até encontrar a primeira melhora ou esgotar todas as reconstruções geradas. Durante a perturbação, escolhemos o primeiro vizinho viável na ordem sorteada, como nas outras vizinhanças. Não há limite de nós parciais, receitas completas ou tempo de enumeração.

Antes de gerar uma receita, a enumeração percorre combinações parciais de contagens, calcula limites de qualidade e descarta ramos. O antigo teto contava somente receitas completas, não esse trabalho anterior. Mesmo sem teto, o campo `avaliacoes` continua contando chamadas a `evaluate`, incluindo reparo, perturbação e VND; não conta os ramos e cálculos internos da enumeração.

A enumeração é finita nesta representação inteira, mas pode ser muito grande. Uma VND concluída sem melhora nas três vizinhanças produz um ótimo local em N1, N2 e N3 segundo os operadores implementados e a tolerância numérica; não fornece prova de ótimo global.

Os resultados históricos obtidos com teto de 2.000 não devem ser apresentados como resultados desta versão sem teto. Alterar o teto muda a sequência de sorteios consumidos e a trajetória da busca: mais candidatos não garantem melhor resultado final para um número fixo de ciclos. Dentro de uma mesma execução, a melhor solução registrada nunca piora.

### Se o reparo não encontrar uma solução viável

O reparo termina na primeira solução viável avaliada ou após **100 ciclos de perturbação e VND**. Esses 100 ciclos não são 100 candidatos nem um limite de tempo.

Se esgotar os ciclos, `solve` lança `NoFeasiblePlanError`, com objetivo, número da execução e semente. **Isso significa falha da heurística em encontrar uma solução dentro do limite, não prova de que a instância seja inviável.** A GVNS daquela execução não começa e nenhuma solução inviável é devolvida como resultado.

Na execução pelo terminal, essa falha encerra o programa com código de saída **2** e uma mensagem legível. O lote de 15 execuções é interrompido; a exportação só acontece quando todas terminam com sucesso, então não são exportados novos CSVs, planos ou figuras daquele lote. Arquivos de uma execução anterior na pasta de saída não são apagados e não representam o lote que falhou. Não há reinício automático ou aumento automático do limite.

## Instalação e execução

Use Python 3.10 ou superior. A única dependência externa é Matplotlib, usada para produzir as figuras **diretamente em PDF**.

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest -q test_mono_objetivo.py
python3 mono_objetivo.py --iteracoes 50 --saida minha_execucao
```

O último comando faz **15 execuções**: cinco sementes para cada um dos três objetivos. Sem `--iteracoes`, usa 50; sem `--saida`, escreve em `resultados/`. `--dados arquivo.json` seleciona outra instância e `--semente-base NUMERO` muda a sequência de sorteios. Veja `python3 mono_objetivo.py --help`.

Para reproduzir a comparação versionada:

```sh
for n in 10 20 30 40 50; do
    python3 mono_objetivo.py --iteracoes "$n" --saida "resultados_iteracoes/iter_$n"
done
```

Cada pasta `iter_N` gerada contém `execucoes.csv` (15 linhas de resultados, com valor dos três objetivos, violação, avaliações e tempo medido), `resumo.csv` (mínimo, média, desvio padrão amostral e máximo dos cinco valores do objetivo), `melhores_solucoes.json`, `convergencia.json`, `configuracao.json`, três gráficos `convergencia_f*.pdf` e três figuras `melhor_f*.pdf`. Compare os arquivos `resumo.csv` dos cinco ensaios. Soluções entregues devem ter `violacao = 0`. Os resultados anteriores, com parada por tempo, foram retirados para evitar confusão; execute os comandos acima para gerar os novos.

As sementes são fixadas por objetivo e número da execução para facilitar comparações entre limites de iteração. Isso reproduz a sequência de sorteios numa mesma versão do programa; mudar a versão do Python ou do algoritmo pode alterar os resultados. O número de avaliações e o tempo variam entre execuções porque o custo de cada busca local depende da solução encontrada.

## Arquivos principais

| Arquivo | Função |
| --- | --- |
| `mono_objetivo.py` | Dados, construção, reparo, GVNS, validação e exportação. |
| `figuras.py` | Gráficos PDF com Matplotlib. |
| `dados_exemplo.json` | Instância de exemplo fornecida no anexo do case. |
| `test_mono_objetivo.py` | Testes das fórmulas e movimentos. |
| `requirements.txt` | Dependência para as figuras. |
| `resultados_iteracoes/` | Pasta criada ao executar a comparação com 10, 20, 30, 40 e 50 ciclos. |
