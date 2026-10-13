# Plano da Entrega 2 — otimização multiobjetivo

## Em uma frase

Usar a nossa GVNS para procurar diferentes compromissos entre custo, sílica e alumina, por **Soma Ponderada** e **ε-restrito**, e comparar os conjuntos de soluções não dominadas encontrados.

O modelo físico continua sendo o das dez pilhas. O que muda é o critério de otimização e, no ε-restrito, a inclusão de dois limites adicionais.

## 1. O que o PDF exige

Fonte: `Case-UFMG-Teoria_da_Decisão (2).pdf`, seção “Entrega #2”, páginas 4–5.

| Exigência | Como atender |
|---|---|
| Formular Soma Ponderada e ε-restrito para os três objetivos | Apresentar as duas formulações com as restrições físicas originais. |
| Normalizar antes dos pesos ou ε | Usar referências da otimização isolada da Entrega 1, explicando o cálculo. |
| Usar o algoritmo da primeira entrega | Adaptar a GVNS atual para comparar um critério escalar e verificar as restrições ativas. |
| Cinco execuções por abordagem | Fazer cinco rodadas de exploração das configurações escolhidas, com sementes registradas. |
| Reunir soluções não dominadas das cinco execuções | Filtrar o conjunto de soluções finais de cada abordagem nos três objetivos. |
| Projeções f1×f2, f1×f3 e f2×f3, separadas por abordagem | Produzir seis gráficos, identificando as rodadas por cores ou símbolos. |
| Discutir variabilidade e regiões alcançadas | Comparar cobertura observada, compromissos e diferenças entre as rodadas. |
| Códigos e relatório cumulativo | Atualizar o código e o relatório da Entrega 1 e acrescentar a parte multiobjetivo. |

**Não haverá apresentação oral na Entrega 2.** O relatório deve ser uma evolução do anterior, não um relatório separado. Pesos, grade de ε, normalização e organização das configurações precisam ser definidos e justificados pelo grupo; o PDF não fornece seus valores.

## 2. Ordem de trabalho

1. **Lote mono-objetivo sem teto de N3 concluído e conferido.** Ele fornece a referência atualizada: 15 execuções, 50 ciclos, todas viáveis.
2. Construir e congelar a normalização.
3. Adaptar o critério escalar e a viabilidade na GVNS.
4. Implementar Soma Ponderada e ε-restrito.
5. Fazer um piloto pequeno para verificar correção e medir esforço.
6. Fixar as configurações e fazer as cinco rodadas de cada abordagem.
7. Filtrar as soluções não dominadas, gerar os seis gráficos e ampliar o relatório.

O lote levou 47min39s com três processos em paralelo. A duração média de uma execução foi 20min51s para custo, 1min52s para sílica e 2min02s para alumina. A etapa mono-objetivo está concluída; podemos iniciar a normalização e a implementação multiobjetivo. Os números abaixo foram obtidos desse lote, não dos resultados antigos com teto.

## 3. Base atual a incorporar

- Representação: uma lista de minérios por pilha; cada posição é um caminhão de 2 kt.
- N1: substituição de um minério; N2: troca entre pilhas; N3: reconstrução de uma pilha, com pelo menos metade dos caminhões alterados.
- GVNS com VND de primeira melhora; 50 ciclos globais por execução como configuração inicial.
- **N3 sem teto de candidatos, nós ou tempo.** Primeira melhora e esgotamento são regras da busca, não uma trava de amostragem.
- Reparo com até 100 ciclos; falha explícita se não encontrar solução viável, sem prova de inviabilidade.
- Objetivos calculados por `evaluate`: f1 em reais; f2 e f3 em pp². Mantemos essas fórmulas.

O texto da Entrega 1 precisa refletir a retirada do teto e os resultados atualizados. As tabelas antigas de 2.000 candidatos devem ser identificadas como comparação histórica, e não como execução da versão atual.

## 4. Normalização: uma régua fixa para os três objetivos

### Passo 1 — três soluções de referência

Do lote atualizado, selecionar a melhor das cinco execuções de cada objetivo. Chamá-las de x^(1), x^(2) e x^(3). Avaliar os **três objetivos em cada uma**:

| Solução de referência | f1 (R$) | f2 (pp²) | f3 (pp²) |
|---|---:|---:|---:|
| Melhor custo: execução 5, semente 2031 | 59.860.000 | 6,67309640 | 6,26000512 |
| Melhor sílica: execução 3, semente 12029 | 63.440.000 | 2,37273078 | 3,94656760 |
| Melhor alumina: execução 3, semente 22029 | 65.820.000 | 6,29168750 | 1,41997141 |

Os valores exibidos foram arredondados apenas para leitura. Os valores completos e as referências propostas estão em `analise_limites_20261013/lote_completo_sem_teto/referencias_propostas_entrega2.json`, na pasta de trabalho. Antes dos experimentos multiobjetivo, a implementação deverá salvar essas referências no `normalizacao.json` do projeto.

