# Relatório final de validação da Etapa 5

## Decisão executiva

O SYNERGIA está **tecnicamente pronto para a homologação pré-RPA** no escopo
implementado com Angular, FastAPI e PostgreSQL 16. A release candidate e a
entrada na Etapa 6, porém, estão **não autorizadas** até que o PO e o responsável
técnico registrem aceite no PR e os portões corporativos aplicáveis tenham uma
decisão. O estado canônico e validável por máquina está em
[`stage-5-release-decision.json`](stage-5-release-decision.json).

Isso não é uma aprovação de produção. Identidade, SMTP, observabilidade,
infraestrutura e disaster recovery corporativos continuam fora do escopo; RPA
e conectores não foram simulados como concluídos.

## Resultado dos controles integrados

| Controle | Resultado | Evidência principal | Observação |
| --- | --- | --- | --- |
| Reconstrução e migrations | aprovado pelo procedimento/CI | `local-environment.md`; job `project-data` | banco PostgreSQL 16 vazio, 27 migrations em ordem |
| Jornada Etapas 1–4 | aprovado | `operational-flow.spec.ts`; `web-e2e-demonstration.md` | upload, processamento, consulta, relatório, notificação e decisão usam API e banco reais |
| Autenticação, autorização e organização | aprovado | `security-test-report.md`; suíte PostgreSQL | matriz completa, IDOR/BOLA, revogação e segregação |
| Upload e payload malicioso | aprovado | suíte `security`; DAST | tipo real, macro, HTML, fórmula, traversal e reflexão |
| Rate limiting e recuperação | aprovado | `rate-limiting.md`; testes PostgreSQL | `429`, `Retry-After`, janela, concorrência e falha fechada |
| Dependências, segredos e SBOM | aprovado como gate automatizado | job `security-release` | achado alto/crítico sem exceção válida falha a CI |
| Health, métricas, painéis e alertas | aprovado | `observability.md`; `promtool` | readiness reage a banco/storage; liveness permanece independente |
| Backup e restauração | aprovado | `data-recovery-validation-report.md` | banco e arquivos restaurados, hashes, constraints e trilhas conferidos |
| Volume 6,8 mil/88 mil | integridade aprovada | `performance-reference-v05-pg16.md` | 39/39 checks; latência local não é SLO corporativo |
| Concorrência e recuperação transacional | aprovado no envelope documentado | `performance-baseline-pre-rpa.md` | idempotência, isolamento, rollback e retomada; série comparável no alvo é portão corporativo |
| pt-BR, en-US, teclado, Axe e móvel | aprovado | Playwright e `web-internationalization-accessibility.md` | zero violação Axe séria/crítica nos fluxos exercitados |
| Build de produção e Compose | aprovado pela CI | jobs `frontend` e `project-data` | Angular publicado com CSP; `docker compose config` validado |

Os artefatos transitórios não são versionados. A CI publica as quatro frentes
de evidência relevantes ao aceite: Angular, FastAPI, PostgreSQL/E2E e segurança
ofensiva/supply chain. O job de preservação do protótipo é um quinto gate de
somente leitura, não uma frente funcional da Etapa 5.

## Segurança e riscos residuais

R-25 (headers/CORS/cache) e R-26 (XSS/conteúdo executável) passam a residuais
médios após o build publicado, DAST e regressões de navegador. R-12 passa a
médio após cotas compartilhadas, ensaio de ruptura e reconciliação integral da
V05. A aprovação do envelope de capacidade continua pendente e não é inferida
dessas medições.

Não há defeito técnico crítico ou alto aberto sem tratamento registrado. Os
riscos altos restantes são deliberadamente externos ao escopo pré-RPA:

- R-03: identidade corporativa; bloqueia produção, com autenticação local
  desabilitada em produção como mitigação;
- R-15: provedor corporativo de e-mail; entrega externa permanece desabilitada
  e a homologação usa somente captura local sintética.

Responsável, mitigação, prazo por marco e critério de reteste desses riscos e
dos demais portões constam na decisão JSON. R-24 mantém a alçada corporativa de
aprovações explicitamente transferida ao PO.

## Limitações da evidência de desempenho

A V05 em PostgreSQL 16 comprovou 6.800 Workorders/lotes, 88.000 seriais,
189.600 linhas normalizadas e relatórios/exports reconciliados. O ensaio de
ruptura identificou memória como primeiro limite no envelope isolado. Como a
série de latência nasceu de worktree não comparável e não existe infraestrutura
corporativa dimensionada, a baseline oficial permanece `not_approved`.

Isso não invalida a integridade funcional para homologação. Impede usar os
números locais como compromisso de capacidade e impede autorizar a Etapa 6 sem
a decisão formal descrita no portão `performance-capacity-approval`.

## Evidência local desta revisão

O roteiro de reprodução está em
[`stage-5-demonstration.md`](stage-5-demonstration.md). Quando o executor não
oferece Docker, a reconstrução integral deve ser repetida pela CI ou por um host
com PostgreSQL 16; uma falha de permissão no socket não pode ser registrada como
aprovação nem como defeito do sistema. Resultados de execução pertencem ao log
do PR/CI, enquanto contratos e índices sanitizados permanecem versionados.

## Aceite e entrada na Etapa 6

| Papel/decisão | Estado | Local de registro |
| --- | --- | --- |
| aceite técnico pré-RPA | evidência pronta; assinatura pendente | revisão do responsável técnico no PR |
| aceite do produto | pendente | revisão do PO no PR |
| release candidate | não aprovada | decisão JSON |
| entrada na Etapa 6 | não autorizada | somente após os dois aceites e decisão dos portões aplicáveis |

A Etapa 5 só pode ser encerrada depois dessas duas assinaturas. Alterar a
decisão para `approved`/`authorized` sem satisfazê-las faz o validador falhar.
