# Evidência local da ingestão — issue #141

Execução em 23/10/2026, com os contratos e adapters da `main` após a #140.
Massas públicas são inteiramente inventadas. Os workbooks integrais foram
executados localmente, por opt-in, sem persistência; somente agregados foram
exportados. A evidência não equivale a aceite corporativo ou autorização de release.

## Ambiente e configuração

- Linux x86_64, kernel 6.11.0-26-generic; CPU AMD Ryzen 5 7535HS with Radeon Graphics, 12 CPUs lógicas.
- Memória física: 15.907.278.848 bytes; limite cgroup não informado pelo ambiente.
- Python 3.12.3; openpyxl 3.1.5; FastAPI 0.141.1; psycopg 3.3.6.
- Integração: PostgreSQL 16 local em Docker, banco novo com as 32 migrations.
- Worker novo por cenário; duração inclui admissão e pipeline sem persistência, excluindo geração da massa. Pico RSS por `VmHWM` no Linux.
- Memória estimada padrão: 1 GiB; watchdog externo: 900 s. Configuração numérica efetiva de cada cenário preservada nos JSON.
- Máquina de desenvolvimento compartilhada, com outras validações em execução; nenhuma afinidade de CPU, reserva exclusiva ou promessa de SLA.

## Resultados de ingestão

| Cenário | Lidas | Ignoradas | Importadas | Normalizadas | Rejeitadas | Duração | Pico RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WO Status sintético, 10.000 linhas base | 25.024 | 18 | 25.006 | 25.000 | 6 | 26,02 s | 334,9 MiB |
| Total Decision sintético, 10.000 linhas | 10.000 | 0 | 10.000 | 10.000 | 0 | 18,01 s | 272,6 MiB |
| WO Status integral, restrito | 102.332 | 33.537 | 68.795 | 68.776 | 19 | 190,60 s | 685,2 MiB |
| Total Decision integral, restrito | 551 | 0 | 551 | 550 | 1 | 0,97 s | 70,1 MiB |

Todos os cenários reconciliaram. Cabeçalhos e totais são excluídos antes da
contagem de linhas lidas. As seis rejeições sintéticas do WO Status são as
linhas previstas de `LOT PENDING_OQC`, bloqueada pelo contrato. No exemplar
integral, 18 rejeições pertencem a essa aba e uma é quantidade inválida. No
Total Decision integral, uma quantidade inválida foi rejeitada. Não houve
duplicatas nesses quatro cenários; os casos mínimos congelados e os testes
de concorrência exercitam duplicidade separadamente.

Datas/estados desconhecidos e indicadores OQC sem catálogo confirmado continuam
preservados ou sinalizados conforme o adapter; não foram interpretados como
aceite. O relatório restrito registra apenas as contagens desses códigos.

## Limites e falhas controladas

O perfil sintético executou cinco limites forçados em cada família, além do
processamento normal, totalizando doze cenários aprovados:

| Limite forçado | Código exigido |
| --- | --- |
| Linhas | `workbook_row_limit` |
| Células/dimensão | `workbook_dimension_limit` |
| Memória estimada | `workbook_memory_limit` |
| Ocorrências | `ingestion_issue_limit` |
| Tempo | `ingestion_time_limit` |

Nenhum crash foi tratado como rejeição bem-sucedida. Um teste separado força
o watchdog e exige falha do comando. A API foi exercitada com banco/storage
reais e autorização sintética: rejeições por linhas/memória não deixam resultados,
arquivos aceitos ou reservas de idempotência, e o reenvio posterior funciona.

A medição inicial por `getrusage` foi descartada por herdar o pico pré-exec do
gerador. A massa CTNR foi corrigida para não gerar quantidades negativas ao
ampliar o volume. A tabela e os artefatos abaixo usam as execuções corrigidas.

## Testes e verificações

- 746 testes não integrados aprovados; 631 de integração aprovados em banco novo.
- Dentro dessas suítes: 17 testes do corpus, oito do runner e 22 de persistência/concorrência do corpus.
- Onze fixtures e gabaritos regenerados com bytes idênticos e hashes verificados.
- Concorrência: um proprietário para o mesmo arquivo; arquivos distintos em organizações distintas; lotes gerados simultâneos com 300 e 160 registros normalizados.
- Reprocessamento concorrente: um pedido efetivo e um replay, processamento real da nova tentativa e resultados originais preservados.
- Ruff executado a partir de `backend/`, compilação Python, matrizes de acesso/jornadas/segurança, modelo de ameaças, HTTP e decisão de release aprovados.
- Validação oficial: 32 migrations, 116 arquivos sintéticos e política de 18 grupos de dados aprovados.

Uma rodada da suíte não integrada identificou oito regressões do novo validador
em diretórios temporários sem `ingestion-v1`. A compatibilidade foi corrigida
e a suíte completa repetida com sucesso. Não houve alteração da API, do domínio,
das migrations ou dos contratos dos adapters nesta issue.

## Artefatos sanitizados e limites do aceite

- [Volume sintético e configuração dos doze cenários](evidence/ingestion-v1/synthetic-volume.json).
- [Execução integral WO Status — somente agregados](evidence/ingestion-v1/restricted-wo.json).
- [Execução integral Total Decision — somente agregados](evidence/ingestion-v1/restricted-td.json).

Os relatórios não incluem nome/caminho/hash do workbook real, nomes de abas
desconhecidas nem conteúdo de células. Apenas o corpus inventado possui hashes
e digests semânticos públicos. Arquivos reais permanecem ignorados em `docs/files/`.

A CI passa a reproduzir corpus, gabaritos, perfil reduzido e testes PostgreSQL;
o resultado remoto e a revisão do PR permanecem pendentes. O perfil reduzido
publica seu próprio JSON sanitizado como artefato, identificado pelo ambiente do
runner GitHub. Os dados acima são medições locais e não devem ser apresentados
como benchmark do ambiente corporativo, homologação de chaves/estados ou
autorização para elevar limites e iniciar um piloto.
