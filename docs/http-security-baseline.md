# Baseline de segurança HTTP e navegador

Esta política vale para todas as respostas da API, inclusive erros e preflight.
A API retorna CSP restritiva (`default-src 'none'`), bloqueio de framing e MIME
sniffing, `Referrer-Policy: no-referrer`, `Permissions-Policy` mínima e
`Cross-Origin-Resource-Policy: same-site`. HSTS é emitido somente em produção,
onde a terminação TLS é obrigatória.

Todas as respostas da API usam `Cache-Control: no-store`; `/health` usa
`no-cache`. A escolha conservadora inclui autenticação, perfil, decisões,
relatórios e downloads e impede armazenamento compartilhado de tokens ou dados
sensíveis.

## Configuração por ambiente

`AUTH_ALLOWED_ORIGINS` deve conter uma lista explícita, separada por vírgulas,
de origens HTTP(S). Curingas são rejeitados porque a aplicação usa credenciais.
Os únicos métodos CORS aceitos são `GET`, `POST`, `PUT`, `PATCH`, `DELETE` e
`OPTIONS`; os headers de requisição permitidos são `Authorization`,
`Content-Type` e `X-Correlation-ID`.

| Ambiente | Origem esperada | Cookie de refresh | HSTS |
| --- | --- | --- | --- |
| development | `http://localhost:4200` | `HttpOnly`, `SameSite=Strict`; `Secure` pode ser desligado localmente | não |
| test | origem isolada do teste | mesmas regras de desenvolvimento | não |
| homologation | URL HTTPS homologada e explícita | `Secure`, `HttpOnly`, `SameSite=Strict` | não, se aplicado pelo proxy |
| production | URL HTTPS oficial e explícita | `Secure`, `HttpOnly`, `SameSite=Strict` obrigatório | sim |

O access token continua somente em memória no Angular. A CSP do documento não
permite `unsafe-eval`. A exceção `style-src 'unsafe-inline'` é temporária e
necessária aos estilos de componentes gerados pelo Angular; scripts inline não
são permitidos. O proxy que publicar o frontend deve repetir a CSP como header,
principalmente para garantir `frame-ancestors`, que não é aplicado via meta tag.

Conteúdo de usuário é renderizado por interpolação Angular. O validador
`scripts/validate_http_security.py` impede a introdução dos sinks diretos
`innerHTML`, `bypassSecurityTrustHtml` e `document.write` sem uma revisão
explícita desta política.
