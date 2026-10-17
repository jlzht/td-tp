# Trabalho de Teoria da Decisão — Entregas 1 e 2

A Entrega 1 implementa **GVNS** para três problemas mono-objetivo do case de composição de pilhas: minimizar o custo (`f1`), o desvio quadrático de SiO₂ (`f2`) ou o desvio quadrático de Al₂O₃ (`f3`). Cada objetivo é resolvido separadamente, sempre com as mesmas restrições de massa, qualidade, elegibilidade e disponibilidade dos minérios.

A Entrega 2 reutiliza a mesma GVNS para **Soma Ponderada** e **ε-restrito**, com normalização fixa e filtragem de soluções não dominadas nos três objetivos. O relatório é cumulativo; não há apresentação oral nessa segunda entrega.

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

`--iteracoes` limita os **ciclos globais** por execução, e não 50 visitas a cada vizinhança. O valor padrão é **50**, escolhido para os experimentos; o PDF não fixa esse número. Cada ciclo pode visitar as três vizinhanças durante a VND. **N1, N2 e N3 são examinadas até a primeira melhora ou o esgotamento dos vizinhos distintos, sem teto de candidatos e sem limite de tempo.** O reparo não tem teto de ciclos, avaliações ou tempo: repete até encontrar uma solução admissível ou ser interrompido manualmente. O tempo em segundos é apenas medido e registrado; ele não encerra a busca.

### N3 sem teto de candidatos

A versão atual **retirou o antigo teto de 2.000 candidatos**. Durante a VND, uma visita a N3 continua até encontrar a primeira melhora ou esgotar todas as reconstruções geradas. Durante a perturbação, escolhemos o primeiro vizinho viável na ordem sorteada, como nas outras vizinhanças. Não há limite de nós parciais, receitas completas ou tempo de enumeração.

Antes de gerar uma receita, a enumeração percorre combinações parciais de contagens, calcula limites de qualidade e descarta ramos. O antigo teto contava somente receitas completas, não esse trabalho anterior. Mesmo sem teto, o campo `avaliacoes` continua contando chamadas a `evaluate`, incluindo reparo, perturbação e VND; não conta os ramos e cálculos internos da enumeração.

A enumeração é finita nesta representação inteira, mas pode ser muito grande. Uma VND concluída sem melhora nas três vizinhanças produz um ótimo local em N1, N2 e N3 segundo os operadores implementados e a tolerância numérica; não fornece prova de ótimo global.

Os resultados históricos obtidos com teto de 2.000 não devem ser apresentados como resultados desta versão sem teto. Alterar o teto muda a sequência de sorteios consumidos e a trajetória da busca: mais candidatos não garantem melhor resultado final para um número fixo de ciclos. Dentro de uma mesma execução, a melhor solução registrada nunca piora.

### Reparo sem teto

O reparo repete os ciclos de perturbação e VND até avaliar a primeira solução
admissível. Foi removido o antigo limite de 100 ciclos. A lógica dos movimentos,
a aceitação por redução da violação e a mudança de vizinhança permanecem iguais.
Não há parada automática por estagnação, avaliações ou tempo.

**O reparo não tem garantia de término:** ele pode revisitar planos, inclusive
quando uma configuração ε-restrita não admite solução ou a heurística não a
encontra. Use `Ctrl+C` para interromper. Isso não prova inviabilidade e não
transforma um plano provisório em resultado válido. No lote multiobjetivo,
chamadas concluídas são preservadas; a chamada interrompida recomeça ao retomar.
No lote mono-objetivo, a exportação ocorre somente após concluir as 15 chamadas.
Os 50 ciclos globais contam apenas a otimização após o reparo.

## Instalação e execução

