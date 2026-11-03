# E-mail: worker e API interna LG

> [!IMPORTANT]
> Provedores existentes: `disabled`, `local_capture` e `smtp`. Há fila persistente
> `synergia.email_deliveries`, templates, auditoria, worker isolado e reconciliação
> em `synergia.email_delivery_reconciliations`. O SMTP foi validado na #143;
> isso não comprova integração com a API HTTP da LG. A PoC depende da #171 e
> o adaptador `LgEmailApiProvider` da #170. `EMAIL_PROVIDER=lg_email_api` ainda
> não é aceito. Na homologação LG, manter `EMAIL_DELIVERY_ENABLED=false` e
> `EMAIL_PROVIDER=disabled`, ou usar captura local aprovada sem envio externo.

## Contrato conhecido e o que falta confirmar

O relato de integração descreve `POST /SMTP`, multipart/form-data, em serviço
HTTP interno documentado por Swagger. Não se trata de SMTP por host/porta.
Exemplo exclusivamente fictício: `https://email-api.example.invalid/SMTP`.

| Campo | Informação conhecida / validação pendente na PoC |
| --- | --- |
| `Subject` | Texto UTF-8; usar assunto sintético sem controles |
| `Body` | Corpo sintético; confirmar suporte a texto/HTML e encoding |
| `To` | Caixa interna explicitamente autorizada; confirmar formato/cardinalidade |
| `CC` | Opcional conforme contrato real; confirmar comportamento quando omitido |
| `Files` | Anexos fora da integração inicial; não enviar arquivos reais |

Resposta relatada: HTTP `200 Success` genérico. Ainda confirmar autenticação,
TLS/CA, esquema OpenAPI, limites, erros, prazo, significado de sucesso e mecanismo
de correlação/idempotência. Não assumir que 200 garante inbox. Timeout ou queda
depois de transmitir o corpo deve ser tratado como resultado `uncertain`, sem
repetição automática até reconciliação externa. Estas são regras exigidas para
o futuro adaptador, não capacidade HTTP já entregue no SYNERGIA.

## PoC interna autorizada (#171)

Obter da equipe LG, por canal restrito: URL base e do OpenAPI, autenticação,
CA confiável, egress permitido e caixa de teste. A estação deve representar
a rede de saída do futuro worker; sucesso no host não comprova acesso de container.
Sem essas informações, não executar POST nem tentar adivinhar endpoints.

O operador prepara, com editor privado e modo 0600 em diretório 0700, dois
arquivos de configuração curl fora do Git:

- `lg-email-read.curl`: `url` para o OpenAPI aprovado (GET somente leitura),
  autenticação/CA conforme LG, sem opções verbose, trace, retry, redirect ou insecure.
- `lg-email-send.curl`: `url` para `/SMTP`, mesma segurança, e `form-string`
  para `To` com caixa autorizada. Não reutilizar URL GET. Nunca incluir Files.

Sintaxe de referência sem dados reais: `url = "https://email-api.example.invalid/SMTP"`
e `form-string = "To=recipient@example.invalid"` no arquivo de envio. No arquivo
de leitura, usar `url` do OpenAPI informado pela LG; autenticação e CA devem
seguir o contrato fornecido, sem presumir um esquema de credenciais.

URLs e destinatários são carregados por curl a partir desses arquivos;
não exportar valores nem digitá-los na linha de comando/histórico. Os nomes de
arquivo são exemplos privados, não variáveis reconhecidas pelo backend.

```bash
chmod 0600 /caminho/privado/synergia-config/lg-email-read.curl /caminho/privado/synergia-config/lg-email-send.curl
curl -q --config /caminho/privado/synergia-config/lg-email-read.curl --silent --fail --retry 0 --connect-timeout 5 --max-time 20 --output /dev/null --write-out '%{http_code} %{content_type}\n'
```

- **Onde executar:** host interno autorizado, terminal privado, após revisão dos arquivos curl.
- **Efeito:** ajusta permissões e faz GET, sem envio de e-mail; testa DNS, TCP, TLS e acesso HTTP ao OpenAPI.
- **Resultado esperado:** 0, HTTP 200 e tipo esperado do OpenAPI (normalmente application/json).
- **Interpretação de falhas:** curl 6 DNS, 7 conexão/rota, 28 timeout, 60 certificado; 22 com 401/403 indica autenticação/acesso, 404 caminho incorreto. HTTP 000 é falha anterior à resposta; 200 HTML pode ser página de login.
- **Próxima ação:** equipe de rede/identidade corrige a camada indicada sem desligar TLS; revisar contrato real no Swagger restrito e só então autorizar envio.

Depois da autorização explícita para **um envio** e confirmação da caixa de
teste, executar uma vez. Registrar horário UTC e identificador sintético no
assunto para o destinatário confirmar recebimento sem expor mensagem real.

