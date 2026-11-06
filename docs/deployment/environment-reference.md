# Referência de ambiente

Use os modelos [.env.example](../../.env.example),
[homologação](../../.env.homologation.example) e
[produção](../../.env.production.example) sem inserir credenciais no Git.
Os exemplos com domínio `.invalid` não são destinos acessíveis.

## O que realmente chega ao processo

`--env-file` alimenta a interpolação do Compose; **não injeta automaticamente
cada variável no container**. A coluna “Aplicação” distingue repasse, valor fixo
e configuração apenas do host. Para uma opção não repassada, um fluxo Compose
manual especializado precisa de overlay privado revisado com
`environment`/mounts explícitos e os mesmos `-f` em toda a operação.
**A CLI `deploy.py` usa apenas o Compose base versionado e não aceita overlays
arbitrários nem `--file`.** Não misture alterações manuais de runtime com seu
histórico. Se a implantação depende de mounts/opções ausentes do base, pare e
encaminhe a extensão do contrato de automação para implementação e teste antes
de adotá-la. O overlay SMTP permanece restrito ao procedimento especializado do
worker e seus transmissores devem estar parados durante o deploy.

A automação também ignora o `.env` implícito e variáveis de aplicação/Compose
exportadas no shell. Edite o arquivo externo aprovado; não use prefixos de
variáveis no comando para substituir sua configuração. Tokens de métricas e
limites de ingestão são exemplos que exigem repasse adicional antes de uso em
container. Credenciais SMTP nunca devem ser acrescentadas ao backend.

Em todos os perfis o Compose exige `SYNERGIA_ENV` e `POSTGRES_PASSWORD`.
Fora de development/test, config-check rejeita padrões locais, segredos vazios
ou iniciados por `CHANGE_ME`, chaves menores que 32 bytes e origens locais
(`localhost`, `127.0.0.1`, `::1`). Origens não admitem curingas, credenciais,
path (inclusive `/` final), query ou fragmento; `CHANGE_ME` em URLs também é
rejeitado. Substitua TODOS os placeholders, mesmo os não cobertos pelo validador.
Produção exige HTTPS, cookie seguro, MFA, provedor corporativo e caminhos
absolutos de secrets/mapeamento; os mounts não estão no Compose base.

Nas tabelas, “modelo” informa padrão de referência sem reproduzir segredos; regras de
obrigatoriedade em homologação e produção estão na última coluna. Quando não
houver exigência específica, a opção é ajustável e usa o padrão da aplicação.

## Perfil, imagens e banco

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `BACKEND_PORT` | Compose, porta publicada | 8000 | Porta do host para API; ajustar smoke e acesso público. |
| `WEB_PORT` | Compose, porta publicada | 8080 | Porta do host para web; ajustar origem CORS e acesso público. |
| `POSTGRES_DB` | Compose / repassada conforme serviço | synergia | Nome PostgreSQL; padrão synergia; manter idêntico em toda a operação. |
| `POSTGRES_USER` | Compose / repassada conforme serviço | synergia | Nome PostgreSQL; padrão synergia; manter idêntico em toda a operação. |
| `POSTGRES_PASSWORD` | Compose / repassada conforme serviço | configuração privada | Obrigatória na interpolação. Segredo privado, distinto dos padrões locais fora de dev. Alterar o arquivo não altera senha de volume existente. |
| `POSTGRES_PORT` | Compose / repassada conforme serviço | 5432 | Porta publicada no host; ajustar disponibilidade/rede. Não muda a porta interna. |
| `SYNERGIA_IMAGE_TAG` | Compose / repassada conforme serviço | local | Referência explícita fora de dev; apply gera tags únicas e fixa imagens por ID. Não sobrescrever tags anteriores nem usá-las para inferir o runtime confirmado. |
| `MIGRATION_BASELINE_THROUGH` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Vazia em bancos novos; uso único em legado, nome SQL exato comprovado; remover após adoção. |
| `DATABASE_URL` | Host; exige overlay para container | conninfo privado, sem valor publicado | Obrigatória no processo Python do host. Nos containers, entrypoint gera conninfo por make_conninfo a partir de PG*, preservando caracteres especiais. |
| `SYNERGIA_ENV` | Compose / repassada conforme serviço | development | Obrigatória em todos os perfis; development/test locais, homologation assistido, production condicionado. |
| `PGHOST` | Fixa no Compose; host configurável | postgres | Interno fixo postgres no Compose; host de operações usa endereço publicado aprovado. |
| `PGPORT` | Fixa no Compose; host configurável | 5432 | 5432 interno; no host corresponde a POSTGRES_PORT. |
| `PGDATABASE` | Compose / repassada conforme serviço | synergia | Derivada de POSTGRES_DB pelo Compose. |
| `PGUSER` | Compose / repassada conforme serviço | synergia | Derivada de POSTGRES_USER pelo Compose. |
| `PGPASSWORD` | Compose / repassada conforme serviço | configuração privada | Derivada de POSTGRES_PASSWORD; segredo, nunca imprimir. |

