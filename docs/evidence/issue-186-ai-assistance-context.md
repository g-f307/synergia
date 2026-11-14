# Validação do contexto determinístico — issue #186

Base: `0258376a24f5023fbdc2b977392e941a9aa5bdea` (merge da #185).
Contrato interno 1.0.0; API pública permanece 0.12.0, sem nova rota.
Data: 2026-11-14. Python 3.12, PostgreSQL 16 descartável.

## Evidências reproduzíveis

| Validação | Resultado local |
| --- | --- |
| `pytest -q tests/test_ai_assistance_context.py --tb=short` | 38 aprovados |
| `pytest -q -s backend/tests/test_ai_assistance_context_persistence.py --tb=short` | 11 aprovados |
| Backend: `pytest -q -m 'not integration' --tb=short` | 2091 aprovados; 830 desmarcados; 16 subtests aprovados |
| `pytest -q -m integration backend/tests --tb=short` | 830 aprovados; 2091 desmarcados |
| Backend: `ruff check . ../scripts` | aprovado |
| `python -m compileall -q backend/app` e `git diff --check` | aprovados |
| `validate_access_matrix.py`, `validate_web_journey_map.py`, `security_matrix.py --check` | aprovados; nenhuma operação pública adicionada |

Os primeiros comandos unitários são executados em backend; o comando de
persistência parte da raiz com DATABASE_URL de banco de testes. Fixtures usam
somente identificadores sintéticos e domínios `.invalid`. As permissões são
resolvidas pelo contrato ActorContext vigente. A aplicação principal não foi
iniciada; nenhum runtime/modelo de IA foi instalado ou chamado.

## Snapshots e hashes conhecidos

Arquivos em `backend/tests/fixtures/ai_context_1_0_0_<caso>.json`.
O hash é do payload canônico, excluindo generated_at e context_sha256, e não do
arquivo JSON com indentação. O envelope inteiro permanece abaixo de 8192 bytes.

| Caso | Bytes do envelope | SHA-256 do payload canônico |
| --- | --- | --- |
| completo | 1812 | `ec7c00e363f49c7c60e145324ff996d9119f8d8b41749e2f213323e0cec4e917` |
| vazio | 893 | `e40da42f57fdbf24a18aae057c9b740553fa2eca302709600da7a3bea934ced0` |
| insuficiente | 1328 | `941824b3e25fa4d52722a5a44cc53e30d89a1ae6f00d4982f61d7ac2506ad049` |
| truncado | 8039 | `cd310d85ab936446cf1f14113a1bad8abe529d048966955d7ace61de7039a304` |

O teste altera instante de geração e representação do fuso mantendo payload/hash
idênticos. Exercita controles, negações, limite de strings, nulls, duplicidade de
refs, tipos extras e suficiência. Testes negativos inserem e-mail, token, path,
reason, original_values e nomes inseguros no adaptador e no banco; não aparecem
no contexto, nos erros públicos ou nos logs. Labels de métricas são fechadas.

## Autorização e leitura consistente

403 sem permissão antes de abrir conexão. 404 uniforme para outra organização
ou execução inexistente; só consulta subject. 409 para estados ativos antes das
coleções. Falha de dados 422 e de banco 503, ambas com mensagens sanitizadas.
Integração testa filtros de cada coleção diretamente com organização errada.

`REPEATABLE READ READ ONLY` preserva subject/contagens/coleções no mesmo snapshot.
Um teste altera metadados em conexão concorrente e comprova que a leitura iniciada
continua consistente. Sete SELECTs por execução, independentemente da quantidade
de itens; contagens comparadas com o resumo real do repositório existente.

## Planos medidos

Fixture: duas organizações, cada uma com uma execução, 1.000 divergências,
1.000 pendências, 1.000 classificações, uma fonte e histórico de transições.
Consultas parametrizadas com execution_id e organização; LIMIT 21 ou 11 inclui
sentinela para registrar truncamento. Nenhum índice/migration novo.

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` na execução direcionada local:

| Consulta | Linhas retornadas | Execução observada (ms) |
| --- | --- | --- |
| counts | 1 | 2.015 |
| divergences | 21 | 0.586 |
| pending_items | 21 | 0.491 |
| classifications | 21 | 0.742 |
| evidences | 1 | 0.082 |
| state_history | 11 | 0.056 |

Cada plano tem uma execução raiz; os SELECTs são fixos, sem consulta por item.
Tempos são observações desse fixture, não SLA. O teste imprime apenas seção,
cardinalidade e tempo; não versiona planos com identificadores/valores de filtro.
A matriz de campos e a política estão no
[contrato de contexto](../architecture/ai-assistance-context-1.0.0.md).
