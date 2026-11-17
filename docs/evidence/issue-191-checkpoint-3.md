# Issue #191 — checkpoint 3: alertas e painel

Data: 16/11/2026. Branch: `feature/191-ai-assistance-observability`.
Entrega incremental: blocos 1–3 concluídos; bloco 4 e validação final #192 pendentes.

## Entrega e limites

- Cinco alertas da assistência, cada um com runbook específico e severidade
  conferida pelo contrato. O validador agora exige URL completa do repositório,
  recusa nomes duplicados e não aceita o runbook de outro alerta.
- Quatorze painéis de IA acrescentados ao dashboard técnico provisionado.
  Quinze painéis anteriores preservados, com os mesmos IDs, consultas e layout;
  datasource e permissões de provisionamento preservados.
- Relógio de última conclusão persistida, derivado do histórico existente,
  sem migration nova, para medir dez minutos sem progresso sem dobrar a espera.
  Reserva/expiração não contam como conclusão; completed/rejected contam.
- Série de pin divergente inicializada com zero para observar o primeiro
  incremento após um scrape inicial, sem resetar contadores já existentes.
- CI ampliado para os novos cenários e consultas reais do painel. O exportador
  usa Python padrão e fixtures sintéticas por painel/target; uma consulta alterada
  chega ao promtool em vez de continuar validando uma cópia antiga.

Sem mudança no frontend, no contrato HTTP, no processamento de negócio ou nas
migrations publicadas. Nenhum modelo foi carregado/chamado. O ambiente operacional
não recebeu configuração, migration ou reinício. `docs/files/` e `.test-tmp/`
continuam ignorados; fixtures não usam planilhas reais, credenciais ou serviços
externos. A imagem de validação foi a mesma do CI, `prom/prometheus:v3.14.0`.

## Condições exercitadas

| Alerta | Disparo e recuperação | Cenários que não devem alertar |
| --- | --- | --- |
| Unavailable, warning | >20% em rate de 5m por 10m; recupera com tráfego saudável ou suspensão | Exatamente 20%, sem tráfego, instância suspensa com erros antigos, grande volume saudável em outra instância, reset sem falhas |
| Stalled, warning | Reserva com idade ≥600s e nenhuma conclusão há ≥600s; recupera com conclusão, esvaziamento ou suspensão | Trabalho novo depois de ociosidade, conclusão recente, coleta ausente/falha, geração suspensa |
| IntegrityViolation, critical | Integridade no POST/GET, escopo confirmado e pin divergente; recupera sem novos eventos na janela de 5m | Rejeição comum de conteúdo, contador antigo estável/reset, flag desligada sem incidente |
| ExpiredReservationsGrowing, warning | delta positivo em 10m, estoque atual positivo, por 2m; recupera ao limpar | Estoque estável/decrescente, falha de coleta, ausência de amostras |
| RetentionFailures, warning | increase failed ≥3 em 15m; recupera com envelhecimento das falhas na janela | Duas falhas duplicadas por dois coletores, lotes vazios bem-sucedidos, ausência de rotina/amostras, falha de coleta |

Testes também cobrem isolamento por ambiente, denegações fora da disponibilidade,
violação persistida não mascarada por canal em memória zerado e um único alerta
por ambiente para o mesmo histórico lido por duas instâncias. Suspensão não
mascara incidentes reais, crescimento de leases expirados ou manutenção necessária.
Um sucesso de retenção não apaga três falhas ainda recentes.

Os relógios de PostgreSQL e Prometheus devem estar sincronizados. Os valores de
increase são extrapolados; a contagem exata pertence à auditoria. Métricas não
reconstroem evento ocorrido antes da primeira coleta. Sem coleta não há prova
de saúde. O contrato assume o banco compartilhado por ambiente deste deploy.
As regras de retenção observam falhas efetivas que puderam ser auditadas; não
detectam por si só ausência de agendamento ou impossibilidade de registrar no
banco. Conferir também idade do sucesso, logs/exit do CLI e controles de banco.

## Resultados reais

| Validação | Resultado |
| --- | --- |
| promtool check config, incluindo regras | Aprovado: configuração válida e 21 regras totais (16 anteriores + 5 novas) |
| Suíte anterior de alertas | Aprovada: 13 cenários, 32 verificações |
| Nova suíte da assistência | Aprovada: 34 cenários, 67 verificações de disparo/recuperação/ausência |
| Consultas reais do dashboard exportadas | Sintaxe de 42 expressões aprovada |
| Consultas com séries sintéticas | 10 verificações aprovadas: razão, deduplicação de banco, soma de provider, idade e ausência de conclusão/sucesso |
| Contrato de observabilidade | Aprovado: 15 alertas contratados, 12 runbooks, 17 vistas (incluindo as 3 anteriores) |
| Pytest de telemetria/contrato/exportador | 60 aprovados, 1,31 s |
| Pytest PostgreSQL de manutenção/repositório | 40 aprovados, 9,44 s; PostgreSQL 16 descartável sem volumes, em loopback |
| Ruff lint backend/tests/scripts | Aprovado |
| Ruff format dos 6 arquivos Python afetados | Aprovado |
| YAML de CI, JSON e preservação dos ativos anteriores | Aprovados |
| git diff --check | Aprovado |

As rodadas de pytest são conjuntos distintos. O aviso restante é a depreciação
já existente Starlette/httpx. Na primeira execução dos novos testes de contrato,
duas fixtures que removiam runbook também removiam a quebra de linha antes do
alerta seguinte; corrigida a fixture, as 60 verificações finais passaram. Não
houve ajuste de limiar para fazer um cenário positivo deixar de alertar.

## Reproduzir

Regras, exportação e testes do painel: comandos completos no
[contrato de observabilidade](../ai-assistance-observability.md#alertas-e-painel).
Esses comandos também estão no CI; a execução remota ainda depende de push.

```bash
backend/.venv/bin/python -m pytest -c backend/pytest.ini \
  backend/tests/test_homologation_observability.py \
  backend/tests/test_ai_assistance_telemetry.py -q
```

Para as integrações, fornecer DATABASE_URL de PostgreSQL **descartável**, com
permissão para os bancos de teste criados/removidos pelas fixtures; nunca usar
conexão operacional. Depois:

```bash
backend/.venv/bin/python -m pytest -c backend/pytest.ini \
  backend/tests/test_ai_assistance_maintenance.py \
  backend/tests/test_ai_assistance_repository_persistence.py -q
```

## Pendências do bloco 4

Revisão de ameaça por fronteira, campanha adversarial integrada, atualização dos
guias de implantação/segurança e exercício indisponibilidade → suspensão →
recuperação com reconciliação PostgreSQL/Graylog e capturas reais sanitizadas.
Neste checkpoint não foi iniciado Grafana/Graylog, validada renderização visual
ou comprovado recebimento externo: as evidências de painel são do JSON provisionado
e da execução das suas consultas, não capturas de uma instalação em operação.
Prometheus avalia os alertas; não foi criado canal externo de notificação.
Não houve push, PR ou encerramento da issue.
