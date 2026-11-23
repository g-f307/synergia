# Validação da versão atual e do histórico de Workorders — #195

## Identificação e limites

Validação local em 23/11/2026, API 0.18.0, PostgreSQL 16. Base Git:
`239a44e2fbd776a8c2e55373c3c1581343a8bc9c`. O código validado está versionado até
`1450aad11bbd49896f269ff3f1c0aad79443bd1f`; os hashes em
[evidências](evidence/issue-195-validation.json) e nos
[planos SQL](evidence/issue-195-query-plans.json) identificam os arquivos
medidos. A documentação e as capturas compõem o quarto commit lógico.
Publicação, CI remota e revisão são acompanhadas no PR.

Foram usados apenas dados sintéticos, bancos descartáveis separados para suíte
geral, navegador e desempenho, e portas locais exclusivas. Nenhuma planilha
real, credencial de operação, peso de modelo ou volume operacional foi usado.
Capturas não incluem tokens; traces e logs brutos permanecem fora do Git.

## Matriz de aceite

| Critério | Implementação | Evidência executada |
| --- | --- | --- |
| Uma versão atual e três históricas em A | `workorder_snapshots.py`: janela por IAM/número; API default history e UI current explícito | PostgreSQL `test_default_history_preserves_three_versions_in_one_iam_organization`, `test_api_preserves_history_default_and_exposes_current_snapshot_identity`; E2E real com `000123` |
| Mesmo número em A/B, sem vazamento | Escopo e organização solicitada antes da janela; projeção de nome IAM depois do filtro; metadados de negócio separados | PostgreSQL de interseção, ator global e recusa 401/403/404; E2E real de A/B e 409 |
| Empate estável e paginação após seleção | `updated_at DESC, id DESC`; contagem e página em transação somente leitura/repeatable read | PostgreSQL `test_current_breaks_update_tie_by_id_and_keeps_partial_snapshot_intact`, testes de ordenação e importação concorrente entre contagem/página |
| Histórico abre o snapshot exato | Links com execução e IAM; consolidado fixa os filhos na execução selecionada; cancelamento de consultas antigas | PostgreSQL `test_consolidated_children_stay_on_the_explicitly_selected_execution`; Angular de concorrência/URL; E2E real de detalhe antigo e retorno |
| Período antes da seleção | Filtros inclusivos de início da execução, normalização UTC e fuso do perfil | PostgreSQL de recorte/fuso/inversão; Angular de microssegundos; E2E real escolhe `a-tie-earlier`, mesmo com atualização fora do período |
| Nova parcial não herda campos antigos | Seleção integral da linha, sem somar/completar versões | PostgreSQL e E2E real: versão atual com planejada ausente/produzida 0; versão antiga permanece 40/20 |
| Compatibilidade e rastreabilidade | API 0.18.0 aditiva; metadados de identidade; histórico legado; lotes/seriais preservados | OpenAPI e testes de lote/serial; links de painel/relatório Angular; regressões de processamento e ciclo de vida com IAM sintético explícito |
| Visual e navegação | Shell e tabela compartilhados; filtros recolhíveis; pt-BR/en-US; estado de ambiguidade explícito | 13 E2E: 5 reais e 8 de contratos HTTP; 24 auditorias Axe sem violações; 24 capturas em 390/768/1440 px, ambos os temas e zoom nativo 250% |

## Resultados locais

- Backend sem integração: **2.391 aprovados**, 16 subtestes aprovados.
- PostgreSQL: **1.001 aprovados** na rodada completa em base nova (292,05 s).
- Angular: **490 aprovados** no bloco 3; código da aplicação web preservado no
  bloco 4, que acrescenta as jornadas integradas e a configuração de execução.
- Navegador: **27 aprovados**, sem skips ou retries: 13 da issue (cinco com
  autenticação/API/PostgreSQL reais e oito de contratos HTTP/apresentação) e
  14 da jornada operacional existente, incluindo importação, relatórios e papéis.
- Ruff, ESLint, build de produção, compilação Python, catálogo i18n, sistema
  visual, ativos, matriz de acesso e mapa de jornadas aprovados. O build mantém
  avisos de orçamento de CSS, inclusive nos componentes de consulta/detalhe;
  não foram classificados como build aprovado sem avisos.
- Corpus congelado da assistência de IA verificado, sem alteração.
- **41 migrations e 218 arquivos sintéticos** validados em base descartável.
  Nenhuma migration nova foi necessária.

A preparação da campanha corrigiu o código de organização da nova fixture para
minúsculas e o seletor do teste E2E para distinguir o JSON da API do HTML de
`/search`. A suíte ampla também identificou fixtures antigas sem IAM e um
chamador interno com `sort=newest`: as fixtures receberam IAM sintético, e o
repositório preserva a ordenação interna legada sem ampliar o enum HTTP.

