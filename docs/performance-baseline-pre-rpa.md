# Baseline pré-RPA: publicação exploratória e decisão de release

## Estado da evidência

**Baseline local publicada para investigação, não baseline de referência. Release
candidate ainda não aprovada por desempenho/confiabilidade.** A massa de
referência `V05` (6.800 linhas de plano/88.000 seriais) foi gerada, mas **não
foi processada nem consultada**. Não houve teste de ruptura, que requer ambiente
isolado. Não é válido extrapolar percentis de `V02` ou de concorrência pequena
para `V05`.

O índice reproduzível `artifacts/performance/evidence-index-local-pg18-v3.json`
registra SHA-256 e tamanho dos artefatos, ambiente, massa, workload, percentis,
recursos e verificações. São sete rodadas indexadas: seis `exploratory_pass` e
uma `diagnostic` (`C03/C08` inicial, 14/17 oráculos). Ambas as suítes JUnit
indexadas não têm falhas. Os dois manifestos `V05` e os hashes das oito fontes
também são indexados como `generated_only_not_processed`. O índice declara
`exploratory_non_comparable` e
`not_approved`, independentemente de os oráculos locais terem passado.

## Ambiente, massa e comparabilidade

Execução local em 15/09/2026, Fedora 44/Linux 7.1.5 x86_64, Python 3.14.7,
12 CPUs lógicas, 8.022.978.560 bytes de RAM física, um worker Uvicorn e
PostgreSQL **18.3** temporário (`shared_buffers=128MB`,
`max_connections=100`). Gerador, API e banco em loopback no mesmo host;
armazenamento local temporário, sem limites de CPU/RAM por serviço. Coleta por
`/proc` e estatísticas PostgreSQL. A worktree continha alterações não
commitadas sobre `61c25fb6a158c1a25f0932b72646e06ca0637c1e`.
PostgreSQL 16 é o alvo do projeto. O host já usava swap; CPU/modelo do host e
limites de serviço não estavam disponíveis nos artefatos. Por isso, mesmo as
rodadas com metadados internos completos são **não comparáveis com a futura
baseline oficial**. Artefatos de rodadas diferentes não devem ser misturados
para calcular percentis.

O bundle `v05-reference-valid` usa seed `20260830`, oito organizações,
6.800 Workorders/lotes, 88.000 seriais e digest lógico
`8f7e20d939eebc0ac14ff696af8d32dae0846f50afec956fe1f0673cf2230300`.
O SHA-256 do manifesto é
`395bb3d6e81c0cee878778f83d40a23713408a467a792915622bd9c66b2342fe`;
as quatro fontes somam 189.600 registros e têm bytes/hashes discriminados no
manifesto. Esta é evidência de **geração**, não de processamento.

O bundle `v05-org001-valid`, próprio para um upload na organização 001,
contém o **mesmo volume total**, mas uma organização; seu digest lógico é
`e8aac580f62c91a11a199a44a4daca8c40f498fc4cb7f9fdbda1af40cd0aa059`
e o SHA-256 do manifesto é
`7e351dfbb2689a06d261d6e64ff92f5771b20631f2a75d8b78774fa65325d9e5`.
Ele também foi somente gerado. O teste cumulativo de oito organizações exige
reservas/importações e atores autorizados separados por organização; não se
deve enviar um bundle multi-organização como se fosse uma única organização.
`V00`–`V02` usaram apenas a organização sintética 001, com 50/500, 680/8.800 e
1.700/22.000 Workorders/seriais, respectivamente. Seus digests e arquivos
estão incorporados em `environment.json` de cada execução. A concorrência
usou 50/500 por massa. Quantidade ausente continuou `null`, distinta de zero.

## Medições locais que servem de ponto de investigação

