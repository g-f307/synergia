# Diagnóstico por sintoma

Use o mesmo projeto, env-file e overlays da implantação. Examine saídas apenas
em terminal restrito; compartilhe códigos sanitizados, nunca configuração,
URLs internas, tokens, dados de usuários ou logs brutos.

| Sintoma inicial | Seguir |
| --- | --- |
| Compose/config-check falha | Ambiente abaixo |
| 401/403/503 no login, CORS, sessão cai | Autenticação abaixo |
| migrate falha, banco unhealthy, readiness postgresql 503 | Banco abaixo |
| Tela branca, localhost no navegador, CSP | Frontend abaixo |
| readiness storage 503, upload rejeitado | Storage abaixo |
| E-mail ausente ou worker termina | Worker abaixo |
| Operação interrompida ou lock | Deploy abaixo |

## Ambiente

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env config --quiet
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env run --rm --no-deps config-check
```

- **Onde executar:** host, raiz do checkout já construído.
- **Efeito:** valida interpolação e cria tarefa temporária sem banco.
- **Resultado esperado:** 0; configuração válida e perfil homologation.
- **Interpretação de falhas:** mensagens abaixo identificam o campo bloqueado.
- **Próxima ação:** corrigir arquivo privado e repetir pré-validação; seguir [primeira implantação](deployment-guide.md).

| Mensagem | Causa e correção |
| --- | --- |
| `Set SYNERGIA_ENV explicitly` / `Set POSTGRES_PASSWORD explicitly` | Campo ausente na interpolação; preencher no arquivo privado correto |
| `invalid deployment configuration: ... must be configured outside development` | Campo vazio, padrão local ou iniciado por CHANGE_ME; gerar configuração privada |
| `must not contain an unedited placeholder` | URL ainda contém CHANGE_ME; substituir origem |
| `must contain at least 32 bytes` | Chave curta; gerar chave independente e revisar impacto em sessões |
| `must not use a local address outside development` | Origem localhost/loopback; usar origem acessível ao navegador |
| `must not contain credentials, path, query or fragment` | Valor não é origem exata; retirar barra final e demais componentes |
| `port is already allocated` | Porta do host ocupada; plataforma identifica proprietário ou ajusta portas públicas |

## Autenticação

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env logs --tail 80 backend
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' http://127.0.0.1:8000/health/ready
```

- **Onde executar:** host, raiz do checkout; porta ajustada ao ambiente.
- **Efeito:** consulta logs e readiness (sonda escreve arquivo temporário no storage).
- **Resultado esperado:** perfil correto, readiness 200; verificar login separadamente no navegador autorizado.
- **Interpretação de falhas:** readiness saudável não prova autenticação; usar tabela abaixo e painel Network sem copiar tokens.
- **Próxima ação:** corrigir configuração/IAM; recriar backend/web conforme [atualização](update-and-rollback.md), depois validar sessão.

- `AUTH_LOCAL_LOGIN_EXPIRES_AT must be in the future and at most 90 days`:
  autorização temporária expirada/inválida; responsável deve aprovar novo prazo.
- `503 identity_adapter_unavailable` ou `auth_configuration_invalid`:
  adaptador corporativo ausente/incompleto; não alegar SSO operacional.
  Ver [ativação corporativa](../runbooks/corporate-identity-activation.md).
- 401: conferir credencial/sessão e janela local com IAM; 403: conferir permissão
  e escopo organizacional. Não desabilitar autorização para contornar.
- CORS: comparar origem exata na barra do navegador com `AUTH_ALLOWED_ORIGINS`.
  IP e hostname diferentes são origens diferentes. CSP também deve permitir API.
- Sessão cai após refresh em HTTP: cookie Secure não é enviado por HTTP;
  usar HTTPS ou a configuração transitória aprovada de homologação. Não relaxar produção.

