# Administração de templates de notificação

A issue #110 introduz uma jornada administrativa global, protegida por
`access.admin`, para governar texto e ativação das notificações. Ela não cria,
edita nem exclui ocorrências: notificações continuam sendo produzidas somente
por eventos persistidos do domínio.

## Modelo e decisões

- a política de eventos, permissão do recurso e placeholders é um catálogo
  técnico somente leitura;
- cada revisão pertence a evento, canal (`in_app` ou `email`) e locale
  (`pt-BR` ou `en-US`), com número, autor, datas e justificativas;
- texto é sempre plano; HTML, handlers, esquemas de URL inseguros, caracteres
  de controle, material de segredo e placeholders não declarados são rejeitados;
- rascunhos usam concorrência otimista; depois da publicação, conteúdo e
  metadados autorais são imutáveis no serviço e no PostgreSQL;
- publicar substitui atomicamente a ativação anterior da mesma combinação;
  desativar encerra a ativação sem apagar a revisão;
- `notification_template_events` registra criação, alteração, publicação e
  desativação com usuário, sessão, correlation ID e motivo, sem copiar conteúdo;
- a prévia usa valores sintéticos controlados no servidor e o Angular a
  apresenta por interpolação textual, nunca como HTML.

Foi mantida a permissão global existente `access.admin`: não foi criado um
papel implícito nem uma permissão operacional nova. A política de ativação é
versionada por evento, canal e locale; canais e eventos suportados não podem ser
inventados pelo cliente.

## API e interface

O catálogo oferece filtros por evento, canal, locale e estado, além de
paginação e histórico. A tela de detalhe permite editar rascunho, gerar prévia,
publicar e desativar com confirmação e justificativa. Conflitos `409` preservam
o trabalho persistido e oferecem recarga; `403` é distinto de indisponibilidade.

O estado de entrega externa exibido vem do backend. Nesta entrega, e-mail pode
estar desabilitado ou usar captura local; a interface declara explicitamente
que SMTP corporativo não foi habilitado.

## Invariantes

Há no máximo uma ativação por evento, canal e locale. A revisão exata é fixada
na ocorrência interna e na entrega de e-mail. O fallback considera apenas
revisões publicadas e é determinístico. Eventos reais continuam verificando
destinatário, preferência, permissão e organização antes de projetar conteúdo.