## Origens e identidade

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `SYNERGIA_API_ORIGIN` | Compose / repassada conforme serviço | http://localhost:8000 | Origem pública absoluta esquema://host[:porta], sem barra final; chega ao backend, runtime-config.js e CSP connect-src do web. Exemplo: http://api.homolog.example.invalid:8000; HTTPS obrigatório em produção. |
| `SYNERGIA_LOCAL_AUTH_ENABLED` | Compose / repassada conforme serviço | false | false por padrão; homologação permite true temporário com expiração; produção exige false. |
| `AUTH_LOCAL_LOGIN_EXPIRES_AT` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Obrigatória se login local ativo em homologação: ISO 8601 com fuso, futura e até 90 dias; gerar data atual, não copiar data vencida. |
| `AUTH_IDENTITY_PROVIDER` | Compose / repassada conforme serviço | local | local ou corporate; produção exige corporate, adaptador ainda condicionado à aprovação. |
| `AUTH_JWT_ALGORITHM` | Compose / repassada conforme serviço | HS256 | HS256 fora dos testes offline. |
| `AUTH_JWT_SIGNING_KEY` | Compose / repassada conforme serviço | configuração privada | Segredo privado independente com >=32 bytes fora de dev; não usar padrão local. |
| `AUTH_JWT_ISSUER` | Compose / repassada conforme serviço | synergia-local | Emissor dos tokens locais; homologação usa emissor próprio; consumidores devem concordar. |
| `AUTH_JWT_AUDIENCE` | Compose / repassada conforme serviço | synergia-api | Audiência dos tokens da API; consumidores devem concordar. |
| `AUTH_ACCESS_TOKEN_MINUTES` | Host; exige overlay para container | 15 | Duração do access token em minutos; aplicar por overlay no container. |
| `AUTH_REFRESH_IDLE_HOURS` | Host; exige overlay para container | 8 | Prazo ocioso do refresh em horas. |
| `AUTH_REFRESH_ABSOLUTE_HOURS` | Host; exige overlay para container | 24 | Prazo absoluto do refresh em horas. |
| `AUTH_CLOCK_SKEW_SECONDS` | Host; exige overlay para container | 30 | Tolerância temporal em segundos; relógios devem estar sincronizados. |
| `AUTH_REFRESH_COOKIE_SECURE` | Compose / repassada conforme serviço | false | true obrigatório em produção/HTTPS; false somente em HTTP transitório autorizado da homologação. |
| `AUTH_ALLOWED_ORIGINS` | Compose / repassada conforme serviço | http://localhost:4200,http://localhost:8080 | Origens web exatas separadas por vírgula. Exemplo: http://web.homolog.example.invalid:8080; HTTPS obrigatório em produção. |
| `AUTH_LOGIN_MAX_ATTEMPTS` | Host; exige overlay para container | 5 | Máximo de tentativas de login na janela de bloqueio. |
| `AUTH_LOGIN_WINDOW_SECONDS` | Host; exige overlay para container | 900 | Janela de contagem de tentativas em segundos. |
| `AUTH_LOGIN_BLOCK_SECONDS` | Host; exige overlay para container | 900 | Prazo de bloqueio de login em segundos. |
| `AUTH_CORPORATE_ISSUER` | Compose / repassada conforme serviço | https://identity.example.invalid | URL HTTPS do provedor aprovado, obrigatória para corporate. |
| `AUTH_CORPORATE_DISCOVERY_URL` | Compose / repassada conforme serviço | https://identity.example.invalid/.well-known/openid-configuration | URL HTTPS de discovery no mesmo hostname do issuer, obrigatória para corporate. |
| `AUTH_CORPORATE_AUDIENCE` | Compose / repassada conforme serviço | definir por ambiente | Audiência corporativa aprovada, obrigatória para corporate. |
| `AUTH_CORPORATE_CLIENT_ID` | Compose / repassada conforme serviço | definir por ambiente | Identificador público de cliente aprovado, obrigatório para corporate. |
| `AUTH_CORPORATE_CLIENT_SECRET_FILE` | Compose / repassada conforme serviço | configuração privada | Caminho absoluto de segredo montado; obrigatório para corporate. O Compose base não cria esse mount. |
| `AUTH_CORPORATE_MAPPING_FILE` | Compose / repassada conforme serviço | /run/secrets/identity-mapping.json | Caminho absoluto do mapeamento aprovado; obrigatório em produção. Requer mount adicional. |
| `AUTH_CORPORATE_REQUIRE_MFA` | Compose / repassada conforme serviço | true | true obrigatório em produção. |

