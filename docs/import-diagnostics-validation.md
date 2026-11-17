# Validação do diagnóstico de importações — #194

Implementação concluída e validada localmente nos quatro blocos, versionada em
quatro commits na branch `fix/194-imports-resultados-divergencias`. Os resultados
abaixo são locais; a integração depende da CI remota e da revisão do PR.
Não houve nova migration nem mudança nas regras de ingestão, deduplicação ou retenção.

O [contrato](import-result-summary.md) descreve API, precedência e sanitização.
O [runbook](runbooks/import-result-unavailable.md) orienta o diagnóstico operacional.

## Resultados executados

| Validação | Resultado |
| --- | --- |
| Suíte completa de backend sem integração | 2.371 aprovados; 16 subtests aprovados |
| Guardas do runner de fixtures | 9 aprovados adicionais |
| Suíte completa PostgreSQL 16 | 951 aprovados, incluindo 570 combinações de autorização |
| Suíte Angular completa | 458 aprovados |
| Seleção final de importações Angular | 50 aprovados; subconjunto da suíte |
| Rodada final Playwright | 55 aprovados, zero falhas, skips ou flaky |
| Cenários da #194 na rodada web | 13 com API/IAM/PostgreSQL reais e 9 com HTTP sintético |
| Axe da #194 | 15 auditorias sem violações: seis com HTTP sintético e nove integradas |
| Layout integrado | 390/768/1440 px, claro/escuro, teclado, scroll interno e tabela horizontal |
| Zoom nativo | `chrome.tabs.getZoom()=2.5`, `devicePixelRatio=2.5`, largura CSS 576 em janela de 1440; ambos os temas |
| Ruff, lint Angular e compilação | Aprovados |
| Build Angular | Aprovado; avisos de orçamento CSS, sem exceder o limite de erro de 8 KiB por componente |
| Matriz IAM, inventário web, ameaças, HTTP/CSP, i18n e norma visual | Aprovados |
| `git diff --check` e migrations publicadas | Sem erros; migrations existentes inalteradas |

Os números das seleções não devem ser somados como testes distintos. A suíte
PostgreSQL foi executada em banco próprio, separado do banco do navegador.
Backup/restauração usaram `pg_dump`/`pg_restore` 16 do mesmo contêiner descartável,
por wrappers locais no PATH; não foi utilizado o Compose operacional.

Uma primeira rodada web encontrou dois problemas de preparação dos testes:
troca de ator com cookie da sessão anterior e reuso de CSV estático que recebeu
409 por duplicidade. O helper limpa os cookies do contexto de teste e o CSV
de upload usa identificador único. A rodada final começou em banco e storage
descartáveis novos e aprovou os 55 cenários.

## Relação entre critérios e evidências

| Critério | Implementação e teste |
| --- | --- |
| Localizar erros de linha/campo | `ImportIssue`, consulta compartilhada de `pipeline_issues`, tabela traduzida. Testes PostgreSQL enviam CSV e XLSX com erro conhecido; navegador envia CSV real com dois erros na linha 2. |
| Paginação e totais reconciliados | Massa de 55 linhas/ocorrências: 35 válidas, 20 rejeitadas, 20 erros e 35 alertas. Páginas 20/20/15, filtro de alertas 20/15 e CSV com 35 ocorrências. |
| Ocorrência diferente de linha rejeitada | Upload real com duas ocorrências na mesma linha rejeitada; duas linhas lidas, uma válida, uma rejeitada, dois erros. |
| JSON removido com resumo no banco | Runner remove fisicamente o JSON sintético; legado retorna 404 e novo recurso continua `ready`. Tabela, CSV e seis contagens permanecem acessíveis. |
| JSON e resumo persistido ausentes | Fixture terminal controlada remove ambos. UI mostra indisponibilidade e suporte, sem zeros ou processamento pendente. Atualizar permanece somente leitura. |
| Estados distintos | Preparação falha, macro rejeitada, duplicidade, vínculo anterior fora do escopo, sucesso, zero ocorrências e estado ativo cobertos no PostgreSQL e navegador. |
| `import.read` suficiente e limitado | Ator com somente essa permissão acessa o diagnóstico da organização A; outra organização recebe 404, ausência de permissão 403 e ausência de autenticação 401. A rota legada de divergências continua exigindo `artifact.read`. |
| Vínculo anterior autorizado | Resumo, GET legado e 409 ocultam referência sem `import.read` na organização anterior. Testes confirmam que a referência persistida e a deduplicação permanecem intactas. |
| Falha parcial e recuperação | 503 controlado sobre uma consulta real já autorizada; contagens são preservadas e o retry recupera somente divergências. Unitários também cobrem 401/403/404/503, CSV e cancelamento de contexto. |
| Ausência de conteúdo sensível | Motivos por catálogo; sem `details`, células ou joins de valores normalizados. Canário sintético presente no banco não aparece na tabela/CSV. Metadados desconhecidos viram null; CSV protege fórmulas. |
| GET sem reparo ou processamento | Hashes de nove tabelas de negócio/histórico e inventário de arquivos iguais antes/depois das consultas. Transações `REPEATABLE READ READ ONLY` e tentativa de escrita recusada. |
| Correlação útil e discreta | Detalhes recolhíveis, ID copiável, fallback de seleção e textos pt-BR/en-US. Cópia real testada no navegador; cabeçalho preservado também em HTTP 200 indisponível. |
| Compatibilidade | API 0.16.0 aditiva; rota do artefato preservada. Filtros e projeção legados de divergências cobertos em PostgreSQL. Nenhuma cópia adicional da planilha no schema. |

