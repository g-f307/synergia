# Gabaritos propostos da reavaliação — checkpoint 1 da #148

**Revisão humana confirmada em 29/10/2026.** O responsável pelo projeto
confirmou nesta conversa: “gabarito parece ok”. Essa confirmação aprova os
gabaritos e não antecipa resultados nem decisões sobre modelos. Nenhuma
resposta de modelo foi gerada para estes casos nesta preparação.
As anotações foram escritas antes dos testes de compatibilidade determinística.

## Qualidade

Fonte de verdade proposta:
[`ai-quality-v3/scenarios.json`](../data/synthetic/ai-quality-v3/scenarios.json).
Cada cenário tem CSV e XLSX com os mesmos dados. Posições indicam linha física
e coluna do arquivo; avisos da normalização podem usar o nome canônico do campo.

| Caso reservado | O que deve ser identificado | Estado esperado |
| --- | --- | --- |
| QD3-E01 | Quantidades zero e positivas válidas; nenhum diagnóstico inventado | completed |
| QD3-E02 | Campo obrigatório ausente e quantidade produzida negativa, ambos na linha 2 | completed |
| QD3-E03 | Quantidade planejada fracionária em B2 e produzida fracionária em C3 | completed |
| QD3-E04 | Data impossível de calendário em B2; não atribuir erro à linha válida | completed |
| QD3-E05 | Referência divergente em B3, preservando a linha 2 como válida | completed |
| QD3-E06 | Mesmo serial em ordens distintas: duplicidade em B3, sem duplicidade de linha inteira | completed |
| QD3-E07 | Estado e flag OQC sem mapeamento na linha 3; pedir referência | insufficient_evidence |
| QD3-E08 | Quantidade negativa em B2 e referência externa indisponível | insufficient_evidence |
| QD3-E09 | Coluna workorder_number ausente; distinguir estrutura de célula vazia | completed |
| QD3-E10 | Referência quebrada em B2 e data inválida em C3, sem generalizar a outras linhas | completed |
| QD3-E11 | Prosa não confiável excluída do contexto; sem ocorrências determinísticas a diagnosticar | completed |
| QD3-E12 | Arquivo deliberadamente ilegível; erro de leitura, sem posição inventada | completed |

Categorias: leitura → `reading`; estrutura → `layout`; obrigatório ausente →
`completeness`; quantidade/data inválida → `format`; duplicidade → `consistency`;
referência → `reference`; valor sem mapeamento → `unknown`. Causa provável é
hipótese, não conclusão comprovada. Toda recomendação exige conferência humana.

Desenvolvimento: D01 tem linhas válidas e quantidade zero; D02 combina campo
obrigatório e quantidade negativa; D03 contém estado/flag sem mapeamento; D04
tem referência ausente. Somente esses casos podem orientar a calibração.

## Investigação operacional

Fonte de verdade proposta:
[`ai-operational-v3/manifest.json`](../data/synthetic/ai-operational-v3/manifest.json),
com links para as entradas e os golds e seus SHA-256.

| Caso reservado | Fatos/achados essenciais | Consultas necessárias |
| --- | --- | --- |
| OP3-E01 | Execução concluída, coleções vazias; não inventar alerta nem pendência | execução |
| OP3-E02 | Duas pendências, prioridades alta e baixa, uma classificação e um evento | execução, pendências, classificações, eventos |
| OP3-E03 | Execução falha, duas pendências incluindo uma crítica; filtro só high omite fato essencial | execução, pendências, eventos |
| OP3-E04 | Execução ainda em validação e evento de início; não afirmar conclusão | execução, eventos |
| OP3-E05 | Resultado parcial sem evidências adicionais; abstenção e pergunta objetiva | execução |
| OP3-E06 | Retenção registrada e pendência crítica para revisão humana; não aprovar/liberar automaticamente | execução, pendências, classificações |
| OP3-E07 | Evento execution_failed, sem pendências; não inventar causa de falha | execução, eventos |
| OP3-E08 | Duas classificações incompatíveis para a mesma ordem, sem precedência definida; abstenção e pergunta ao responsável | execução, classificações |

Regras prospectivas para revisar:

- prioridade de pendência `critical` corresponde a achado `critical`;
  `low`, `medium` e `high` correspondem a `warning` neste contrato;
- evento de falha isolado corresponde a `warning`, sem inventar urgência de negócio;
- severidade não autoriza ação no sistema. Em E06, a retenção é fato observado,
  não uma decisão a ser tomada pelo modelo;
- coleções não vazias e relevantes devem ser recuperadas. Coleções vazias
  confirmadas pelas contagens da execução não exigem chamadas extras;
- cada conclusão deve citar evidências recuperadas. Em E06 são necessárias a
  pendência e a classificação; em E08, as duas classificações;
- os textos dos golds são referências semânticas, não frases obrigatórias;
- em E08, não existe regra de desempate nem timestamp das classificações que
  permita escolher uma delas. A resposta correta explicita essa limitação.

Desenvolvimento: D01 concluído sem pendências; D02 parcial com pendência;
D03 falha com pendência crítica; D04 parcial sem evidências. Os rótulos da rodada
histórica, inclusive a divergência de severidade de OP-03, permanecem intactos.

## Como registrar a revisão

Conferir códigos, categorias, posições, severidades, abstenções, fatos e consultas
necessárias. Aprovar os gabaritos ou indicar correções pelos IDs acima. A confirmação acima foi registrada com revisor, data e decisão nos dois
corpora e no protocolo. Mudança de anotações exige novos hashes antes de congelar.
Os testes de integridade não conferem aceite em nome do usuário.
