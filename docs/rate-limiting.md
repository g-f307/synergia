# Rate limiting e proteção contra abuso

A API aplica cotas compartilhadas no PostgreSQL antes das operações críticas. Cada
requisição consome uma cota por origem e, quando autenticada, cotas adicionais por
usuário e sessão. O parâmetro `organization_id`, quando faz parte da URL, também
consome uma cota própria. Trocar rota ou organização não restaura as cotas de
identidade.

No refresh, o token opaco é resolvido para a sessão persistida antes da cobrança.
Assim, a rotação normal do cookie não cria uma nova cota e tokens desconhecidos
continuam limitados por origem e pelo fingerprint da credencial apresentada.

| Operação | Limite padrão | Janela | Falha do limitador |
| --- | ---: | ---: | --- |
| Login | 10 | 60 s | fechada |
| Refresh | 30 | 60 s | fechada |
| Upload | 20 | 60 s | fechada |
| Busca | 120 | 60 s | fechada |
| Reprocessamento | 10 | 300 s | fechada |
| Geração de relatório | 20 | 300 s | fechada |
| Exportação | 60 | 60 s | fechada |
| Decisão humana | 30 | 60 s | fechada |

Os limites e janelas usam as variáveis `RATE_LIMIT_<OPERATION>_LIMIT` e
`RATE_LIMIT_<OPERATION>_WINDOW_SECONDS` documentadas em `.env.example`. Valores
inválidos impedem o processamento protegido. `RATE_LIMIT_KEY_SECRET` deve ser um
segredo aleatório com pelo menos 32 bytes; se omitido, a chave de assinatura JWT é
usada. A produção deve fornecer segredos distintos e rotacioná-los de forma
coordenada.

## Proxies e privacidade

Por padrão, somente o endereço do peer TCP é considerado. `X-Forwarded-For` só é
aceito quando o peer pertence a uma rede listada explicitamente em
`RATE_LIMIT_TRUSTED_PROXY_CIDRS`. A cadeia é percorrida da direita para a esquerda
e somente hops confiáveis são descartados, impedindo spoofing do primeiro valor.
As chaves são protegidas com HMAC-SHA-256. IPs,
tokens, parâmetros de negócio e payloads nunca são persistidos nos buckets ou nos
eventos.

## Resposta e recuperação

Uma cota esgotada responde `429` com código estável `rate_limit_exceeded`, campo
`retry_after_seconds` e header `Retry-After`. A cota volta a aceitar requisições ao
fim da janela. Falhas do PostgreSQL respondem `503 rate_limit_unavailable`.
Nenhuma operação protegida segue sem consumir sua cota, evitando bypass durante
degradações.

## Observabilidade e ajuste

`synergia.rate_limit_buckets` expõe contadores agregados e
`synergia.rate_limit_events` registra apenas negações, operação, dimensão, hash,
correlation ID e espera recomendada. Alertas devem usar volume de negações por
operação, nunca tentar reidentificar o hash. Exceções temporárias devem alterar a
configuração por ambiente, possuir prazo e ser revisadas após observar picos
legítimos; não se deve desabilitar globalmente o controle em produção.