Use Python 3.10 ou superior. A única dependência externa é Matplotlib, usada para produzir as figuras **diretamente em PDF**.

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest -q
python3 mono_objetivo.py --iteracoes 50 --saida minha_execucao
```

O último comando faz **15 execuções**: cinco sementes para cada um dos três objetivos. Sem `--iteracoes`, usa 50; sem `--saida`, escreve em `resultados/`. `--dados arquivo.json` seleciona outra instância e `--semente-base NUMERO` muda a sequência de sorteios. Veja `python3 mono_objetivo.py --help`.

Para fazer uma nova comparação de ciclos (os resultados anteriores com teto de N3 são históricos):

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
| `mono_objetivo.py` | Modelo físico, construção, movimentos e uma única GVNS para as duas entregas. |
| `multiobjetivo.py` | Normalização, critérios escalares, rodadas, dominância e exportação multiobjetivo. |
| `normalizacao.json` | Três receitas de referência da Entrega 1, matriz cruzada, escalas e hash dos dados. |
| `configuracoes_multi.json` | Sete vetores de pesos e nove pares de ε. |
| `test_multiobjetivo.py` | Testes das escalas, ε no reparo/otimização, dominância e retomada. |
| `entrega-1.tex` | Relatório cumulativo das duas etapas. |
| `figuras.py` | Gráficos PDF com Matplotlib. |
| `dados_exemplo.json` | Instância de exemplo fornecida no anexo do case. |
| `test_mono_objetivo.py` | Testes das fórmulas e movimentos. |
| `requirements.txt` | Dependência para as figuras. |
| `resultados_iteracoes/` | Pasta criada ao executar a comparação com 10, 20, 30, 40 e 50 ciclos. |


## Entrega 2 — começar por aqui

### O que muda no problema

Os três objetivos continuam sendo calculados por `evaluate`: custo em reais,
desvio de SiO₂ em pp² e desvio de Al₂O₃ em pp². Massa, qualidade por pilha,
elegibilidade e disponibilidade continuam obrigatórias.

1. **Normalizar:** `normalizacao.json` contém as três melhores receitas isoladas
   do lote sem teto (15 chamadas, 50 ciclos). Para cada coluna da matriz cruzada,
   `a` é o mínimo e `b` o máximo. Usamos `(f-a)/(b-a)`, sem cortar resultados fora
   de `[0,1]`. Essas referências são empíricas, não ideais/nadires provados.
   O carregamento confere o hash dos dados, as receitas e seus objetivos.
2. **Soma Ponderada:** minimizar `w1*f1_normalizado + w2*f2_normalizado +
   w3*f3_normalizado`, com pesos não negativos que somam 1. Peso zero não remove
   restrições físicas.
3. **ε-restrito:** minimizar custo normalizado, exigindo também
   `f2_normalizado <= eps2` e `f3_normalizado <= eps3`. São limites dos desvios
   agregados, não novos percentuais de cada pilha.
4. **Buscar:** a mesma GVNS recebe o valor a minimizar e a medida de violação.
   O ε é verificado no reparo, na perturbação, na VND e ao registrar a melhor
   solução. Não adicionamos penalidade ao custo. N3 mantém sua definição e não
   tem teto de candidatos, nós ou tempo.
5. **Comparar:** guardar a receita final de cada configuração, reunir resultados
   por abordagem e filtrar dominância nos três objetivos. Gerar seis projeções
   PDF com Matplotlib.

No reparo de ε-restrito, a medida é `violacao_fisica + excesso_eps2 +
excesso_eps3`. Excessos normalizados de até `1e-10` são desprezados apenas como
arredondamento. O reparo não tem teto: só termina automaticamente ao encontrar
um plano admissível. Uma configuração não resolvida pode ficar em execução
indefinidamente; `Ctrl+C` interrompe o lote e preserva as chamadas concluídas.
Não se registra falha automática por esgotamento de ciclos.

### Política obrigatória de partida: construção original em todas as abordagens

**Mono-objetivo, Soma Ponderada e ε-restrito chamam a mesma função
`construct(case)` da Entrega 1 em todas as execuções.** Ela distribui os mínimos
obrigatórios e completa as pilhas por preço, conforme o procedimento original.
Para os mesmos dados, o vetor construído é idêntico nas três interfaces.

As receitas mono-objetivo são usadas exclusivamente para calcular e validar a
normalização. Elas não são selecionadas como partida de nenhuma chamada.

Depois dessa construção comum, cada chamada executa o reparo com suas restrições
ativas: físicas em mono e Soma Ponderada; físicas e ε em ε-restrito. O reparo
usa a semente da chamada, portanto a solução admissível obtida ao final dele
pode diferir entre abordagens e execuções. **Construção igual não significa
necessariamente a mesma solução no início da otimização após o reparo.**

Cada registro informa `partida: construcao`, e o manifesto registra a política
comum. Essa regra substitui o antigo atalho de usar uma referência admissível
como partida no ε-restrito.

### Configurações e rodadas

`configuracoes_multi.json` define:

- 7 pesos: equilíbrio, três prioridades individuais e três compromissos entre pares;
- 9 pares de ε: produto cartesiano de `{0.25, 0.50, 1.00}`.

Uma **rodada** percorre toda a grade da abordagem. Cinco rodadas fazem
**35 chamadas** para Soma Ponderada e **45 chamadas** para ε-restrito, 80 no total.
Cada chamada é uma nova GVNS com 50 ciclos globais por padrão. Essa organização,
as grades e os 50 ciclos são decisões do grupo; o PDF exige cinco execuções por
abordagem, mas não fornece esses valores da grade.

As sementes são `base + deslocamento + 1000*rodada + indice_configuracao`, com
índice começando em 1 e deslocamento 100000 para soma e 200000 para epsilon.
A ordem do arquivo de configurações participa dessa fórmula. Não mudamos
sementes para escolher resultados melhores. Processos paralelos não alteram a
semente de cada chamada; tempos medidos dependem da carga da máquina.

### Como executar

Prepare o ambiente e execute os testes automatizados:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest -q
```