## Rate limiting

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `RATE_LIMIT_ENABLED` | Host; exige overlay para container | true | Manter limitação habilitada; não desativar em homologação para contornar 429. |
| `RATE_LIMIT_KEY_SECRET` | Compose / repassada conforme serviço | configuração privada | Segredo privado independente com >=32 bytes fora de dev. |
| `RATE_LIMIT_TRUSTED_PROXY_CIDRS` | Host; exige overlay para container | vazio / opcional conforme regra | Somente CIDRs de proxies efetivamente confiáveis; não confiar em rede inteira por conveniência. |
| `RATE_LIMIT_LOGIN_LIMIT` | Host; exige overlay para container | 10 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REFRESH_LIMIT` | Host; exige overlay para container | 30 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REFRESH_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_UPLOAD_LIMIT` | Host; exige overlay para container | 20 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_UPLOAD_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_SEARCH_LIMIT` | Host; exige overlay para container | 120 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_SEARCH_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPROCESS_LIMIT` | Host; exige overlay para container | 10 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPROCESS_WINDOW_SECONDS` | Host; exige overlay para container | 300 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPORT_GENERATE_LIMIT` | Host; exige overlay para container | 20 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPORT_GENERATE_WINDOW_SECONDS` | Host; exige overlay para container | 300 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPORT_EXPORT_LIMIT` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_REPORT_EXPORT_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_DECISION_LIMIT` | Host; exige overlay para container | 30 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_DECISION_WINDOW_SECONDS` | Host; exige overlay para container | 60 | Cota ou janela em segundos por operação; respeitar contrato de rate limiting. |
| `RATE_LIMIT_AI_QUALITY_GENERATE_LIMIT` | Host; não repassada pelo Compose base | 3 | Cota da geração de explicação; desabilitar o modelo não remove a cota do POST. |
| `RATE_LIMIT_AI_QUALITY_GENERATE_WINDOW_SECONDS` | Host; não repassada pelo Compose base | 300 | Janela da geração em segundos; diagnóstico detalhado em IA — Qualidade. |

## Demonstrador de IA — Qualidade

O Compose padrão não inclui Ollama. A consulta a fatos/baseline determinístico
permanece disponível sem modelo. Veja [IA — Qualidade](../ai-quality-ui.md).

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `SYNERGIA_AI_QUALITY_MODEL_ENABLED` | Host; não repassada pelo Compose base | false | Manter false no Compose padrão; a geração só deve ser habilitada em runtime provisionado e validado conforme o contrato do demonstrador. |
| `SYNERGIA_AI_QUALITY_ENDPOINT` | Host; não repassada pelo Compose base | http://127.0.0.1:11434 | Loopback do processo backend; loopback de container não alcança automaticamente o host. Não publicar porta do modelo para contornar essa restrição. |

