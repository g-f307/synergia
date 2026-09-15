# Concorrência e idempotência exploratórias pré-RPA

## Conclusão e comparabilidade

Foram exercitados os cenários `C01` a `C08` com dados exclusivamente sintéticos.
As ondas pequenas de escrita concluíram sem erro inesperado e os oráculos de
duplicidade, reprocessamento, leitura consistente, relatórios e isolamento
organizacional foram atendidos. `C05` também completou cinco ciclos em níveis
de dois e quatro leitores sem erro e com conteúdo de negócio estável.

Esta execução é **exploratória** (`non_comparable`): worktree suja, PostgreSQL
18.3 em vez do alvo PostgreSQL 16, apenas um worker Uvicorn, API e PostgreSQL
sem limite de recursos por container e massa de 50 Workorders/500 seriais.
Não substitui a medição obrigatória com 6.800 linhas de plano e 88.000
seriais, nem representa capacidade corporativa.

## Ambiente, massa e método

Execuções em 15/09/2026 no host Linux 7.1.5 (Fedora 44), Python 3.14.7,
12 CPUs lógicas, 8.022.978.560 bytes de RAM, PostgreSQL 18.3 local com
`max_connections=100` e `shared_buffers=128MB`, banco temporário na porta
55432, API FastAPI em `127.0.0.1:58000` com um worker e storage temporário
local. Gerador, API e banco estavam no mesmo host; não havia container ou
limite de CPU/RAM por serviço. O commit informado nos artefatos é
`61c25fb6a158c1a25f0932b72646e06ca0637c1e`, mas o worktree continha
alterações não commitadas.

A massa-base foi `v00-formal-org001-valid` (seed 20260831, perfil `small`,
50 Workorders, 50 lotes, 500 seriais, 1.100 registros nas quatro fontes,
organização `SYN-ORG-001`, digest lógico
`594ea4caa2853e2f9e7fe378a19e962042a2e89af0e6cd8042e18f8849b7c567`).
As ondas de escrita usaram massas novas do mesmo tamanho, com seeds 20261005,
20261006, 20261007 e 20261008; digests, hashes e tamanhos exatos constam dos
manifestos e de `workload.json`. O ator de controle era um gestor da organização
001; o ator de isolamento pertencia somente à organização 002. Nenhum token
foi persistido nos artefatos.

As ondas começam com barreira de clientes. `waves.csv` registra duração de
parede e throughput agregado; `samples.csv` registra latências individuais
para calcular p50/p95/p99 e erro, `resources.csv` registra sistema e banco.
As consultas voláteis descartam **apenas** `generated_at` de nível superior
do digest funcional: quantidades ausentes continuam `null` e zero permanece
distinto de ausência.

## Resultados observados

| Cenário e evidência | Clientes/ciclos | Duração por onda | Resultado funcional |
| --- | --- | --- | --- |
| `C01` — `c01-c02-c07-small-local-pg18-repeat` | 2/1 | 25,43 s | duas execuções concluídas distintas |
| `C02` — mesma execução | 2/1 | 16,03 s | um `201`, um `409 duplicate_file`, vínculo com a vencedora |
| `C07` — um escritor e dois leitores | 3/1 | 15,31 s | 17 requisições, snapshot anterior/posterior coerente |
| `C03` — `c03-c08-smoke-local-pg18` | 2/1 | 74,52 ms | uma tentativa, uma resposta replay |
| `C04` — chaves distintas | 2/1 | 89,10 ms | duas tentativas distintas |
| `C05` — `c05-local-pg18-five-cycles` | 2 e 4/5 por nível | 473–502 ms (2); 685–721 ms (4) | 240 respostas `200`, 81/81 verificações, zero erro |
| `C06` — `c06-export-integrity-smoke-local-pg18` | 2/1 | 187,96 ms | duas versões `succeeded`; CSV 50 linhas e JSON iguais aos snapshots, 12/12 verificações |
| `C08` — `c03-c08-smoke-local-pg18` | 2/1 | 372,17 ms | seis detalhes `200` no controle e seis `404` no ator de outra organização |

No `C05`, throughput de parede variou de 31,86 a 33,89 req/s para dois
leitores e de 44,38 a 46,72 req/s para quatro. A tabela de percentis por
rota, taxa de erro, CPU/memória, conexões, espera, cache, temporários e
deadlocks está em `summary.json` de cada execução. Nos dados de escrita,
observou-se memória disponível mínima do sistema de aproximadamente 1,94 GB,
até duas conexões PostgreSQL e nenhuma transação revertida, arquivo temporário
ou deadlock durante a coleta. O host já usava swap antes de novos degraus;
isso impede interpretá-lo como ambiente isolado para saturação ou ruptura.

## Limitações e decisão

A primeira fumaça `c03-c08-smoke-local-pg18` registrou 14/17 verificações:
três falsos positivos de comparação byte a byte causados pelo campo
`generated_at` de busca, pendências e indicadores. Após limitar a exclusão a
esse único campo volátil, `C05` foi repetido por cinco ciclos, com 81/81
verificações. A primeira execução de uploads
`c01-c02-c07-small-local-pg18` terminou sem erro HTTP, mas não publicou
`correctness.json`: o oráculo `C02` usava um `set` não serializável. Depois de
correção e novo conjunto de seeds, a repetição publicou todos os artefatos,
16/16 verificações e zero erro. As execuções de diagnóstico não são usadas
como evidência de aprovação.

Os níveis maiores (4/8 uploads, 8–32 leitores, cinco ciclos completos de
escrita e concorrência na massa de referência) **não foram executados**:
o host não oferece isolamento de CPU/RAM, já apresentou crescimento de memória
da API na baseline de volume e utilizava swap. Isso é um limite de segurança
do ambiente de teste, não prova saturação do PostgreSQL nem certifica a API
para o volume de referência. O runner agora verifica memória e, se
configurado, swap antes de cada ciclo; interrompe aumento da carga após falha
funcional e retorna `2` quando um nível fica incompleto.

Para fechar o critério de aceite, executar `C01`–`C08` no PostgreSQL 16 e em
ambiente descartável com limites registrados, massa de referência após corrigir
o gargalo de memória/processamento síncrono e monitoramento completo. Preservar
os manifestos, `environment.json`, `workload.json`, `summary.json`,
`correctness.json`, `samples.csv`, `waves.csv`, `resources.csv` e `report.md`
de cada execução como artefatos do PR.
