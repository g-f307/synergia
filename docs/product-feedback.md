# Feedback de produto — Issue #168

## Jornada e política de acesso

A ação **Enviar feedback** aparece no cabeçalho autenticado, inclusive no modo
TV. O usuário escolhe Bug ou Sugestão de melhoria, informa título e descrição e,
para bugs, pode acrescentar resultados esperado e observado. O protocolo
imutável é exibido na confirmação. O menu **Meus feedbacks** oferece consulta,
filtros e histórico; **Triagem de feedback** aparece com a permissão correspondente.

O servidor deriva o autor e a sessão de `CurrentActor`. Deriva a organização
da união de vínculos ativos via papel, grupo/papel e permissão direta. Vínculos
repetidos na mesma organização contam uma vez; organizações inativas, vínculos
revogados e papéis expirados/inativos não contam. Concessões globais não
constituem vínculo organizacional.

A política aprovada para esta entrega exige **uma única organização**:
sem vínculo ou com vínculos ambíguos, a criação e as consultas ficam bloqueadas
com 409 e orientação para solicitar ajuste a um administrador. Nenhuma
organização pode ser escolhida no payload. `GET /feedback/policy` informa a
condição sem expor a lista de organizações quando há ambiguidade.

Autores consultam **somente seus próprios registros**, dentro desse vínculo.
Triadores precisam de `feedback.triage` no mesmo escopo organizacional, inclusive
quando a concessão é direta ou via grupo; o nome do papel não autoriza.
O catálogo 1.5.0 concede a permissão inicialmente ao papel `gestor`.
Administração de acesso global não implica triagem nem uma organização.

## API

| Operação | Contrato |
| --- | --- |
| `GET /feedback/policy` | Condição organizacional e identificadores de origem permitidos |
| `POST /feedback` | Criação autenticada; 201 com protocolo e primeiro evento |
| `GET /feedback` | Lista exclusiva do autor, com contagem no mesmo escopo |
| `GET /feedback/{feedback_id}` | Detalhe e histórico exclusivos do autor |
| `GET /feedback/triage` | Lista organizacional com permissão explícita |
| `GET /feedback/triage/{feedback_id}` | Detalhe para triagem |
| `PATCH /feedback/triage/{feedback_id}` | Transição com versão atual e justificativa |

`feedback.own` na matriz é um contrato de autenticação/autoria, como
`profile.own`, e não uma permissão atribuível no IAM.

Exemplo de criação, sem autor, organização, data, URL ou histórico:
```json
{
  "kind": "bug",
  "title": "Filtro não mantém o estado",
  "description": "Passos sintéticos para reproduzir o problema.",
  "expected_result": "Manter o estado selecionado",
  "observed_result": "O filtro foi limpo",
  "source_id": "executions/:executionId"
}
```

`backend/app/model/feedback_sources.json` traduz identificadores exatos para
rotas funcionais canônicas. A API verifica a permissão de acesso à origem.
Não recebe URL, query string, identificadores reais de recursos ou dados da
tela. O cabeçalho usa o padrão da rota Angular; parâmetros concretos ficam fora
do registro. Teste de contrato exige cobertura de todas as rotas autenticadas.
Na ausência de contexto reconhecido, o formulário usa a origem permitida
`profile`, exibida ao usuário antes do envio.

Filtros: `protocol`, `kind`, `state`, `created_from` inclusivo e
`created_to` exclusivo, com timezone obrigatório e normalização UTC.
Quando ambas as datas são informadas, o período deve ser positivo e de até
366 dias. Datas são opcionais; a interface explica os limites.
Paginação: `page` de 1 a 10000, `page_size` de 1 a 100 (padrão 20),
`sort=newest|oldest`; desempate por UUID. Contagem e lista usam o mesmo snapshot
e os mesmos filtros de organização/autoria. Recursos inexistentes e fora do
escopo recebem o mesmo 404; consultas administrativas sem permissão recebem 403.