## Storage e ingestão

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `IMPORT_STORAGE_DIR` | Fixa no Compose; host configurável | ./data/imports | No Compose fixo /var/lib/synergia/imports; no host apontar para os mesmos arquivos, com acesso autorizado. |
| `UPLOAD_ALLOWED_EXTENSIONS` | Host; exige overlay para container | csv,json,xlsx | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `UPLOAD_MAX_BYTES` | Host; exige overlay para container | 26214400 | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `UPLOAD_MAX_ARCHIVE_ENTRIES` | Host; exige overlay para container | 2000 | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `UPLOAD_MAX_ARCHIVE_UNCOMPRESSED_BYTES` | Host; exige overlay para container | 104857600 | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `UPLOAD_MAX_COMPRESSION_RATIO` | Host; exige overlay para container | 100 | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `UPLOAD_REJECTED_RETENTION_HOURS` | Host; exige overlay para container | 24 | Limite de segurança de upload; bytes, contagem, razão ou horas conforme o nome; extensões csv,json,xlsx. |
| `INGESTION_MAX_SHEETS` | Host; exige overlay para container | 64 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_ROWS` | Host; exige overlay para container | 1048576 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_COLUMNS` | Host; exige overlay para container | 16384 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_CELLS` | Host; exige overlay para container | 2000000 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_FORMULAS` | Host; exige overlay para container | 2000000 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_MEMORY_BYTES` | Host; exige overlay para container | 1073741824 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_OPEN_BYTES` | Host; exige overlay para container | 33554432 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_FILES` | Host; exige overlay para container | 10 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_SECONDS` | Host; exige overlay para container | 300 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_SECONDS_WO_STATUS` | Host; exige overlay para container | 900 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_MAX_ISSUES` | Host; exige overlay para container | 250000 | Limite positivo do orçamento; ajustar somente com medição. Sufixos por fonte podem restringir o global; WO Status tem prazo próprio. |
| `INGESTION_PROGRESS_INTERVAL` | Host; exige overlay para container | 10000 | Intervalo de progresso em linhas; manter orçamento compatível com a fonte. |
| `INGESTION_ALLOWED_SHEETS` | Compose / repassada conforme serviço | * | Vazia não autoriza abas; nomes exatos separados por &#124; em homologação/produção; * somente sintético local. |
| `INGESTION_ALLOWED_SHEETS_WO_STATUS` | Host; exige overlay para container | NFP&#124;OWM SN&#124;CTNR STATUS | Restringe abas do contrato WO Status; nomes separados por &#124;. |
| `PROFILE_AVATAR_STORAGE_ROOT` | Fixa no Compose; host configurável | ./.data/avatars | No Compose fixo /var/lib/synergia/avatars; no host usar montagem correspondente. |
| `INGESTION_ALLOWED_SHEETS_TOTAL_DECISION` | Host; exige overlay para container | Sheet1 | Restringe contrato Total Decision, somente Sheet1. |

## E-mail

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `EMAIL_DELIVERY_ENABLED` | Compose / repassada conforme serviço | false | false inicialmente. true somente após autorização e provedor validado. |
| `EMAIL_PROVIDER` | Compose / repassada conforme serviço | disabled | disabled, local_capture ou smtp; lg_email_api ainda não implementado. |
| `EMAIL_FROM_ADDRESS` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Remetente autorizado obrigatório para envio; exemplo fictício: sender@example.invalid. |
| `EMAIL_CAPTURE_PATH` | Fixa no Compose; host configurável | ./data/email-capture/messages.jsonl | No Compose fixo /var/lib/synergia/email-capture/messages.jsonl; captura contém dados restritos. |
| `EMAIL_BATCH_SIZE` | Compose / repassada conforme serviço | 50 | Máximo de itens processados por chamada do worker; tarefa finita. |
| `EMAIL_MAX_ATTEMPTS` | Compose / repassada conforme serviço | 3 | Orçamento de tentativas por entrega; não zerar manualmente para reenviar. |
| `EMAIL_RETRY_SECONDS` | Compose / repassada conforme serviço | 60 | Intervalo de retry para não aceitação conhecida, em segundos. |
| `EMAIL_CONSOLIDATION_SECONDS` | Compose / repassada conforme serviço | 60 | Janela de consolidação de notificações, em segundos. |
| `EMAIL_SMTP_HOST` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Hostname/IP sem esquema nem porta; somente se smtp ativo. |
| `EMAIL_SMTP_PORT` | Compose / repassada conforme serviço | 587 | Inteiro entre 1 e 65535; depende do relay e modo TLS aprovado. |
| `EMAIL_SMTP_TLS_MODE` | Compose / repassada conforme serviço | starttls | starttls ou implicit; TLS obrigatório. |
| `EMAIL_SMTP_TIMEOUT_SECONDS` | Compose / repassada conforme serviço | 15 | Prazo por operação do transporte, finito, maior que zero e no máximo 30 segundos. |
| `EMAIL_SMTP_AUTH_MODE` | Compose / repassada conforme serviço | password | password ou none explícito para relay autorizado com TLS. |
| `EMAIL_SMTP_USERNAME` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Obrigatório no modo password; configuração privada. |
| `EMAIL_SMTP_PASSWORD` | Compose / repassada conforme serviço | configuração privada | Segredo somente no email-worker; escolher senha OU arquivo, nunca ambos. |
| `EMAIL_SMTP_PASSWORD_FILE` | Compose / repassada conforme serviço | configuração privada | Arquivo UTF-8 externo, legível pelo UID 10001; somente email-worker. |
| `EMAIL_SMTP_ALLOWED_RECIPIENTS` | Compose / repassada conforme serviço | vazio / opcional conforme regra | Allowlist de 1 a 500 caixas exatas separadas por vírgula, sem curingas. |
| `EMAIL_SMTP_SECRET_PATH` | Somente overlay SMTP | configuração privada | Caminho privado do host, obrigatório no overlay docker-compose.smtp.yml; não é lido diretamente pela aplicação. |

