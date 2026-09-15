# Plano de desempenho e confiabilidade pré-RPA

## Propósito e estado

Este documento define a baseline reproduzível para os volumes conhecidos de
6.800 linhas de plano e 88.000 seriais. Ele cobre a API FastAPI, o PostgreSQL e
o armazenamento local usados nos fluxos manuais atuais. Celery, Redis,
conectores e RPA não fazem parte da medição.

As metas de tempo e capacidade deste plano são **propostas preliminares**. Elas
servem para detectar regressões e orientar a release candidate, mas só poderão
ser confirmadas depois da execução em infraestrutura corporativa. Requisitos de
integridade, autorização, auditoria, proveniência e isolamento organizacional
são invariantes e não podem ser relaxados para atingir uma meta de desempenho.

## Princípios de comparação

Um resultado só é comparável quando registra, no mesmo artefato:

- commit, data, responsável e identificador da execução de teste;
- perfil, cenário, seed, versões e SHA-256 do manifesto sintético;
- recursos, limites e versões do host, containers, API e PostgreSQL;
- parâmetros do cenário, concorrência, duração, aquecimento e repetições;
- percentis, throughput, erros, recursos consumidos e validações funcionais;
- mudanças de configuração, código, consulta ou índice desde a execução usada
  como comparação.

Resultados com metadados obrigatórios ausentes devem ser marcados como
`non_comparable` e não podem substituir a baseline publicada.

Quantidades ausentes permanecem `null` durante a preparação, validação,
consolidação, relatório e comparação. Nenhum coletor ou cálculo pode converter
ausência em zero.

## Ambiente de teste

Testes até o volume de referência podem usar um ambiente de desempenho
compartilhado desde que ele esteja reservado e sem outra carga conhecida.
Testes acima desse volume, de saturação, ruptura ou interrupção usam somente um
ambiente isolado e descartável. Dados reais e credenciais de produção são
proibidos.

O relatório deve preencher todos os campos abaixo; use `not_available` com
justificativa quando o ambiente não expuser uma informação:

| Grupo | Campos obrigatórios |
| --- | --- |
| Identidade | nome do ambiente, região/local, execução, commit e worktree limpa/suja |
| Host | sistema operacional, arquitetura, CPU/modelo, CPUs lógicas e RAM total |
| Armazenamento | tipo, filesystem, capacidade livre inicial e limites de volume |
| Containers | runtime e versão, imagem, CPUs/memória/IO configurados por serviço |
| Backend | Python, dependências, workers, timeouts, variáveis não secretas e nível de log |
| PostgreSQL | versão, CPUs/memória, armazenamento, `max_connections`, memória e paralelismo relevantes |
| Rede | topologia entre gerador, API e banco e latência básica quando não locais |
| Massa | perfil/cenário, seed, contagens, formatos, bytes e hash do manifesto |

O relógio do gerador de carga e dos serviços deve estar sincronizado. Métricas
começam antes da carga e terminam depois da última validação. O estado inicial
do banco (vazio ou preparado), o tratamento de cache (`cold`, `warm` ou ambos)
e qualquer processo concorrente conhecido devem ser registrados.

## Operações críticas

| ID | Operação | Fronteira medida | Resultado funcional |
| --- | --- | --- | --- |
| `UPLOAD` | upload multifuente | início ao fim de `POST /imports` | execução terminal e artefatos rastreáveis |
| `PROCESS` | validação, normalização, consolidação e regras | transições e tempos internos da execução | contagens e consolidado iguais ao manifesto |
| `QUERY` | consulta operacional | `GET /search`, Workorder, lote, serial, pendências, histórico, consolidado e indicadores | resposta paginada e restrita ao ator |
| `REPORT` | geração de snapshot | `POST /reports` ou criação de nova versão | versão `succeeded`, completa/parcial correta |
| `EXPORT` | exportação persistida | download CSV e JSON da versão | bytes válidos, classificação e `null` preservados |
| `REPROCESS` | reserva de nova tentativa | `POST /executions/{id}/reprocess` e conclusão aplicável | histórico preservado e replay idempotente |

