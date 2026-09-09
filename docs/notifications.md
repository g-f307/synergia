# Notificações internas

A caixa interna transforma eventos persistidos de execução, pendência e
relatório em avisos próprios e auditáveis. Ela não envia e-mail, não chama
terceiros e não executa agendamento distribuído.

## Projeção e preferências

A migration `0021_create_internal_notifications.sql` instala templates
versionados em `pt-BR` e `en-US` e projeta, na mesma transação do evento fonte:

- conclusão ou falha de execução para quem iniciou a execução;
- um resumo consolidado das pendências abertas da execução para destinatários
  ativos com `pending.read` e `notification.read` na organização;
- sucesso, falha ou cancelamento de relatório para quem solicitou a versão.

`notification_preferences.in_app=false` produz um registro `suppressed` e um
evento seguro de auditoria, mas nada aparece na caixa. Reativar a preferência
vale apenas para eventos futuros. A preferência `email` não é usada por esta
entrega.

Ocorrências repetidas são idempotentes por evento, destinatário e projeção. Uma
notificação ainda não lida com a mesma chave é consolidada de forma atômica e
incrementa `occurrence_count`; pendências nunca geram uma mensagem por item.

## API e autorização

As quatro operações exigem `notification.read`:

| Operação | Comportamento |
| --- | --- |
| `GET /notifications` | lista própria com `filter`, `sort`, `page` e `page_size` |
| `GET /notifications/unread-count` | conta somente itens visíveis e não lidos |
| `PATCH /notifications/{id}/read` | persiste leitura com campo `version` |
| `POST /notifications/read-all` | lê atomicamente todos os itens visíveis |

A visibilidade é a interseção do escopo de `notification.read` com a permissão
do recurso fonte (`execution.read`, `pending.read` ou `report.read`). O
destinatário também precisa ser o usuário da sessão. Recursos de outro usuário
ou fora do escopo não são enumerados. O link só é devolvido quando o recurso
ainda existe no mesmo escopo; a rota de destino repete sua própria autorização.

## Conteúdo e auditoria

O tipo, o estado e a versão do template são códigos estáveis. Título e corpo
são renderizados no idioma atual do perfil; locales sem template usam `pt-BR`
como fallback. Apenas `execution_id`, contagem e versão numérica podem ser
interpolados. Payloads fontes, nomes de arquivo, caminhos, credenciais e tokens
não são copiados.

`notification_events` registra criação, entrega interna, consolidação,
supressão, falha técnica e leitura. Leituras incluem usuário, sessão e
correlation ID. `notification_occurrences` garante idempotência e mantém o
vínculo técnico com o evento fonte sem reproduzir seu conteúdo.

O canal assíncrono e opcional de e-mail reutiliza essa projeção e está descrito
em [`email-notifications.md`](email-notifications.md).
