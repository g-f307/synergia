# Roteiro de demonstração e checklist operacional da Etapa 5

Execute apenas em ambiente descartável, com identidades `.invalid`, fixtures
sintéticas e segredos efêmeros. Não copie tokens, DSN, caminhos privados ou
payloads para o PR.

## 1. Reconstruir

```bash
docker compose down --volumes --remove-orphans
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U synergia -d synergia
python scripts/validate_project_assets.py
```

Confirme que as 27 migrations foram aplicadas em ordem e que nenhum volume
anterior foi reutilizado. O procedimento destrói somente o volume local deste
Compose.

## 2. Executar regressões e build

```bash
backend/.venv/bin/ruff check backend scripts
backend/.venv/bin/pytest -q -m "not integration"
DATABASE_URL=postgresql://synergia:synergia-local-only@127.0.0.1:5432/synergia \
  backend/.venv/bin/pytest -q -m integration backend/tests
python scripts/validate_stage5_release.py
npm --prefix web run lint
npm --prefix web test -- --watch=false --browsers=ChromeHeadless --code-coverage
npm --prefix web run build
docker compose config
git diff --check
```

Não publique arquivos sob `reports/private`, `.test-tmp` ou `artifacts/`. A CI
sanitiza JUnit e relatórios de segurança antes de expô-los.

## 3. Demonstrar a jornada real

Crie um banco vazio `synergia_e2e`, aplique migrations, execute
`scripts/bootstrap_web_e2e.py` e então:

```bash
cd web
DATABASE_URL=postgresql://synergia:synergia-local-only@127.0.0.1:5432/synergia_e2e \
E2E_BROWSER_CHANNEL=chrome E2E_RECORD_VIDEO=false npm run e2e
```

Durante a demonstração, identifique no mesmo fluxo:

1. login do operador e upload N-FP/GMES-OQC;
2. processamento e consulta de execução/Workorder no PostgreSQL;
3. geração, visualização e exportação segura de relatório;
4. notificação interna e preferências persistidas;
5. envio, atribuição, devolução, reenvio e decisão segregada;
6. captura local idempotente do e-mail, sem alegar SMTP corporativo;
7. negação por papel/organização, sessão revogada e upload hostil;
8. recuperação após indisponibilidade temporária da API;
9. idioma inglês, navegação por teclado, Axe e viewport 390 × 844.

## 4. Demonstrar controles operacionais

- execute o DAST somente contra loopback descartável e confira os audits de
  Python, Node, filesystem e imagem no job `security-release`;
- force esgotamento e expiração de uma cota e confirme `429`, `Retry-After`,
  evento sanitizado e recuperação;
- derrube PostgreSQL, confira `liveness=200` e `readiness=503`, restaure-o e
  confira readiness/alerta recuperados;
- rode os testes `promtool` e abra os painéis provisionados;
- execute o runbook de backup/restauração em banco e storage vazios e compare
  inventário, hashes, constraints, snapshots e trilhas;
- valide o índice e `SHA256SUMS` da evidência V05; não refaça cargas destrutivas
  fora do envelope aprovado.

## 5. Fechar ou bloquear

Antes de encerrar o PR, confirme:

- [ ] quatro frentes de artefatos da CI disponíveis e sanitizadas;
- [ ] nenhum achado alto/crítico sem correção ou exceção válida;
- [ ] nenhum segredo, caminho interno ou dado real no diff/artefatos;
- [ ] riscos residuais com responsável, mitigação, prazo e reteste;
- [ ] `git diff --check` aprovado;
- [ ] aceite do PO registrado no PR;
- [ ] aceite do responsável técnico registrado no PR;
- [ ] decisão de capacidade e demais portões corporativos registrada.

Se qualquer um dos três últimos itens estiver pendente, mantenha
`release_candidate=not_approved` e `stage_6_entry=not_authorized` no arquivo de
decisão. Defeito crítico ou alto sem tratamento acordado interrompe a
demonstração e bloqueia a candidata.