Os testes automatizados limitam os casos que usam N3 real a cinco visitas de
até 25 candidatos completos. O teste de retirada do teto usa um gerador
controlado com 3.001 candidatos baratos. Essas limitações pertencem somente
aos testes; a execução normal mantém N3 e reparo sem teto.

Para um piloto da grade completa com uma rodada e dois ciclos globais:

```sh
python3 multiobjetivo.py --rodadas 1 --iteracoes 2 --processos 3 --saida meu_piloto
```

Esse piloto usa a GVNS normal, sem limitar N3 ou reparo; poucos ciclos globais
não garantem execução curta.

Execute as cinco rodadas completas:

```sh
python3 multiobjetivo.py --rodadas 5 --iteracoes 50 --processos 3 --saida resultados_entrega2/oficial_construcao_comum
```

Sem opções, executa as duas abordagens, cinco rodadas, 50 ciclos e um processo.
`--metodo soma` ou `--metodo epsilon` executa só uma abordagem. `--configuracao ID`
pode ser repetido para selecionar configurações num piloto:

```sh
python3 multiobjetivo.py --rodadas 1 --iteracoes 1 \
  --configuracao equilibrada --configuracao eps_100_100 --configuracao eps_025_025 \
  --saida piloto_curto
```

Use `--configuracoes arquivo.json` para uma grade diferente; o formato é o de
`configuracoes_multi.json`. `--normalizacao arquivo.json` seleciona referências
compatíveis com `--dados arquivo.json`. Não reutilize as escalas desta instância
em dados diferentes. Veja `python3 multiobjetivo.py --help`.

**Retomada automática:** repetir exatamente o comando usa as chamadas já salvas
em `chamadas/` e executa apenas as pendentes. É permitido mudar `--processos`.
Se dados, versão do Python, código, normalização, seleção ou parâmetros mudarem,
o programa exige outra pasta de saída. Não mistura versões de experimentos.
Resultados antigos com `falha_reparo` pertencem às versões com teto. A versão
atual não gera essa falha automaticamente. `Ctrl+C` preserva chamadas concluídas; a chamada em andamento
será refeita ao retomar. Não há teto de tempo dentro de uma chamada.