```bash
curl -q --config /caminho/privado/synergia-config/lg-email-send.curl --silent --fail --retry 0 --connect-timeout 5 --max-time 20 --form-string 'Subject=[SYNERGIA-POC] Teste Sintetico ISSUE167-TESTE01' --form-string 'Body=Mensagem sintetica autorizada para validar conectividade.' --output /dev/null --write-out '%{http_code} %{content_type}\n'
```

- **Onde executar:** host interno aprovado, com arquivo privado que contém URL/auth/To revisados.
- **Efeito:** mutável e externo; POST multipart pode enviar e-mail real para caixa de ensaio. Não executar como health check.
- **Resultado esperado:** 0/HTTP 200 conforme contrato confirmado, mais confirmação independente da caixa autorizada e correlação ISSUE167-TESTE01.
- **Interpretação de falhas:** 200 sem confirmação não prova entrega; timeout após transmissão é incerto. Sem retry nem redirect; não repetir para descobrir se chegou.
- **Próxima ação:** correlacionar com administrador/destinatário; registrar resultado sanitizado na #171 e especificar adaptador na #170. O CLI SMTP abaixo não reconcilia uma chamada HTTP avulsa da PoC.

Evidência permitida: data UTC, revisão do contrato sem host interno, códigos
HTTP/saída, duração, correlação sintética e confirmação sim/não. Nunca anexar
arquivos curl, Authorization, URL/IP, destinatários, conteúdo ou resposta bruta.

## Operação atual do worker

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env --profile email run --rm --no-deps email-worker
```

- **Onde executar:** host, raiz do checkout, após banco e migrations prontos; somente com estado do canal aprovado.
- **Efeito:** mutável; processa um lote, podendo transmitir se canal estiver habilitado.
- **Resultado esperado:** 0 e evento email_worker.completed; disabled processa zero, sucesso não comprova recebimento externo.
- **Interpretação de falhas:** 1 falha parcial/estado indisponível, 2 configuração inválida; tarefa não é daemon e não se agenda sozinha.
- **Próxima ação:** conferir contagens/códigos; não agendar sem política aprovada. Seguir [recuperação de notificações](../runbooks/report-notification-recovery.md).

Para SMTP aprovado, usar overlay de secret file somente nos transmissores.
O backend recebe configuração pública e **não recebe a senha SMTP**. O arquivo
externo precisa ser legível pelo UID 10001; o secret do Compose não garante
criptografia no host. Configure EMAIL_SMTP_SECRET_PATH no arquivo privado.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env -f docker-compose.yml -f docker-compose.smtp.yml --profile email run --rm --no-deps email-worker python scripts/smoke_smtp_delivery.py --notification-id UUID_DA_NOTIFICACAO
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env -f docker-compose.yml -f docker-compose.smtp.yml --profile email run --rm --no-deps email-worker python scripts/reconcile_smtp_delivery.py UUID_DA_ENTREGA
```

- **Onde executar:** host, raiz do checkout; substituir UUIDs por alvos aprovados, banco/migrations prontos.
- **Efeito:** inspeção sem envio nem resolução; cria containers temporários com segredo só no worker.
- **Resultado esperado:** 0 com JSON sanitizado; smoke ready, entrega identificada para inspeção.
- **Interpretação de falhas:** 2 indica configuração/alvo inválido, 1 indisponibilidade; smoke sem --send não transmite.
- **Próxima ação:** envio SMTP controlado exige as duas flags --send e --allow-real-send e autorização específica; resolução exige procedimento abaixo e evidência externa.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env -f docker-compose.yml -f docker-compose.smtp.yml --profile email run --rm --no-deps email-worker python scripts/reconcile_smtp_delivery.py UUID_DA_ENTREGA --apply --resolution accepted --evidence recipient_confirmation --request-id UUID_DA_REQUISICAO --actor-id UUID_DO_ATOR --workers-stopped
```

- **Onde executar:** host, raiz do checkout; UUIDs válidos, evidência de aceitação obtida, todos os transmissores e agendadores realmente parados.
- **Efeito:** mutável; resolve incerteza com auditoria. --workers-stopped declara uma pré-condição, não para processos.
- **Resultado esperado:** 0 e reconciliação registrada sem novo envio.
- **Interpretação de falhas:** 2 smtp_reconciliation_rejected, 1 smtp_reconciliation_unavailable; não modificar tabelas manualmente.
- **Próxima ação:** accepted também admite evidência smtp_log. not_accepted exige evidência positiva smtp_log; ausência na inbox não basta. Avaliar orçamento de tentativas antes de retomar worker. Ver [runbook SMTP](../smtp-email-provider.md).