## Banco

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env ps --all
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env logs --tail 80 postgres migrate
```

- **Onde executar:** host, raiz do checkout; logs de migrate só existem se foi criado como serviço persistente.
- **Efeito:** somente leitura; verifica disponibilidade e logs.
- **Resultado esperado:** postgres healthy/accepting connections; migration concluída com 0.
- **Interpretação de falhas:** pg_isready não comprova senha correta nem schema. Com `run --rm migrate`, usar resultado capturado da tarefa, não ausência no ps.
- **Próxima ação:** seguir mensagem abaixo e [banco indisponível](../runbooks/database-unavailable.md); não apagar volume.

| Mensagem/estado | Causa e ação |
| --- | --- |
| `published migration changed: ...` | Checksum divergiu; recuperar artefato aprovado, não alterar ledger |
| `recorded migration is unavailable: ...` | Checkout/imagem omite SQL já registrado; selecionar versão íntegra |
| `legacy synergia schema detected without migration history` | Adotar somente com backup e última migration comprovada |
| `legacy schema is partial or incompatible` | Probes de baseline falharam; revisão por DBA, sem forçar adoção |
| migrate aguardando indefinidamente | Lock `7347319119`; verificar migrador concorrente com DBA. Não matar sessão sem avaliar transação |
| password authentication failed | Senha do volume existente difere da configuração; alinhar/rotacionar por procedimento de banco. Alterar POSTGRES_PASSWORD não redefine usuário existente |

## Frontend

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/runtime-config.js
curl --fail --silent --show-error --head http://127.0.0.1:8080/
```

- **Onde executar:** host e, depois, estação do usuário com o endereço público correto.
- **Efeito:** somente leitura; consulta configuração pública e headers.
- **Resultado esperado:** 200, `apiUrl` igual à origem aprovada, CSP com `connect-src 'self'` e a origem da API.
- **Interpretação de falhas:** localhost aponta à máquina do navegador; CSP incorreta bloqueia requisições mesmo com API healthy.
- **Próxima ação:** ajustar `SYNERGIA_API_ORIGIN`/CORS no arquivo privado, recriar serviços abaixo e reabrir navegador; se CSP persistir, revisar proxy/headers.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env up -d --no-deps --force-recreate backend web
```

- **Onde executar:** host, raiz da revisão implantada, janela autorizada após correção do arquivo.
- **Efeito:** mutável; recria containers para aplicar ambiente/runtime sem SQL.
- **Resultado esperado:** healthy, runtime-config e CORS corrigidos.
- **Interpretação de falhas:** restart simples não injeta novo ambiente; erro de perfil bloqueia backend.
- **Próxima ação:** repetir smoke e [aceite](post-deployment-checklist.md).

## Storage

```bash
curl --silent --show-error http://127.0.0.1:8000/health/ready
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env exec -T backend id
```

- **Onde executar:** host, raiz do checkout, ajustando porta.
- **Efeito:** consulta readiness (teste de escrita temporária) e identidade do processo.
- **Resultado esperado:** status ready, storage pronto e UID 10001.
- **Interpretação de falhas:** storage 503 indica montagem/permissão/espaço; rejeição de planilha com readiness saudável pode ser contrato ou orçamento.
- **Próxima ação:** plataforma corrige acesso ao volume para UID/GID 10001; não usar chmod 777. Para abas, preencher INGESTION_ALLOWED_SHEETS com nomes exatos, repassar limites via overlay quando necessário.

Ver [storage](../runbooks/storage-unavailable.md),
[arquivo inválido](../runbooks/invalid-file.md) e
[referência de ambiente](environment-reference.md). Não liberar `*` para dados reais.

## Worker

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env logs --tail 80 email-worker
```

- **Onde executar:** host, raiz do checkout; se tarefa foi descartada, usar saída privada da execução.
- **Efeito:** somente leitura; não dispara envio para diagnosticar.
- **Resultado esperado:** evento email_worker.completed com contagens e outcome esperado.
- **Interpretação de falhas:** saída 0 significa lote sem falhas OU canal desabilitado; 1 indica falha parcial/email_state_unavailable; 2 indica email_configuration_invalid. O entrypoint pode falhar antes do worker.
- **Próxima ação:** verificar perfil/provedor, rede/TLS e configuração; seguir [operação de e-mail](lg-email-api.md).

O worker não é daemon nem possui agendamento automático. `uncertain` bloqueia
reenvio: parar transmissores, inspecionar e reconciliar com evidência externa.
Aceitação pelo servidor não garante recebimento. Falha de API LG não se resolve
selecionando smtp; o adaptador HTTP depende de #171/#170.

## Deploy

No fluxo manual, não existe estado automatizado `uncertain`: registrar a fase
interrompida, suspender tráfego, consultar ledger e imagens antes de qualquer
nova execução. Não repetir migrate por suposição de que houve rollback integral.

Para a automação #166, ainda indisponível aqui, o contrato previsto usa
`scripts/deploy.py diagnose` e `reconcile` primeiro em inspeção. Estado `running`
ou `uncertain` bloqueia apply/rollback até decisão; não remover arquivos de lock
ou histórico. Regras de resume/rollback e recuperação completa estão em
[atualização e rollback](update-and-rollback.md).