### Pseudocódigo multiobjetivo

```text
carregar os dados, a normalização fixa e as grades
para abordagem em {Soma Ponderada, ε-restrito}:
    para rodada de 1 a 5:
        para configuração da grade:
            fixar semente, valor escalar e restrições ativas
            construir com construct(case), igual à Entrega 1 em todas as chamadas
            reparar sem teto até obter plano admissível (Ctrl+C pode interromper)
            executar a mesma GVNS por 50 ciclos globais
            salvar melhor receita admissível, curva, tempo e avaliações
    reunir receitas finais das cinco rodadas
    unir composições idênticas preservando suas origens
    retirar receitas dominadas nos três objetivos
    gerar f1×f2, f1×f3 e f2×f3 identificando as rodadas
```

### O que esperar na pasta de saída

| Arquivo | Conteúdo |
| --- | --- |
| `normalizacao.json` | Cópia das escalas e referências fixas usadas. |
| `configuracoes.json` | Grades, seleção, parâmetros, hashes do código/dados, Python e sementes. |
| `chamadas/*.json` | Receita completa e curva de cada chamada, ou registro explícito de falha. |
| `execucoes.csv` | Uma linha por chamada concluída; status, semente, ciclos, partida, tempo, avaliações e objetivos. |
| `resumo.json` | Completude do lote, viáveis, falhas, não dominadas, extremos e esforço por abordagem. |
| `historico_lote.json` | Tempo de relógio, quantidade de processos e retomadas de cada invocação. |
| `nao_dominadas_soma.json`, `nao_dominadas_epsilon.json` | União filtrada em 3D por abordagem, com receitas e origens. |
| `nao_dominadas_rodadas_*.json` | Conjunto filtrado de cada rodada, para comparar variabilidade. |
| `soma_f1_f2.pdf`, `soma_f1_f3.pdf`, `soma_f2_f3.pdf` | Três projeções da Soma Ponderada. |
| `epsilon_f1_f2.pdf`, `epsilon_f1_f3.pdf`, `epsilon_f2_f3.pdf` | Três projeções do ε-restrito. |

Se executar apenas um método, são produzidas suas três projeções. Receitas
compartilhadas por rodadas aparecem como círculos vazados de cores/tamanhos
diferentes. Os objetivos dos eixos estão nas unidades originais; custo em
milhões de reais. Um ponto pode parecer dominado em 2D e ser não dominado em 3D.
Empates nos objetivos de receitas distintas são preservados para a Entrega 3.

Dominância usa tolerâncias absolutas de `1e-6` R$ e `1e-10` pp², antes de arredondar.
Os conjuntos são aproximações entre soluções encontradas, sem prova da fronteira
exata. Não compare métodos apenas contando pontos: 35 e 45 chamadas têm esforços
diferentes. A soma dos tempos de chamadas paralelas não é o tempo de relógio do lote.

Pilotos ficam separados do lote oficial; consulte o status e os comandos em
`resultados_entrega2/LEIA-ME.md`. Somente um lote completo de cinco rodadas por
abordagem atende ao experimento planejado para a entrega.


### Resultados anteriores à política de construção comum

`resultados_entrega2/piloto_validado/`, `teste_rapido/` e `oficial/` preservam
resultados da implementação anterior, cujo ε-restrito podia partir de uma
referência. Eles permanecem como histórico com os hashes originais.
O lote anterior tem 28 chamadas de Soma Ponderada, todas iniciadas pela
construção; nenhuma chamada oficial ε-restrito foi executada.

O programa rejeita a retomada automática desses manifestos com o código novo.
Para os experimentos da política atual, use `oficial_construcao_comum/`.
Um reaproveitamento das chamadas ponderadas anteriores exige uma migração
verificada e com proveniência registrada; essa migração não foi realizada.
Os resultados de verificações limitadas em `teste_rapido_construcao_comum/`
são históricos de desenvolvimento, não substituem o lote oficial e foram
gerados por um roteiro auxiliar posteriormente removido.
