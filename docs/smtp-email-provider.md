# Entrega SMTP substituível — issue #143

## Estado da implementação

Os blocos 1 a 3 implementam contrato, configuração, transporte e integração
segura com a fila. `EMAIL_PROVIDER=smtp` requer a migration `0033` e configuração
SMTP válida. O canal permanece desabilitado por padrão; `local_capture` continua
disponível. Nenhuma conexão SMTP externa ou mensagem real foi realizada.

O bloco 4 ainda deve concluir a apresentação coordenada de SMTP na API/frontend,
a configuração operacional e o smoke real opt-in. Até essa atualização, a política
de templates apresenta `unavailable` para SMTP, preservando o contrato atual sem
identificar incorretamente o transporte como captura local.

## Contrato independente do transporte

`app/email_contracts.py` define `EmailMessage`, `EmailProvider` e os resultados
de falha, sem importar SMTP, Google, banco ou HTTP. Os imports públicos anteriores
de `app.email_delivery` permanecem compatíveis por reexportação.

- sucesso retorna referência técnica opaca após confirmação de aceitação;
- `TemporaryEmailError`: não aceitação conhecida, elegível a retry limitado;
- `PermanentEmailError`: rejeição sem retry automático;
- `ConfigurationEmailError`: requer intervenção de configuração;
- `UncertainEmailError`: aceitação desconhecida, exige reconciliação explícita.

O identificador estável de entrega permite correlação. Não é uma garantia de
deduplicação do servidor remoto. A fila bloqueia retries de resultados SMTP incertos até reconciliação
explícita, conforme o procedimento abaixo. A captura
local mantém sua deduplicação por `delivery_id`.

Destinatário, remetente, assunto, corpo, usuário e segredo SMTP são omitidos de
`repr` dos contratos/configuração. Erros de validação contêm códigos ou nomes
de campos, sem valores fornecidos, respostas remotas ou caminhos de segredo.
Isso não autoriza registrar o conteúdo completo dos objetos por outros meios.

## Configuração preparada

| Variável | Regra |
| --- | --- |
| `EMAIL_SMTP_HOST` | hostname ASCII ou IP, sem esquema de URL ou porta embutida |
| `EMAIL_SMTP_PORT` | inteiro entre 1 e 65535; padrão 587 |
| `EMAIL_SMTP_TLS_MODE` | `starttls` ou `implicit`; padrão `starttls`; sem modo aberto |
| `EMAIL_SMTP_TIMEOUT_SECONDS` | finito, maior que zero e no máximo 30; padrão 15 |
| `EMAIL_SMTP_AUTH_MODE` | `password` (padrão) ou `none` explícito para relay autorizado |
| `EMAIL_SMTP_USERNAME` | obrigatório na autenticação por senha |
| `EMAIL_SMTP_PASSWORD` | segredo via ambiente, omitido de representações e erros |
| `EMAIL_SMTP_PASSWORD_FILE` | alternativa ao segredo em variável; UTF-8, no máximo 4096 bytes; remove apenas uma terminação de linha |
| `EMAIL_SMTP_ALLOWED_RECIPIENTS` | 1 a 500 endereços explícitos separados por vírgula; sem entradas vazias ou curingas |
| `EMAIL_FROM_ADDRESS` | único remetente autorizado para o envelope |

Não configurar simultaneamente senha e arquivo. O modo `none` recusa credenciais
configuradas e mantém a exigência de TLS. A negociação TLS e a verificação de
certificado pertencem ao transporte do bloco 2; configurar um modo não comprova
que uma conexão já foi estabelecida.

A allowlist usa a normalização em minúsculas do cadastro de identidade. Aceita
um endereço ASCII com local part dot-atom e domínio pontuado; não aceita listas
de destinatários em um campo, nomes de exibição, local part entre aspas,
SMTPUTF8, curingas ou cabeçalhos injetados. Pontos e tags `+` não são removidos:
nenhuma regra de alias é aplicada por provedor. Um endereço fora da lista é
recusado, mesmo que outro endereço da mesma pessoa esteja autorizado.

`SMTPConfig.validate_message()` valida envelope, remetente exato, destinatário,
assunto e corpo antes de uma futura conexão. Assunto não permite controles e
tem no máximo 998 caracteres; corpo deve ser texto UTF-8 válido, não vazio e
com no máximo 256 KiB, permitindo tabulações e quebras de linha. Isso não libera
HTML arbitrário nos templates: o adapter do bloco 2 gera HTML escapado a partir
do texto validado.

## Checkpoint do bloco 1

