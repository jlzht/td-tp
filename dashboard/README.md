# Arquivos consumidos

- `dados/dados_exemplo.json`: minérios, pilhas, Sinters e limites de qualidade;
- `resultados/entrega_3/uniao_nao_dominadas.json`: alternativas, objetivos e receitas (quando exportadas junto às alternativas);
- Outros JSONs de receitas/composições de `resultados/entrega_3` ou `resultados/entrega_2`: consultados quando a união contém apenas os critérios;
- `resultados/entrega_3/tabela_alternativas.csv`: matriz dos quatro critérios, quando disponível;
- `resultados/entrega_3/decisao.json`: seleção do ELECTRE I e ranking AHP.

A aplicação valida os registros carregados. A composição das pilhas é recuperada por identificador ou por correspondência **única dos quatro critérios recalculados** com os resultados da otimização.
