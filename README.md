# tb-tp

## Entrega 1: otimização mono-objetivo das pilhas

Este repositório contém uma implementação em Python de **GVNS** para o caso de composição de pilhas de minério. O programa resolve três objetivos **separadamente**: custo total (`f1`, em R$), desvio quadrático de SiO₂ (`f2`, em pontos percentuais ao quadrado) e desvio quadrático de Al₂O₃ (`f3`, na mesma unidade). Todas as execuções verificam as mesmas restrições de massa, qualidade, elegibilidade dos minérios e disponibilidades mínima e máxima.

### O problema representado no código

Há **10 pilhas no total**: P1–P5 alimentam o Sinter 1 e P6–P10 alimentam o Sinter 2. As massas do arquivo de exemplo vão de 20 a 38 kt, em passos de 2 kt. Cada caminhão leva **2 kt = 2.000 toneladas** de um único minério. Assim, P1 precisa de 10 caminhões (20 kt) e P10 precisa de 19 caminhões (38 kt); **19 é o número de caminhões da P10, não o número de pilhas**. Cada posição da lista de uma pilha representa um caminhão. A quantidade de posições ocupadas pelo minério `j` na pilha `i` corresponde à variável matemática `x_ij`.

`dados_exemplo.json` transcreve o **anexo de exemplo de formato dos dados** do PDF do caso. Ele não deve ser tratado como uma instância definitiva caso a professora forneça novos dados. O campo FeT está registrado no JSON, mas os objetivos e limites de qualidade implementados nesta entrega usam SiO₂ e Al₂O₃.

### Método

1. A construção distribui primeiro as disponibilidades mínimas obrigatórias e completa as pilhas com minérios elegíveis em ordem de preço.
2. Se a mistura inicial violar os limites, o reparo procura um plano viável. A medida de violação orienta **apenas esse reparo**; não é adicionada a nenhum objetivo.
3. A GVNS perturba a solução e aplica busca local nas vizinhanças: **N1** substitui o minério de um caminhão dentro da pilha; **N2** troca caminhões entre duas pilhas; **N3** escolhe novamente a composição completa de uma pilha, mantendo as outras nove e mudando o minério de pelo menos metade dos seus caminhões.
4. Durante a GVNS, candidatos inviáveis são rejeitados. Uma nova solução corrente só é aceita se melhorar o objetivo que está sendo resolvido.

**Por que N3?** N1 altera um caminhão; N2 troca dois caminhões entre pilhas e mantém inalterado o uso total de cada minério. A N3 fixa nove pilhas e **recalcula as quantidades de minérios da décima**, permitindo mudar vários caminhões e o uso total dos minérios em um único movimento. A nova receita pode conservar alguns minérios antigos, mas deve trocar o minério de **pelo menos metade** dos caminhões daquela pilha. O gerador respeita massa, elegibilidade, disponibilidade e os limites de SiO₂ e Al₂O₃ da pilha reconstruída. Escolhemos esse movimento para explorar misturas mais distantes, com lógica diferente de N1 e N2, como o PDF solicita; a regra de metade dos caminhões é uma decisão nossa, não uma exigência do enunciado. A N3 pode ser mais demorada de examinar, e o limite de tempo pode interromper sua busca.

### Como executar

É necessário **Python 3.10 ou superior**. O código usa somente a biblioteca padrão; não há dependências para instalar com `pip`. No terminal, a partir da raiz do repositório:

```sh
python3 -m unittest -q test_mono_objetivo.py
python3 mono_objetivo.py --segundos 10 --saida minha_execucao_10s
```

O primeiro comando executa os testes. O segundo faz **cinco execuções para cada um dos três objetivos**, com limite de 10 segundos por execução inteira (construção, reparo e GVNS), levando aproximadamente 2,5 minutos no total. Para repetir o ensaio de 30 segundos por execução, use:

```sh
python3 mono_objetivo.py --segundos 30 --saida minha_execucao_30s
```

Esse segundo ensaio leva aproximadamente 7,5 minutos. Os nomes de saída acima preservam as pastas `resultados/` e `resultados_30s/` já versionadas. Sem `--saida`, a saída padrão é `resultados/` e seus arquivos serão substituídos. `--dados outro_arquivo.json` permite usar outra instância no mesmo formato; `--semente-base` altera os sorteios. Use `python3 mono_objetivo.py --help` para ver as opções. O limite de tempo é uma escolha do experimento, não um valor exigido pelo PDF.

### Arquivos e saídas

| Caminho | Conteúdo |
| --- | --- |
| `mono_objetivo.py` | Leitura dos dados, construção, reparo, GVNS, avaliação das restrições e gravação dos resultados. |
| `figuras.py` | Funções importadas pelo programa principal para gerar gráficos SVG; é necessário para executar `mono_objetivo.py`. |
| `test_mono_objetivo.py` | Testes das fórmulas e das regras principais. |
| `dados_exemplo.json` | Dados de entrada do anexo de exemplo. |
| `resultados/` | Ensaio salvo com 10 segundos por execução. |
| `resultados_30s/` | Ensaio salvo com 30 segundos por execução. |

Em cada pasta de saída, `execucoes.csv` tem as **15 execuções** e o campo `violacao` (zero nas soluções viáveis); `resumo.csv` traz mínimo, média, desvio padrão amostral e máximo dos cinco valores por objetivo; `melhores_solucoes.json` guarda o melhor plano de cada objetivo; `convergencia.json` guarda os pontos das curvas; `configuracao.json` registra tempo, semente e hash dos dados. Os arquivos `convergencia_f1.svg` a `convergencia_f3.svg` mostram as cinco curvas por objetivo, e `melhor_f1.svg` a `melhor_f3.svg` mostram as composições dos melhores planos.

O programa gera **SVG**. Os **PDFs** presentes nas duas pastas são versões convertidas dessas figuras para uso em LaTeX; para converter novas figuras, pode-se usar a ferramenta externa opcional `rsvg-convert`. Como a parada depende do relógio, uma repetição em outra máquina pode produzir resultados diferentes mesmo com a mesma semente.