Essa é a matriz de resultados cruzados, ou *payoff table*. Não devemos usar apenas a pequena variação entre as cinco soluções que otimizam o mesmo objetivo como escala.

### Passo 2 — fórmula proposta pelo grupo

Para cada objetivo q∈{1,2,3}, usar o menor e o maior valor de sua coluna nessa matriz. Reservamos j para identificar minérios na formulação original.

\[
a_q=\min_{r=1,2,3} f_q(x^{(r)}),\qquad
b_q=\max_{r=1,2,3} f_q(x^{(r)}),\qquad
\bar f_q(x)=\frac{f_q(x)-a_q}{b_q-a_q}.
\]

Interpretar 0 como o menor valor de referência e 1 como o maior. São **referências empíricas**, não provas de ideal ou nadir exatos. Uma nova solução pode sair do intervalo [0,1]; não devemos cortá-la artificialmente para caber nele.

Salvar `normalizacao.json` com a matriz, a e b, origem das soluções, configuração e hash dos dados. Usar **a mesma normalização para os dois métodos, todas as configurações e todas as rodadas**. Não recalcular durante a busca. Se b=a, interromper a calibração e obter referências adicionais, em vez de dividir por zero ou ignorar o objetivo silenciosamente.

## 5. Soma Ponderada

Se X é o conjunto de planos que atendem às restrições originais:

\[
\min_{x\in X} g_w(x)=w_1\bar f_1(x)+w_2\bar f_2(x)+w_3\bar f_3(x),
\quad w_q\ge0,\quad \sum_qw_q=1.
\]

Aqui os pesos expressam prioridades entre objetivos normalizados. Não são penalidades por violação. A GVNS aceita melhorias em g_w, preservando a viabilidade física.

**Proposta inicial de sete configurações**, a validar no piloto:

| Configuração | Pesos (custo, sílica, alumina) | Intenção |
|---|---|---|
| Equilibrada | (1/3, 1/3, 1/3) | Considerar os três igualmente na escala normalizada. |
| Ênfase no custo | (0,6; 0,2; 0,2) | Favorecer economia. |
| Ênfase na sílica | (0,2; 0,6; 0,2) | Favorecer o alvo de sílica. |
| Ênfase na alumina | (0,2; 0,2; 0,6) | Favorecer o alvo de alumina. |
| Custo e sílica | (0,5; 0,5; 0) | Explorar esse compromisso. |
| Custo e alumina | (0,5; 0; 0,5) | Explorar esse compromisso. |
| Sílica e alumina | (0; 0,5; 0,5) | Explorar o compromisso químico. |

Peso zero não elimina as restrições físicas daquele indicador. Como os objetivos podem empatar e usamos uma heurística, filtraremos dominância depois, sem presumir que todo resultado escalar seja Pareto-ótimo.

## 6. ε-restrito

**Proposta:** otimizar custo, limitando os dois desvios químicos normalizados:

\[
\min_{x\in X}\bar f_1(x),\qquad
\bar f_2(x)\le\varepsilon_2,\qquad
\bar f_3(x)\le\varepsilon_3.
\]

“Encontrar o menor custo observado mantendo os desvios globais dentro dos níveis escolhidos.” Os ε limitam a **soma de desvios quadráticos**, não substituem os limites químicos de cada pilha. Ambos os tipos de restrição devem ser respeitados.

**Grade inicial proposta:** ε2 e ε3 em {0,25; 0,50; 1,00}, formando nove pares. O valor 0,25 significa a+0,25(b−a) na escala original, não 0,25% de teor. Essa grade é uma escolha de exploração do grupo, não um requisito do PDF nem garantia de cobertura completa.

### A adaptação mais importante do código

Hoje `Evaluation.feasible` considera apenas as restrições físicas. Isso não basta para ε-restrito. Precisaremos verificar conjuntamente:

```text
viável no problema escalar =
    viável fisicamente
    E desvio normalizado de sílica <= ε2
    E desvio normalizado de alumina <= ε3
```

Essa regra entra no reparo, na perturbação, na VND e no registro da melhor solução. N3 preserva as restrições físicas quando parte de um plano físico viável, mas **não garante automaticamente os ε**.

Se a construção violar ε, o reparo deve tratar também essas violações. Uma medida proposta, apenas para reparo, é:

\[
V_\varepsilon(x)=V_{\mathrm{fis}}(x)
+\max(0,\bar f_2(x)-\varepsilon_2)
+\max(0,\bar f_3(x)-\varepsilon_3).
\]

