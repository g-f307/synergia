# Perfil, preferências e administração inicial

## Objetivo

A entrega da issue #44 conecta a identidade persistida ao Angular e oferece uma
jornada mínima para o usuário autenticado. O backend continua sendo a única
autoridade de autenticação e autorização; menus ocultos no navegador não
substituem RBAC.

## Contratos pessoais

| Operação | Finalidade |
| --- | --- |
| `GET /me` | identidade, e-mails, preferências e permissões efetivas |
| `PATCH /me` | nome exibido, idioma, fuso e preferências de notificação |
| `POST /me/avatar` | valida e substitui a foto própria |
| `GET /me/avatar` | entrega privada da foto após autenticação |
| `DELETE /me/avatar` | remove metadados e arquivo da foto própria |

O `PATCH` exige a versão atual do perfil. Requisições concorrentes recebem
`409 profile_version_conflict`. Alterar o próprio perfil nunca aceita estado,
papel, grupo, e-mail, permissão ou identificador de outro usuário.

Idiomas inicialmente aceitos: `pt-BR`, `en-US` e `es-ES`. Fusos são validados
contra a base IANA disponível no servidor. As preferências de notificação são
somente configuração pessoal; esta entrega não envia e-mails e não representa
consentimento jurídico para comunicação externa.

## Segurança do avatar

- tamanho máximo de 2 MiB;
- formatos raster PNG, JPEG e WebP;
- MIME declarado deve coincidir com a assinatura detectada;
- dimensões máximas de 1024 × 1024;
- SVG, scripts, arquivos disfarçados e conteúdo corrompido são rejeitados;
- o nome original nunca participa do caminho físico;
- a chave interna possui 192 bits aleatórios e não é exposta pela API;
- SHA-256 é verificado novamente no download;
- substituição e remoção eliminam o arquivo anterior.

O diretório é configurado por `PROFILE_AVATAR_STORAGE_ROOT`. Em produção, ele
deve apontar para volume privado, sem publicação direta pelo servidor web.

## Jornada Angular

O Angular fornece login, renovação pelo cookie `HttpOnly`, access token somente
em memória, interceptor Bearer, guards de sessão e administração, shell
autenticado, edição de perfil/avatar e leitura inicial de usuários, grupos e
papéis. Em `401`, o interceptor tenta uma renovação e conduz ao login se a
sessão tiver expirado. Respostas `403` não são convertidas em autorização local.

## Auditoria

As alterações persistem os eventos `profile.updated`,
`profile.avatar_updated` e `profile.avatar_removed`, vinculados ao usuário,
sessão e correlation ID. Caminhos internos e conteúdo do avatar não entram no
evento.
