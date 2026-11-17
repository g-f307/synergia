# Resultado persistido da importação (#194)

## Contrato aditivo — API 0.16.0

`GET /imports/{execution_id}/result-summary` exige **somente `import.read`**
na organização da execução. A consulta reaplica esse escopo no PostgreSQL,
inclusive quando chamada diretamente pelo repositório. Organizações IAM
desconhecidas ficam excluídas também para concessões globais.

A resposta contém:

- `execution_id` e `execution_status`: identidade e estado persistido;
- `summary_status`: `ready`, `processing`, `unavailable` ou `not_applicable`;
- `summary`: contagens persistidas (`rows_read`, `valid_records`,
  `rejected_records`, `normalized_records`, `errors`, `warnings`) ou **null**;
- `issues_total`: quantidade real de registros em `pipeline_issues`, sem
  confundir ocorrências com linhas rejeitadas;
- `generated_at`: instante da consulta em UTC;
- `reason_code`: motivo público estruturado para a disponibilidade;
- `inspection_reason_code`: código público da inspeção recusada, quando aplicável;
- `duplicate_of_execution_id`: referência somente quando `import.read` também
  autoriza a importação anterior e sua organização IAM é conhecida.

Não retorna valores de células, nomes de arquivos, `details`, paths,
`failure_reason` livre ou detalhes internos de inspeção. Códigos de inspeção
desconhecidos recebem o fallback público `security_rejected`.

## Precedência e disponibilidade

| Condição, nesta ordem | `summary_status` | `reason_code` |
| --- | --- | --- |
| Linha em `pipeline_summaries`, inclusive contagens zero | `ready` | `summary_persisted` |
| Duplicata sem resumo persistido | `not_applicable` | `duplicate` |
| Inspeção recusada sem resumo persistido | `not_applicable` | `security_rejected` |
| Estado ativo conhecido sem resumo | `processing` | `execution_processing` |
| Estado desconhecido sem resumo | `unavailable` | `unknown_execution_state` |
| Estado terminal sem resumo, com `failure_reason=preparation_error` | `unavailable` | `preparation_error` |
| Demais estados terminais sem resumo | `unavailable` | `summary_unavailable` |

Estados ativos são obtidos de `ExecutionState` menos `TERMINAL_STATES`, sem
criar uma segunda máquina de estados. `ready` indica disponibilidade das
contagens, **não sucesso da execução**: uma validação recusada ou conclusão com
erros pode possuir resumo válido. Ausência não é convertida em seis zeros.

O PostgreSQL é a fonte de verdade desta rota. A presença ou ausência de
`pipeline-summary.json` não interfere no resultado. Mesmo um JSON existente
não substitui contagens ausentes no banco.

## Compatibilidade e consultas sem reparo

`GET /imports/{execution_id}/pipeline-summary` permanece com seu contrato de
artefato: retorna o JSON disponível ou 404. Não foi convertido silenciosamente
no novo recurso persistido. `validation-report` e `normalized-data` também
preservam seus contratos e permissões. Os três GETs resolvem o diretório sem
criá-lo quando ausente; o upload continua criando diretórios normalmente.

O novo recurso usa uma transação `REPEATABLE READ READ ONLY` e uma consulta
para obter estado, resumo, total de ocorrências, inspeção e referência autorizada.
Não lê nem cria artefatos, não chama o pipeline e não reprocessa ou altera o
histórico. Registros de autenticação/acesso seguem a política existente.

Recurso acessível sem resumo é **HTTP 200** com disponibilidade explícita.
Autenticação ausente/inválida retorna 401; falta de `import.read`, 403;
execução inexistente, sem IAM ou externa ao escopo, 404. Falha operacional de
conexão ao repositório retorna 503 `import_result_unavailable`, sem expor a
exceção. Nenhum desses erros equivale a `processing`.

## Diagnóstico inicial

1. Consulte o estado de disponibilidade com `import.read` na organização correta.
2. Para `ready`, use as contagens persistidas; o desaparecimento do JSON não
   significa que o pipeline esteja em execução.
3. Para `not_applicable`, examine o motivo de inspeção ou o vínculo anterior
   autorizado. Não tente processar conteúdo recusado.
4. Para `processing`, confirme o estado ativo e consulte o
   [runbook de processamento interrompido](runbooks/processing-interrupted.md)
   se ele não evoluir.
5. Para `unavailable`, registre execução, código público e correlation ID por
   canal restrito de suporte. Use o [runbook de storage](runbooks/storage-unavailable.md)
   quando houver evidência de falha no armazenamento. Não fabrique JSON nem
   edite contagens/estados para produzir um resultado.

## Divergências paginadas e CSV

`GET /imports/{execution_id}/issues` exige somente `import.read` na organização
da execução. Parâmetros: `severity=error|warning` (opcional), `page>=1`
(padrão 1), `page_size=1..100` (padrão 20) e `sort=oldest|newest`
(padrão `oldest`). A ordenação por instante e ID desempata ocorrências.

