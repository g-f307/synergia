# Validação da Issue #168

## Ambiente e alcance

Validação local em 3 de novembro de 2026 (America/Manaus), branch
`feature/168-in-app-feedback`, baseada em `87b4944` da main após o merge
da #169. Ambiente atualizado com `npm ci` e dependências Python conferidas
por `pip check`; nenhuma dependência nova foi adicionada à aplicação.
Python 3.12.15, Node 22.23.1, PostgreSQL 16 em container temporário e Chromium
153 via Playwright. API e web vinculadas somente a 127.0.0.1.

Bancos descartáveis separados para a suíte completa e para E2E. Somente dados
sintéticos foram utilizados. As migrations 0001–0035 foram aplicadas em banco
novo; testes cobrem adoção de schema legado e recusam baseline incompleto.
Os testes de backup/restore usam clientes PostgreSQL 16 do container, em
compatibilidade com o servidor, em vez dos clientes 18 instalados no host.

## Comandos executados

| Comando | Resultado |
| --- | --- |
| `ruff check backend scripts` | Aprovado |
| `cd backend && pytest -q --tb=short` | 2.400 aprovados; inclui integração PostgreSQL e matriz real de 535 combinações de autorização |
| `cd backend && pytest tests/test_web_i18n.py tests/test_rate_limiting.py -q` | 14 aprovados; inclui os dois testes de validação do catálogo espanhol acrescentados após a coleta da suíte completa |
| `cd web && npm test -- --watch=false --browsers=ChromeHeadless --reporters=dots --code-coverage` | 336 aprovados; linhas 83,51%, statements 77,27% |
| `cd web && npm run lint` | Aprovado |
| `cd web && npm run build` | Aprovado; build de produção também executado pelo servidor E2E |
| `cd web && npm run e2e` | 23 cenários aprovados, incluindo fluxos operacionais, administração, segurança HTTP e modo TV |
| `cd web && npm run e2e -- feedback.spec.ts` | 5 cenários aprovados, com API e persistência reais, exceto falha temporária controlada |
| `python scripts/validate_access_matrix.py` | 107 operações privadas documentadas |
| `python scripts/validate_web_journey_map.py` | 36 rotas e 113 operações inventariadas |
| `python scripts/security_matrix.py --check` | 535 combinações e relatório sincronizado |
| `python scripts/validate_i18n.py` | Catálogos PT/EN e extensão ES válidos |
| `python scripts/validate_web_assets.py`, `validate_visual_system.py`, `validate_http_security.py` | Aprovados |
| `python scripts/validate_threat_model.py`, `validate_stage5_release.py`, `validate_stage6_pilot.py` | Contratos aprovados; não representam aprovação de release nem autorização de piloto |
| `python scripts/security_release.py validate`, `python scripts/security_release.py secrets` | Aprovados |
| `git diff --check` | Aprovado |

As variáveis DATABASE_URL e PG* apontaram exclusivamente para bancos
temporários. `CHROME_BIN` foi definido para o Chromium instalado no ambiente.

## Casos relevantes

- Criação de bug/sugestão com protocolo, autor/sessão/organização/data derivados.
- Normalização NFC/quebras de linha; limites; campos extras proibidos; origem
  não autorizada, URL e query string rejeitadas.
- Autor vê só os próprios registros; outra pessoa da mesma organização não
  recebe o detalhe; organização distinta recebe o mesmo 404 de recurso ausente.
- Concessão direta de triagem funciona sem depender de papel; usuário sem
  permissão recebe 403; concessão global não fabrica vínculo organizacional.
- Vínculos ausentes ou ambíguos são bloqueados com orientação.
- Filtros, contagem, ordenação e paginação no escopo correto.
- Transições válidas, estados terminais e justificativa obrigatória; tentativa
  concorrente resulta em um sucesso e um 409, sem perda de histórico.
- Triggers impedem mutação de identidade e exclusão do registro/histórico.
- Criação/transições são exportáveis pela auditoria #169 sem texto do usuário.
- Formulário preserva dados em falha e bloqueia duplo envio. Conflito exige
  recarga explícita. Descrição contendo tags é exibida como texto.
- Temas claro/escuro, viewport 390×844, navegação por Tab e regiões com scroll
  acessíveis por teclado. Axe não encontrou violações graves/críticas no
  domínio de feedback nos cenários examinados.
- Espanhol selecionado pelo perfil e reaplicado após navegação; campos
  exclusivos de bug desaparecem para sugestão.

## Capturas sintéticas

| Estado | Evidência |
| --- | --- |
| Principal, claro | [principal](evidence/issue-168-principal-light.png) |
| Principal, escuro | [escuro](evidence/issue-168-principal-dark.png) |
| Viewport estreito e foco por teclado | [móvel](evidence/issue-168-principal-mobile.png) |
| Confirmação com protocolo | [confirmação](evidence/issue-168-confirmation.png) |
| Sem registros na organização do leitor | [vazio](evidence/issue-168-empty.png) |
| Falha controlada com texto preservado | [erro](evidence/issue-168-error.png) |
| Triagem e histórico | [triagem](evidence/issue-168-triage-history.png) |
| Jornada em espanhol | [espanhol](evidence/issue-168-spanish.png) |

A indisponibilidade é injetada no navegador somente para o POST de feedback
(503 sintético), sem substituir autenticação, política, backend ou listagens.
As demais etapas usam a aplicação real. Capturas não contêm tokens,
cabeçalhos, planilhas ou dados de pessoas reais. O relatório Playwright e os
anexos são gerados em `web/reports/e2e-*` e publicados pelo job existente
no artefato `fluxo-web-e2e` da CI.

## Reprodução pelo revisor

1. Configurar um PostgreSQL descartável e as variáveis de autenticação conforme
   a documentação local; aplicar migrations com `python scripts/apply_migrations.py`.
2. Usar `python scripts/bootstrap_web_e2e.py` somente no banco sintético.
3. Executar `npm ci` em `web`, disponibilizar Chromium e executar
   `npm run e2e -- feedback.spec.ts`, com DATABASE_URL e E2E_PYTHON adequados.
4. Conferir envio pelo operador, protocolo, consulta própria, triagem pelo
   gestor e estado devolvido ao autor. A conta leitora pertence à outra
   organização e deve receber lista vazia e bloqueio da rota de triagem.
5. Em `/feedback/triage/:feedbackId`, abrir duas abas, salvar em uma e tentar
   salvar a versão anterior na outra: conferir 409 e ausência de sobrescrita.

## Limitações e operação

- A revisão humana e a CI remota do PR são etapas posteriores à validação
  local; este relatório não declara aprovação de merge, release ou produção.
- A suíte emitiu avisos de depreciação de Starlette/HTTPX já presentes. O build
  mantém avisos de orçamento CSS em componentes anteriores; o orçamento de
  erro não foi aumentado.
- O espanhol cobre toda a nova jornada. Telas antigas sem tradução espanhola
  usam pt-BR; a extensão está documentada no contrato e testada.
- Não houve DAST adicional, deployment ou integração corporativa nesta entrega.
- Rollout exige aplicar a migration 0035 antes da nova aplicação; rollback
  preserva feedback e auditoria. Consulte [o contrato](product-feedback.md).
