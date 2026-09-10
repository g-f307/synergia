# Entrega segura de notificações por e-mail

O canal de e-mail consome as notificações internas persistidas e não participa
da transação que originou uma execução, pendência ou relatório. Uma falha de
entrega nunca desfaz o evento operacional. Esta etapa fornece o contrato de
provedor e um capturador estritamente local para desenvolvimento e CI; nenhum
provedor externo ou leitura de caixa postal é realizado.

## Habilitação explícita

O canal nasce desabilitado. Nesse estado, o processador encerra sem consultar a
fila e sem criar tentativas. Para uma captura local, configure no ambiente:

```dotenv
EMAIL_DELIVERY_ENABLED=true
EMAIL_PROVIDER=local_capture
EMAIL_FROM_ADDRESS=no-reply@example.invalid
EMAIL_CAPTURE_PATH=./data/email-capture/messages.jsonl
```

Esses valores são exemplos sem credenciais. Segredos de um futuro adaptador
corporativo deverão vir exclusivamente do gerenciador de segredos do ambiente.
Eles não pertencem ao banco, frontend, documentação ou repositório. Nesta
versão, qualquer provedor diferente de `local_capture` é rejeitado.

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

Assunto e corpo são versionados em `pt-BR` e `en-US`; idiomas não suportados
usam `pt-BR`. Apenas identificador de execução, contagem e versão podem ser
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
reserva a entrega, antes da chamada ao provedor. Recuperações de leases vencidos
também consomem tentativa e nunca ultrapassam `EMAIL_MAX_ATTEMPTS`. Todo adaptador
de provedor deve usar `delivery_id` como chave de idempotência; o capturador local
devolve a primeira referência sem duplicar a mensagem.

Cada finalização também informa o número da tentativa reservada. A atualização
só ocorre se a entrega ainda estiver em `processing` e continuar pertencendo à
mesma tentativa. Assim, um worker cujo lease expirou não pode concluir, falhar
ou produzir auditoria em nome do worker que recuperou a entrega.
