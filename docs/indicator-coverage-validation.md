# Validação de subtotais e cobertura dos indicadores — #196

## Identificação e limites

Validação local em **24/11/2026**, API **0.19.0**, PostgreSQL 16. Base Git:
`d87248d`. O backend e o frontend estão versionados até
`d55625e3fb243efbecc2c51ee4cfad3e904b5986`. Os hashes dos arquivos
validados estão no [manifesto sanitizado](evidence/issue-196-validation.json)
e nos [planos SQL](evidence/issue-196-query-plans.json). Essas referências
identificam as fontes medidas antes do versionamento. Testes de validação,
documentação e capturas compõem o quarto commit lógico. Publicação, CI remota
e revisão são acompanhadas no PR.

Foram usados apenas dados sintéticos e bancos descartáveis separados para
regressão, navegador, desempenho e assets. Nenhum serviço operacional, planilha
real, credencial de operação ou modelo de IA foi usado. Logs brutos, relatórios
Playwright com tokens e traces ficam fora do Git; somente capturas sintéticas
e resultados sanitizados integram as evidências.

## Matriz de aceite

| Critério da issue | Implementação | Teste e evidência executados |
| --- | --- | --- |
| 4/null/0 → subtotal 4 e cobertura 2/3; zero informado | `workorder_indicators.py`: SUM ignora null e COUNT FILTER conta zero | PostgreSQL `test_four_null_zero_is_known_subtotal_and_zero_is_informed`; API `test_indicators_add_current_coverage_without_redefining_legacy_values`; Angular e E2E real `4/null/0 reconciles…` |
| Uma nova versão não duplica soma ou denominador | Mesma seleção atual por IAM/número da #195, com desempate por atualização/id | PostgreSQL `test_new_version_replaces_value_without_increasing_denominator`, `test_update_tie_is_broken_by_snapshot_id`; API `test_updated_version_reconciles_coverage_current_list_and_exact_detail`; E2E real troca 4 por 7 e mantém 3 Workorders |
| Completo, parcial, ausente e vazio distinguíveis | `QuantityCoverageResponse`, exemplos OpenAPI e quatro estados na UI | PostgreSQL `test_complete_zero_missing_and_partial_zero_are_distinct`, `test_all_null_quantities_remain_missing_without_inventing_subtotals`, `test_empty_never_invents_zero_or_a_coverage_percentage`; Angular e navegador vazio/PT/EN |
| Total, soma e links respeitam organização, período e versão | Filtros antes da janela; agregado e lista current compartilham seleção; detalhe fixado por execução/IAM | PostgreSQL de IAM, período, filtros, execução fixada e paginação; API/JWT real A/B/global/externa; E2E real de período antigo, retorno e nova versão |
| Subtotal não é total completo; sem meta inventada | Rótulo Subtotal conhecido, X/Y e barras de cobertura; ausência não usa zero nem campo histórico | Angular de rótulos, arredondamento PT/EN e ausência; capturas nos 3 tamanhos/2 temas e zoom 250% |
| Compatibilidade legada | `workorders`/`quantities` mantêm histórico e all-or-nothing; `workorders_current`/`quantities_coverage` são aditivos; API related default history | API compara histórico produzido=500 com atual produzido=0; default history e current explícito; exemplos OpenAPI e regressão PostgreSQL completa |
| Autorizações independentes sem forçar igualdade | Painel: dashboard.read; detalhes: interseção com business.read; scope efetivo na API e diferença explícita na UI | API `test_current_scope_is_permission_intersection_not_an_expansion`; Angular sem link proibido/escopo menor; E2E real A/B agregado=4 e lista autorizada A=3 |
| Leitura consistente e imutabilidade | Transação somente leitura/repeatable read; sem escrita nem preenchimento de uma versão por outra | `test_reader_preserves_callers_snapshot_and_historical_rows`, `test_current_list_count_and_rows_share_the_same_read_snapshot`; regressões completas de auditoria/histórico |
| Contrato visual, teclado e acessibilidade | Shell/scroll interno existentes; texto alternativo às barras; meter com nome/valores e PT/EN | 13 E2E (4 reais e 9 sintéticos), 16 auditorias Axe sem violações; teclado Enter no link do cartão; zoom nativo 2,5 confirmado por API de abas e devicePixelRatio |

O total do cartão e da lista coincide quando **filtros e escopos efetivos**
coincidem. Se o painel permite A/B e os detalhes somente A, a diferença é
explicitada; os números do agregado não são reduzidos e o acesso não é ampliado.

## Resultados executados

- **2.394 testes sem integração**, mais **16 subtestes**, aprovados; depois,
  **7 guardas adicionais** da fixture de validação aprovados: 2.401 casos únicos.
