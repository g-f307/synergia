# Roadmap

## Etapas concluídas

- **Etapa 1 — fluxo ponta a ponta sem RPA:** ingestão, validação,
  normalização, consolidação, regras, persistência, consulta e
  reprocessamento.
- **Etapa 2 — identidade, acesso e administração:** usuários, grupos, papéis,
  JWT, sessões, RBAC, perfil e regressão de segurança.
- **Etapa 3 — aplicação web operacional:** design system, i18n, upload,
  dashboard, execuções, consultas e pendências. O aceite integrado está
  documentado em [stage-3-validation-report.md](stage-3-validation-report.md).
- **Etapa 4 — relatórios, notificações e decisão humana:** snapshots
  persistentes e versionados, catálogo web, exportação segura, caixa interna,
  canal de e-mail desacoplado e aprovações auditáveis com segregação de função.
  O aceite integrado está documentado em
  [stage-4-validation-report.md](stage-4-validation-report.md).

## Etapa 5 — gate pré-RPA

A implementação e os controles técnicos estão prontos para homologação pré-RPA:
segurança, abuso, observabilidade, recuperação, volume de referência e jornada
integrada possuem evidência reproduzível. O resultado consolidado está em
[stage-5-validation-report.md](stage-5-validation-report.md).

A release candidate continua **não aprovada** e a entrada na Etapa 6 está
**não autorizada**. Faltam os aceites do PO e do responsável técnico no PR e as
decisões corporativas de capacidade, identidade, e-mail, alçadas,
observabilidade e disaster recovery registradas em
[stage-5-release-decision.json](stage-5-release-decision.json). Esses portões
não são substituídos por serviços locais ou mocks.

## Próximas capacidades planejadas

- Etapa 6: contratos de integrações e automação RPA, após autorização formal;
- integrações corporativas definitivas.

Essas capacidades não são simuladas na aplicação atual. Cada uma exige contrato
de API, controle de acesso, persistência, rastreabilidade e evidência própria.