| Operação/cenário | Amostras e percentis | Recurso, erro e consistência |
| --- | --- | --- |
| Upload/processamento `V00`, `V01`, `V02` | uma amostra por degrau: 9,26 s; 217,09 s; 453,59 s | zero erro inesperado/divergência nas contagens verificadas; `V02` pico RSS API 2.148.466.688 B, CPU média 53,79% de um núcleo, até 3 conexões, zero deadlock/temporário |
| Consulta `V02` | maior p50/p95/p99: consolidado 171,313/196,935/196,935 ms, cinco medidas aquecidas | status HTTP esperado; conteúdo consolidado completo **não** comparado ao manifesto |
| Relatório `V02` | OQC p50/p95/p99 893,234/955,950/955,950 ms, cinco medidas | status HTTP esperado; snapshot **não** comparado ao oráculo da massa |
| Exportação `V02` | OQC CSV p50/p95/p99 1.037,478/1.047,628/1.047,628 ms, cinco medidas | status HTTP esperado; bytes CSV/JSON **não** comparados ao oráculo da massa nesta rodada |
| Leitores concorrentes `C05` | 2 e 4 leitores, cinco ciclos por nível, 240 amostras; consolidado p50/p95/p99 150,882/182,283/183,010 ms (30 amostras) | 240 HTTP `200`, 81/81 oráculos, zero erro; até 4 conexões, 1 espera, zero rollback/deadlock/temporário |
| Índice `0027`, SQL de avaliações | p95 `EXPLAIN ANALYZE` 115,182 → 0,579 ms, cinco amostras por fase | scan global de 853.842 avaliações → index scan; mesmo resultado de 309 linhas; índice de 66.183.168 B |
| Índice `0027`, leitura completa e sonda de escrita | `get_consolidated` p95 201,531 → 85,139 ms; INSERT sintético de 1.000 avaliações p95 29,544 → 32,463 ms | digest de leitura igual; 853.842 avaliações antes/depois; mais WAL e manutenção de índice; **não** é custo de upload |

As rotas com maior p95 de cada classe nos degraus formais foram consolidado,
relatório OQC e exportação OQC CSV. Cada trio abaixo é p50/p95/p99 em **ms**,
calculado em cinco medidas aquecidas por rota; não agrega rotas diferentes.

| Degrau | Upload (amostra única) | Registros de fonte/s fim a fim | Consulta | Relatório | Exportação | Erro inesperado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `V00` 50/500 | 9,26 s | ~118,8 | 136,066/150,220/150,220 | 106,320/162,045/162,045 | 70,664/74,830/74,830 | 0/72 = 0% |
| `V01` 680/8.800 | 217,09 s | ~87,3 | 123,060/130,212/130,212 | 401,640/409,983/409,983 | 437,488/457,919/457,919 | 0/72 = 0% |
| `V02` 1.700/22.000 | 453,59 s | ~104,5 | 171,313/196,935/196,935 | 893,234/955,950/955,950 | 1.037,478/1.047,628/1.047,628 | 0/72 = 0% |

Os p95/p99 de série de cinco medidas são o máximo pelo método de rank mais
próximo, não estimativas de cauda robustas. `POST /imports` teve somente uma
amostra por degrau: seu “p95” mecânico em `summary.json` é a própria duração e
**não** deve ser usado como p95 da baseline. As metas de
[plano de testes](performance-test-plan.md) são propostas, não compromissos de
capacidade corporativa. `V02` ultrapassou a proposta de 300 s para upload,
embora tenha concluído antes do teto proposto de 600 s.

### Throughput, erro e recursos observados

Em `V02`, os 47.400 registros de fonte corresponderam a aproximadamente
104,5 registros/s e os 22.000 seriais a 48,5 seriais/s durante os 453,586 s
do upload **fim a fim**; não são taxas puras da fase de processamento. Foram
72 amostras HTTP com zero erro inesperado (0/72 = 0%). `C05` mediu 240
respostas `200`, zero erro inesperado (0/240 = 0%); o throughput de parede
variou de 31,86 a 33,89 req/s com dois leitores e de 44,38 a 46,72 req/s
com quatro. Os `409` de `C02` e `404` de `C08` são resultados contratuais,
não foram escondidos na taxa de erro inesperado.

