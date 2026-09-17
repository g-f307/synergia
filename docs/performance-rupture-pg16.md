# Ponto de saturação em ambiente isolado PostgreSQL 16

## Decisão

O primeiro critério de parada foi identificado no degrau `V01` (680
Workorders/8.800 seriais): **memória do PostgreSQL acima de 90% do cgroup**.
No ambiente primário, o banco atingiu 366.149.632 de 402.653.184 bytes
(90,93%). O resultado é classificado como **`environment_limit`**, não como
`application_defect`.

A contraprova ampliou o PostgreSQL de 384 para 512 MiB. O consumo do banco no
mesmo degrau caiu para 83.582.976 bytes (15,57% do novo limite) e o primeiro
critério mudou para a memória da API, que estava deliberadamente limitada a
640 MiB e atingiu 670.920.704 de 671.088.640 bytes (99,97%). A mudança do
recurso limitante com a redistribuição do orçamento confirma que a ruptura é
causada pelo envelope de memória do ambiente.

Não houve OOM, deadlock ou divergência funcional antes da saturação. O `V00`
passou todos os seus checks nas duas rodadas. Ao atingir o limiar, o runner
cancelou a requisição e parou a API; o `exit 137` do contêiner é consequência
desse `SIGKILL` controlado após o prazo de parada, não do OOM killer. Os
contadores `oom_kill` permaneceram em zero.

## Limites efetivos

As duas rodadas usaram PostgreSQL 16, Podman rootless, cgroup v2, swap
desativada e um pod descartável. O runner conferiu `memory.max`, `cpu.max` e os
valores declarados pelo runtime antes de iniciar.

| Recurso | Rodada primária | Contraprova |
| --- | ---: | ---: |
| API CPU | 2 CPUs (`200000/100000`) | 2 CPUs (`200000/100000`) |
| API memória/swap | 1.280/1.280 MiB | 640/640 MiB |
| PostgreSQL CPU | 2 CPUs (`200000/100000`) | 2 CPUs (`200000/100000`) |
| PostgreSQL memória/swap | 384/384 MiB | 512/512 MiB |
| Filesystem | 509.332.160.512 bytes; sem quota por contêiner | mesmo filesystem |
| Ocupação inicial | 11,33% | 11,37% |
| Critério de storage | parar em 85% | parar em 85% |
| Segurança do host | parar abaixo de 512 MiB disponíveis; soma dos limites ≤ 80% da memória disponível | mesmos critérios |

O armazenamento é um filesystem compartilhado do host, sem quota dedicada.
Isso está registrado como limite efetivo em vez de ser apresentado como
isolamento inexistente. O menor `MemAvailable` observado foi 1.792.032.768
bytes na rodada primária e 1.230.946.304 bytes na contraprova, acima do critério
de segurança.

Os contadores `nr_throttled` de API e PostgreSQL não aumentaram em nenhum dos
quatro degraus observados, reforçando que CPU não foi o primeiro limite.

## Resultados por degrau

| Rodada | Degrau | Duração | Resultado | API memória máx. | PG memória máx. | CPU máx. API/PG | Storage máx. |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| Primária | `V00` 50/500 | 10,011 s | aprovado; correção integral | 139.862.016 B | 122.003.456 B | 20,15%/44,75% | 11,33% |
| Primária | `V01` 680/8.800 | 29,283 s | parada: `postgres_memory_threshold` | 951.832.576 B | 366.149.632 B | 49,84%/37,94% | 11,33% |
| Contraprova | `V00` 50/500 | 10,015 s | aprovado; correção integral | 136.753.152 B | 86.048.768 B | 26,84%/47,89% | 11,37% |
| Contraprova | `V01` 680/8.800 | 6,396 s | parada: `api_memory_threshold` | 670.920.704 B | 83.582.976 B | 49,80%/10,88% | 11,37% |

`V02+` não foi iniciado porque o plano determina que o primeiro critério de
parada interrompa a progressão automática. O ponto de ruptura deste envelope é,
portanto, a transição entre `V00` e `V01`, e não uma extrapolação da antiga
rodada local `V02`.

## Integridade na parada

Em ambas as rodadas, o banco permaneceu com exatamente uma execução terminal,
50 Workorders e 500 seriais do `V00`. A tentativa `V01` ficou em
`applying_rules`, mas sem Workorder ou serial parcialmente publicado. Isso
confirma a fronteira transacional durante a parada e não fornece sinal de
defeito de integridade, autorização, auditoria ou proveniência.

A execução V05 com limites maiores já havia terminado e passado 39/39 checks
de reconciliação. Em conjunto, as evidências mostram que a aplicação preserva
correção quando há memória suficiente e para preventivamente neste envelope
reduzido.

## Evidências publicadas

- envelope primário: `evidence/performance/issue-95/rupture/primary/`;
- contraprova: `evidence/performance/issue-95/rupture/counterproof/`;
- inventário: `evidence/performance/issue-95/index.json`;
- hashes verificáveis: `evidence/performance/issue-95/SHA256SUMS`.

As duas pastas preservam o resultado por degrau, as amostras de cgroup e a
rodada `V00` completa. Logs vazios de processos interrompidos não foram
publicados; essa omissão está declarada no campo `scope` do índice e não remove
nenhuma medição ou saída funcional produzida.