A primeira execução ampla não tinha todas as variáveis/utilitários PostgreSQL
exigidos pelos testes de backup e migration. A repetição na mesma base expôs
resíduos de fixtures antigas de aprovação/e-mail; por isso a rodada definitiva
usa uma base nova. Essas falhas de preparação não foram omitidas nem tratadas
como aprovação da suíte.

## Medição SQL e decisão sobre índices

Massa dedicada e reproduzível: **50.000 snapshots**, duas organizações IAM,
5.000 números por organização e cinco versões por número. Um aquecimento e
cinco amostras em cache por operação, com `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.
Os valores abaixo são medianas locais em milissegundos; não são latências HTTP,
p95 de produção ou promessa de capacidade sob concorrência.

| Cenário | Contagem | Página |
| --- | ---: | ---: |
| Atual, A, número exato | 0,258 | 0,318 |
| Histórico, A, número exato | 0,160 | 0,270 |
| Atual, A/B, número exato | 0,206 | 0,361 |
| Atual com período | 0,222 | 0,294 |
| Versão antiga fixada por execução | 0,140 | 0,184 |

As consultas operacionais usaram `idx_workorders_number` ou a chave única
`(execution_id, workorder_number)` e não gravaram blocos temporários. Esta massa
não demonstrou necessidade de índice adicional no escopo da #195; não se criou
migration apenas para acrescentar índice sem ganho medido.

A reutilização futura da relação para agregado, sem filtro de número, também
foi sondada: **48,495 ms** em A e **93,239 ms** global. O agregado global fez
ordenação em disco com `work_mem=4MB`. Esse é um limite observado, não um ajuste
já entregue: indicadores e seu orçamento pertencem à #196. Reavaliar índices e
memória com a distribuição/concorrência representativas daquela entrega.

## Roteiro reproduzível

Use uma instância **descartável** PostgreSQL 16 e bancos novos. Configure
`DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` e `PGDATABASE` para essa
instância; disponibilize `psql`, `pg_dump` e `pg_restore` 16. Não aponte os
comandos para o banco operacional. A fixture recusa ambientes diferentes de
`test` e nomes fora de `synergia_195_*`, `synergia_ci` ou `synergia_e2e`.

1. Na base nova da suíte, execute `python scripts/validate_project_assets.py`
   com as variáveis PG explícitas, depois `python -m pytest -m integration
   backend/tests -q`. A campanha local usou os utilitários 16 do container por wrappers temporários.
   Alguns testes legados deixam resíduos: uma repetição
   completa exige outra base nova.
2. Em outro banco vazio `synergia_195_browser`, execute
   `python scripts/apply_migrations.py`. Ative o Python do backend no PATH e
   configure `E2E_PYTHON`, `E2E_API_PORT`, `E2E_WEB_PORT`, `E2E_API_COMMAND` e
   `E2E_BROWSER_EXECUTABLE_PATH` para as portas e Chromium locais disponíveis.
3. Em `web`, execute `E2E_NATIVE_ZOOM=true npm run e2e --
   --config=playwright.workorder-versions.config.ts`. O `beforeAll` cria a massa
   sintética; o login usa a senha sintética padrão do runner ou `E2E_PASSWORD`.
   O opt-in de zoom exige Chromium com suporte à extensão local já existente.
4. Confira, como leitor de A, `000123`: Atual = uma linha parcial, Histórico =
   três versões. Abra `e2e195-a-old`: quantidades 40/20. Volte e recarregue:
   modo, organização e período permanecem. Em `000456`, avance ao histórico,
   página 2, abra `e2e195-paged-12` e volte à mesma página.
5. O perfil sintético A/B vê duas linhas atuais em `000123`; abrir o número
   sem organização/execução retorna 409. O leitor A recebe 404 para execução B,
   não publicada e sem IAM; o ator sem `business.read` recebe 403.
6. Em um terceiro banco vazio `synergia_195_perf`, aplique migrations e execute
   `SYNERGIA_ENV=test python scripts/measure_workorder_queries.py --output
   /tmp/issue-195-query-plans.json`. A medição recusa uma base com Workorders
   alheias à própria massa de desempenho.

As [capturas](evidence/issue-195/), seu
[índice com hashes e auditorias](evidence/issue-195-validation.json) e os
[planos completos](evidence/issue-195-query-plans.json) acompanham este relatório.
A #196 continua responsável pelos totais do painel; a #197, pela cobertura de
fontes; a #206, pela busca parcial. Relatórios emitidos, snapshots históricos e
normalização não foram reescritos.
