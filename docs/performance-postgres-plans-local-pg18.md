# Planos PostgreSQL exploratórios das consultas pré-RPA

## Resultado e decisão

**Estado da etapa 7 em 15/09/2026:** investigação e correção **locais**
concluídas; validação de referência ainda pendente. Decisão formal: manter a
migration `0024` no ramo de preparação **somente como correção candidata**,
pois o defeito de scan global é comprovado e a regressão local passou, mas
não declarar ganho fim a fim nem aprovação de capacidade antes de PG16/`V05`.
O custo adicional de índice, WAL e INSERT direto foi medido e aceito apenas
para essa investigação. O efeito em upload completo permanece desconhecido.
Não foram adicionados outros índices sem plano que justificasse a mudança.

Em 15/09/2026 foram coletados 15 grupos de `EXPLAIN (ANALYZE, BUFFERS,
WAL, SETTINGS, FORMAT JSON)` sobre a execução sintética `V02`, antes e depois
de um índice. Cada grupo teve uma execução de aquecimento e cinco medidas.
Os 11 grupos iniciais mostraram buscas exatas e relatórios sem gargalo crítico
de índice. A inclusão das consultas componentes do **consolidado**, a consulta
HTTP mais lenta de V02, identificou o defeito: a leitura de avaliações de
regras por Workorder varria paralelamente a tabela inteira de 853.842 linhas
(203 MB) para retornar 309 linhas. O p95 SQL era 115,182 ms.

Foi criada a migration `0024_index_rule_evaluations_workorder.sql` com índice
`(workorder_id, execution_id, id)`. No mesmo banco, massa, parâmetros e série
de cinco medidas aquecidas, o plano passou a usar esse índice e o p95 SQL caiu
para **0,579 ms**. O índice ocupa 63 MB. Não houve mudança de consulta,
autorização, auditoria, proveniência ou integridade. Os demais índices não
foram alterados por falta de evidência de problema. Uma sonda de escrita local
e a leitura completa do repositório foram medidas depois, mas o ganho HTTP e
o custo de escrita do **upload** ainda precisam ser medidos no ambiente de
referência;
portanto, esta correção não resolve o gargalo de memória/processamento síncrono
da API nem autoriza promover a baseline final.

Isto é `non_comparable` como baseline final: PostgreSQL 18.3 em vez de 16,
worktree suja, banco com outras massas sintéticas e apenas `V02` (1.700
Workorders/22.000 seriais), não `V05` (6.800/88.000). A etapa de análise
local é reproduzível, mas planos da massa de referência no ambiente corporativo
permanecem exigidos antes da decisão definitiva de release candidate.

## Ambiente, massa e método

Host Fedora 44/Linux 7.1.5, Python 3.14.7, 12 CPUs lógicas,
8.022.978.560 bytes de RAM; PostgreSQL 18.3 local na porta 55432,
`shared_buffers=128MB`, `max_connections=100`, sem limites de CPU/RAM por
serviço. A evidência incorpora a descrição do ambiente da baseline V02, o
manifesto 1.1 da massa e seus hashes no próprio `run.json`. Commit base
`61c25fb6a158c1a25f0932b72646e06ca0637c1e`, com alterações ainda não
commitadas. Manifesto: seed 20260830, digest lógico
`652c5713efb2685b45c61a026af4388654ac0fd8f483d753151a62854b671ff5`
e SHA-256 de manifesto
`7772be27d70ed9af44986ae73a535fa058614016354229c9224846345b183fbe`.

A execução `5250fbd3-3b11-4395-aabf-e92c2f8e4d60` pertence somente à
organização sintética `SYN-ORG-001` (`63000000-0000-4000-8000-000000000011`)
e estava `completed`. Contagens verificadas no banco: 1.700 Workorders,
1.700 lotes, 22.000 seriais, 45.700 decisões OQC, 45.700 classificações,
372.400 linhas de proveniência, 523.100 avaliações de regras, zero pendências
e 1.711 eventos de auditoria dessa execução. As tabelas globais também continham
outras rodadas; por isso, o coletor valida a execução/massa antes de medir e
preserva o filtro da execução ou da organização conforme a operação. Os
identificadores de detalhe são os medianos do manifesto, nunca escolhidos
após observar o resultado.

`scripts/collect_postgres_query_plans.py` executa somente `SELECT` em uma
transação read-only, com timeout de 30 s. Os SQLs são **representativos** das
operações do backend: mantêm tabelas, joins, filtros e ordenação relevantes,
mas reduzem a projeção de colunas; o tempo deles não é o tempo integral da
rota. `run.json` registra ambiente, massa, cardinalidades, aquecimento,
repetições, parâmetros sintéticos, percentis, buffers, scans e sorts; cada
amostra conserva SQL, hash do SQL e plano JSON completo. Os arquivos brutos
estão em `artifacts/performance/pgplans-v02-consolidated-local-pg18/` (antes)
e `artifacts/performance/pgplans-v02-index-after-local-pg18/` (depois),
ignorados pelo Git para anexação ao PR.

