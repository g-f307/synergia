# Relatório da baseline sintética das PoCs de IA

Execução realizada em **05/10/2026** com
`scripts/ai_poc_evaluation.py`, schemas `1.1.0` e conjunto sintético congelado
`1.0.0`.

## Resultado

| Caso | PoC | Schema | Referências | Precisão | Cobertura | F1 |
|---|---|---:|---:|---:|---:|---:|
| QD-01 | qualidade | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| QD-02 | qualidade | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| QD-03 | qualidade | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| QD-04 | qualidade | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| OP-01 | operacional | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| OP-02 | operacional | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| OP-03 | operacional | válido | válidas | 1,0000 | 1,0000 | 1,0000 |
| OP-04 | operacional | válido | válidas | 1,0000 | 1,0000 | 1,0000 |

O manifesto SHA-256 foi validado sem divergências. Os casos QD-04 e OP-04
resultaram em `insufficient_evidence`, conforme o gabarito.

## Interpretação

Este resultado comprova somente que a baseline determinística, os contratos,
as referências e o cálculo de métricas são reproduzíveis sobre os fixtures
sintéticos congelados. A igualdade com o gabarito é esperada para este teste de
integridade e **não constitui avaliação de modelo de IA nem resultado do
produto**. Modelo, prompt, latência, memória, repetibilidade de geração e ganho
sobre a baseline ainda precisam ser medidos em uma issue posterior.