| Recurso | `V02` local | `C05` pequeno | Limitação da medição |
| --- | --- | --- | --- |
| API/CPU | 473 amostras; RSS máximo 2.148.466.688 B; CPU média 53,79% de um núcleo | CPU/RSS do backend não coletados nessa rodada | não há CPU máxima nem perfil por fase; host compartilhado |
| Host/memória | disponível mínima 1.651.736.576 B | disponível mínima 2.665.730.048 B | swap já usada; não há limite de serviço para correlacionar saturação |
| PostgreSQL | até 3 conexões, 2 em espera; 0 rollback, deadlock e arquivo temporário; 239.274 blocos lidos, 27.499.132 hits | até 4 conexões, 1 em espera; 0 rollback, deadlock e arquivo temporário; 13 blocos lidos, 711.878 hits | `pg_stat` mede o banco misto, não CPU/RSS específicos do processo PostgreSQL |
| Armazenamento | filesystem dos artefatos: livre inicial 450.405.404.672 B, final 450.404.892.672 B | livre mínima do mesmo filesystem 450.403.827.712 B | o coletor não apurou separadamente espaço/IO de importações e banco temporários em `/tmp`; WAL só foi medido na sonda de índice |

O primeiro **recurso saturado** não foi identificado: `V02` concluiu, e o
degrau seguinte foi interrompido preventivamente por risco de pressão de
memória no host sem isolamento. Não houve ponto de ruptura observado. Os
números de CPU, banco e disco acima não permitem atribuir a eles a limitação
do teste; a projeção de RSS também não equivale a medição em `V05`.

### Esperado versus observado

| Oráculo/cenário | Esperado | Observado | Situação |
| --- | --- | --- | --- |
| Pipeline `V02` | `completed`; 47.400 lidos/válidos/normalizados; 0 rejeitados | exatamente esses valores em `pipeline-summary` | verificado, 6/6 checks |
| Consolidado, relatórios e exports `V02` | conteúdo/contagens/classificações/ausências iguais ao oráculo sintético | apenas status HTTP foram medidos pelo runner de volume; não houve digest de conteúdo contra oráculo completo | **não verificado**; não alegar zero perda/duplicação |
| Duplicidade `C02`, reprocessamento `C03` | uma vencedora + `409`; uma tentativa + replay | respostas e vínculos esperados na massa pequena | verificado localmente |
| Consultas `C05` | conteúdo funcional estável nos níveis 2/4, sem erro inesperado | 81/81 checks e 240/240 HTTP `200` | verificado localmente |
| Isolamento `C08` | ator de outra organização não vê detalhes da organização 001 | seis respostas `404` contra seis `200` de controle | verificado localmente na massa pequena |
| Recuperação `F01`–`F06` | transação revertida antes do commit; terminal/no-op depois | fixtures pequenas e 63/63 testes integrados | verificado localmente; referência pendente |
| Referência `V05` | 6.800/88.000 processados, consultados e reconciliados | bundle gerado e hashes das quatro fontes válidos; nenhum upload | **não verificado** |

## Concorrência, falha e decisão sobre gargalos

Na massa pequena, `C01` concluiu dois uploads distintos; `C02` produziu uma
reserva e uma duplicidade contratual `409`; `C03` repetiu a mesma chave sem
criar nova tentativa; `C04` preservou tentativas com chaves distintas; `C06`
gerou duas versões e exportações íntegras; `C07` não publicou leitura parcial;
`C08` devolveu `404` ao ator da outra organização. A fumaça inicial `C03/C08`
teve três falsos positivos por comparar `generated_at`; ficou classificada
como diagnóstico e não como aprovação. A repetição `C05` passou 81/81 após
excluir **somente** esse campo volátil do digest funcional. Contagens, `null`,
autorização e conteúdo de negócio não foram relaxados.