- **1.030 testes PostgreSQL únicos aprovados**, incluindo 29 específicos dos
  novos agregados/API e as regressões da #195, autorização, auditoria, histórico,
  SMTP, backup e migrations. Não houve migration nova.
- **506 testes Angular aprovados**, com cobertura: statements 81,45%, branches
  69,77%, functions 73,58%, lines 86,73% (suíte global, não apenas a issue).
- **13 E2E aprovados**: 4 com login/API/PostgreSQL reais e 9 com HTTP sintético,
  incluindo temas claro/escuro, 390/768/1440 px, PT/EN e zoom nativo 250%.
- **16 auditorias Axe sem violações** e 16 capturas, relacionadas a cenário,
  instante da campanha, base Git e hashes no manifesto.
- Ruff, ESLint, compileall, catálogos PT/EN, ativos, sistema visual, baseline HTTP,
  matrizes de acesso/jornadas/ameaças/segurança, verificadores das Etapas 5/6,
  schemas AJV das PoCs e corpus congelado da assistência aprovados. Os
  verificadores de Etapa 5/6 preservam os estados formais de liberação pendentes;
  sua aprovação técnica não autoriza liberação operacional.
- **41 migrations e 218 arquivos sintéticos** validados em outra base vazia.
- Build Angular aprovado **com avisos de orçamento CSS**. O dashboard passou
  de aproximadamente 5,31 para 5,88 kB; warning 4 kB e limite de erro 8 kB.
  Outros componentes já emitem avisos semelhantes. Nenhum limite foi elevado.
- `git diff --check` aprovado. Nenhum dado real ou relatório bruto integra a entrega.

A primeira rodada PostgreSQL teve 941 aprovações e 89 erros de preparação:
fixtures de migrations/SMTP usam conexões sem `DATABASE_URL` e precisavam de
`PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE`. Esses mesmos 89 casos foram repetidos
com a configuração correta e passaram; a identidade de cada caso foi conferida
nos JUnit. Os utilitários PostgreSQL 16 vieram do próprio container por wrappers
temporários. Não se declarou aquela primeira rodada como inteiramente verde.

A CI inicial do PR #233 encontrou quatro violações E501 no script de medição.
O Ruff executado da raiz não aplicava a mesma configuração aos scripts; o
comando correto, `cd backend && .venv/bin/ruff check . ../scripts`, reproduziu
a falha e passou após dividir as linhas. AST e strings SQL foram comparadas
antes/depois e permaneceram idênticas; as medições não foram repetidas. Os
manifestos preservam o hash medido e identificam o arquivo após a formatação.

A primeira campanha E2E confirmou os fluxos principais, mas falhou em três
cenários por preparação: URLs do dashboard usavam `started_from/started_to`
(parâmetros da API), em vez de `date_from/date_to` (parâmetros da tela), e o
perfil sintético não tinha `session.revoke.own` para trocar de usuário pelo
logout. As fixtures/testes foram corrigidos; a campanha final passou integralmente.

## Desempenho e decisão de schema

Massa reproduzível: **50.000 snapshots**, duas organizações IAM, 5.000 números
por organização e cinco versões por número. Reutiliza a distribuição da #195,
com planned/released 70% informados, recebida zero completo e produzida ausente
na versão mais nova; o recorte de período seleciona uma versão anterior completa.
Um aquecimento e cinco amostras em cache, com `EXPLAIN (ANALYZE, BUFFERS)`.

| Cenário | Agregado de cobertura | Contagem da lista | Página atual | Repositório completo de indicadores |
| --- | ---: | ---: | ---: | ---: |
| Organização A | 48,128 ms | 42,348 ms | 53,804 ms | 73,333 ms |
| Global A/B | 112,928 ms | 88,213 ms | 119,028 ms | 122,141 ms |
| A com período | 20,670 ms | 16,814 ms | 23,124 ms | 40,815 ms |

A última coluna mede tempo de parede, conexão e todas as consultas legadas/atuais
do repositório. As outras colunas medem operações SQL separadas; a listagem usa
contagem e página. Não são latências HTTP, p95 ou capacidade sob concorrência.

Com `work_mem=4MB`, o agregado global gravou **484 blocos temporários**; em A e
no período não houve temporários. A página global também usou disco. Trata-se
de uma limitação medida, já relacionada à seleção da #195, e não de uma garantia
de escala. Os resultados locais, sem SLO operacional definido, não justificam
uma migration de índice nem alteração global de memória nesta entrega. Volume,
concorrência e distribuição reais devem orientar eventual otimização posterior;
a avaliação não presume que o desempenho em produção será igual ao local.

## Roteiro reproduzível

