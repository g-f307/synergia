# Homologação SMTP assistida — issue #143

## Contexto e autorização

- Data: 24/10/2026, timezone de referência `America/Manaus`.
- Branch: `feature/143-smtp-homologacao`.
- Commit testado: `38e7e18`.
- O responsável informou ter concluído a preparação da conta exclusiva e do
  ambiente privado, autorizou explicitamente um único envio e posteriormente
  confirmou o recebimento nesta conversa.
- O arquivo importado foi a massa sintética versionada
  `data/synthetic/fixtures/minimal-valid/n-fp.xlsx`. Não foram usados conteúdos
  dos workbooks reais em `docs/files/`.

## Alvo técnico

| Campo | Valor |
| --- | --- |
| Execução | `bf3c2c00-da20-4a37-97b8-08c802012e77` |
| Estado da execução | `completed_with_errors` |
| Tipo de notificação | `execution.completed_with_errors` |
| Notificação | `032c6e47-a067-4c57-b3ac-08244a629649` |
| Entrega | `c6d8a817-8327-4d7f-9051-3b0ff56c1c2b` |
| Provider | `smtp` |

A mensagem corresponde ao evento de conclusão com erros; o smoke comprova o
canal de entrega, não o sucesso integral dos dados da importação.

## Preflight

Executado `scripts/smoke_smtp_delivery.py` via serviço Compose `email-worker`,
limitado ao UUID da notificação e sem flags de envio:

- `mode=dry_run`;
- `delivery_state=not_projected`;
- `eligible=true`;
- `provider_matches=true`;
- `recipient_allowed=true`;
- `ready=true`;
- código de saída `0`.

Essa fase não transmitiu nem criou tentativas.

## Envio autorizado e recebimento

Após autorização explícita, o smoke foi executado uma única vez com
`--send --allow-real-send` para a mesma notificação:

- `outcome=accepted`, `processed=1`, `sent=1`, `failed=0`;
- código de saída `0`;
- estado persistido `sent`, `attempt_count=1`;
- auditoria da tentativa 1: `started` e `sent`;
- instante persistido de aceitação: **24/10/2026 às 13:27:41 America/Manaus**
  (`2026-10-24T17:27:41.517949+00:00` no banco).

O responsável respondeu “Chegou”, confirmando recebimento. Na revisão do
roteiro, confirmou também que remetente, assunto, idioma e corpo estão corretos
e legíveis. Não houve leitura programática de inbox, IMAP ou captura da caixa.
Essa confirmação visual não equivale à inspeção separada das duas partes MIME;
a estrutura e os idiomas têm cobertura automatizada registrada no runbook.

## Repetição da entrega confirmada

Foi exercitado `SMTPEmailSmoke.run(..., send=True)` com a configuração do
ambiente e a entrega real já em `sent`, injetando um transporte que lança erro
se `send()` for chamado. O estado técnico foi consultado antes e depois:

- `outcome=already_accepted`;
- `sent=0`;
- estado continua `sent`;
- `attempt_count` continua `1`;
- quantidade de registros de auditoria inalterada;
- nenhuma chamada ao transporte SMTP.

A verificação não realizou uma segunda transmissão e não depende de
interpretação de Message-ID pelo servidor remoto.

## Limites e pendências

- Este registro omite endereços, remetente, segredo, tokens, corpo e resposta
  remota do SMTP. Credenciais e `.env` não foram versionados.
- Não houve teste deliberado de falha de rede no servidor real. Classificação,
  TLS, recuperação e reconciliação têm testes sintéticos/isolados.
- A homologação corporativa LG, OAuth e políticas de operação contínua não são
  comprovadas por este smoke.
- CI remota, revisão e merge continuam pendentes. O envio de homologação não
  habilita agendamento automático nem autoriza novas mensagens.


## Revisão do encerramento do roteiro

Na revisão de 24/10/2026, a entrega continuava em `sent`, com uma tentativa e
um registro de aceitação. O `.env` está ignorado e com permissões restritas ao
proprietário. O worker de e-mail não estava rodando no Compose.

Naquela revisão, o roteiro ainda não estava integralmente encerrado: o backend
mantinha `EMAIL_DELIVERY_ENABLED=true`. A desativação local e a confirmação de
revogação da senha de app estavam pendentes. A revisão, por si só, não alterou
a configuração privada, revogou credenciais nem executou novo envio.

## Encerramento local e restauração autorizados

Em 24/10/2026, o responsável autorizou encerrar o teste e desfazer as mudanças
temporárias do cadastro e dos acessos:

- `.env` restaurado aos padrões de e-mail do exemplo versionado, preservando as
  configurações de outros componentes. Canal e provider desabilitados; senha,
  usuário, remetente, allowlist e referências de segredo SMTP retirados do arquivo.
- Apenas o backend foi recriado para aplicar a configuração e retirar a senha do
  ambiente do processo; o worker Compose permaneceu parado.
- O comando de e-mail retornou `outcome=disabled`, com zero processados, zero
  envios, zero falhas e código de saída `0`. A política de templates retornou
  `disabled`. A conferência não encontrou senha SMTP ou referência de arquivo de
  senha no ambiente do backend.
- O endereço sintético `admin.e2e@example.invalid` foi reativado como primário e
  verificado. O endereço temporário foi desabilitado no cadastro, preservando o
  histórico pelo procedimento existente.
- Somente o vínculo temporário de Operador do admin na organização de teste foi
  revogado. O papel Admin e suas permissões de administração, auditoria e sessões
  foram preservados; permissões operacionais de Operador deixaram de ser efetivas.
- As alterações usaram os repositórios da aplicação, com eventos
  `user.admin_updated` e `access.association_revoked` e motivo de encerramento da
  homologação. A senha de login não foi alterada.
- Backend, frontend e PostgreSQL saudáveis; migrate encerrado com código zero.
  Notificação interna preservada. Entrega segue `sent`, com uma tentativa e os
  mesmos dois eventos de tentativa (`started`, `sent`). Nenhuma mensagem adicional.

**Revogação externa confirmada pelo responsável:** após o encerramento local,
o responsável informou ter revogado a senha de app na conta Google. A operação
foi executada por ele, fora desta sessão; não houve acesso programático à
segurança da conta. Essa confirmação encerra a pendência externa do roteiro.
A remoção local da senha, por si só, não seria prova de revogação no provedor.

A [revisão final da issue](issue-143-final-review.md) cruza os critérios de aceite,
as evidências e os resultados de regressão após esse encerramento.