O tempo de `UPLOAD` observado pelo cliente atualmente inclui o processamento
síncrono executado pela rota. `PROCESS` deve ser decomposto pelas transições de
estado ou por instrumentação interna; não deve ser somado novamente ao tempo
fim a fim.

## Métricas e cálculo

Cada amostra registra `scenario_id`, operação, organização, início, fim,
duração, status HTTP, código de erro seguro, bytes, linhas e identificador de
correlação. O relatório consolidado apresenta:

- duração fim a fim e, quando disponível, por fase;
- latência p50, p95, p99, mínima e máxima em milissegundos;
- throughput em requisições/s e, para processamento, linhas/s e seriais/s;
- total, sucessos, erros esperados, erros inesperados, timeouts e taxa de erro;
- CPU média e máxima, RSS/memória máxima, I/O e espaço utilizado da API e banco;
- conexões ativas/usadas, espera por conexão, locks, deadlocks, transações,
  cache hit, linhas lidas/retornadas, temporários e WAL do PostgreSQL;
- contagens persistidas, duplicidades, divergências e consolidados observados
  versus esperados.

Percentis são calculados a partir das amostras individuais, sem média de
percentis. A taxa de erro inesperado é
`unexpected_errors / total_requests`. Respostas esperadas pelo cenário, como o
`409` de uma duplicidade concorrente, são contadas separadamente e só são
sucesso funcional quando código e corpo correspondem ao contrato.

## Metas preliminares

As metas temporais abaixo valem para a massa `reference`, cache aquecido, uma
operação por vez e ambiente sem carga externa conhecida. A baseline deve
registrar o valor medido mesmo quando a meta não for atingida.

| Operação | Meta proposta para a primeira baseline |
| --- | --- |
| Upload e processamento multifuente | p95 menor ou igual a 300 s e conclusão em até 600 s |
| Consulta exata de Workorder, lote ou serial | p95 menor ou igual a 1 s; p99 menor ou igual a 2 s |
| Listas, histórico e indicadores paginados | p95 menor ou igual a 2 s; p99 menor ou igual a 5 s |
| Geração de relatório | p95 menor ou igual a 30 s |
| Exportação CSV ou JSON | p95 menor ou igual a 30 s e primeiro byte em até 5 s |
| Reserva de reprocessamento | p95 menor ou igual a 2 s |

Para leituras concorrentes, a meta proposta é menos de 1% de erros inesperados
e p95 de até duas vezes a medição isolada enquanto o ambiente não estiver
saturado. Upload, processamento, relatório e reprocessamento não admitem falha
inesperada no volume de referência. Todas as operações exigem:

- zero perda e zero duplicação silenciosa;
- zero vazamento entre organizações;
- consolidado e contagens iguais aos resultados esperados;
- estado transacional válido após falha;
- auditoria e proveniência completas;
- valores ausentes preservados como ausência.

Uma execução é considerada estável quando pelo menos cinco repetições medidas,
após uma de aquecimento, não apresentam erro inesperado e o p95 varia no máximo
20% entre duas séries equivalentes. Variação maior deve ser registrada e
investigada; não se escolhe apenas a melhor repetição.

## Matriz de cenários

### Correção e volume

| ID | Massa | Concorrência | Objetivo |
| --- | --- | ---: | --- |
| `V00` | `small/valid`: 50 Workorders e 500 seriais | 1 | verificar executor, coleta e oráculos |
| `V01` | 680 Workorders e 8.800 seriais | 1 | primeiro degrau, 10% da referência |
| `V02` | 1.700 Workorders e 22.000 seriais | 1 | degrau de 25% |
| `V03` | 3.400 Workorders e 44.000 seriais | 1 | degrau de 50% |
| `V04` | 5.100 Workorders e 66.000 seriais | 1 | degrau de 75% |
| `V05` | `reference/valid`: 6.800 Workorders e 88.000 seriais | 1 | volume obrigatório de referência |
| `V06+` | 125%, 150% e 200% da referência | 1 | localizar saturação/ruptura, apenas isolado |
| `V10` | `reference/comprehensive` | 1 | ausências, rejeições e divergências conhecidas |