Não somar Vε ao custo otimizado. Antes de reparar, podemos procurar um plano já conhecido que satisfaça aquele par de ε, documentando uma regra fixa de seleção da partida. Se não existir no banco, isso não prova impossibilidade: tentar o reparo. Se o reparo falhar em 100 ciclos, registrar **configuração sem solução encontrada**, tempo e semente; não exportar uma solução que viole ε como resultado válido.

## 7. O que significa “cinco execuções” nesta proposta

Definir uma **rodada** como explorar todas as configurações de uma abordagem, com sementes registradas. Repetir a rodada cinco vezes. Essa organização é uma decisão operacional nossa para cumprir as cinco execuções por abordagem e produzir um conjunto de compromissos; deve ser explicada no relatório.

Com as grades propostas:

- Soma Ponderada: 5 rodadas × 7 configurações = **35 chamadas à GVNS**.
- ε-restrito: 5 rodadas × 9 configurações = **45 chamadas à GVNS**.
- Total inicial: **80 otimizações escalares**, além das referências mono-objetivo.

Não são apenas dez chamadas à GVNS se queremos variar pesos e ε. Registrar uma semente por (abordagem, rodada, configuração), sem escolhê-la pelos resultados. Cada chamada reinicia a busca; não proibir planos repetidos. Congelar os parâmetros antes da rodada oficial.

### Piloto antes das 80 chamadas

1. Testar manualmente normalização, g_w, limites de ε e dominância numa instância pequena.
2. Executar, com uma semente e poucos ciclos, a configuração equilibrada e um par ε permissivo; testar também um par apertado para observar reparo/falha.
3. Medir a duração e o número de soluções distintas obtidas. Só então fechar a grade oficial e usar 50 ciclos nas duas abordagens.
4. Manter cinco rodadas por abordagem. Se a grade mudar após o piloto, documentar os motivos e recalcular o número total de chamadas.

N3 está sem teto por decisão atual do grupo. Portanto, não estimar o tempo das 80 chamadas multiplicando cegamente um único teste de custo: as restrições de ε e a combinação de objetivos mudam a busca.

Como a proposta usa sete configurações de pesos e nove pares de ε, a quantidade de pontos encontrada não deve ser interpretada isoladamente como superioridade de um método. Comparar também o número de chamadas, falhas, avaliações e tempo, explicitando essa diferença de esforço experimental. Usar o mesmo número de ciclos por chamada não torna o esforço computacional idêntico.

## 8. Soluções não dominadas e gráficos

Guardar a solução final de **cada configuração em cada rodada**, com sua receita completa. Para o conjunto de cada abordagem, A domina B quando A não é pior em nenhum dos três objetivos e é estritamente melhor em pelo menos um.

Exemplo didático: A=(60,3,2) domina B=(61,4,2). C=(59,4,2) oferece menor custo e maior desvio de sílica que A; nenhuma das duas domina a outra.

- Comparar usando os três valores completos, antes de arredondar para as tabelas.
- Eliminar repetições da **mesma composição** e preservar suas origens. A ordem dos caminhões na pilha não distingue receitas.
- Receitas diferentes com os mesmos três objetivos podem ser úteis na Entrega 3; não eliminá-las só por coincidência dos objetivos.
- Filtrar a união das cinco rodadas separadamente em cada abordagem. Para análise de variabilidade, guardar também o conjunto não dominado de cada rodada.
- A filtragem é nos **três objetivos**. Um ponto pode parecer dominado numa projeção 2D e continuar não dominado em 3D; não refiltrar cada desenho em duas dimensões.
- Usar Matplotlib para seis PDFs: três projeções de Soma Ponderada e três de ε-restrito. Cores indicam rodadas 1–5; eixos podem mostrar custo em R$ milhões e desvios em pp².

Esses são conjuntos **não dominados entre as soluções encontradas**, não uma fronteira exata de todo o problema. A Soma Ponderada pode deixar de alcançar partes não suportadas de uma fronteira não convexa; ε-restrito é uma exploração complementar, não uma promessa de superioridade com GVNS.

## 9. Mudanças de código e arquivos

| Arquivo/área | Trabalho |
|---|---|
| `mono_objetivo.py` | Reutilizar construção, avaliação, movimentos, perturbação e VND. Parametrizar o critério comparado, a viabilidade ativa e a medida de reparo, preservando a execução mono-objetivo. |
| `multiobjetivo.py` (novo) | Normalização, configurações, cinco rodadas, coleta de planos, dominância e exportação. |
| `figuras.py` | Acrescentar gráficos de projeções, mantendo Matplotlib e PDF. |
| Testes | Normalização/zero de escala; soma ponderada; rejeição de violação de ε; reparo com ε; dominância e duplicatas; regressão da etapa mono-objetivo. |
| `README.md` | Instruções das duas etapas, parâmetros, comandos e descrição dos arquivos. |
| `entrega-1.tex` | Evoluir para relatório cumulativo: atualizar a etapa 1 e adicionar formulações, experimentos e análise multiobjetivo. |