Os testes `F01`–`F06` pequenos verificaram exceções e saídas abruptas antes e
depois do commit PostgreSQL: antes, saídas operacionais foram revertidas e a
retomada concluiu a **mesma** execução; depois, a retomada foi no-op. Reserva,
auditoria, relatórios e reprocessamentos preservaram fronteiras transacionais.
Foram 63/63 testes integrados e 10/10 testes de dashboard; a regressão após a
migration `0027` foi 46/46. A retomada é operacional/manual, não automática,
e a queda foi de subprocesso, não do container/API no volume de referência.

A investigação PostgreSQL tem correção justificada: a consulta de avaliações
do consolidado fazia scan global e a migration `0027` fornece o índice pela
Workorder/execução/ordem. O ganho SQL e da leitura de repositório foi medido
antes/depois, preservando auditoria, autorização, proveniência e integridade.
O custo de armazenamento e INSERT direto também foi medido. **Falta** medir
efeito HTTP e upload completo com a migration no ambiente-alvo antes de
considerar o gargalo resolvido. Os outros planos avaliados não justificaram
novos índices nesta massa.

O host local impediu avanço seguro além de `V02`: a API atingiu 2,15 GiB em
22.000 seriais e a projeção para 88.000 supera seus 8,0 GiB de RAM física;
sem cgroup/VM isolada, continuar poderia pressionar o host. Isto é um
**limite de teste preventivo**. A retenção de memória e o processamento
síncrono em um único worker são candidatos a gargalo da aplicação, não prova
de capacidade definitiva da infraestrutura. Até perfilar as fases e repetir
com limites registrados, a origem/solução não está decidida. Não houve sinal
de saturação por conexões, deadlocks ou temporários PostgreSQL em `V02`.

### Classificação, impacto e decisão formal

| Classe solicitada | Evidência e alcance | Decisão, risco e acompanhamento |
| --- | --- | --- |
| Limite conhecido do ambiente | host físico de 8,0 GiB, swap em uso e serviços sem limite explícito; `/tmp` temporário sem observação de espaço por serviço | **limite de teste preventivo**, não `environment_limit` comprovado; não executar ruptura neste host. Risco alto de interferir em outras cargas. Repetir em VM/container descartável, com limites e contraprova por carga menor/recurso ampliado. |
| Degradação aceitável | `C05` 2/4 leitores pequenos, p95 consolidado 182,283 ms, 0/240 erro e 81/81 checks | aceitável **somente** como smoke funcional local. Sem séries equivalentes de mesma massa/configuração não há decisão de degradação aceitável em `V05`. Acompanhar p95 e throughput no ambiente isolado. |
| Configuração inadequada | um worker com processamento síncrono; saúde da API não respondeu durante upload `V02`; sem cgroup e sem métricas do storage de banco/importações | hipótese de configuração/capacidade, **não** fix validado. Risco alto de indisponibilidade concorrente. Perfilar fases, medir workers/timeouts/limites e instrumentar armazenamento; não ampliar workers às cegas com RSS crescente. |
| Defeito da aplicação | scan global de avaliações no consolidado e publicação parcial antes do commit observados nas etapas 7 e 6 | migration `0027` e commit atômico/filtro terminal corrigidos localmente. Regressões 46/46 e 63/63. Risco residual médio: PG16/`V05`, HTTP, escrita e falha de container ainda não validados. |
| Gargalo crítico para a release | `V02` upload 453,59 s > meta proposta 300 s, RSS 2,15 GiB; `V05` não executado; oráculo completo de consolidado ausente | **bloqueador de aprovação** por evidência insuficiente e provável escala de memória. Corrigir após perfil ou registrar aceitação formal com limites/risco no ambiente-alvo; não promover RC nem declarar capacidade de 88.000 seriais antes de `V05` reconciliado. |

Nenhum recurso limitante do sistema sob teste foi isolado por correlação e
contraprova. A classificação acima separa fatos de hipóteses; a decisão de
aceitar custo do índice é restrita à investigação local, não ao upload de
referência. Os acompanhamentos exigem responsável e data no PR/issue da
execução em infraestrutura; esses campos ainda não foram atribuídos aqui.

## Portões ainda abertos para a release candidate