Cada degrau executa upload/processamento, amostras de todas as consultas,
geração dos dois tipos de relatório e exportação CSV/JSON. `V06+` pode avançar
além de 200% em passos de 25% até encontrar o limite ou atingir o teto seguro
registrado para o ambiente.

### Concorrência e isolamento

| ID | Carga | Níveis iniciais | Oráculo principal |
| --- | --- | --- | --- |
| `C01` | uploads distintos | 2, 4 e 8 | todas as execuções corretas e isoladas |
| `C02` | mesmo upload simultâneo | 2, 4 e 8 | uma reserva; demais duplicidades contratuais |
| `C03` | reprocessamento com a mesma chave | 2, 4 e 8 | uma tentativa; demais replays idempotentes |
| `C04` | reprocessamentos com chaves distintas | 2, 4 e 8 | tentativas distintas, histórico preservado |
| `C05` | mix de consultas exatas e paginadas | 2, 4, 8, 16 e 32 | respostas corretas e degradação medida |
| `C06` | geração, consulta e exportação de relatórios | 2, 4, 8 e 16 | versões imutáveis e downloads íntegros |
| `C07` | upload com consultas e relatórios | 1 escritor + 4, 8 e 16 leitores | sem leitura parcial ou inconsistência |
| `C08` | mesmas operações em duas organizações | mesmos níveis de `C01` a `C07` | zero resultado ou identificador cruzado |

Cada nível usa uma barreira para iniciar os clientes juntos e mantém a mesma
composição por pelo menos cinco minutos ou até concluir cinco ciclos, o que for
maior. O nível seguinte só começa depois da validação funcional do anterior.

### Interrupção e recuperação

| ID | Ponto de falha controlado | Resultado esperado |
| --- | --- | --- |
| `F01` | depois da reserva do upload | nenhuma publicação parcial; retomada/repetição segura |
| `F02` | durante validação ou normalização | estado terminal coerente e registros da transação revertidos |
| `F03` | durante persistência/consolidação | nenhuma Workorder parcialmente confirmada |
| `F04` | antes e depois do commit final | resultado inteiro uma única vez |
| `F05` | durante geração de relatório | versão falha/cancelada auditável; snapshot não exportável |
| `F06` | durante solicitação de reprocessamento | reserva, vínculo e evento confirmados juntos ou revertidos |

As falhas devem ser injetadas por pontos explícitos e reversíveis de teste ou
pela interrupção isolada do processo/container. Depois de cada falha, comparar
banco, artefatos, auditoria e resposta da API com o estado anterior e com o
manifesto. Não editar dados diretamente para fazer a recuperação passar.

## Seleção determinística das consultas

O manifesto ou artefato derivado deve registrar identificadores existentes nas
posições inicial, mediana e final de cada organização, além de identificadores
inexistentes. Cada rodada mistura:

- busca, detalhe de Workorder, lote e serial;
- consolidado, pendências e histórico com primeira, intermediária e última
  página;
- indicadores sem filtro, por organização e por período;
- catálogo, versão e exportação de relatório.

Os identificadores são escolhidos pela seed, não manualmente após observar o
resultado. Consultas fora do escopo devem retornar o mesmo contrato seguro de
recurso inexistente e nunca revelar contagem, organização ou outro metadado.

## Saturação, ruptura e classificação

O primeiro destes sinais encerra um degrau e impede aumento automático da
carga: memória acima de 90% do limite, filesystem acima de 85%, pool ou
`max_connections` acima de 90%, swap/thrashing, risco ao host compartilhado ou
taxa de erro inesperado acima de 5%. CPU sustentada acima de 85%, crescimento
contínuo da fila/latência, throughput sem aumento por dois degraus, lock waits e
temporários em disco são sinais de saturação a analisar.

Classifique o resultado como:

- `application_defect`: quebra de integridade, isolamento, autorização,
  auditoria ou proveniência; deadlock/erro repetível abaixo da saturação; ou
  regressão localizada em código/consulta;
- `environment_limit`: um recurso registrado atinge seu limite, a aplicação
  preserva correção e o gargalo muda quando esse recurso é ampliado;
- `test_limit`: gerador, rede de carga ou observabilidade saturam antes do
  sistema sob teste;
- `inconclusive`: evidência insuficiente ou interferência externa.

A classificação de limite do ambiente exige correlação temporal e uma
contraprova, como repetir com o recurso ampliado ou com carga menor. Uma
execução lenta, isoladamente, não prova defeito nem limite.

## Planos PostgreSQL

As consultas com maior tempo acumulado, maior p95, mais leituras, temporários ou
degradação sob concorrência devem ser avaliadas no volume de referência com:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
```

O comando só pode ser usado com parâmetros sintéticos e em ambiente seguro.
Cada plano preservado deve informar cenário, cardinalidade, parâmetros
anonimizados/sintéticos, estado de cache e estatísticas. Índices ou reescritas
só são aceitos com hipótese, plano antes/depois, impacto de escrita e teste de
regressão. Não se remove filtro organizacional, autorização, integridade,
auditoria ou proveniência para melhorar o plano.

## Artefatos e modelo de relatório

O executor versionado é `scripts/run_performance_baseline.py`. O token é lido
somente da variável indicada por `--token-env` e não é persistido. Antes do
upload, o executor consulta a política ativa e interrompe o fluxo quando um
arquivo excede o limite, um formato não é aceito ou a organização não está
autorizada. Exemplo local, após gerar um bundle de uma única organização:

```bash
export SYNERGIA_PERFORMANCE_TOKEN='<access-token-temporario>'
python scripts/run_performance_baseline.py \
  --bundle artifacts/synthetic/v05-org001-valid \
  --environment-name perf-isolated-01 \
  --organization-id 63000000-0000-4000-8000-000000000011 \
  --organization-code SYN-ORG-001 \
  --process backend=12345 \
  --metadata container_runtime='Docker 27' \
  --metadata backend_limits='2 CPU/2 GiB' \
  --metadata postgres_limits='2 CPU/4 GiB' \
  --metadata resource_collection='runner /proc e pg_stat_*' \
  --metadata storage_type='SSD local' \
  --metadata network_topology='gerador/API/banco no mesmo host'
```

Para a massa de referência atual, configure a política de upload acima do maior
arquivo gerado antes de iniciar a API. O runner não altera limites para fazer o
teste passar; ele registra a incompatibilidade no preflight.

### Executor de concorrência e idempotência

O executor `scripts/run_performance_concurrency.py` cobre `C01` a `C08` em
ondas iniciadas por barreira. Cada onda registra tempo de parede, clientes,
requisições, throughput e erros; portanto o throughput concorrente não é
calculado pela soma das latências individuais. Por padrão são usados os níveis
2, 4 e 8 e cinco ciclos. Para `C05`, `C06` e `C08`, níveis adicionais podem ser
informados em `--levels`.

As massas usadas por cenários de escrita precisam ser inéditas no banco e ter
digests diferentes entre si:

- `C01`: uma opção `--c01-bundle` para cada cliente de cada onda;
- `C02`: uma opção `--c02-bundle` para cada onda;
- `C07`: uma opção `--c07-bundle` para o escritor de cada onda.

A quantidade exigida é validada antes da execução. Gere os bundles com seeds
distintas, `--scenario valid`, `--organization-count 1` e o mesmo
`--organization-start` da organização sob teste. A ordem é nível, ciclo e,
para `C01`, cliente. Os manifestos e digests efetivamente selecionados são
registrados em `workload.json`.

Exemplo para os cenários que reutilizam uma execução concluída:

```bash
export SYNERGIA_PERFORMANCE_TOKEN='<token-gestor-org-001>'
export SYNERGIA_ISOLATION_TOKEN='<token-leitor-somente-org-002>'
python scripts/run_performance_concurrency.py \
  --bundle artifacts/synthetic/v01-org001-valid \
  --execution-id '<execucao-concluida-org-001>' \
  --environment-name perf-isolated-01 \
  --organization-id 63000000-0000-4000-8000-000000000011 \
  --organization-code SYN-ORG-001 \
  --scenario C03 --scenario C04 --scenario C05 --scenario C06 \
  --scenario C08 \
  --isolation-token-env SYNERGIA_ISOLATION_TOKEN \
  --isolation-organization-id 63000000-0000-4000-8000-000000000012 \
  --isolation-organization-code SYN-ORG-002 \
  --levels 2,4,8 \
  --cycles 5 \
  --process backend=12345 \
  --metadata container_runtime='Docker 27' \
  --metadata backend_limits='2 CPU/2 GiB' \
  --metadata postgres_limits='2 CPU/4 GiB' \
  --metadata resource_collection='runner /proc e pg_stat_*' \
  --metadata storage_type='SSD local' \
  --metadata network_topology='gerador/API/banco no mesmo host'
