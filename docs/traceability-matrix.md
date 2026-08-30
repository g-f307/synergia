# Matriz de rastreabilidade da Etapa 0

Esta matriz liga requisitos, regras, issues, implementação e evidências
automatizadas. `Atendido` significa que a capacidade está implementada e
coberta na fundação atual; não implica que integrações futuras estejam prontas.

| Requisito | Tipo | Regra ou decisão relacionada | Issue | Implementação principal | Evidência automatizada | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| Frontend oficial em Angular sem substituir o protótipo publicado | NF | Angular é a implementação; protótipo é referência separada | [#1](https://github.com/g-f307/synergia/issues/1) | `frontend-angular/src/app/`, `angular.json` | `app.component.spec.ts`; job `frontend` | Atendido |
| Congelar e publicar o protótipo navegável sem duplicá-lo na `main` | NF | branch `prototype-pages` e tag imutável | [#2](https://github.com/g-f307/synergia/issues/2) | branch `prototype-pages`; configuração GitHub Pages | job `prototype` verifica `index.html`, `styles.css` e `script.js` | Atendido |
| Validar aplicação e dados sem alterar a branch publicada | NF | PRs contra `main`; protótipo somente leitura | [#3](https://github.com/g-f307/synergia/issues/3) | `.github/workflows/ci.yml`, `scripts/validate_project_assets.py` | quatro jobs do workflow `CI` | Atendido |
| Persistir execuções, fontes, Workorders, lotes, seriais, pendências e auditoria | F/NF | rastreabilidade por execução e arquivo; IDs como texto; liberação parcial | [#4](https://github.com/g-f307/synergia/issues/4) | `database/migrations/0001_*` e `0002_*` | `backend/tests/test_persistence.py` | Atendido |
| Importar CSV, JSON e XLSX manualmente com ator, hash e evidência | F | fonte e ator obrigatórios; duplicidade SHA-256; original preservado | [#5](https://github.com/g-f307/synergia/issues/5) | `backend/app/imports.py`, migration `0003_*` | `backend/tests/test_imports.py`, `test_persistence.py` | Atendido |
| Validar estrutura, tipos, fórmulas, identificadores e relações antes de consolidar | F | erro impeditivo bloqueia; aviso não bloqueia; ocorrência rastreável | [#6](https://github.com/g-f307/synergia/issues/6) | `backend/app/validation.py`, migration `0004_*` | `test_validation.py`, `test_imports.py` e massas `invalid/` | Atendido |
| Normalizar fontes sem alterar valores originais | F/NF | aliases declarativos; IDs textuais; estados/flags rastreáveis | [#7](https://github.com/g-f307/synergia/issues/7) | `backend/app/normalization.py`, `model/normalization_rules.json`, migration `0005_*` | `test_normalization.py`, `test_persistence.py` | Atendido |
| Consolidar por Workorder, Demand ID, lote, modelo e serial | F | precedência de quantidades; proveniência; conflitos não contaminam Workorder | [#8](https://github.com/g-f307/synergia/issues/8) | `backend/app/consolidation.py`, `processing.py`, `pipeline.py` | `test_consolidation.py`, `test_processing.py`; `consolidation_records.json`; `wo-status-reference.csv` | Atendido |
| Classificar OQC, holds, rework, bloqueio, aging e impacto em container | F | catálogo versionado; categorias simultâneas; fila ativa determinística | [#9](https://github.com/g-f307/synergia/issues/9) | `backend/app/business_rules.py`, `processing.py`, `model/business_rules.json` | `test_business_rules.py`, `test_processing.py`; `rules_scenarios.json` | Atendido |
| Consultar execução, Workorder, lote e serial por API | F | frontend usa API, nunca banco ou arquivos diretamente | [#10](https://github.com/g-f307/synergia/issues/10) | `backend/app/queries.py`, `main.py` | `test_queries.py`, `test_query_persistence.py` | Atendido |
| Listar pendências ativas e consultar detalhe, histórico e consolidado | F | `open` por padrão; filtros/paginação; mesma execução no consolidado | [#10](https://github.com/g-f307/synergia/issues/10) | `backend/app/queries.py` | `test_queries.py`, `test_query_persistence.py` | Atendido |
| Reprocessar sem sobrescrever a execução anterior | F/NF | nova tentativa e evento auditável; execução ativa gera conflito | [#10](https://github.com/g-f307/synergia/issues/10) | `PostgresQueryRepository.request_reprocessing` | `test_queries.py`, `test_query_persistence.py` | Atendido |
| Expor OpenAPI e erros HTTP seguros e estáveis | NF | envelope `error`; detalhes internos não são retornados | [#10](https://github.com/g-f307/synergia/issues/10) | `backend/app/errors.py`, modelos de `queries.py` | testes de erro e OpenAPI em `test_queries.py` e `test_imports.py` | Atendido |
| Apresentar indicadores operacionais básicos | F | agregados não substituem histórico auditável | [#10](https://github.com/g-f307/synergia/issues/10) | endpoint `/indicators` em `backend/app/queries.py` | `test_returns_basic_indicators`; integração PostgreSQL | Atendido |
| Persistir consolidados, classificações, decisões OQC, pendências e proveniência | F/NF | transação por Workorder; rollback isolado; regra e prioridade versionadas; integridade por execução | [#25](https://github.com/g-f307/synergia/issues/25) | `backend/app/persistence.py`, migration `0008_*`, `PostgresQueryRepository.get_consolidated` | `test_processing_persistence.py`; suíte de integração PostgreSQL | Atendido |
| Controlar estados, idempotência e reprocessamento seguro | F/NF | transições autorizadas; fingerprint por arquivos e versões; lock da raiz; histórico imutável | [#26](https://github.com/g-f307/synergia/issues/26) | `backend/app/execution.py`, migration `0009_*`, repositórios de importação e consulta | `test_execution.py`, `test_execution_lifecycle.py`; PostgreSQL 16 | Atendido |

## Estados usados

- **Atendido:** implementado, documentado e com evidência automatizada.
- **Parcial:** parte verificável foi entregue, mas resta capacidade da mesma
  obrigação.
- **Planejado:** aceito no roadmap, sem implementação vigente.
- **Bloqueado:** depende de decisão ou recurso externo registrado.

## Manutenção

Toda PR que alterar uma capacidade desta matriz deve atualizar a linha
correspondente. Nova capacidade deve adicionar linha com issue e teste; mudança
de regra deve apontar a versão do catálogo aplicável. Componentes futuros de
[architecture.md](architecture.md) permanecem `Planejado` até possuírem issue,
implementação e evidência próprias.
