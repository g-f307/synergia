# Baseline de segurança HTTP e navegador

A política vale para respostas da API, inclusive erros e preflight. Ela aplica
CSP restritiva, bloqueio de framing e MIME sniffing, `no-referrer`, uma
`Permissions-Policy` mínima e `Cross-Origin-Resource-Policy: same-site`. HSTS é
emitido somente em produção, onde a terminação TLS é obrigatória.

Todas as respostas da API usam `Cache-Control: no-store`; as rotas `/health*`
usam `no-cache`. Isso inclui autenticação, perfil, decisões, relatórios e downloads.

## Configuração por ambiente

`AUTH_ALLOWED_ORIGINS` contém as origens explícitas aceitas pela API. Curingas
são rejeitados porque a aplicação usa credenciais. O CORS aceita apenas `GET`,
`POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, `Authorization`, `Content-Type` e
`X-Correlation-ID`.

`SYNERGIA_API_ORIGIN` define o `connect-src` do frontend publicado. Ela deve ser
uma origem HTTP(S) absoluta, sem caminho, e assumir o endereço real da API em
cada implantação.

| Ambiente | `AUTH_ALLOWED_ORIGINS` | `SYNERGIA_API_ORIGIN` | Cookie/HSTS |
| --- | --- | --- | --- |
| development | URL local do Angular | URL local da API | cookie seguro opcional; sem HSTS |
| test | URL isolada do teste | URL isolada da API | cookie seguro opcional; sem HSTS |
| homologation | URL HTTPS homologada | URL HTTPS homologada da API | cookie `Secure`; HSTS no proxy |
| production | URL HTTPS oficial | URL HTTPS oficial da API | cookie `Secure`; HSTS obrigatório |

O access token permanece somente em memória. A CSP não permite `unsafe-eval`.
A exceção `style-src 'unsafe-inline'` é temporária e necessária aos estilos de
componentes Angular; scripts inline não são permitidos.

## Publicação do frontend

A CSP não usa meta tag. `web/Dockerfile` e
`web/nginx/default.conf.template` publicam o header definitivo e substituem
`SYNERGIA_API_ORIGIN` na inicialização do container. Assim,
`frame-ancestors 'none'` é efetivo no navegador. A imagem define
`NGINX_ENVSUBST_FILTER=^SYNERGIA_` para preservar variáveis próprias do Nginx.

O fluxo E2E gera o build de produção e o publica com os mesmos headers usando
`scripts/serve_secure_web.py`. O Playwright confirma a CSP, executa a aplicação
sob a política e tenta enquadrá-la em um `iframe`, que deve ser bloqueado.

Conteúdo de usuário é exibido por interpolação Angular. O validador
`scripts/validate_http_security.py` impede `innerHTML`,
`bypassSecurityTrustHtml` e `document.write` sem revisão explícita da política.