## Estados, concorrência e auditoria

| Estado atual | Próximos estados |
| --- | --- |
| `received` | `under_review`, `discarded` |
| `under_review` | `planned`, `resolved`, `discarded` |
| `planned` | `under_review`, `resolved`, `discarded` |
| `resolved`, `discarded` | Terminais |

Para concluir ou descartar, a justificativa deve ter 5 a 2000 caracteres.
As demais transições aceitam justificativa opcional. Ela é visível ao autor.
A atualização informa `version`; a API bloqueia a linha com `FOR UPDATE`
e confere versão e transição antes de atualizar. Uma decisão concorrente
vence; a outra recebe 409 sem sobrescrever o histórico. A interface preserva
a justificativa e exige recarregar antes de salvar novamente.

O protocolo `FB-<UUID em hexadecimal>` não expõe um contador global.
Identidade, conteúdo original, origem e protocolo não podem ser alterados;
triggers impedem exclusão e mutações inválidas. Cada criação/transição produz
evento append-only com ator, sessão, organização, instante, estado anterior,
estado novo, versão, justificativa e correlação.

Um segundo evento, sanitizado, é gravado atomicamente em
`identity_access_events` para o catálogo e a exportação da Issue #169.
O texto do usuário e a justificativa não são copiados para esse evento.
A exportação consolidada mantém seu contrato de campos aprovados; o inventário
documenta que `feedback_events` já está representado pela fonte de identidade.

## Limites, privacidade e interface

Título: 5–160 caracteres; descrição: 10–4000; resultados opcionais: até 2000.
A API normaliza NFC, quebras de linha e espaços externos, rejeita controles
invisíveis e campos adicionais. Resultado esperado/observado aplica-se a bugs.
A UI renderiza texto por interpolação, sem HTML executável, e informa os
limites antes do envio. Erros preservam os campos e recebem foco; duplo envio
é bloqueado enquanto a requisição está em andamento.

As políticas de rate limit são `feedback_create` (10/min),
`feedback_read` (120/min) e `feedback_triage` (30/min), configuráveis pelo
mecanismo existente. Não há upload, coleta automática de conteúdo da tela,
stack trace, IP, user-agent ou cabeçalhos no feedback. Nenhum feedback é
encaminhado a GitHub, e-mail ou outro serviço. Logs técnicos registram somente
a operação e seu resultado, seguindo a instrumentação já existente.

A jornada está traduzida integralmente para pt-BR, en-US e es-ES. Espanhol
pode ser escolhido no perfil e já é aceito pelo backend. O catálogo espanhol
é uma extensão do catálogo base: telas anteriores a esta entrega ainda usam
fallback pt-BR quando não traduzidas. O validador exige todas as chaves
`feedback.*` em espanhol. A tradução completa das telas antigas permanece
fora do escopo da #168.

Referências visuais: central de notificações para lista/filtros/paginação e
detalhes operacionais para leitura/histórico. São reutilizados shell, tokens,
`StateComponent` e `PaginationComponent`, com scroll interno, regiões
acessíveis por teclado e ações identificadas. Veja as
[evidências e reprodução](feedback-validation.md).

## Atualização e reversão

Aplicar a migration 0035 com `python scripts/apply_migrations.py` usando o
procedimento habitual do ambiente, antes de servir o backend 0.11.0 e o novo
frontend. A migration não reescreve migrations anteriores. O reconhecimento
de bancos legados verifica as tabelas, a permissão e os três triggers.
Não há novas dependências.

A reversão manual é conservadora: retornar primeiro a aplicação à versão
anterior e executar `database/rollbacks/0035_create_product_feedback.down.sql`.
Ela desativa a permissão e restaura o catálogo anterior, preservando registros,
protocolos e auditoria. Não é uma limpeza nem uma reversão destrutiva do schema.
Reativação posterior exige procedimento revisado; não reaplicar a migration
já registrada. Nenhuma migration foi executada em dados reais nesta validação.
