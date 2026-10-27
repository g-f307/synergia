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

A release candidate continua **não aprovada** e a liberação para produção está
**não autorizada**. Faltam os aceites do PO e do responsável técnico no PR e as
decisões corporativas de capacidade, identidade, e-mail, alçadas,
observabilidade e disaster recovery registradas em
[stage-5-release-decision.json](stage-5-release-decision.json). Esses portões
não são substituídos por serviços locais ou mocks.

## Etapa 6 — homologação com dados reais e liberação assistida

A preparação documental da Etapa 6 está em andamento. Ela inclui contratos
sanitizados dos workbooks reais autorizados, leitura incremental, adapters,
corpus reproduzível, correção da expiração de sessão, SMTP substituível,
observabilidade e piloto assistido. O início dessa preparação não aprova a
release candidate nem remove os portões corporativos da Etapa 5.

A homologação assistida possui roteiro, ensaios sintéticos por cenário, checklist
de suporte e registro de decisão do piloto em
[stage-6-pilot.md](stage-6-pilot.md). A decisão permanece **não tomada**: depende
da execução com os stakeholders e dos aceites do PO e do responsável técnico.

A observabilidade da homologação possui contrato versionado, destinos locais
temporários, painel, alertas, runbooks e exercício sintético de recuperação. A
plataforma, retenção, grupos de acesso e SLOs corporativos continuam pendentes;
os limiares atuais servem apenas para medir e proteger a homologação assistida.

O monitor operacional em Modo TV foi implementado para a validação com os
stakeholders. Ele reutiliza o catálogo autorizado de execuções, sem criar dados
ou uma API paralela, e permanece sujeito aos mesmos escopos organizacionais. A
validação em ambiente de fábrica poderá ajustar densidade, intervalo e seleção
dos painéis sem bloquear a primeira experiência de uso.

Integrações corporativas definitivas e automação RPA permanecem planejadas e
dependem de autorização formal.

Essas capacidades não são simuladas na aplicação atual. Cada uma exige contrato
de API, controle de acesso, persistência, rastreabilidade e evidência própria.
