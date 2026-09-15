# Baseline exploratória local pré-RPA

## Conclusão

Esta execução encontrou o limite seguro do host no degrau `V02`, com 1.700
Workorders e 22.000 seriais. Os cenários `V00`, `V01` e `V02` terminaram sem
rejeição inesperada ou divergência **nas contagens verificadas do pipeline**.
O conteúdo consolidado completo não foi comparado com um oráculo derivado da
massa; ausência de perda/duplicação silenciosa ainda exige essa comparação.
`V02` levou 453,59 s e
ultrapassou a meta preliminar de 300 s, embora tenha permanecido abaixo do teto
de 600 s.

`V03`, `V04` e `V05` não foram executados neste host. O backend atingiu 2,15
GiB de RSS em `V02`; uma projeção linear para os 88.000 seriais de `V05` resulta
em aproximadamente 8,6 GiB somente para o processo da API, acima dos 8,0 GiB de
RAM física disponíveis. Como os processos locais não possuíam limite de cgroup,
prosseguir caracterizaria ruptura fora de um ambiente com isolamento de
recursos.

Os resultados são exploratórios e `non_comparable` para publicação definitiva:
foram produzidos sobre uma worktree ainda não commitada e PostgreSQL 18.3,
enquanto a referência do projeto é PostgreSQL 16. Eles são comparáveis entre si
para localizar o primeiro limite deste ambiente, pois massa, processo e
configuração permaneceram constantes entre os degraus formais.

## Ambiente

| Item | Valor |
| --- | --- |
| Data local | 2026-09-15, America/Manaus |
| Commit base | `61c25fb6a158c1a25f0932b72646e06ca0637c1e` |
| Estado do código | worktree suja; runner e gerador ainda não commitados |
| Host | Linux x86_64, 8.022.978.560 bytes de RAM, swap disponível |
| Backend | um worker Uvicorn, sem limite de cgroup, token sintético de 120 min |
| Banco | PostgreSQL 18.3 temporário, `shared_buffers=128MB`, `max_connections=100` |
| Topologia | gerador, API e banco em loopback no mesmo host |
| Armazenamento | filesystem local; banco e importações descartáveis em `/tmp` |
| Observabilidade | `/proc` para API e host; `pg_stat_database`/`pg_stat_activity` para banco |

O PostgreSQL temporário usou a porta 55432 e recebeu as 23 migrations vigentes.
Foram provisionados exclusivamente usuários e organizações sintéticos. O limite
OWM foi configurado em 50.000.000 bytes porque o JSON de referência possui
40.568.003 bytes; o runner confirmou a política antes de cada upload.

## Massas e método

Todos os bundles utilizaram quatro fontes canônicas, somente a organização
`SYN-ORG-001` e manifestos 1.1 validados. Cada rodada realizou um upload
multifuente, conferiu o resumo do pipeline, aqueceu as consultas e relatórios
uma vez e mediu cinco repetições. Upload possui uma amostra por degrau; portanto
seu valor ainda não constitui um p95 estatisticamente estável.

| Cenário | Workorders | Seriais | Registros de fonte | Seed |
| --- | ---: | ---: | ---: | ---: |
| `V00` | 50 | 500 | 1.100 | 20260831 |
| `V01` | 680 | 8.800 | 18.960 | 20260830 |
| `V02` | 1.700 | 22.000 | 47.400 | 20260830 |

## Resultados consolidados

| Cenário | Upload/processamento | Maior p95 consulta | Maior p95 relatório | Maior p95 exportação | Pico RSS API | Erros |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `V00` | 9,26 s | 150,22 ms | 162,04 ms | 74,83 ms | 109.465.600 B | 0 |
| `V01` | 217,09 s | 130,21 ms | 409,98 ms | 457,92 ms | 863.825.920 B | 0 |
| `V02` | 453,59 s | 196,94 ms | 955,95 ms | 1.047,63 ms | 2.148.466.688 B | 0 |

As consultas, relatórios e exportações permaneceram dentro das metas propostas.
O gargalo observado está no upload/processamento síncrono e no crescimento de
memória da API. Durante cada upload, o único worker não respondeu ao endpoint
de saúde, logo consultas concorrentes não têm capacidade disponível nessa
configuração mesmo antes de esgotar CPU ou conexões do banco.

No banco, `V02` atingiu no máximo três conexões, não registrou deadlocks nem
arquivos temporários e apresentou zero rollbacks durante a rodada. O backend
usou em média 53,79% de um núcleo. Esses sinais não sustentam saturação do
PostgreSQL; apontam para trabalho e retenção de dados no processo da aplicação.

## Consistência

Em cada cenário foram confirmados:

- estado terminal `completed`;
- `rows_read`, válidos e normalizados iguais ao manifesto;
- zero registros rejeitados;
- status HTTP esperados em todas as operações medidas; o conteúdo completo de
  consultas, relatórios e exportações não foi confrontado com um oráculo do
  manifesto nesta rodada;
- zero deadlocks;
- quantidades ausentes mantidas no manifesto como ausentes, sem conversão para
  zero.

Esta rodada ainda não comprova concorrência, recuperação após falha ou
isolamento entre duas organizações; esses cenários pertencem às próximas
etapas.

## Decisão e próximos passos

Classificação: `environment_limit` preventivo, com provável gargalo de memória
da aplicação. A decisão é não executar `V03–V05` neste host sem limite de
recursos. Para concluir a baseline de referência:

1. executar em container/VM com limites explícitos e PostgreSQL 16;
2. perfilar as fases de parsing, normalização, consolidação, regras e geração de
   artefatos para identificar quais estruturas mantêm cópias integrais da massa;
3. corrigir o crescimento comprovado sem remover auditoria, proveniência ou
   transação;
4. repetir `V00–V02` após commit e então avançar progressivamente até `V05`;
5. obter pelo menos cinco amostras independentes de upload antes de promover
   percentis de processamento à baseline oficial.

Os artefatos brutos permanecem em `artifacts/performance/v00-formal-local-pg18`,
`v01-local-pg18` e `v02-local-pg18`, diretório ignorado pelo Git.
