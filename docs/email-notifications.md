# Entrega segura de notificações por e-mail

> Configuração SMTP, smoke opt-in e reconciliação estão no
> [runbook de entrega SMTP](smtp-email-provider.md).

O canal de e-mail consome as notificações internas persistidas e não participa
da transação que originou uma execução, pendência ou relatório. Uma falha de
entrega nunca desfaz o evento operacional. O contrato de
provedor tem captura local para desenvolvimento/CI e transporte SMTP genérico
para homologação autorizada. Não há leitura de caixa postal.

## Habilitação explícita

O canal nasce desabilitado. Nesse estado, o processador encerra sem consultar a
fila e sem criar tentativas. Para uma captura local, configure no ambiente:

```dotenv
EMAIL_DELIVERY_ENABLED=true
EMAIL_PROVIDER=local_capture
EMAIL_FROM_ADDRESS=no-reply@example.invalid
EMAIL_CAPTURE_PATH=./data/email-capture/messages.jsonl
```

Esses valores são exemplos sem credenciais. Para SMTP, use `EMAIL_PROVIDER=smtp`
e siga o runbook. Segredos pertencem ao gerenciador de segredos/arquivo externo
do ambiente, nunca ao banco, frontend, documentação ou repositório.

O lote, máximo de tentativas e intervalo inicial são limitados por
`EMAIL_BATCH_SIZE`, `EMAIL_MAX_ATTEMPTS` e `EMAIL_RETRY_SECONDS`. A janela
`EMAIL_CONSOLIDATION_SECONDS` posterga o primeiro envio para absorver ocorrências
relacionadas. Execute:

```bash
python scripts/process_email_notifications.py
```

## Elegibilidade, idioma e consolidação

Ao reservar uma entrega, o processador confirma usuário ativo, preferência
`email` habilitada, endereço ativo verificado e a mesma versão da notificação.
Endereços não verificados e preferências desabilitadas ficam como `skipped`, sem
tentativa. O endereço primário verificado tem precedência.

Assunto e corpo são versionados em `pt-BR` e `en-US`. A projeção fixa a revisão
ativa do canal de e-mail no locale do destinatário, com fallback determinístico
para `pt-BR` e depois `en-US`; uma publicação posterior não reescreve a entrega
reservada. Apenas os placeholders declarados pela política do evento podem ser
interpolados. A consolidação reutiliza a chave atômica da caixa interna, então
um resumo de pendências produz uma mensagem, não uma mensagem por ocorrência.
Enquanto a entrega não começou, novas versões substituem o conteúdo reservado e
reiniciam a janela. Depois de enviada, a mesma notificação interna não gera novo
e-mail; uma notificação criada após a leitura possui outro identificador.

## Auditoria e privacidade

`email_deliveries` controla estado, limites, disponibilidade, versão e referência
técnica. `email_delivery_attempts` é append-only e guarda somente resultado,
código seguro de falha e correlation ID. Endereço, assunto, corpo e credenciais
não são persistidos nessas tabelas.

Falhas temporárias usam espera exponencial limitada. Exceções viram códigos
estáveis; o texto do provedor não é registrado, evitando vazamento de token,
senha, corpo ou autenticação. A captura local contém a mensagem para inspeção
controlada e sua pasta está excluída do versionamento.

A tentativa é incrementada e registrada como `started` na mesma transação que
reserva a entrega, antes da chamada ao provedor. Na captura local, a recuperação
de reserva vencida consome tentativa e o capturador devolve a primeira referência
sem duplicar a mensagem. Em SMTP, reserva vencida ou confirmação incerta exige
reconciliação explícita, sem retry automático. O `delivery_id` é estável, mas o
Message-ID não oferece deduplicação remota. Retries automáticos SMTP só ocorrem
após não aceitação conhecida e respeitam `EMAIL_MAX_ATTEMPTS`.

Cada finalização também informa o número da tentativa reservada. A atualização
só ocorre se a entrega ainda estiver em `processing` e continuar pertencendo à
mesma tentativa. Assim, um worker cujo lease expirou não pode concluir, falhar
ou produzir auditoria em nome do worker que recuperou a entrega.

O editor do canal e-mail informa configuração desabilitada, captura local,
envio configurado (`smtp`) ou indisponível. A prévia nunca transmite. O estado
de configuração não comprova conexão, recebimento ou integração corporativa;
nesses casos, o aceite requer evidência operacional.
