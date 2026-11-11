# E-mail: worker e API interna LG

> [!IMPORTANT]
> Provedores existentes: `disabled`, `local_capture` e `smtp`. Há fila persistente
> `synergia.email_deliveries`, templates, auditoria, worker isolado e reconciliação
> em `synergia.email_delivery_reconciliations`. O SMTP foi validado na #143;
> isso não comprova integração com a API HTTP da LG. A PoC depende da #171 e
> o adaptador `LgEmailApiProvider` da #170. `EMAIL_PROVIDER=lg_email_api` ainda
> não é aceito. Na homologação LG, manter `EMAIL_DELIVERY_ENABLED=false` e
> `EMAIL_PROVIDER=disabled`, ou usar captura local aprovada sem envio externo.

## Estado comprovado em 06/11/2026

A rodada interna da #171 aprovou a configuração local, mas o GET do OpenAPI
terminou com TimeoutError, o JSON não abriu no navegador e o teste TCP foi
falso. Não houve POST de envio no roteiro relatado. Isso comprova que o acesso
necessário não foi estabelecido nessa estação; não identifica isoladamente
firewall, rota, proxy, destino incorreto ou indisponibilidade do serviço.

O [PR #180](https://github.com/g-f307/synergia/pull/180) mantém o utilitário
isolado, o roteiro Windows e o relato sanitizado. Essa preparação não equivale
a aprovação da integração ou à disponibilidade do provider na aplicação.
A #171 continua aguardando acesso e contrato, e a #170 não deve iniciar sem
decisão explícita. Nenhum endereço, conta ou resposta real deve ser copiado
para este guia.

## Contrato conhecido e o que falta confirmar

O relato de integração descreve `POST /SMTP`, multipart/form-data, em serviço
HTTP interno documentado por Swagger. Não se trata de SMTP por host/porta.
Exemplo exclusivamente fictício: `https://email-api.example.invalid/SMTP`.

| Campo | Informação conhecida / validação pendente na PoC |
| --- | --- |
| `Subject` | Campo string documentado; confirmar encoding e obrigatoriedade, usando conteúdo sintético |
| `Body` | Corpo sintético; confirmar suporte a texto/HTML e encoding |
| `To` | Caixa interna explicitamente autorizada; confirmar formato/cardinalidade |
| `CC` | Campo string documentado; confirmar obrigatoriedade e diferença entre omitido/vazio |
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

Enquanto navegador e TCP não acessarem o JSON, registrar bloqueio e acionar
TI/responsável pelo serviço para confirmar destino, disponibilidade, origem
de rede e eventual proxy. Não executar POST nem tratar esse timeout de GET
como ensaio de timeout de envio.

Para diagnóstico GET em host Linux autorizado, preparar um único arquivo
privado 0600, em diretório 0700 fora do Git: `lg-email-read.curl`, contendo
a URL OpenAPI aprovada e o mecanismo de acesso confirmado. Revisar para não
incluir opções verbose, trace, retry, redirect ou insecure. Não presume TLS,
token ou outro mecanismo que o responsável ainda não confirmou; nunca
desative verificação TLS para contornar falha de certificado.

```bash
chmod 0600 /caminho/privado/synergia-config/lg-email-read.curl
curl -q --config /caminho/privado/synergia-config/lg-email-read.curl --silent --fail --retry 0 --connect-timeout 5 --max-time 20 --output /dev/null --write-out '%{http_code} %{content_type}\n'
```

- **Onde executar:** host interno autorizado, terminal privado, após revisão do arquivo curl.
- **Efeito:** ajusta permissões e faz somente GET, sem envio de e-mail; testa acesso ao OpenAPI.
- **Resultado esperado:** 0, HTTP 200 e conteúdo JSON esperado; confirmar privadamente que não é HTML de login.
- **Interpretação de falhas:** curl 6 DNS, 7 conexão, 28 timeout, 60 certificado; 22 com 401/403 exige revisão de acesso e 404 de caminho. HTTP 000 não é resposta da API.
- **Próxima ação:** corrigir a camada com a equipe, sem publicar valores privados; depois retomar o roteiro da #171 com captura/hash da especificação e envio individual autorizado.
- **Pré-condições:** Acesso interno autorizado e arquivo curl previamente revisado, sem opções de envio/retry/redirect/insecure.
- **Entradas:** Arquivo privado lg-email-read.curl com destino GET e mecanismo de acesso confirmados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

O GET acima é diagnóstico de acesso, não validação de entrega nem obtenção
completa do contrato. Após desbloqueio, seguir o roteiro do PR #180, preservar
hash/versão da especificação e confirmar autorização, destinatários e
correlação antes do primeiro envio. Não usar um POST avulso como health check.
O CLI SMTP abaixo não reconcilia uma chamada HTTP da PoC.

Evidência permitida: data, revisão lógica, códigos, duração, marcador sintético,
confirmação observada e pendências. Não publicar arquivos privados, headers,
URLs/IPs, destinatários, conteúdo, configuração ou resposta bruta.

## Operação atual do worker

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env --profile email run --rm --no-deps email-worker
```

- **Onde executar:** host, raiz do checkout, após banco e migrations prontos; somente com estado do canal aprovado.
- **Efeito:** mutável; processa um lote, podendo transmitir se canal estiver habilitado.
- **Resultado esperado:** 0 e evento email_worker.completed; disabled processa zero, sucesso não comprova recebimento externo.
- **Interpretação de falhas:** 1 falha parcial/estado indisponível, 2 configuração inválida; tarefa não é daemon e não se agenda sozinha.
- **Próxima ação:** conferir contagens/códigos; não agendar sem política aprovada. Seguir [recuperação de notificações](../runbooks/report-notification-recovery.md).
- **Pré-condições:** Canal/provedor autorizados, banco/migrations prontos e condições específicas de inspeção/resolução satisfeitas.
- **Entradas:** Configuração externa, overlay SMTP quando indicado e UUIDs aprovados; segredo somente no transmissor.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

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
- **Pré-condições:** Canal/provedor autorizados, banco/migrations prontos e condições específicas de inspeção/resolução satisfeitas.
- **Entradas:** Configuração externa, overlay SMTP quando indicado e UUIDs aprovados; segredo somente no transmissor.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env -f docker-compose.yml -f docker-compose.smtp.yml --profile email run --rm --no-deps email-worker python scripts/reconcile_smtp_delivery.py UUID_DA_ENTREGA --apply --resolution accepted --evidence recipient_confirmation --request-id UUID_DA_REQUISICAO --actor-id UUID_DO_ATOR --workers-stopped
```

- **Onde executar:** host, raiz do checkout; UUIDs válidos, evidência de aceitação obtida, todos os transmissores e agendadores realmente parados.
- **Efeito:** mutável; resolve incerteza com auditoria. --workers-stopped declara uma pré-condição, não para processos.
- **Resultado esperado:** 0 e reconciliação registrada sem novo envio.
- **Interpretação de falhas:** 2 smtp_reconciliation_rejected, 1 smtp_reconciliation_unavailable; não modificar tabelas manualmente.
- **Próxima ação:** accepted também admite evidência smtp_log. not_accepted exige evidência positiva smtp_log; ausência na inbox não basta. Avaliar orçamento de tentativas antes de retomar worker. Ver [runbook SMTP](../smtp-email-provider.md).
- **Pré-condições:** Canal/provedor autorizados, banco/migrations prontos e condições específicas de inspeção/resolução satisfeitas.
- **Entradas:** Configuração externa, overlay SMTP quando indicado e UUIDs aprovados; segredo somente no transmissor.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.
