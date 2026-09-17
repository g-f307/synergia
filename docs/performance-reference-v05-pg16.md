# Reconciliação do volume de referência V05 em PostgreSQL 16

## Resultado

Em 17/09/2026, a execução
`9945d638-c048-44c2-80d7-93a5ce24900e` terminou como `completed` e foi
consultada integralmente contra um oráculo determinístico reconstruído do
manifesto `v05-org001-valid`. Os **39/39 checks passaram**, sem erro HTTP
inesperado, perda, duplicação silenciosa ou divergência semântica.

O bundle usa seed `20260830`, uma organização e digest lógico
`e8aac580f62c91a11a199a44a4daca8c40f498fc4cb7f9fdbda1af40cd0aa059`.
O oráculo regenera os registros a partir do perfil, seed e configuração do
manifesto e recusa a comparação se o digest lógico reconstruído divergir.

| Resultado | Esperado | Observado | Verificação |
| --- | ---: | ---: | --- |
| Arquivos recebidos/aceitos/rejeitados | 4/4/0 | 4/4/0 | contagem da execução |
| Linhas lidas/válidas/normalizadas/rejeitadas | 189.600/189.600/189.600/0 | 189.600/189.600/189.600/0 | resumo e execução |
| Workorders/lotes/seriais | 6.800/6.800/88.000 | 6.800/6.800/88.000 | contagem da execução |
| Classificações | 182.800 | 182.800 informadas e 182.800 buscadas | multiconjunto e digest semântico |
| Pendências | 0 | 0 informadas e 0 buscadas | paginação integral |
| Erros/avisos | 0/0 | 0/0 | contagem da execução |
| Relatório consolidado | 6.800 | 6.800 | conteúdo, JSON e CSV |
| Relatório OQC | 182.800 | 182.800 | conteúdo, JSON e CSV |

Os digests observados foram:

- classificações: `d64b759944a985c1dbca8868d0eca2e53c8495a26d0c3bc47bc687f5c0002f87`;
- consolidado e export JSON: `f37ca1debd6485ffe581bbe15b56121fc1f1a6945095af4d83fe15e948dd095f`;
- consolidado CSV: `096480f392284177fb71990720a138066a5a207b9554cb4edf3e4125fab82de7`;
- OQC e export JSON: `37f420c37b595ed1a9eead4040b0a5c0263d334235cfd3d439c636b007fb1cda`;
- OQC CSV: `b5766543dd691d19763ac385e880d95ba6e6dba2e27c4ee1cf99d777289d6107`.

Os digests são calculados sobre campos semânticos canônicos e preservam a
multiplicidade: linhas iguais não são colapsadas em `set`. Os CSVs são
normalizados segundo a serialização da própria exportação antes da comparação.

## Ambiente e execução

A API e o PostgreSQL foram executados em um pod descartável com Podman 5.8.4.
A API tinha limite de 2 CPUs, 4 GiB de RAM e 6 GiB incluindo swap; o PostgreSQL
16.15 tinha 2 CPUs e 768 MiB de RAM/swap. O banco e as importações usaram
volumes locais nomeados. O runner no host acessou a porta publicada do pod.

O processamento inicial excedeu o limite de memória anterior durante a fase de
regras e foi revertido integralmente. Depois da redução de retenção em memória,
a operação manual retomou os quatro arquivos aceitos da **mesma execução** e
commitou 189.600 registros normalizados. A reconciliação posterior usou o modo
`--existing-execution-id`, que verifica o estado terminal, o resumo do pipeline,
consultas, relatórios, exports e o oráculo completo sem reenviar a massa.

O runner mediu 16 requisições funcionais, todas bem-sucedidas. Durante a rodada
final de consulta/oráculo, a API atingiu 387.874.816 bytes de RSS; o PostgreSQL
registrou zero rollback e zero deadlock. Essas medições não substituem a série
de processamento nem identificam saturação; esse objetivo pertence ao ensaio
de degraus.

## Evidência e limitações

Os arquivos sanitizados e versionados estão em
`evidence/performance/issue-95/runs/v05-reference/`:
`environment.json`, `workload.json`, `summary.json`, `correctness.json`,
`oracle-results.json`, `samples.csv`, `resources.csv` e `report.md`.

A rodada foi executada sobre a worktree `dirty` no commit-base
`f4bd4284cca0357a5daa9b4b20454a314fa45426`; por isso seu ambiente declara
`non_comparable`. Ela encerra a lacuna funcional do volume obrigatório, mas
**não** é usada como baseline de latência oficial. O conjunto publicado é
inventariado por `evidence/performance/issue-95/index.json` e verificável por
`evidence/performance/issue-95/SHA256SUMS`.

Esta rodada cobre o volume total de uma organização exigido para a referência.
Não comprova ainda isolamento cumulativo das oito organizações, repetição de
upload, ponto de ruptura nem recurso limitante.
