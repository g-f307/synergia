# Contrato sanitizado — API de e-mail LG (#171)

**Estado: preparação concluída; validação interna não executada.**
**Decisão: pendente. #170: aguardando validação e aprovação do contrato.**

Este é um modelo, não uma evidência de execução. Não contém dados corporativos.
Preencha com os resultados reais seguindo [o roteiro](lg-email-poc.md).
Não inserir URL interna, host, destinatário, remetente real, credencial,
identificador corporativo, resposta bruta, caminho privado ou conteúdo real.
Se não souber algo, mantenha `pendente`, `não comprovado` ou `não executado`.

## Rastreabilidade e condições

| Item | Resultado |
| --- | --- |
| Data/hora com fuso | Pendente |
| Ambiente lógico | Validação interna (execução pendente) |
| SHA-256 da especificação | Pendente |
| Versão lógica da especificação | Pendente; não copiar títulos/URLs internos |
| Obtenção da especificação | Pendente: GET pelo utilitário ou exportação JSON autorizada |
| Revisão base e hashes do kit | Pendente |
| Aprovação da janela/conta/destinatários | Pendente; referenciar papéis, sem pessoas/contas reais |
| Conectividade e autorização comprovadas | Pendente; indicar evidência, não só `check` local |
| Fonte da confirmação de recebimento | Pendente: destinatário/log corporativo |

## Contrato funcional e operacional

| Aspecto | Comprovado / fonte / restrições |
| --- | --- |
| Operação documentada | `POST /SMTP`, `multipart/form-data`; confirmação interna pendente |
| Autenticação/autorização | Pendente: mecanismo, esquema e emissão/validade, sem valores |
| Headers/certificado/origem de rede | Pendente: categorias e obrigatoriedade, sem detalhes internos |
| Remetente efetivo e política de automação | Pendente: descrever papel lógico, não endereço |
| Subject e Body | Pendente: obrigatórios, omissão versus vazio, codificação |
| Texto simples / HTML / Unicode / múltiplas linhas | Pendente: o que foi enviado e observado |
| To e CC | Pendente: formatos autorizados e comprovados; regra para CC vazio/omitido |
| Múltiplos destinatários/CC | Pendente: contagem prevista versus recebida, sem caixas reais |
| Files | Não validado; anexos fora da primeira rodada |
| Limites de assunto/corpo/destinatários/requisição | Pendente: valor, unidade e fonte; distinguir limite local do cliente |
| Códigos e estrutura lógica de resposta | Pendente: campos/tipos/categorias sem valores reais |
| Semântica de 200 | Não comprovada: aceitação, fila ou entrega; indicar confirmação do responsável |
| Identificador de correlação | Pendente: mecanismo e vínculo lógico; não publicar identificador real |
| Consulta/callback/log de entrega | Pendente: mecanismo disponível e autoridade da confirmação |
| Idempotência/deduplicação | Não comprovada; não inferir de entrega única |
| Timeout/desconexão | Pendente: caso ocorrido ou não reproduzido, resultado e reconciliação |
| Retry | Cliente da PoC faz zero retries; política do serviço pendente |
| Rate limit / Retry-After | Pendente; não provocar carga para descobrir |
| Retenção | Pendente: regras e responsável pela evidência privada |
| Domínios permitidos / regras de CC e criptografia | Pendente; não publicar os domínios reais |
| Conteúdo e aprovações corporativas | Pendente; sem dados de negócio |

## Matriz de resultados

Associe cada linha ao marcador sintético da exportação revisada. A coluna de
resultado deve distinguir resposta HTTP, recebimento e comprovação do conteúdo.
Não marque cenário como aprovado se não foi executado ou ficou inconclusivo.

| Caso | Execução | HTTP/classificação | Recebimento / cópias / conteúdo | Duração/timeout | Evidência lógica |
| --- | --- | --- | --- | --- | --- |
| single | Não executado | — | Não confirmado | — | — |
| unicode | Não executado | — | Não confirmado | — | — |
| to_multiple | Não executado | — | Não confirmado | — | — |
| cc | Não executado | — | Não confirmado | — | — |
| cc_empty | Não executado | — | Não confirmado | — | — |
| html | Não executado | — | Não confirmado | — | — |
| subject_missing | Não executado | — | Não confirmado | — | — |
| subject_empty | Não executado | — | Não confirmado | — | — |
| body_missing | Não executado | — | Não confirmado | — | — |
| body_empty | Não executado | — | Não confirmado | — | — |
| to_missing | Não executado | — | Não confirmado | — | — |
| to_empty | Não executado | — | Não confirmado | — | — |
| invalid_recipient | Não executado | — | Não confirmado | — | — |
| over_limit | Não executado | — | Não confirmado | — | — |
| timeout | Não executado | — | Não confirmado | — | — |
| desconexão controlada (manual, se autorizada) | Não executado | — | Não confirmado | — | — |

Outros erros não induzidos: registrar códigos conhecidos, fonte (observação,
documentação, confirmação do responsável) e o que permanece não comprovado.

## Aceite, riscos e decisão

| Critério da #171 | Situação |
| --- | --- |
| Conectividade e autorização confirmadas internamente | Pendente |
| Mensagem recebida e correlacionada em destino autorizado | Pendente |
| To/CC, Unicode e obrigatoriedade comprovados | Pendente |
| 200 e principais erros caracterizados | Pendente |
| Timeout e duplicidade com decisão operacional segura | Pendente |
| Limites e restrições corporativas registrados | Pendente |
| Evidência revisada sem informações internas/sensíveis | Pendente |
| Decisão explícita sobre iniciar #170 | Pendente |
| Contrato baseado em execução além do Swagger | Pendente |

- **Limitações e riscos observados:** pendentes de execução.
- **Pendências, papel responsável e prazo:** a definir pela equipe.
- **Recomendação:** pendente; selecionar integrar / integrar com restrições /
  não integrar com justificativa baseada nas evidências.
- **#170 pode iniciar?** Não, enquanto o contrato e a decisão estiverem pendentes.
- **Restrições obrigatórias para #170, se aprovada:** a definir; não presumir
  entrega por HTTP 200 e não repetir automaticamente tentativa incerta.
- **Revisão técnica e corporativa:** pendente; registrar papéis e aceite pelo
  canal autorizado, sem dados pessoais.

Somente o relatório revisado e este contrato preenchido de forma sanitizada
podem ser propostos para versionamento, sujeito à autorização de retirada da LG.