## Planos avaliados

| Grupo | p95 SQL (ms) | Caminho relevante e interpretação |
| --- | ---: | --- |
| Workorder exata | 0,090 | `idx_workorders_number`; um candidato antes do filtro de organização/publicação |
| Lote exato | 0,090 | `idx_lots_number`; join por chave da Workorder |
| Serial exato | 0,170 | `idx_serials_number`; um serial, join por chave da Workorder |
| Seriais da Workorder | 0,123 | `idx_serials_workorder`; consulta filha do detalhe |
| Busca Workorder — count | 0,069 | `idx_workorders_number`; cardinalidade um |
| Busca Workorder — página | 0,074 | mesmo índice; ordenação de um resultado |
| Histórico — página | 1,426 | scan sequencial de 1.711 eventos da execução; filtro organizacional preservado |
| Avaliações do consolidado | **115,182** | scan paralelo de 853.842 avaliações globais para 309 linhas; índice ausente |
| Proveniência do consolidado | 0,646 | `idx_provenance_workorder_field`; filtro por Workorder |
| Classificações do consolidado | 0,160 | `idx_classifications_workorder`; filtro por Workorder |
| Pendências — página | 0,151 | tabela global com 15 registros; zero dessa execução; scan sequencial proporcional |
| Indicadores Workorder | 1,937 | scan de 2.931 Workorders globais para agregação e filtro de estados/organização |
| Relacionados Workorder | 0,168 | `idx_executions_authorization_scope` e chave da Workorder por execução |
| Relatório Workorder | 49,191 | 1.700 Workorders/lotes, `idx_serials_workorder` para 22.000 seriais; sorts em memória |
| Relatório OQC | 91,261 | scan de 45.700 decisões da execução; sort em memória (~3,9 MB) |

### Avaliações: antes e depois da migration 0024

| Métrica | Antes | Depois |
| --- | ---: | ---: |
| p50 SQL | 102,864 ms | 0,514 ms |
| p95 SQL | 115,182 ms | 0,579 ms |
| Caminho | `Parallel Seq Scan` em `rule_evaluations` | `Index Scan` em `idx_rule_evaluations_workorder_execution_id` |
| Linhas retornadas | 309 | 309 |
| Máximo de blocos lidos do buffer PostgreSQL | 25.096 | 0 |
| Temporários escritos | 0 | 0 |
| Tamanho adicional de índice | 0 | 66.183.168 bytes (63 MB) |

O filtro por `workorder_id`, `execution_id` e a ordenação por `id` são
atendidos na mesma ordem do índice. O índice anterior
`idx_rule_evaluations_execution_rule` é mantido para consultas por execução e
regra. O custo de criação/armazenamento é medido. A sonda de escrita abaixo
mede manutenção do índice para INSERT direto, **não** latência de upload;
repetir o fluxo de referência com e sem a migration em ambientes equivalentes
antes da meta final.

A regressão de importação, relatório, consultas, escopo organizacional e
catálogo do índice e rollback da sonda concluiu com 46/46 testes após a
migration restaurada
(`artifacts/performance/pgplans-v02-index-final-regression-local-pg18-junit.xml`).
O rollback versionado remove somente o novo índice; não altera as linhas nem
as chaves estrangeiras. Planos de antes e depois foram obtidos sobre o mesmo
banco temporário, sem alterar a massa entre as séries.

### Leitura completa e custo de escrita local

Para não atribuir o ganho somente ao `EXPLAIN`, foi medida a chamada completa
`PostgresQueryRepository.get_consolidated` da Workorder mediana, com uma
execução de aquecimento e cinco medidas por fase. A sonda de escrita executou
cinco `EXPLAIN ANALYZE INSERT` de 1.000 avaliações sintéticas por fase,
revertendo a execução, fonte, Workorder e avaliações em cada transação. O
rollback `0024` foi aplicado **somente** no banco descartável e a migration
reaplicada antes de encerrá-lo. O total global de avaliações permaneceu
853.842 em ambas as fases; o digest funcional do consolidado foi igual.

| Métrica local | Sem índice | Com índice restaurado |
| --- | ---: | ---: |
| `get_consolidated` p50 | 186,210 ms | 82,505 ms |
| `get_consolidated` p95 | 201,531 ms | 85,139 ms |
| INSERT de 1.000 avaliações p50 SQL | 28,787 ms | 30,140 ms |
| INSERT de 1.000 avaliações p95 SQL | 29,544 ms | 32,463 ms |
| WAL por INSERT, intervalo das cinco amostras | 416.397–431.792 B | 557.290–559.770 B |
| Blocos modificados por INSERT, intervalo | 25–27 | 37–39 |