Testes exclusivamente sintéticos cobrem configuração e envelope inválidos,
allowlist exata, segredo por arquivo, fontes conflitantes de segredo, cabeçalhos
injetados, Unicode inválido, independência de provedor e captura local.
Conexão e resolução DNS são proibidas durante os testes de configuração.

```bash
cd backend
.venv/bin/ruff check . ../scripts
.venv/bin/python -m pytest -q tests/test_email_config.py tests/test_email_delivery.py
```

Credenciais de homologação não são necessárias para estes testes. O smoke real
continuará reservado ao bloco final, com configuração e autorização próprias.

Validação local do checkpoint em 24/10/2026:

- 69 testes direcionados de configuração/captura e 815 não integrados aprovados;
- sete testes de persistência e templates aprovados em PostgreSQL 16 isolado,
  com as 32 migrations existentes;
- Ruff a partir de `backend/`, compilação Python, matriz de acesso, modelo de
  ameaças, matriz de segurança e `git diff --check` aprovados;
- uma tentativa inicial contra o banco local falhou por autenticação; a
  configuração existente foi preservada e a regressão executada na instância
  exclusiva de testes, sem dados reais ou envio SMTP.

## Transporte SMTP — bloco 2

`app/smtp_email_provider.py` implementa `SMTPEmailProvider`, sem acesso ao banco
ou a configuração de Gmail. Valida e serializa a mensagem inteira antes de
abrir conexão. Cada chamada usa uma conexão e exatamente um destinatário no
envelope, sem Cc/Bcc e sem retries dentro do provider.

O adapter usa `smtplib.SMTP` com STARTTLS ou `SMTP_SSL` com TLS implícito. O
contexto padrão verifica cadeia e hostname do certificado e exige ao menos
TLS 1.2. O hostname configurado é usado para SNI/verificação; a saudação local
usa identificador estático, sem descobrir nem expor o hostname da máquina.
No STARTTLS, ocorre novo EHLO após a negociação. Autenticação e envelope só
seguem depois de TLS; não há fallback para uma sessão aberta.

O timeout configurado é passado ao socket e limita operações bloqueantes; não
é um prazo global para o processamento do lote. A fila reserva uma entrega SMTP de cada vez, imediatamente antes do envio;
reservas expiradas são retidas para reconciliação, sem reenvio automático. A conexão é criada antes do connect
para permitir fechamento também em falhas parciais.

### Autenticação substituível

`SMTPAuthenticator` separa validação e autenticação do restante da entrega.
A implementação padrão usa `smtplib.login` com usuário e senha ASCII, limitação
explícita dessa implementação de SASL; encoding incompatível é recusado antes
da conexão. O modo `none` representa relay explicitamente configurado, mantém
TLS e não envia credenciais. Um adapter futuro de OAuth/autenticação pode ser
injetado nessa porta, sem modificar mensagem, templates ou casos de uso. OAuth
live não foi implementado neste bloco.

### Conteúdo e confirmação

O MIME é `multipart/alternative`, com partes `text/plain` e `text/html` em
UTF-8 e quoted-printable. Cabeçalhos são codificados para trânsito 7-bit, sem
exigir SMTPUTF8/8BITMIME. HTML deriva exclusivamente de `html.escape` do mesmo
texto, com quebras de linha controladas. Não há edição de HTML no catálogo de
templates. Locale é validado como tag de idioma antes de definir Content-Language.

O Message-ID deriva do UUID da entrega e do domínio do remetente configurado.
A referência retornada é `smtp-<UUID>`, sem copiar identificador remoto,
destinatário, domínio ou resposta do servidor para a auditoria. Chamadas
repetidas ao provider podem transmitir novamente: Message-ID estável é
correlação, não deduplicação remota. A fila deve impedir chamadas indevidas.

| Situação | Resultado do contrato |
| --- | --- |
| Resposta 4xx negativa conhecida | temporário, sem retry interno ao adapter |
| Rejeição definitiva de destinatário/conteúdo | permanente |
| Certificado, capability, autenticação ou remetente incompatíveis | configuração; 4xx explícito continua temporário |
| Falha de conexão antes de DATA | temporário: corpo ainda não foi transmitido |
| Recusa explícita do comando DATA ou resposta final negativa | não aceitação conhecida, classificada pelo código |
| Timeout, desconexão, erro TLS ou resposta inconclusiva durante DATA | incerto; precisa de reconciliação e bloqueio de retry automático na fila |
| Resposta final 250 seguida de erro em QUIT/close | aceitação confirmada; o erro de fechamento não invalida o resultado |

