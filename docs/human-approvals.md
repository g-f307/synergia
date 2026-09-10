# Decisão humana auditável

O fluxo de aprovação é associado a uma pendência persistida e permanece
separado da classificação automática. A classificação é evidência e
recomendação; somente um evento de aprovação registra uma decisão humana.

## Estados e transições

```text
pendência aberta
      │ submeter com justificativa
      ▼
  submitted ── atribuir ──> in_review
                                ├── aprovar + consentimento ──> approved
                                ├── rejeitar ─────────────────> rejected
                                └── devolver ─────────────────> returned
                                                                  │
                                                                  └── reenviar ──> submitted
```

Cada transição usa a versão atual da solicitação. Uma requisição concorrente
com versão antiga recebe `409` e não registra decisão. Eventos anteriores são
append-only: banco e aplicação rejeitam atualização ou remoção do histórico.

## Política inicial

A política `pending.standard`, versão 1, é deliberadamente conservadora:

- grupo revisor: `gestor`;
- justificativa explícita em submissão, atribuição e decisão;
- consentimento explícito para aprovação;
- solicitante e decisor devem ser usuários diferentes;
- somente responsável atribuído pode decidir.

Essa política não representa alçadas corporativas adicionais. Novas etapas,
limites ou grupos somente podem ser adicionados em uma nova versão após
confirmação do negócio; solicitações existentes preservam a versão original.
Versões publicadas são imutáveis no banco: qualquer alteração de regra deve
ser publicada com outro número de versão. Nesta entrega, a única política
homologada exige aprovador distinto; autoaprovação configurável permanece fora
do escopo até que uma política sem segregação seja aprovada pelo negócio.

## Contratos

| Operação | Permissão | Finalidade |
| --- | --- | --- |
| `GET /pending-items/{id}/approval` | `approval.read` | consultar estado e histórico |
| `POST /pending-items/{id}/approval` | `approval.submit` | submeter pendência aberta |
| `POST /approvals/{id}/assign` | `approval.assign` | atribuir ou reatribuir responsável elegível |
| `POST /approvals/{id}/approve` | `approval.decide` | aprovar com consentimento |
| `POST /approvals/{id}/reject` | `approval.decide` | rejeitar com justificativa |
| `POST /approvals/{id}/return` | `approval.decide` | devolver sem apagar histórico |
| `POST /approvals/{id}/resubmit` | `approval.submit` | reenviar pelo solicitante |

O backend cruza permissão, organização, estado, responsável, sessão ativa e
versão em todas as mutações. Recursos inexistentes ou de outra organização
retornam `404`, evitando enumeração horizontal.

## Auditoria e notificações

Cada transição registra ator, sessão, organização, permissões efetivas,
responsável, justificativa, consentimento, versão, horário e correlation ID.
O conteúdo da justificativa permanece no histórico protegido e não é copiado
para notificações ou logs. Eventos relevantes geram notificações internas em
português ou inglês conforme as preferências do destinatário.