Retorna `items`, `pagination` (`page`, `page_size`, `total`, `pages`), `sort`
e `generated_at` em UTC. O total corresponde **ao filtro**, enquanto
`result-summary.issues_total` representa todas as ocorrências. Não confundir
ocorrências com linhas rejeitadas: uma linha pode ter vários erros ou avisos.
Página além da última retorna lista vazia e preserva total e quantidade de
páginas; zero ocorrências retorna total e páginas zero.

Cada item possui `id`, `severity`, `safe_file_name`, `sheet_name`, `row_number`,
`column_name`, `code`, `reason`, `scope` e `occurred_at`. A projeção pública:

- gera `arquivo-<id>.csv|json|xlsx` a partir do arquivo pertencente à execução,
  sem consultar seu nome original ou caminho; extensão desconhecida é omitida;
- preserva nomes de abas e campos conhecidos nos contratos dos adapters,
  schemas e normalização, além de rótulos genéricos como CSV, Dados e Sheet1
  e letras válidas de coluna Excel;
- retorna **null** para localização desconhecida ou fora desse catálogo:
  nomes livres também podem conter dados privados. O cliente deve apresentar
  “Não informado”, sem inventar uma posição ou revelar o texto recusado;
- obtém o motivo de um catálogo público por código. Não lê o motivo livre,
  `details`, valores originais/normalizados, número de ordem ou exceções;
- converte código desconhecido em `unmapped_issue`, com orientação ao suporte;
- mantém a ocorrência, mas oculta o arquivo quando uma referência histórica
  não pertencer à mesma execução. Não segue esse vínculo para outra organização.

`GET /imports/{execution_id}/issues/export` aceita os mesmos `severity` e
`sort`. Exporta **todas** as ocorrências desse filtro, sem paginação, usando
os mesmos campos e a mesma projeção. Retorna CSV UTF-8 com BOM, cabeçalho fixo,
valores ausentes vazios e `Content-Disposition: attachment` com nome fixo
`import-issues.csv`. Protege células iniciadas por `=`, `+`, `-` ou `@`,
inclusive após espaços. CSV vazio de ocorrências continua contendo o cabeçalho.

A exportação usa cursor de servidor e lotes de 500 registros, sem materializar
toda a consulta em memória, ler o arquivo-fonte, criar temporário ou gravar
artefatos. Cursor e conexão pertencem ao ciclo da resposta e são fechados ao
concluir ou cancelar. Falha operacional na preparação retorna 503 estruturado;
interrupção depois do início do stream exige descartar o download incompleto
e repetir o GET. Não se promete um novo status HTTP após os headers enviados.

Lista e CSV verificam a execução autorizada **antes** de contagens, joins de
arquivo e paginação e reaplicam o escopo na consulta. Usam snapshots
`REPEATABLE READ READ ONLY`. A consulta compartilhada em
`pipeline_issue_query.py` preserva os filtros e a projeção legada de
`/executions/{id}/divergences`, que continua exigindo `artifact.read`.
`import.read` não concede acesso a esse recurso nem ao download da evidência.
O CSV contém apenas diagnóstico sanitizado da importação e não exige
`artifact.export`, pois não exporta a evidência original.

401, 403, 404 e 422 mantêm seus significados; falha operacional da nova consulta
retorna 503 `import_issues_unavailable`, sem exceção ou caminho privado.
As rotas não alteram resumo, dados, transições ou histórico de negócio.

O mesmo controle do vínculo anterior também se aplica agora ao campo
`duplicate_of_execution_id` do GET legado da importação e às respostas 409
do upload. O campo permanece no contrato, mas vale null sem `import.read`
na organização anterior, inclusive para quem tem apenas `import.create`.
Detecção de duplicidade, estado e referência persistida permanecem intactos.

## Implementação e validação

Os quatro blocos da #194 estão concluídos localmente. O detalhe Angular usa
os três recursos novos, com seções independentes, filtro/página na URL,
cancelamento de requisições antigas, explicações públicas pt-BR/en-US e
correlação recolhível/copiável. Ações de atualizar repetem somente GETs.

O [relatório e roteiro](import-diagnostics-validation.md) relaciona critérios,
comandos, resultados reais e [evidências sanitizadas](evidence/issue-194-validation.json).
O [runbook](runbooks/import-result-unavailable.md) orienta disponibilidade,
ausência de artefato, permissões, falhas parciais e encaminhamento ao suporte.

A validação inclui backend, PostgreSQL, Angular e navegador com autorização
real, remoção física do JSON, reconciliação de 55 ocorrências, duas organizações,
recusa por macro e zoom nativo 250% nos dois temas. A implementação está
versionada por responsabilidade, com correção posterior de revogação de acesso. A integração ainda depende da CI remota e da revisão do PR; resultados locais não representam aprovação
desses portões.