Evitar duas cópias da GVNS: a diferença entre os problemas deve ficar no critério e nas restrições adicionais, não numa repetição do algoritmo inteiro.

Resultados propostos: `normalizacao.json`, `configuracoes.json`, CSV de cada chamada com status/tempo/semente/objetivos, JSON dos planos, conjuntos não dominados por abordagem/rodada e seis gráficos PDF. Falhas e empates precisam permanecer auditáveis.

## 10. Divisão sugerida para seis pessoas

1. Formulação e normalização; conferir matriz de referências.
2. Soma Ponderada e adaptação do critério escalar da GVNS.
3. ε-restrito, viabilidade adicional e reparo.
4. Experimentos, sementes, tempos e reprodução.
5. Dominância, tabelas e gráficos.
6. Relatório cumulativo, README e revisão cruzada código–texto.

As pessoas 2 e 3 precisam combinar a interface da GVNS antes de editar o mesmo trecho. A pessoa 6 revisa principalmente se o relatório descreve exatamente os parâmetros e a política de falha usados.

## 11. Checklist da entrega

- [ ] Etapa 1 atualizada, incluindo a retirada do teto e os feedbacks do reparo.
- [ ] Preencher as subseções de representação computacional que ainda estão vazias no LaTeX: vetor da pilha, plano completo, relação com xij e verificação de viabilidade.
- [ ] Duas formulações escalares com as três funções e restrições originais.
- [ ] Normalização fixa, reproduzível e baseada na etapa 1.
- [ ] Pesos e ε definidos, justificados e registrados.
- [ ] Cinco rodadas de cada abordagem, com configuração e semente identificáveis.
- [ ] Nenhum resultado ε-restrito apresentado como válido se violar seus ε.
- [ ] Soluções finais não dominadas filtradas em 3D, separadamente por abordagem.
- [ ] Seis projeções com identificação das rodadas e análise dos compromissos.
- [ ] Código, dependências, dados e instruções que reproduzem os resultados.
- [ ] Relatório único cumulativo; a Entrega 2 não exige apresentação oral.

## Referências de apoio

- Enunciado fornecido pelo grupo: `Case-UFMG-Teoria_da_Decisão (2).pdf`, páginas 4–5. É a fonte dos requisitos; as grades e decisões de implementação acima são propostas nossas.
- [Implementação e descrição de ε-restrito no GAMS](https://www.gams.com/latest/gamslib_ml/libhtml/gamslib_epscm.html): uso de um objetivo e restrições nos demais, e matriz de resultados cruzados. O exemplo usa uma versão aumentada; nosso plano propõe inicialmente o ε-restrito convencional com filtragem posterior, sem presumir garantias de um solucionador exato.
- [Blank e Deb, Pymoo: Multi-Objective Optimization in Python](https://www.julianblank.com/_static/research/ieee20-pymoo.pdf): discussão da decomposição e da limitação da Soma Ponderada em partes não convexas da fronteira. A referência conceitual não implica trocar a GVNS por outra biblioteca.


## Desenvolvimento em 13/10/2026

- Estado anterior registrado no commit `a0b7d93`, antes da implementação.
- Normalização fixa salva e conferida com reavaliação das três receitas.
- Uma única GVNS utilizada pelas interfaces mono e multiobjetivo.
- ε incluído no reparo, perturbação, VND e registro da melhor solução.
- Dominância em 3D, receitas e origens preservadas, seis projeções Matplotlib PDF.
- Retomada por chamada com configuração e hashes, sem misturar experimentos.
- Piloto da grade: 16 chamadas, uma rodada, dois ciclos, todas admissíveis.
  A grade de sete pesos e nove pares ε foi mantida.
- Os 18 testes passaram; regressão contra a base anterior conferiu receitas,
  objetivos, avaliações, sementes e curvas nos três objetivos com um ciclo.
- As quatro subseções de representação do relatório foram preenchidas e a
  formulação multiobjetivo foi incorporada ao mesmo LaTeX.
- Lote oficial: 80 chamadas, cinco rodadas, 50 ciclos, três processos.
  O status auditável fica em `resultados_entrega2/oficial/resumo.json`; não
  confundir resultados parciais ou do piloto com lote completo.

- Após o crash, quatro chamadas oficiais completas foram preservadas. O lote
  foi retomado com dois processos e ambiente local `.venv`, mantendo Python
  3.14.7 e Matplotlib 3.11.2.
- A pedido do grupo, `teste_rapido.py` limita N3 a cinco visitas de até 25
  candidatos completos por visita; esses resultados são rotulados como teste,
  não como experimentos oficiais. Os smoke tests automatizados reais também
  usam essas travas; produção e lote oficial continuam sem teto.
