# Revisão final — issue #143

## Referência e conclusão

- Data: 24/10/2026, referência `America/Manaus`.
- Branch: `feature/143-smtp-homologacao`.
- Base da feature: `dc08d49`; código e evidências revisados até `45fce59`.
- Regressões adicionais da revisão: commit `fc0209e`.
- Critérios confrontados com a issue #143 consultada no GitHub nesta revisão.

A implementação e a homologação assistida atendem ao escopo e aos critérios
funcionais da issue. Não foram encontrados bloqueadores funcionais no código
revisado. O encerramento formal da issue depende de PR, CI remota, revisão e
merge, conforme o fluxo do projeto. Não houve novo envio SMTP nesta revisão.

## Critérios de aceite

| Critério | Verificação | Resultado |
| --- | --- | --- |
| Automação independente de Gmail e credenciais externas | transporte/configuração com sockets simulados, provider falso e fixtures sintéticas; testes de banco em instância exclusiva | Atendido; CI remota ainda não executada nesta branch |
| Porta e adapter substituíveis | `EmailProvider`, `EmailMessage`, classes de falha e `SMTPAuthenticator`; configuração sem regras por domínio Gmail | Atendido |
| TLS, timeout e fechamento seguro | STARTTLS/TLS implícito, contexto com certificado/hostname verificados, TLS 1.2 mínimo, timeout por operação e limpeza sem desfazer aceitação | Atendido |
| Configuração privada e allowlist | ambiente ou arquivo de segredo, fonte única, allowlist exata validada antes da conexão, cabeçalhos/envelope validados | Atendido |
| Captura local e templates preservados | reexports compatíveis, isolamento de providers, revisão/idioma fixados, MIME texto e HTML escapado | Atendido |
| Entrega ao destinatário autorizado | envio único aceito, persistido em uma tentativa, recebimento e apresentação confirmados pelo responsável | Atendido; evidência assistida vinculada abaixo |
| Retry sem duplicata após confirmação | entregas `sent` não são reclamadas; repetição assistida com transporte bloqueado retorna `already_accepted` sem nova tentativa | Atendido |
| Retries limitados e incerteza | limite explícito e backoff; timeout durante DATA, lease expirado e perda da confirmação de banco ficam sem retry automático; reconciliação explícita e auditada | Atendido |
| Auditoria e logs sem conteúdo sensível | códigos autorizados, referência técnica, objetos sem campos privados em repr, erros de CLI sanitizados, auditorias append-only | Atendido |
| Canal desligado independente das notificações internas | worker desligado não reclama fila; novo teste cria notificações internas em PostgreSQL e confirma ausência de entregas/tentativas de e-mail | Atendido |
| Troca futura para SMTP corporativo | parâmetros genéricos e porta de autenticação substituível, sem mudança de templates ou casos de uso | Atendido arquiteturalmente; destino corporativo não foi homologado |
| Runbook de operação | configuração, opt-in, rotação, revogação, diagnóstico, reconciliação, transição corporativa/OAuth/relay e encerramento | Atendido |

## Resultados executados na revisão

| Validação | Resultado |
| --- | --- |
| Backend, suíte completa não integrada | 880 aprovados |
| Backend, suíte completa integrada antes das duas regressões adicionais | 670 aprovados |
| Suíte SMTP de persistência após as duas adições | 37 aprovados, incluindo os dois casos novos; os outros 35 já pertenciam à suíte integrada anterior |
| Angular, suíte completa | 313 aprovados |
| Ruff; ESLint; build Angular; compilação Python | Aprovados |
| i18n; sistema visual; acesso; ameaças; matriz de segurança; baseline HTTP; governança de dados; validador da Etapa 5 | Aprovados |
| Compose com `.env.example` e perfil `email` | Configuração válida, sem iniciar serviços |
| Migrations em banco vazio PostgreSQL 16 | 33 aplicadas; testes de baseline, concorrência e rollback aprovados |
| Diff e conteúdo versionado | Sem erro de whitespace; `.env`, planilhas reais e temporários ignorados |

Há 672 cenários integrados distintos aprovados considerando a suíte de 670 e
as duas regressões novas. Os 37 testes SMTP direcionados não foram somados
novamente como se todos fossem cenários novos. Relatórios locais permanecem
ignorados em `.test-tmp/issue143-review-*`.

A instância exclusiva de testes estava parada e foi iniciada para a regressão.
Foi usada a base nova `synergia_issue143_final_review`, não a base do smoke real.
Os clientes de backup/restauração vieram do container isolado, por encaminhamento
temporário restrito a bancos descartáveis; não foram instalados no host.

## Ajustes feitos durante a revisão

- Acrescentada regressão de não aceitação SMTP conhecida até esgotar exatamente
  duas tentativas, sem uma terceira transmissão e com o mesmo UUID de entrega.
- Acrescentada regressão PostgreSQL de criação de novas notificações internas
  com o canal desligado, sem projetar entregas ou tentativas de e-mail.
- Corrigida a evidência que ainda apontava revogação da senha de app como
  pendente: o responsável já confirmou essa operação na conta Google. A fonte
  dessa confirmação é o responsável, não uma consulta à segurança da conta.
- Não foi necessária alteração na implementação de produção para esses cenários.

## Encerramento operacional conferido

O backend permanece com canal `disabled`, sem senha SMTP nem referência de
arquivo de senha no processo. O e-mail sintético original do admin está ativo,
primário e verificado; o vínculo temporário de Operador foi revogado, preservando
o papel Admin e suas permissões próprias. A notificação interna e a entrega
homologada permanecem íntegras, com `sent`, uma tentativa e os dois eventos de
auditoria originais. Nenhuma credencial ou endereço real foi publicado.

O responsável confirmou a revogação da senha de app no Google. Evidência:
[homologação SMTP assistida](issue-143-smtp-homologation.md).

## Limitações preservadas

- O layout móvel preexistente do shell excede 390 px no editor, com a mesma largura
  ao remover o novo status. Foi registrado no checkpoint anterior e não foi
  ampliado para uma correção de shell nesta issue. A responsividade completa não
  está declarada aprovada; a limitação deve ser considerada na revisão do PR.
- O build Angular mantém avisos preexistentes de orçamento de estilos. Não houve
  mudança de CSS nesta feature.
- O Gmail foi usado para homologação autorizada. SMTP corporativo LG e OAuth
  efetivo não foram implementados nem homologados; a issue exige substituição por
  configuração ou adapter de autenticação, com porta e procedimento disponíveis.
- Falhas reais provocadas, rotação ao vivo e reconciliação de uma entrega real
  incerta não foram executadas. Esses caminhos têm cobertura sintética/isolada;
  o smoke real limitou-se ao envio único autorizado e à confirmação de recebimento.
- CI remota, aprovação da descrição do PR, publicação, revisão externa e merge
  continuam pendentes. A revisão não publica alterações nem encerra a issue.