Use PostgreSQL 16 **descartável**. Configure `DATABASE_URL` e todas as variáveis
`PG*` explicitamente para ele; disponibilize `psql`, `pg_dump` e `pg_restore` 16.
A fixture da issue exige `SYNERGIA_ENV=test` e um banco com nome
`synergia_196_*`, `synergia_ci` ou `synergia_e2e`.

1. Em uma base nova da regressão, aplique migrations com
   `python scripts/apply_migrations.py`. Execute
   `python -m pytest -q -m integration backend/tests`. Para as verificações de
   backup, use diretórios temporários próprios em `IMPORT_STORAGE_DIR` e
   `PROFILE_AVATAR_STORAGE_ROOT`. Execute também
   `python -m pytest -q -m 'not integration' backend/tests`.
2. Em outra base vazia, como `synergia_196_browser`, aplique migrations. Configure
   `E2E_PYTHON`, `E2E_API_PORT`, `E2E_WEB_PORT`, `E2E_API_COMMAND` e
   `E2E_BROWSER_EXECUTABLE_PATH`. Use portas exclusivas: o runner recusa reutilizar
   servidores já abertos. Em `web`, execute:

   ```bash
   E2E_NATIVE_ZOOM=true npm run e2e -- --config=playwright.indicator-coverage.config.ts
   ```

   O `beforeAll` prepara a massa e os quatro perfis com e-mails `.invalid`;
   a senha sintética padrão é a mesma do runner existente, substituível por
   `E2E_PASSWORD`. Zoom exige Chromium com suporte à extensão local existente.
   A última prova acrescenta uma versão: use uma base nova para repetir a campanha.
   A campanha termina com subtotal 7. Os passos manuais 3–5 abaixo descrevem a
   massa inicial: para segui-los, prepare outra base vazia, aplique migrations e
   execute `SYNERGIA_ENV=test python scripts/bootstrap_indicator_coverage_e2e.py`
   sem `--append-version`, em vez de executar primeiro a campanha inteira.
3. Como `coverage-reader.e2e@example.invalid`, abra Visão geral, organização
   **Synthetic 196 A**, período de **01/10/2026 a 05/10/2026** no fuso Manaus.
   Espere 3 Workorders atuais, planejada **4 / Subtotal conhecido / 2 de 3 / 66,7%**,
   produzida **0 / 3 de 3 / 100%**, recebida **Não informado / 0 de 3** e liberada
   **0 / Subtotal conhecido / 2 de 3**. O histórico tem 4 registros, sem influenciar
   esses valores atuais.
4. Clique **Ver Workorders**: espere 3 linhas e período/organização mantidos.
   Abra WO-001: execução `e2e196-a-1`, quantidade planejada 4. Volte e recarregue:
   lista, modo e filtros permanecem. Limite o período à primeira data: espere
   uma Workorder antiga com planejada 400 e detalhe `e2e196-a-old`.
5. O perfil `coverage-both.e2e@example.invalid`, sem filtro organizacional, vê
   4 Workorders atuais e subtotal planejado 1.003. O perfil
   `coverage-restricted.e2e@example.invalid` vê o mesmo agregado, aviso de escopo
   mais restrito e lista de apenas 3 Workorders A. O perfil `coverage-denied`
   vê indicadores de A, sem link de detalhes; a API recusa a lista com 403.
6. Um período futuro vazio mostra **Sem Workorders no período**, sem quantidade
   zero nem barra fictícia. Para a substituição controlada, execute:

   ```bash
   SYNERGIA_ENV=test python scripts/bootstrap_indicator_coverage_e2e.py --append-version
   ```

   Agora WO-001 atual tem planejada 7, o subtotal passa a 7 e o denominador
   continua 3. A execução antiga e seu conteúdo permanecem consultáveis.
7. Em uma terceira base vazia `synergia_196_perf`, aplique migrations e execute:

   ```bash
   SYNERGIA_ENV=test python scripts/measure_indicator_coverage.py --output /tmp/issue-196-query-plans.json
   ```

   O script recusa Workorders alheias à massa de desempenho e nunca altera dados
   operacionais. Em uma quarta base vazia, execute `validate_project_assets.py`
   com as variáveis PG explícitas para conferir migrations e corpus sintético.
8. No frontend, execute lint, teste com cobertura e build. Confira os quatro
   estados, teclado, temas e tamanhos pelas [capturas](evidence/issue-196/).
   PT usa 66,7%; EN usa 66.7%; a API preserva o valor sem arredondamento.

## Pendências externas ao checkpoint local

A entrega está organizada em quatro commits lógicos. Publicação e PR com
`Closes #196` são acompanhados no GitHub; CI remota, revisão e merge por squash
continuam sendo portões de conclusão, sem aprovação antecipada neste relatório.
Cobertura de **fontes** e aplicabilidade de campos continuam fora do contrato
quantitativo desta issue, conforme #197; não há metas corporativas inferidas.
