# #191 — checkpoint 1: degradação, suspensão e reservas

16/11/2026, America/Manaus. Base `e618902`, branch
`feature/191-ai-assistance-observability`. Bloco 1 de 4; não representa conclusão
da issue nem autorização de ativação operacional.

## Entrega e evidências

| Critério deste bloco | Implementação e comprovação |
| --- | --- |
| Suspender geração preservando leitura | `GENERATION_ENABLED=false`, com flag geral ligada; POST 503 específico; capability mantém leitura. Testes HTTP e PostgreSQL comprovam consulta de resultado persistido sem endpoint/modelo/digest ou segredo do limitador |
| Não inicializar provider para leitura | `get_read_service` usa somente contexto/repositório; teste falha se provider ou limitador forem construídos |
| Preservar comportamento anterior | Flag geral false continua bloqueando GET/POST e ocultando o card; padrão da nova flag não ativa a feature |
| Diagnóstico autenticado | Sonda técnica protegida pelo Bearer de observabilidade; 401 sem token/errado; somente estados, duração e códigos fechados |
| Diagnóstico sem inferência | Servidor HTTP local falso confirma apenas GET de versão/tags, zero POST; cenários de redirect, resposta grande e lentidão mantêm lock recuperável |
| Readiness independente | Testes confirmam `/health/ready` e `/health/live` saudáveis durante falha do runtime, com dependências obrigatórias controladas |
| Recuperação segura | Prévia padrão, `--apply` explícito, lote limitado, SKIP LOCKED, ator técnico existente; reservas válidas e resultados preservados; repetição idempotente e finalização com token antigo recusada |
| Auditoria da recuperação | Evento `expired` e uma projeção na fila Graylog na mesma transação; nenhum envio ao modelo |
| Interface após suspensão | Atualiza capability e lê resultado, sem ocultar o conteúdo nem oferecer nova geração; teste Angular de corrida após clique |
| Contratos e operação | API 0.13.0 pela nova sonda; resultado 1.0.0 e estrutura de capability preservados; Compose, configuração, inventários e runbook atualizados |

## Validações executadas

Ambiente: Python 3.12, PostgreSQL 16 em container novo e descartável, sem volumes,
porta aleatória somente em loopback; Angular com Chromium Headless 153.
Nenhum banco operacional, modelo real ou credencial externa foi usado.

| Validação | Resultado |
| --- | --- |
| Regressão consolidada abaixo | **416 testes aprovados**, 1 aviso preexistente de depreciação Starlette/httpx; 22,92 s |
| Componente Angular + capability | **60 testes aprovados** em ChromeHeadless |
| `npm run lint` em `web` | Aprovado |
| `npm run build` em `web` | Aprovado; avisos de orçamento CSS em componentes preexistentes, nenhum CSS alterado neste bloco |
| `.venv/bin/ruff check . ../scripts` em `backend` | Aprovado |
| Ruff format dos 19 arquivos Python afetados | Aprovado |
| `scripts/validate_web_journey_map.py` | Aprovado: 119 operações OpenAPI inventariadas |
| `scripts/validate_access_matrix.py` | Aprovado: 112 operações privadas documentadas e 5 públicas; 2 técnicas autenticadas |
| `scripts/validate_homologation_observability.py` | Aprovado para a baseline existente; alertas da IA pertencem ao bloco 3 |
| `scripts/validate_threat_model.py` | Baseline existente aprovada; extensão específica da IA pertence ao bloco 4 |
| `git diff --check` | Aprovado |
| `docker compose config --quiet` | Aprovado; nenhum serviço iniciado ou recriado |

As 39 migrations existentes foram aplicadas no banco descartável pelo runner
oficial. Na primeira rodada, dois testes que exigem schema previamente migrado
falharam por ausência de tabelas nesse banco novo. Após preparar o schema, ambos
passaram; a rodada consolidada final passou integralmente. Não houve migration
nova ou alteração de migration publicada neste bloco.
O container descartável foi encerrado ao final; o ambiente operacional não foi
reiniciado nem teve configurações alteradas.

Reprodução, na raiz e com `DATABASE_URL` apontando para PostgreSQL **descartável**
e migrado até 0039 (a suíte cria/removerá bancos próprios para várias integrações):

```bash
backend/.venv/bin/python -m pytest -c backend/pytest.ini \
  backend/tests/test_ai_assistance_*.py \
  backend/tests/test_observability.py \
  backend/tests/test_security_regression.py \
  backend/tests/test_homologation_observability.py \
  backend/tests/test_project_assets.py \
  backend/tests/test_deployment_docs.py -q
```

Para Angular, executar em `web`, com `CHROME_BIN` apontando a Chromium instalado:

```bash
npm test -- --watch=false --browsers=ChromeHeadless \
  --include=src/app/domains/executions/execution-assistance.component.spec.ts \
  --include=src/app/core/ai-assistance-capability.service.spec.ts
npm run lint
npm run build
```

## Limitações e próximos checkpoints

- A sonda comprova anúncio de versão/pin e transporte; não comprova integridade
  física do host ou sucesso futuro da inferência.
- Timeout/cancelamento HTTP não promete interromper instantaneamente trabalho
  já admitido. Permanecem os limites do provider, idempotência e prazo da reserva;
  o runbook exige tratar instâncias antigas antes de recuperar/reabilitar.
- Não houve implantação no ambiente em uso, inferência real, E2E autenticado
  completo ou alteração visual de layout. O ajuste de interface foi coberto
  pelos testes direcionados e build.
- Conferida a projeção transacional Graylog no PostgreSQL; entrega/pesquisa e
  capturas no Graylog real serão realizadas no bloco 4.
- Instrumentação completa/rotinas persistentes: bloco 2; alertas/painel: bloco 3;
  threat model específico e campanha adversarial/exercício integrado: bloco 4.
- A #192 permanece responsável pela validação final e retirada dos caminhos
  experimentais. A funcionalidade continua desligada por padrão.

Procedimentos: [runbook da assistência](../runbooks/ai-assistance.md).