1. Repetir em ambiente descartável com recursos/limites registrados,
   PostgreSQL 16 e código commitado; processar **e consultar** `V05`, construir
   oráculo completo derivado do manifesto e comparar contagens, consolidados,
   classificações, relatórios/exports e `null` no volume de uma organização;
   repetir isolamento/cumulativo com massas particionadas nas oito organizações.
2. Fazer degraus `V03`–`V06+`, inclusive ruptura **somente** no ambiente
   isolado, até saturação/ponto de parada com CPU, memória, banco,
   armazenamento de API/importações/PG separadamente, duração e erro;
   classificar primeiro recurso limitante com contraprova.
3. Repetir upload pelo menos cinco vezes, instrumentar fases e corrigir ou
   formalizar decisão sobre memória/processamento síncrono sem reduzir
   auditoria, autorização, proveniência ou integridade.
4. Executar níveis/ciclos completos `C01`–`C08` com massa de referência,
   uploads/reprocessamentos e consultas/relatórios concorrentes, incluindo
   duplicidade, idempotência e isolamento entre organizações.
5. Repetir falha/retomada no volume de referência, também com interrupção do
   processo/container, recursos medidos e contagens, artefatos e auditoria
   confrontados antes/depois; documentar operação manual e estados legados.
6. Coletar planos críticos em PG16/`V05`, comparar migration `0027` com
   rollback em bancos equivalentes, medindo upload e HTTP antes/depois.

Nenhum desses portões pode ser substituído por projeção da massa menor ou por
“zero erro” da pequena concorrência. Metas finais continuam propostas até
serem calibradas na infraestrutura corporativa.

### Metas propostas para comparar releases futuras

Na massa de referência, cache aquecido e ambiente sem carga externa: upload
fim a fim p95 ≤ 300 s e conclusão ≤ 600 s; consulta exata p95 ≤ 1 s/p99 ≤ 2 s;
listas/indicadores p95 ≤ 2 s/p99 ≤ 5 s; relatório e exportação p95 ≤ 30 s
(exportação com primeiro byte ≤ 5 s); reserva de reprocessamento p95 ≤ 2 s.
Sob concorrência antes de saturação, erro inesperado < 1% e p95 ≤ 2 vezes a
medida isolada são **propostas**, não metas aprovadas. Integridade,
autorização, auditoria, proveniência, isolamento, `null` e recuperação válida
continuam requisitos absolutos, sem margem de erro. Percentis de upload
exigem cinco rodadas independentes e duas séries equivalentes com variação de
p95 ≤ 20%, como definido no plano de testes.

## Como reproduzir e anexar a evidência

Os documentos versionados de [volume](performance-baseline-local-pg18.md),
[concorrência](performance-concurrency-local-pg18.md),
[recuperação](performance-recovery-local-pg18.md) e
[planos/índice](performance-postgres-plans-local-pg18.md) contêm método,
interpretação e limitações. Os artefatos brutos ficam ignorados pelo Git em
`artifacts/performance/`; os bundles/manifests em `artifacts/synthetic/`.
**Anexar ambos ao PR** ou armazenar em repositório de artefatos com hashes do
índice. Eles não estarão presentes em um clone limpo por padrão.

No **ambiente isolado PG16**, com API iniciada, política de upload acima dos
bytes do manifesto e token temporário do gestor definido apenas em variável
de ambiente, a rodada de volume de uma organização pode ser repetida por:

```bash
backend/.venv/bin/python scripts/run_performance_baseline.py \
  --bundle artifacts/synthetic/v05-org001-valid \
  --scenario-id V05 --run-id v05-pg16-run-01 \
  --environment-name perf-isolated-pg16 \
  --organization-id 63000000-0000-4000-8000-000000000011 \
  --organization-code SYN-ORG-001 \
  --base-url http://127.0.0.1:8000 \
  --process backend=12345 \
  --metadata container_runtime='<runtime-e-versao>' \
  --metadata backend_limits='<cpu-ram-io>' \
  --metadata postgres_limits='<cpu-ram-io-pg16>' \
  --metadata storage_type='<volume-e-capacidade>' \
  --metadata resource_collection='procfs e pg_stat' \
  --metadata network_topology='<gerador-api-banco>'
```