Após DATA incerto, o adapter fecha a conexão sem enviar QUIT em uma sessão que
pode estar aguardando o restante do corpo. Falhas de fechamento não substituem
o resultado principal. Erros e tracebacks propagados contêm apenas códigos
estáveis, não o texto SMTP; debug do protocolo é desabilitado antes do connect.

Aceitação pelo servidor SMTP não é confirmação de recebimento na caixa do
destinatário. Essa confirmação continua sendo um aceite separado do smoke
real, que só ocorrerá no bloco final com configuração e autorização próprias.

### Checkpoint do bloco 2

Os testes usam respostas simuladas e o próprio `smtplib` com sockets em memória.
Verificam ordem de negociação/autenticação, hostname, contexto TLS, MIME,
escape de HTML, envelope, respostas 4xx/5xx, resultado incerto e falhas de
fechamento após aceitação. Nenhum servidor SMTP, DNS, conta ou credencial real
é necessário. A validação criptográfica de certificados em um handshake live
permanece parte da configuração e do smoke final.

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_smtp_email_provider.py \
  tests/test_email_config.py tests/test_email_delivery.py
```

Validação local do bloco 2 em 24/10/2026:

- 49 testes novos do transporte; 118 direcionados incluindo configuração e
  captura local; 864 testes não integrados aprovados;
- Ruff a partir de `backend/`, compilação Python, matriz de acesso, modelo de
  ameaças, matriz de segurança e `git diff --check` aprovados;
- o teste MIME identificou que a conversão multipart movia/removia o cabeçalho
  de idioma; sua definição foi corrigida e a leitura MIME pt/en foi validada;
- sem envio externo, credenciais reais, migration ou alteração da fila, da API
  e do frontend. A ativação SMTP e sua persistência aguardam o bloco 3.


## Fila e reconciliação explícita — bloco 3

A numeração `0033` foi conferida antes da criação: a base e o remoto terminavam
em `0032`. A migration amplia o CHECK do provider e cria auditoria de
reconciliação append-only. Não altera migrations anteriores. Seu rollback só é
permitido antes de existir qualquer entrega SMTP ou histórico de reconciliação;
não apaga histórico para viabilizar downgrade.

O worker constrói o provider sem conectar. Cada entrega SMTP é reservada
individualmente e tem posse/validade verificadas antes do transporte. Workers
concorrentes usam `FOR UPDATE SKIP LOCKED`. Cada entrega preserva seu provider:
um worker SMTP não consome capturas locais pendentes, e vice-versa. Trocar a
configuração não reclassifica nem retransmite entregas existentes.

- Rejeição temporária conhecida: backoff exponencial, limitado por
  `EMAIL_MAX_ATTEMPTS`, sem alterar o UUID da entrega.
- Rejeição permanente: falha terminal; problema de configuração também interrompe
  o lote para evitar repetir a mesma configuração em outros destinatários.
- Resultado incerto, exceção inesperada no transporte ou falha ao persistir a
  confirmação: sem retry automático; estado `failed` com
  `smtp_confirmation_unknown` quando o banco permite gravar.
- Banco totalmente indisponível após transmissão: a reserva pode permanecer em
  `processing`. Ao expirar em cinco minutos, o próximo worker SMTP a coloca em
  `failed/smtp_confirmation_unknown`, independentemente do orçamento restante.
  Nunca recupera esse caso transmitindo novamente.
- Aceitação SMTP já gravada continua `sent`, inclusive quando a confirmação da
  transação se perde para o worker. `sent` não significa recebimento na caixa.

A finalização usa UUID e número da tentativa: um worker atrasado não sobrescreve
uma entrega já finalizada. Os contadores do lote representam tentativas
processadas nessa execução; a retenção de reservas expiradas é registrada na
fila/auditoria e deve ser monitorada por `failure_code`, mesmo com zero envios
no lote. Logs e falhas persistidas usam códigos estáveis autorizados; não usam
texto da exceção/resposta SMTP, conteúdo, destinatário ou segredo.

### Procedimento de reconciliação

Execute com privilégios operacionais de banco e a mesma `DATABASE_URL` do worker.
O comando não depende de credenciais SMTP e nunca transmite mensagens.

1. Pare todos os workers SMTP, incluindo agendadores, e termine processos antigos
   que ainda possam estar transmitindo. A flag `--workers-stopped` registra uma
   declaração operacional; não encerra processos. Se a entrega ainda estiver em
   `processing`, aguarde a expiração da reserva de cinco minutos. A reconciliação
   explícita admite essa reserva expirada e registra a tentativa como incerta
   na mesma transação, sem precisar retomar um worker. Reservas vigentes são
   recusadas. Não mantenha um transmissor antigo ativo.
2. Inspecione somente os metadados técnicos. Por padrão, o comando é de leitura:

   ```bash
   backend/.venv/bin/python scripts/reconcile_smtp_delivery.py <delivery-uuid>
   ```

3. Obtenha evidência em canal restrito: confirmação de recebimento ou registro do
   servidor associado ao Message-ID `<synergia.UUIDsemhifens@dominio-remetente>`.
   Ausência na caixa de entrada, spam ou ausência de registro não prova rejeição.
   Se a evidência continuar inconclusiva, mantenha a entrega bloqueada. Não faça
   UPDATE manual, não limpe tentativas e não crie outra notificação para reenviar.
4. Com aceitação comprovada, marque como enviada sem retransmissão:

   ```bash
   backend/.venv/bin/python scripts/reconcile_smtp_delivery.py <delivery-uuid> \
     --apply --resolution accepted --evidence recipient_confirmation \
     --request-id <request-uuid> --actor-id <operator-uuid> --workers-stopped
   ```

   Use `--evidence smtp_log` quando a evidência for aceitação registrada no servidor.
   `sent_at` será o instante da reconciliação, não uma estimativa do envio original.
5. Somente com prova positiva de **não aceitação** nos registros do servidor,
   libere uma nova tentativa:

   ```bash
   backend/.venv/bin/python scripts/reconcile_smtp_delivery.py <delivery-uuid> \
     --apply --resolution not_accepted --evidence smtp_log \
     --request-id <request-uuid> --actor-id <operator-uuid> \
     --workers-stopped --max-attempts 3
   ```

   Informe o mesmo limite de tentativas do worker. A contagem não é zerada: a
   entrega passa a `retry` apenas se ainda houver orçamento; senão, permanece
   `failed/max_attempts_exceeded`. O comando não envia; a transmissão depende da
   retomada explícita do worker.
6. Guarde a referência à evidência no registro operacional de acesso restrito,
   associada ao `request-id`. Não inclua conteúdo da mensagem, endereços, respostas
   SMTP ou segredos no comando, no Git ou nos logs. `actor-id` é um UUID técnico
   do operador. Confirme o resultado antes de retomar os workers.

A alteração de estado e a auditoria são atômicas. Repetir os mesmos argumentos
com o mesmo `request-id` retorna o resultado original; reutilizar a chave com
outra decisão é recusado. O histórico de tentativas não é reescrito. A auditoria
registra decisão, categoria da evidência, UUID técnico do operador e correlação;
não guarda o conteúdo sensível da prova. UPDATE/DELETE na auditoria são recusados.

### Validação do bloco 3

Os testes usam PostgreSQL 16 isolado, bancos descartáveis por cenário e provider
sintético sem DNS/SMTP real. Cobrem concorrência, templates pt/en, retries
limitados, isolamento de providers, expiração de reserva, falha após aceitação,
reconciliação concorrente/idempotente, CLI de inspeção e proteção de rollback.

```bash
backend/.venv/bin/python -m pytest -q -m integration \
  backend/tests/test_smtp_queue_persistence.py \
  backend/tests/test_email_delivery_persistence.py \
  backend/tests/test_migration_runner.py