O p95 do INSERT aumentou 2,919 ms (aproximadamente 9,9%) nesta sonda, e o
WAL aumentou. Esses valores não predizem o custo de um upload completo:
transações, cache, concorrência e distribuição de regras são diferentes.
Uma execução de diagnóstico com índice havia produzido p95 de 75,563 ms para
o INSERT; ela foi descartada do comparativo por variabilidade e não foi usada
para escolher o resultado. Os artefatos do comparativo estão em
`artifacts/performance/workorder-index-absent-local-pg18/run.json` e
`artifacts/performance/workorder-index-present-local-pg18/run.json`; o runner
versionado é `scripts/benchmark_postgres_workorder_index.py`.

O relatório OQC percorre aproximadamente 61% das 74.490 decisões OQC
existentes no banco misto; o scan sequencial é coerente com essa baixa
seletividade. O histórico possui índice por execução, mas o planner escolheu
scan sequencial no conjunto pequeno observado. Essa escolha não demonstra
índice ausente. Os planos completos, inclusive leituras, linhas estimadas e
reais, e configuração, devem ser consultados antes de extrapolar essa decisão.

Na baseline HTTP V02 anterior, o p95 do consolidado foi 196,935 ms, de
`oqc_summary` 955,950 ms e de `workorder_consolidated` 166,789 ms. O plano
pré-índice das avaliações explica uma parte plausível do consolidado, mas
**não há medição HTTP depois da migration**. A rota inclui outras consultas,
serialização e resposta; não se deve subtrair p95 de séries diferentes para
declarar ganho fim a fim. Os p95 SQL representativos dos relatórios são bem
menores que os HTTP, indicando trabalho fora dos SQLs medidos, sem provar
saturação do PostgreSQL.

## Repetição e limite seguro

Com PostgreSQL isolado iniciado, migrations aplicadas, massa V02 importada e
`DATABASE_URL` configurado:

```bash
backend/.venv/bin/python scripts/collect_postgres_query_plans.py \
  --execution-id 5250fbd3-3b11-4395-aabf-e92c2f8e4d60 \
  --organization-id 63000000-0000-4000-8000-000000000011 \
  --organization-code SYN-ORG-001 \
  --mass-manifest artifacts/synthetic/v02-org001-valid/manifest.json \
  --baseline-environment artifacts/performance/v02-local-pg18/environment.json \
  --output-dir artifacts/performance/pgplans-v02-repeat \
  --run-id pgplans-v02-repeat --cache-label warm \
  --warmups 1 --repetitions 5
```

No momento da decisão, o host já usava aproximadamente 3,1 GB de swap e o
`/tmp` tinha cerca de 1,55 GB livre. Não se materializou uma massa somente
para consultas de 88.000 seriais nesse ambiente sem limite explícito de
serviço: ela não equivaleria à massa **processada** e criaria risco de pressão
de memória/armazenamento. Esse é um limite de teste, não um defeito provado da
aplicação nem capacidade definitiva do banco. A próxima medição deve repetir
os mesmos planos com PostgreSQL 16, ambiente descartável e massa V05 realmente
processada, registrar cardinalidades/recursos e comparar a migration 0024 com
seu rollback isolado, medindo também o custo de escrita e o tempo HTTP do
consolidado antes/depois.

### Portão de revalidação da etapa 7

O host disponível nesta continuação oferece apenas PostgreSQL 18.3; não havia
imagem PostgreSQL 16 local, e o banco temporário da medição anterior já não
existia. Assim, as evidências brutas preservadas são a fonte do comparativo
local, mas **não** é possível repetir a contraprova PG16/`V05` no ambiente
atual. No ambiente isolado de referência, o responsável deve:

1. importar e confirmar a massa `V05`, registrar ambiente/manifesto e comparar
   cardinalidades, consolidados e escopo organizacional;
2. coletar os 15 grupos de planos antes/depois em bancos equivalentes, com
   `ANALYZE`, cache, aquecimento, cinco medidas e hashes dos SQLs registrados;
3. medir a rota HTTP do consolidado e pelo menos cinco uploads completos com e
   sem `0024`, junto de RSS, CPU, I/O, WAL, armazenamento e erro;
4. preservar a migration se o ganho seletivo persistir e o custo de escrita
   for aceitável; caso contrário, registrar decisão técnica e comparar
   alternativa sem enfraquecer autorização, auditoria, proveniência ou
   integridade.

Sem esses quatro itens, a etapa 7 tem fechamento **local**, não fechamento do
critério de aceite global sobre planos PostgreSQL na massa de referência.
