# Experimentos da Entrega 2

## Piloto validado

`piloto_validado/`: uma rodada, duas iterações globais, sete pesos e nove pares
ε, três processos. As 16 chamadas encontraram soluções admissíveis. As grades
foram mantidas após o piloto. Esse ensaio valida implementação e configurações;
não substitui as cinco rodadas oficiais.

Comando:

```sh
python3 multiobjetivo.py --rodadas 1 --iteracoes 2 --processos 3 --saida resultados_entrega2/piloto_validado
```

## Lote oficial

`oficial/`: cinco rodadas por abordagem, 50 ciclos globais por chamada,
35 chamadas da Soma Ponderada e 45 do ε-restrito. N3 sem teto.

Comando:

```sh
python3 multiobjetivo.py --rodadas 5 --iteracoes 50 --processos 3 --saida resultados_entrega2/oficial
```

A pasta guarda uma receita/registro de falha por chamada, configuração completa,
normalização e hashes. Repetir o comando retoma chamadas pendentes. Consulte
`resumo.json`: `completo: true` significa que todas as chamadas previstas foram
concluídas; falhas de reparo ficam contadas separadamente.

`historico_lote.json` registra tempo de relógio de cada invocação e número de
processos. `segundos` em cada chamada mede o reparo e a GVNS. Somar tempos de
chamadas paralelas não fornece o tempo de relógio do lote.

As soluções não dominadas são filtradas em três objetivos, separadamente por
abordagem; as seis projeções são feitas com Matplotlib em PDF. A quantidade de
pontos, por si só, não permite comparar a qualidade dos métodos com esforços
experimentais distintos.

### Retomada após interrupção

O computador foi interrompido após quatro chamadas completas. Elas foram
preservadas. A retomada usa dois processos para reduzir a carga simultânea,
mantendo sementes, código e parâmetros de busca. O tempo de relógio anterior
não foi salvo; não deve ser inventado a partir da soma dos tempos das chamadas.

```sh
python3 multiobjetivo.py --rodadas 5 --iteracoes 50 --processos 2 --saida resultados_entrega2/oficial
```