```

`C08` usa um segundo ator sem acesso à organização da massa. Em cada par de
clientes, o ator de controle deve receber `200` e o ator de outra organização
deve receber `404` para Workorder, serial e consolidado. A organização de
isolamento é registrada explicitamente no workload. Tokens são lidos apenas
das variáveis indicadas e não são persistidos. `C01`, `C02` e `C07` só devem
ser executados no ambiente reservado porque criam e processam novas execuções.

Antes de cada nível, o runner verifica a memória disponível. O padrão impede o
início abaixo de 512 MiB e `--min-available-memory-bytes` pode elevar essa
guarda conforme o limite documentado do ambiente. A verificação ocorre antes
de cada ciclo; `--max-swap-used-bytes 0` impede a continuação se houver swap
utilizada no ambiente isolado. Ondas com erro ou oráculo funcional falho
impedem novos ciclos/degraus. Um nível ou ciclo omitido e os recursos observados
são registrados em `summary.json` e geram código de saída `2` (incompleto);
a guarda não substitui isolamento por container ou host descartável.

Cada execução publica um diretório com esta estrutura lógica:

```text
performance/<run-id>/
  environment.json
  workload.json
  summary.json
  samples.csv
  waves.csv
  resources.csv
  correctness.json
  postgres/
    statistics.json
    plans/*.json
  logs/
    sanitized-*.log
  report.md
```

Arquivos volumosos permanecem como artefatos temporários da CI ou da execução,
não no Git. `report.md` deve conter, nesta ordem:

1. conclusão da execução e status de comparabilidade;
2. commit, ambiente, massa, seed e hashes;
3. cenários realizados, omitidos e justificativas;
4. tabela por operação com amostras, p50/p95/p99, máximo, throughput e erros;
5. gráficos ou tabelas de CPU, memória, banco, armazenamento e duração;
6. validações de contagem, consolidado, duplicidade e isolamento;
7. falhas injetadas e estado observado após recuperação;
8. consultas críticas e referências aos planos PostgreSQL;
9. comparação com a baseline anterior;
10. gargalos, classificação, limitações, correção ou decisão formal.

Segredos, tokens, cookies, nomes originais de upload, caminhos internos e dados
não sintéticos devem ser removidos dos artefatos. A sanitização não pode apagar
IDs sintéticos, códigos de erro, correlações ou evidências necessárias à
reprodução.

## Critério de saída desta fase de planejamento

O planejamento está pronto para implementação quando:

- operações, cenários, métricas e metas propostas estão revisados;
- o ambiente isolado para ruptura e os responsáveis pela execução estão
  identificados no PR ou na issue;
- o gerador pode ser estendido para os degraus sem introduzir dados reais;
- há estratégia para coletar recursos e planos sem expor segredos;
- os oráculos do manifesto cobrem contagens, ausências e consolidados;
- qualquer exceção a este plano está registrada antes da execução.
