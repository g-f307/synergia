# Backlog de aprovação humana

## Responsável e escalonamento

Gestor da organização lidera; operação de negócio trata ausência de aprovador;
segurança participa diante de segregação de função violada.

## Pré-condições

- fila filtrada pela organização autorizada;
- política e grupo revisor ativos;
- solicitante e aprovador distintos quando exigido.

## Procedimento

1. Conferir idade, estado e responsável sem exportar justificativas.
2. Atribuir ou reatribuir pela API com versão otimista atual.
3. Solicitar correção quando faltarem evidências; não aprovar por contingência.
4. Acompanhar redução de profundidade e idade da fila.

## Rollback

Decisões concluídas são imutáveis. Uma atribuição incorreta deve ser
reatribuída por nova ação auditada; nunca alterar o histórico no banco.

## Validação e evidências

Confirmar permissão, organização, consentimento, justificativa obrigatória e
evento append-only. Registrar somente contagens, estados e correlation IDs.