```

Configure `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` e `DATABASE_URL` para uma
instância exclusiva de testes com permissão de criar bancos. Não use dados de
homologação real nesta suíte.

Resultados locais em 24/10/2026:

- 872 testes não integrados e 664 de integração aprovados, sem credenciais ou
  serviço SMTP externo; 31 cenários novos de integração e oito testes novos dos
  comandos operacionais;
- 33 migrations aplicadas em PostgreSQL 16 isolado; baseline parcial e rollback
  protegidos, concorrência e cenários de falha/reconciliação aprovados;
- Ruff a partir de `backend/`, compilação Python, matrizes de acesso/segurança,
  modelo de ameaças, baseline HTTP, validador da Etapa 5 e `git diff --check`
  aprovados;
- a primeira regressão integrada identificou duas expectativas antigas a
  atualizar para a `0033` (inventário de tabelas e ordem de rollback). Foram
  corrigidas e a suíte repetida em banco vazio;
- `pg_dump`/`pg_restore` não estão instalados no host. A regressão de backup e
  restauração passou usando os clientes PostgreSQL 16 do container isolado,
  encaminhados por scripts temporários ignorados, restritos aos bancos de teste;
- execuções restritas de testes HTTP locais ficaram paradas no sandbox e foram
  encerradas. A execução autorizada com os acessos locais necessários passou;
- nenhum envio real, configuração de credencial real, alteração do banco de
  desenvolvimento ou modificação do frontend neste bloco. O smoke real permanece
  dependente de configuração e autorização específicas no bloco final.
