# Reconciliação de execuções — issue #193

## Resultado e limites

A implementação local unifica a projeção `outcome` e o agregado autorizado de
Visão geral, catálogo, detalhe e Modo TV. `completed` é a única situação que
participa de “Concluídas”; parcialidade, duplicidade, cancelamento e situação
desconhecida permanecem separados. Não houve alteração de schema, estados
persistidos, regras de deduplicação ou transições do pipeline.

O contrato e a compatibilidade estão em
[Acompanhamento de execuções](execution-monitoring.md#situação-canônica-e-agregado-autorizado-193).
Esta validação usa apenas dados sintéticos, PostgreSQL 16 e o build publicado
localmente com CSP. Não requer SMTP, dados de cliente, modelo de IA ou rede
corporativa. CI remota, commits, PR e revisão ainda dependem da publicação.

## Cenários e evidências

| Critério | Verificação |
| --- | --- |
| 3 concluídas, 2 com erros, 9 ignoradas, total 14 | PostgreSQL/API e navegação real painel → catálogo → detalhe → catálogo → TV → painel; igualdade das categorias e filtros efetivos. |
| Mais de 25 execuções | 30 execuções autorizadas em A; catálogo mostra 20 por página, TV consulta 25 e exibe seis recentes; cartões continuam mostrando 30. |
| Organização B e IAM desconhecido | Outras 30 execuções em B; um registro adicional sem organização IAM; testes reais de escopo, permissões independentes e exclusão mesmo com concessão global. |
| Fonte, formato e período | Predicado comum; extensão não multiplica arquivos; UTC com limites inclusivos; dias no fuso do perfil, microssegundos, empate de data e intervalo vazio. |
| Escopos distintos | `dashboard.read` e `execution.read` preservados; comparação somente quando os escopos e filtros são equivalentes; metadados visíveis em cada tela; selecionar uma organização não redefine o escopo da permissão. |
| Atualização e indisponibilidade | Conjunto anterior permanece completo e identificado; falha de resumo não publica página isolada; revogação remove linhas e totais. |
| Navegação e filtros | URLs antigas preservam a semântica de `lifecycle`; seleção canônica o substitui; retorno e entrada no TV mantêm precisão; resposta pendente não cancela outra navegação. |
| Acessibilidade e apresentação | Dois temas, 390/768/1440 px, foco e teclado, scroll interno, áreas roláveis acessíveis, campos associados ao erro e zoom nativo de 250%. |
| Compatibilidade | `status` e `lifecycle` legados preservados; indicadores mantêm datas civis antigas e mapa técnico; versão aditiva da API `0.15.0`. |
| Histórico, publicação e reprocessamento | Suíte completa de persistência e jornada operacional existente; a fixture de publicação agora declara sua organização IAM conhecida. |

Referências executáveis:

- `backend/tests/test_execution_projection*.py`, `test_execution_filters.py`,
  `test_execution_summary*.py` e `test_queries.py`;
- `web/e2e/execution-reconciliation.spec.ts`, `operational-flow.spec.ts` e
  `tv-mode.spec.ts`;
- testes Angular dos serviços, painel, catálogo, detalhe, TV e `profile-time.spec.ts`;
- [índice de evidências](evidence/issue-193/manifest.json), com base Git,
  impressão digital do código, cenário, instante e SHA-256 de cada captura.

O índice preserva o estado sem commits no instante da captura e associa as
evidências aos três commits da implementação; o quarto commit reúne E2E,
relatório e capturas. A impressão digital permite conferir também os testes.
Capturas comprovam apresentação; asserções sobre as respostas HTTP e PostgreSQL
comprovam dados. Página e resumo são requisições separadas, com instantes de
consulta próprios; a atualização do frontend publica o par completo e não
promete uma transação única entre requisições distintas.

## Massa e roteiro reproduzível

Use banco **descartável e exclusivo**, com as 40 migrations aplicadas. Os scripts
de bootstrap não devem ser apontados para o banco operacional. Exemplo de
preparação a partir da raiz, com portas locais livres:

```bash
synergia_root="$PWD"
export PATH="$synergia_root/backend/.venv/bin:$PATH"
docker run -d --rm --name synergia-193-check \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=synergia_193_e2e \
  -p 127.0.0.1:55493:5432 postgres:16-alpine
export DATABASE_URL=postgresql://postgres@127.0.0.1:55493/synergia_193_e2e
backend/.venv/bin/python scripts/apply_migrations.py
backend/.venv/bin/python scripts/bootstrap_web_e2e.py
backend/.venv/bin/python scripts/bootstrap_execution_reconciliation_e2e.py
# Banco separado para a suíte de persistência.
docker exec synergia-193-check createdb -U postgres synergia_193_regression
DATABASE_URL=postgresql://postgres@127.0.0.1:55493/synergia_193_regression \
  backend/.venv/bin/python scripts/apply_migrations.py
export PGHOST=127.0.0.1 PGPORT=55493 PGUSER=postgres PGDATABASE=synergia_193_regression
```

Se o host não possuir `pg_dump`/`pg_restore` 16, estes wrappers opcionais usam
somente o contêiner descartável acima. Execute ainda na raiz, após configurar
o `PATH` do ambiente Python:

```bash
python - <<'PY'
from pathlib import Path
directory = Path('.test-tmp/issue-193-pgtools')
directory.mkdir(parents=True, exist_ok=True)
script = '''#!/usr/bin/env python3
import os, sys, subprocess
from pathlib import Path
from psycopg.conninfo import make_conninfo
args = sys.argv[1:]
for index, argument in enumerate(args):
    if argument == '--dbname' and index + 1 < len(args):
        args[index + 1] = make_conninfo(args[index + 1], host='127.0.0.1', port='5432')
raise SystemExit(subprocess.run([
    'docker', 'exec', '-i', '-e', 'PGPASSWORD', 'synergia-193-check',
    Path(sys.argv[0]).name, *args,
], env=os.environ).returncode)
'''
for executable in ('pg_dump', 'pg_restore'):
    target = directory / executable
    target.write_text(script)
    target.chmod(0o755)
PY
export PATH="$synergia_root/.test-tmp/issue-193-pgtools:$PATH"
```

A fixture cria organizações próprias `Synthetic 193 A/B` e o ator
`reconciliation.e2e@example.invalid`, com papel Consulta apenas em A, locale
pt-BR e fuso America/Manaus. A senha sintética segue `E2E_PASSWORD` e o padrão
do bootstrap existente; nenhum segredo é incluído nas evidências.

No banco, o cenário possui 60 execuções com organização conhecida e uma sem IAM.
Em A, 14 pertencem a OWM/CSV em 01/11/2026: três concluídas, duas com erros e
nove duplicatas. As outras 16 ficam no dia seguinte, incluindo uma sem fonte e
sem arquivos. B contém 30 concluídas, invisíveis para o ator de A.

1. Entre com o ator sintético e abra a Visão geral. Sem filtros, espere 30.
2. Aplique início/fim `01/11/2026`, origem `OWM` e tipo `csv`. Espere total 14,
   Concluídas 3, Com erros 2 e Ignoradas por duplicidade 9.
3. Confira o recorte: `2026-11-01T04:00:00Z` a
   `2026-11-02T03:59:59.999999Z`, refletindo o dia em Manaus.
4. Use Consultar execução, abra uma duplicata e retorne. Confira a situação
   canônica e o status técnico traduzido, com o valor original no atributo title.
5. Abra Modo TV pelo cabeçalho. Espere 14 no total, os mesmos 3/2/9, seis
   recentes e 14 execuções/140 linhas no agrupamento OWM. Saia e confira o recorte.
6. Remova os filtros e confirme 30, independentemente das páginas; confira o
   grupo “Fonte não informada”. Filtre situação e confirme totais correspondentes.
7. A automação injeta 503 e 403 apenas nas respostas de teste para confirmar
   preservação de dados antigos e remoção após perda de autorização.

## Comandos de validação

```bash
cd backend
.venv/bin/ruff check . ../scripts
.venv/bin/pytest -q -m 'not integration'
DATABASE_URL=postgresql://postgres@127.0.0.1:55493/synergia_193_regression .venv/bin/pytest -q -m integration
cd ../web
npm run lint
CHROME_BIN=/caminho/para/chromium npm test -- --watch=false --browsers=ChromeHeadless --code-coverage
npm run build
E2E_PYTHON="$synergia_root/backend/.venv/bin/python" \
E2E_API_COMMAND="$synergia_root/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8193" \
E2E_API_PORT=8193 E2E_WEB_PORT=4293 E2E_RECORD_VIDEO=false \
E2E_BROWSER_EXECUTABLE_PATH=/caminho/para/chromium \
npm run e2e
```

Para o E2E, prefira caminhos absolutos em `E2E_PYTHON` e `E2E_API_COMMAND`:
o primeiro é executado a partir de `web/`, o segundo a partir de `backend/`.
Configure `PGHOST`, `PGPORT`, `PGUSER` e `PGDATABASE` para a mesma instância
descartável nos testes de persistência: algumas fixtures antigas usam libpq
diretamente, além de `DATABASE_URL`. Os testes de backup precisam de ferramentas
PostgreSQL 16; na execução local foram usados wrappers temporários para
`pg_dump`/`pg_restore` do próprio contêiner descartável, sem usar o Compose operacional.

Para zoom nativo, use Chromium com suporte a extensão unpacked e acrescente
`E2E_NATIVE_ZOOM=true`. O teste abre um perfil temporário, usa `chrome.tabs.setZoom`,
confirma zoom `2.5`, `outerWidth=1440`, `innerWidth=576` e `devicePixelRatio=2.5`,
e remove o perfil ao terminar. Não usa CSS zoom, pinch zoom ou simples redução
do viewport. A execução padrão da CI deixa somente esse caso opt-in sem execução;
os demais cenários continuam automáticos.

Validadores adicionais, a partir da raiz:

```bash
backend/.venv/bin/python scripts/validate_access_matrix.py
backend/.venv/bin/python scripts/validate_web_journey_map.py
backend/.venv/bin/python scripts/validate_threat_model.py
backend/.venv/bin/python scripts/security_matrix.py --check
backend/.venv/bin/python scripts/validate_i18n.py
backend/.venv/bin/python scripts/validate_visual_system.py
git diff --check
```

Ao terminar, encerre apenas o contêiner descartável criado para a validação.
Os dados sintéticos não alteram o banco operacional e `docs/files/` continua ignorado.

## Capturas

As referências são o shell vigente, os catálogos/detalhes de execuções e
pendências e o monitor TV existente. Foram preservados moldura, hierarquia e
scroll interno. Os ajustes visuais corrigem contraste, foco, áreas de toque,
overflow e scroll por teclado; não redesenham o shell.

| Tamanho/tema | Visão geral | Catálogo | TV | Fontes |
| --- | --- | --- | --- | --- |
| 390 claro | [captura](evidence/issue-193/issue-193-dashboard-390-light.png) | [captura](evidence/issue-193/issue-193-executions-390-light.png) | [captura](evidence/issue-193/issue-193-tv-390-light.png) | [captura](evidence/issue-193/issue-193-sources-390-light.png) |
| 390 escuro | [captura](evidence/issue-193/issue-193-dashboard-390-dark.png) | [captura](evidence/issue-193/issue-193-executions-390-dark.png) | [captura](evidence/issue-193/issue-193-tv-390-dark.png) | [captura](evidence/issue-193/issue-193-sources-390-dark.png) |
| 768 claro | [captura](evidence/issue-193/issue-193-dashboard-768-light.png) | [captura](evidence/issue-193/issue-193-executions-768-light.png) | [captura](evidence/issue-193/issue-193-tv-768-light.png) | [captura](evidence/issue-193/issue-193-sources-768-light.png) |
| 768 escuro | [captura](evidence/issue-193/issue-193-dashboard-768-dark.png) | [captura](evidence/issue-193/issue-193-executions-768-dark.png) | [captura](evidence/issue-193/issue-193-tv-768-dark.png) | [captura](evidence/issue-193/issue-193-sources-768-dark.png) |
| 1440 claro | [captura](evidence/issue-193/issue-193-dashboard-1440-light.png) | [captura](evidence/issue-193/issue-193-executions-1440-light.png) | [captura](evidence/issue-193/issue-193-tv-1440-light.png) | [captura](evidence/issue-193/issue-193-sources-1440-light.png) |
| 1440 escuro | [captura](evidence/issue-193/issue-193-dashboard-1440-dark.png) | [captura](evidence/issue-193/issue-193-executions-1440-dark.png) | [captura](evidence/issue-193/issue-193-tv-1440-dark.png) | [captura](evidence/issue-193/issue-193-sources-1440-dark.png) |
| Zoom 250% claro | [captura](evidence/issue-193/issue-193-dashboard-zoom250-light.png) | [captura](evidence/issue-193/issue-193-executions-zoom250-light.png) | [captura](evidence/issue-193/issue-193-tv-zoom250-light.png) | — |
| Zoom 250% escuro | [captura](evidence/issue-193/issue-193-dashboard-zoom250-dark.png) | [captura](evidence/issue-193/issue-193-executions-zoom250-dark.png) | [captura](evidence/issue-193/issue-193-tv-zoom250-dark.png) | — |

## Resultados locais

Rodada final em 17/11/2026, sobre a base indicada no manifesto e as alterações
locais da #193:

| Validação executada | Resultado |
| --- | --- |
| Backend — suíte sem integração | 2.303 aprovados; 16 subtestes aprovados; 921 casos de integração não selecionados. |
| Backend — suíte PostgreSQL completa | 921 aprovados; 2.303 casos sem integração não selecionados. Inclui os dois novos cenários de escopo global/múltiplas organizações com filtro. |
| Angular com cobertura | 429 aprovados após a revisão. |
| Playwright — suíte padrão completa, com zoom nativo habilitado | 33 aprovados, sem falhas, retries ou casos pulados; inclui os 10 cenários da #193 e as jornadas anteriores. |
| Auditoria Axe das telas da #193 | 31 auditorias sem violações; 31 capturas indexadas. |
| Zoom nativo | 250%, viewport de layout 576 px em janela de 1440 px, DPR 2,5. |
| Ruff, ESLint e build | Aprovados; build Angular publicado e validado sob CSP; `compileall` Python aprovado. |
| Contratos e documentação | Matriz de acesso (111 operações/555 combinações), rotas (36/118 operações OpenAPI), ameaças, HTTP/CSP, ativos, i18n (1.013 chaves por catálogo) e sistema visual aprovados. |
| Integridade local | `git diff --check`, hashes das capturas e links do relatório aprovados; `docs/files/` e logs locais continuam ignorados. |

Os avisos de depreciação de Starlette e os avisos de orçamento CSS não impediram
as suítes nem o build; os limites de erro não foram ampliados. Os logs desta
confirmação ficam localmente em `.test-tmp/issue-193-final/`, fora do Git.
Na revisão final, dois testes novos reproduziram a remoção indevida de
`lifecycle` ao reaplicar filtros de um link antigo sem selecionar `outcome`.
A comparação agora normaliza a seleção vazia; painel e catálogo mantêm o filtro
legado até a escolha de uma situação canônica. A suíte Angular e o E2E foram
reexecutados, incluindo o recorte legado de 12 execuções, e a condição duplicada
de proteção da navegação foi removida. Os resultados de backend acima continuam
aplicáveis: seu código não foi alterado nesta revisão.

A implementação e os quatro blocos estão concluídos localmente. Publicação,
CI remota, revisão do PR e merge permanecem pendentes; a issue não foi encerrada.
A entrega foi organizada em quatro commits locais por responsabilidade. Nenhum
push foi feito nesta etapa. O banco e os serviços de teste foram usados em
isolamento do ambiente operacional.