O 503 do navegador é **injeção controlada de falha**, não uma indisponibilidade
real do PostgreSQL. Os demais testes integrados usam a API e autorização reais;
o arquivo de testes com HTTP sintético permanece identificado separadamente.

## Roteiro reproduzível

Requer dependências oficiais já instaladas, PostgreSQL 16 descartável e Chromium
compatível com extensões para o teste opt-in de zoom. Use o ambiente descrito em
[local-environment.md](local-environment.md). As ferramentas de fixtures recusam
bancos operacionais e storage fora das áreas de teste.

1. Crie um PostgreSQL vazio exclusivamente para testes, com banco
   `synergia_194_acceptance`. Configure `DATABASE_URL` para esse banco e
   `SYNERGIA_ENV=test`. Para a suíte PostgreSQL completa, configure também `PG*`
   para o mesmo banco e ferramentas PostgreSQL 16 no PATH.
2. Na raiz, aplique as migrations com `backend/.venv/bin/python scripts/apply_migrations.py`
   e execute `backend/.venv/bin/python scripts/bootstrap_web_e2e.py`.
3. Escolha storage novo sob `.test-tmp`, mantendo `IMPORT_STORAGE_DIR` absoluto
   no processo de teste e no servidor. A suíte prepara automaticamente as
   fixtures da #194 por `scripts/bootstrap_import_diagnostics_e2e.py`.
4. Execute a rodada integrada com portas livres e próprias:

   ```bash
   # Na raiz; DATABASE_URL já aponta somente para o banco descartável.
   export SYNERGIA_ENV=test
   export IMPORT_STORAGE_DIR="$PWD/.test-tmp/issue-194-acceptance/imports"
   export E2E_PYTHON="$PWD/backend/.venv/bin/python"
   export PATH="$PWD/backend/.venv/bin:$PATH"
   export E2E_API_PORT=18195 E2E_WEB_PORT=42195
   export E2E_RECORD_VIDEO=false E2E_NATIVE_ZOOM=true
   export E2E_BROWSER_EXECUTABLE_PATH=<chromium-local>
   cd web
   npm run e2e -- import-diagnostics-integrated.spec.ts
   # Para a regressão web completa, use uma base/storage novos e npm run e2e.
   ```

5. Para conferência manual com a fixture preparada, autentique o ator sintético
   `imports-reader.e2e@example.invalid` usando a senha sintética configurada em
   `E2E_PASSWORD`. Ele possui apenas `import.read` na organização A.
   Abra `/imports/e2e194-ready`, confira 55/35/20/35/20/35, páginas e filtro.
   Exporte alertas na segunda página: o CSV deve conter as 35 ocorrências.
6. Exclusão controlada da fixture, na raiz e **no mesmo ambiente descartável**:

   ```bash
   backend/.venv/bin/python scripts/bootstrap_import_diagnostics_e2e.py remove-artifact --execution ready
   backend/.venv/bin/python scripts/bootstrap_import_diagnostics_e2e.py remove-artifact --execution missing --persisted
   ```

   O primeiro caso permanece `ready`; o segundo fica `unavailable`. Não há
   endpoint de reparo. O comando `snapshot` registra somente hashes agregados e
   contagem de arquivos para a comparação antes/depois dos GETs.
7. Confira `/imports/e2e194-preparation`, `rejected`, `duplicate`, `duplicate-b`,
   `zero`, `success` e `active` (todos com o prefixo `e2e194-`). Observe motivo,
   ausência de contagens quando cabível e vínculo anterior somente autorizado.
8. Execute lint/testes/build e validadores normativos; registre os resultados.
   Descarte apenas os recursos criados para esse ensaio. Não remova volumes nem
   altere o banco operacional.

## Evidências sanitizadas e limites

[Manifesto JSON](evidence/issue-194-validation.json): base Git, instante de cada
cenário, hashes dos fontes locais, resultados, reconciliação imutável, zoom,
auditorias e hashes das capturas. O commit de implementação
`1e1cefb431852b721e8ca5c335fe8de336dd7e4b` contém todos os fontes testados, conferidos pelos hashes
do manifesto. A base `69591a3` fica registrada separadamente; o commit seguinte
contém somente documentação e evidências. Não se atribui o resultado à base
antiga nem à CI remota.

Capturas integradas:

| Recorte | Claro | Escuro |
| --- | --- | --- |
| 390 px | [captura](evidence/import-diagnostics-194/issue-194-real-390-light.png) | [captura](evidence/import-diagnostics-194/issue-194-real-390-dark.png) |
| 768 px | [captura](evidence/import-diagnostics-194/issue-194-real-768-light.png) | [captura](evidence/import-diagnostics-194/issue-194-real-768-dark.png) |
| 1440 px | [captura](evidence/import-diagnostics-194/issue-194-real-1440-light.png) | [captura](evidence/import-diagnostics-194/issue-194-real-1440-dark.png) |
| Zoom nativo 250% | [captura](evidence/import-diagnostics-194/issue-194-real-zoom250-light.png) | [captura](evidence/import-diagnostics-194/issue-194-real-zoom250-dark.png) |

[Resumo persistido ausente](evidence/import-diagnostics-194/issue-194-missing-persisted-summary.png).
As capturas mostram a moldura inicial; o conteúdo e as ações abaixo da dobra
permanecem acessíveis pela rolagem interna, exercitada nos testes.

Logs, JUnit, HTML e traces completos ficam ignorados em
`.test-tmp/issue-194-block4/` e `web/reports/e2e-*`. Não são anexados tokens,
credenciais, arquivos reais ou conteúdo de células ao manifesto. `docs/files/`
permanece ignorado. A exportação interrompida após headers exige descartar o
arquivo incompleto; localizações fora do catálogo público continuam “Não
informado”. A entrega não reconstrói dados ou artefatos perdidos.
