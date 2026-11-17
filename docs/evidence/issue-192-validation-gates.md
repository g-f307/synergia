# Portões de Validação Integrada — Issue #192

## O que foi comprovado localmente no sandbox

| Portão / Verificação | Escopo comprovado no sandbox | Evidência / Denominador |
| --- | --- | --- |
| Separação experimental (código/rotas/OpenAPI) | `/ai/quality` ausente de `app.main`, router Angular, navegação e Dockerfiles; assets offline em `scripts/` | `test_ai_experimental_removal.py` (4/4), `test_web_journey_map.py`, `validate_web_journey_map.py`, `validate_access_matrix.py`, `validate_i18n.py` |
| Corpus congelado | 30 casos únicos em 5 categorias disjuntas, 2 orgs, múltiplas fontes, negações, instruções, controles, refs ausentes e alto volume; confinamento de paths e anti-adulteração | `data/synthetic/ai-assistance-v1/manifest.json`, `test_ai_assistance_corpus.py` (3/3) |
| Campanha controlada (`ci-fake`) | Validação por contrato/grounding real, preservação de rodadas e bytes brutos locais, falha não-zero quando runtime indisponível ou model/digest divergem | `test_ai_assistance_campaign.py` (4/4), `run_ai_assistance_campaign.py --mode ci-fake` (30/30) |
| Portões HTTP unitários (com overrides) | Transporte HTTP/pin, mismatch de digest, flags e rejeição de saídas inválidas | `test_ai_assistance_e2e_gates.py` (3/3) |
| Segurança do runner descartável e empacotador | Rejeição de URL/senha enganosa, recusa de banco não vazio, reconciliação exata de conjuntos e empacotamento zip confinado | `test_validate_issue_192_disposable.py` (3/3), `test_package_issue_192_evidence.py` (1/1) |
| Microbenchmark sem inferência | Apenas `SyntheticContextReader + prepare_prompt` (não inclui PostgreSQL/auth/persistência) | `run_ai_assistance_campaign.py --mode ci-fake` |

## Revisão independente no host — 16/11/2026 (America/Manaus)

| Verificação | Resultado observado | Limite da comprovação |
| --- | --- | --- |
| Regressões de documentação, campanha, empacotamento e runners | 52 testes aprovados no Python 3.12 | Subconjunto reproduzido pelo revisor; o executor registrou 96 testes direcionados |
| Integração PostgreSQL/API | Teste autocontido aprovado, autenticação real e duas organizações; hashes do conteúdo de negócio preservados | Inferência substituída somente por HTTP controlado |
| Leitura sem inferência | 5 aquecimentos e 30 amostras por operação; p95 detalhe = 86,97 ms e latest = 120,14 ms | Mede GETs reais; não comprova separadamente todas as etapas de geração |
| Instalação e rollback | 40 migrations aplicadas, rollbacks 0040–0037 exercitados em transação revertida, ledger mantido em 40 | Banco descartável novo; não executado no banco operacional |
| Frontend | 402 testes Angular aprovados; lint/build aprovados | Chromium headless e Node 22 |
| E2E | 8 testes aprovados em banco novo, incluindo importação XLSX real, reuso contado e recusa da organização B | Provider controlado; cenários visuais de indisponibilidade/flag ainda usam interceptação |
| Acessibilidade e layout | Axe sem violações nos estados exercitados, 390 px e zoom nativo de 250% | Escopo do card de assistência; não é auditoria de toda a aplicação |
| Artefatos de produção | Bundle real (53 arquivos), imagem backend e imagem web sem marcadores experimentais | Imagens exclusivas de revisão; aplicação existente não foi substituída |
| Auditoria | Exercício operacional existente executado novamente: 20 eventos reconciliados na pesquisa real do Graylog | Runtime HTTP sintético; não é correlação de cada caso da campanha Qwen |
| Observabilidade | promtool aprovou alertas de IA e regras de dashboard (42 regras) | Não substitui validação em infraestrutura corporativa |

Os três testes de reprodutibilidade XLSX que falharam na suíte ampla também
falham na `main`, inclusive com Python 3.12. A regressão nova de documentação
foi corrigida e os 42 testes documentais passaram. A causa das falhas de baseline
não foi atribuída a uma versão de Python sem comprovação.

As campanhas Qwen são preservadas por rodada, inclusive falhas. A tentativa
inicial encontrou `runtime_pin_mismatch` antes de inferir; ela não conta como
aprovação de modelo. O ensaio seguinte utiliza runtime isolado e manifesto
original com o digest congelado, sem alterar pesos, prompt ou critérios.

## Portão de conclusão e pendências

**Integração ainda não declarada concluída.** A feature continua desligada por
padrão. Este registro não autoriza ativação produtiva nem encerramento da milestone.

- Consolidar o resultado final da campanha real, incluindo rejeições e timeouts.
- Completar medição sem inferência das etapas de contexto e persistência de geração.
- Executar navegação integrada por cada tipo de referência disponível, não somente DIV.
- Comprovar no navegador flag e indisponibilidade reais no servidor, sem interceptação.
- Reconciliar a mesma jornada importação/assistência com Graylog; o exercício de
  20 recibos acima é complementar, não substituto dessa jornada.
- Validar implantação equivalente a homologação e obter resultados da CI do PR.

## Capturas da jornada sintética integrada

As capturas usam autenticação, importação e persistência reais com inferência
controlada. Não são evidências de conteúdo produzido pelo Qwen.

![Resultado persistido após importação real com provider controlado](issue-192-real-import-controlled.png)

![Card em tema escuro e viewport de 390 px com provider controlado](issue-192-mobile-controlled.png)

## Comandos de reprodução

1. **Campanha real com Qwen fixado:**
   `SYNERGIA_AI_ASSISTANCE_ENDPOINT=http://127.0.0.1:11434 backend/.venv/bin/python scripts/run_ai_assistance_campaign.py --mode real --output-dir .local-evidence/issue-192`
2. **Ensaio integrado real em PostgreSQL + p95 real de API/DB (sem overrides de auth/org/repo):**
   `DATABASE_URL="$SYNERGIA_192_DB_URL" backend/.venv/bin/pytest -q backend/tests/test_ai_assistance_integration_192.py`
3. **Migrations e rollback em banco descartável exclusivo da #192:**
   `SYNERGIA_ENV=test backend/.venv/bin/python scripts/validate_issue_192_disposable.py --database-url "$SYNERGIA_192_DB_URL" --output .local-evidence/issue-192/migrations-rollback.json`
4. **Suíte Angular (lint, unit, build), E2E Playwright + Axe e checagem de bundle/imagem:**
   - `cd web && npm run lint && npm test -- --watch=false --browsers=ChromeHeadless && npm run build`
   - `cd web && npx playwright test --config=playwright.assistance.config.ts`
   - `backend/.venv/bin/python scripts/check_experimental_absence_in_artifacts.py --web-dist web/dist/synergia-web/browser --backend-image <img-backend> --web-image <img-web>`
5. **Empacotamento único local de evidências:**
   `backend/.venv/bin/python scripts/package_issue_192_evidence.py --evidence-dir .local-evidence/issue-192`