Substituir `12345` pelo PID real da API. O runner lê
`SYNERGIA_PERFORMANCE_TOKEN` e `DATABASE_URL` do ambiente; não
persistir valores desses segredos. Repetir com run-id novo ao menos cinco
vezes e preservar ambiente, manifesto, amostras e oráculos. `V03` e `V04`
seguem o mesmo comando com seus bundles/IDs; `V06+` deve ser gerado com
`scripts/generate_synthetic_data.py --workorders 8500 --serials 110000
--organization-count 1 --output <diretorio-novo>` para o primeiro degrau
de 125%, **apenas após** comprovar isolamento/limites e concluir `V05`.
O runner agora recusa `V06+` ou massa acima de 6.800/88.000 sem
`--isolation-kind isolated-container` (com runtime registrado) ou
`--isolation-kind isolated-vm` (com `--metadata vm_limits='<cpu-ram-io>'`),
além de limites explícitos de backend, PostgreSQL e storage. Essa guarda
verifica a declaração do operador, **não** comprova o isolamento físico.
Não há comando automático que avance sem validar cada degrau. Encerrar o
degrau se memória > 90% do limite, filesystem > 85%, pool/conexões > 90%,
swap/thrashing, erro inesperado > 5% ou falha funcional; registrar qual
recurso disparou a parada e repetir com carga menor ou recurso ampliado antes
de classificá-lo como limite do ambiente. Não executar esse procedimento no
host local usado neste relatório.

Para concorrência e falha/retomada, os comandos e pré-condições estão no
[plano de testes](performance-test-plan.md) e no
[relatório de recuperação](performance-recovery-local-pg18.md). Os planos
antes/depois de `0027` usam
`scripts/collect_postgres_query_plans.py` e
`scripts/benchmark_postgres_workorder_index.py`, com argumentos e rollback
restritos ao banco descartável conforme o
[relatório de planos](performance-postgres-plans-local-pg18.md).

Com os diretórios locais preservados, o índice é reproduzido por:

```bash
backend/.venv/bin/python scripts/build_performance_evidence_index.py \
  --run artifacts/performance/v00-formal-local-pg18 \
  --run artifacts/performance/v01-local-pg18 \
  --run artifacts/performance/v02-local-pg18 \
  --run artifacts/performance/c01-c02-c07-small-local-pg18-repeat \
  --run artifacts/performance/c03-c08-smoke-local-pg18 \
  --run artifacts/performance/c05-local-pg18-five-cycles \
  --run artifacts/performance/c06-export-integrity-smoke-local-pg18 \
  --junit artifacts/performance/f01-f06-final-local-pg18-junit.xml \
  --junit artifacts/performance/pgplans-v02-index-final-regression-local-pg18-junit.xml \
  --plan-run artifacts/performance/pgplans-v02-consolidated-local-pg18 \
  --plan-run artifacts/performance/pgplans-v02-index-after-local-pg18 \
  --benchmark-run artifacts/performance/workorder-index-absent-local-pg18 \
  --benchmark-run artifacts/performance/workorder-index-present-local-pg18 \
  --manifest artifacts/synthetic/v05-reference-valid/manifest.json \
  --manifest artifacts/synthetic/v05-org001-valid/manifest.json \
  --output artifacts/performance/evidence-index-repeat-local-pg18.json
```

O comando recusa artefato sem ambiente/massa/oráculos, resultados de sonda
inconsistentes ou sobrescrita de índice. `created_at` muda em cada geração;
os hashes dos arquivos-fonte permitem verificar que o conteúdo da evidência
permaneceu igual. Releases futuras devem usar este esquema de artefatos e
comparar **somente** cenários, massa, código, PostgreSQL e recursos
equivalentes, anotando toda diferença de configuração.