## Observabilidade e operações

| Variável | Aplicação | Modelo / formato | Regra por perfil e exemplo seguro |
| --- | --- | --- | --- |
| `OBSERVABILITY_LOG_LEVEL` | Compose / repassada conforme serviço | INFO | Nível de log; INFO recomendado, sem valores sensíveis. |
| `OBSERVABILITY_METRICS_TOKEN` | Host; exige overlay para container | configuração privada | Segredo técnico obrigatório para acesso a /metrics; não chega pelo Compose base. |
| `OBSERVABILITY_PROBE_TIMEOUT_SECONDS` | Host; exige overlay para container | 2 | Prazo em segundos para sonda, heartbeat ou degradação da fila; ver observabilidade. |
| `OBSERVABILITY_WORKER_STALE_SECONDS` | Host; exige overlay para container | 300 | Prazo em segundos para sonda, heartbeat ou degradação da fila; ver observabilidade. |
| `OBSERVABILITY_QUEUE_DEGRADED_SECONDS` | Host; exige overlay para container | 300 | Prazo em segundos para sonda, heartbeat ou degradação da fila; ver observabilidade. |
| `DATA_OPERATIONS_ACTOR` | Host; exige overlay para container | synergia-operator | Identidade técnica para trilha de operações; ajustar ao responsável autorizado. |

## Gerar material privado e validar

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
python3 -c "from datetime import UTC, datetime, timedelta; print((datetime.now(UTC) + timedelta(days=30)).isoformat())"
```

- **Onde executar:** terminal privado do host, sem gravação de sessão.
- **Efeito:** gera chave aleatória e data futura; não configura o sistema.
- **Resultado esperado:** 0; chave com mais de 32 bytes e data ISO 8601 com fuso.
- **Interpretação de falhas:** Python incompatível; não improvisar chave curta.
- **Próxima ação:** guardar a chave diretamente no arquivo privado, gerar outra independente para rate limiting e conferir expiração no momento da implantação. Não copiar as saídas para chamados.
- **Pré-condições:** Terminal privado sem transcrição e Python 3.11+ disponível; nenhuma saída deve ser publicada.
- **Entradas:** Aleatoriedade do sistema e relógio UTC; nenhum segredo existente é consumido.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env config --quiet
```

- **Onde executar:** host, raiz do checkout.
- **Efeito:** somente leitura; valida interpolação sem imprimir segredos.
- **Resultado esperado:** 0, sem saída.
- **Interpretação de falhas:** variável obrigatória ausente ou sintaxe inválida. Sucesso não comprova regras do perfil.
- **Próxima ação:** executar `scripts/deploy.py precheck` e o fluxo da [primeira implantação](deployment-guide.md); a CLI valida também as regras do perfil e a identidade dos recursos.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Contratos detalhados: [autenticação](../authentication.md),
[rate limiting](../rate-limiting.md), [orçamento XLSX](../xlsx-ingestion-budget.md),
[segurança de upload](../upload-security.md), [SMTP](../smtp-email-provider.md),
[observabilidade](../observability.md) e [perfis](../deployment-environments.md).
