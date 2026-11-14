# ADR 0002 — Assistência informativa no detalhe da execução

Status: aceito para o contrato; integração incremental na milestone 10.
Issue: [#185](https://github.com/g-f307/synergia/issues/185).
Contrato **1.0.0**, API **0.12.0**, catálogo RBAC **1.6.0**.

## Contexto e decisão

As PoCs #179/#183 não sustentam investigação autônoma com modelos locais pequenos.
A assistência explica fatos persistidos de uma única execução, selecionados
deterministicamente no servidor e autorizados para o ator. A entrada pública é
somente o identificador da execução na URL; corpo ausente ou `{}`. Qualquer campo
extra, incluindo pergunta, prompt, fatos ou modelo, deve produzir 422.

Não há RAG, embeddings, busca vetorial, memória, agentes, ferramentas, comandos,
decisão automática ou mutação de negócio. A IA não é dependência de readiness.
Aviso de produto obrigatório: **“Assistência gerada por IA: pode conter erros.
A conferência humana das evidências é necessária.”** A interface futura deve
exibi-lo inclusive em fallback, indicando também a origem determinística.

## Fronteiras, fluxo e responsabilidades

1. A rota autentica e exige `execution.read` mais a permissão de assistência.
2. O contexto (#186) seleciona fatos autorizados de uma execução terminal,
   minimiza dados e atribui referências opacas `DIV-`, `PEN-`, `CLA-`, `EVI-`, `HIS-`.
   O navegador nunca fornece fatos ao modelo.
3. O provedor (#187) confere nome e digest do modelo, recusa redirecionamento,
   proxy e ferramentas; limita bytes durante leitura antes de decodificar/parsear.
4. O serviço valida esquema, texto, referências e fundamentação. Saída inválida
   não é apresentada. Só o servidor resolve referências do contexto autorizado.
5. A persistência (#188) aplica expiração e proveniência. A API (#189) reserva uma
   geração por instância, sem transação de banco aberta durante inferência.
6. A interface (#190), revisão de segurança (#191) e integração (#192) precedem
   ativação. A conferência e as decisões de negócio permanecem humanas.

Esta entrega não consulta novos fatos, chama o modelo, persiste resultados ou
altera a tela de execução. Os guards reutilizam a resolução organizacional
existente. O OpenAPI publica modelos compartilhados e `x-ai-assistance`, exemplos
dos quatro estados e matriz HTTP. Rotas de resultados serão publicadas na #189;
esta fundação não anuncia uma rota de geração ainda inexistente.

## Resposta, limites e fallback

Objetos estritos: `extra=forbid`, sem coerção de tipos; UUIDs, datas com fuso e
hashes SHA-256 hexadecimais. `contract_version=1.0.0`. Tempos em ms inteiros:
0 ≤ contexto + geração ≤ total ≤ 30000. Origem `model` exige nome e digest;
origem `deterministic` pode omitir ambos. Nome/digest são presentes em conjunto.

| Campo | Regra |
| --- | --- |
| `state` | `ready`, `insufficient_evidence`, `unavailable`, `rejected` |
| `summary` | texto declarativo de 1–600 caracteres |
| `findings` | até 5; título até 120, explicação até 600; 1–10 referências únicas por item |
| `human_checks` | até 3 textos declarativos de até 600 caracteres |
| `limitations` | obrigatório; até 5 textos de até 600; pode ser vazio em `ready` |
| `provenance` | contrato, modelo, digest, hash do contexto/prompt, origem e tempos |
| `created_at` | instante com fuso |

Referências exigem `context={"evidence_refs": conjunto_autorizado}` durante a
validação. Sem contexto nenhuma referência é aceita; URL nunca é referência.
O guard de texto recusa HTML, links/markup executável, controles e vocabulário
operacional imperativo conhecido após normalizar Unicode. O filtro lexical não
prova segurança semântica: #187 deve validar fundamentação e rejeitar instruções;
#191 cobre evasões. A interface renderiza somente texto (#190). Prompt e filtro
lexical isolados não são garantia de segurança.

`ready` admite explicação validada do modelo ou determinística. Evidência
insuficiente produz `insufficient_evidence`. Saída inválida, não fundamentada ou
acionável produz `rejected`. Estados diferentes de `ready` exigem limitação,
zero achados e origem determinística. Fallback nunca inventa fatos ou recomenda
ação operacional. `unavailable` é um estado de registro, não substitui os erros
503/504 da requisição de geração.

| HTTP | Condição |
| --- | --- |
| 200 | resultado concluído, inclusive `insufficient_evidence` e fallback validado |
| 401 | sessão inválida/ausente/expirada, conforme autenticação existente |
| 403 | ausência de `execution.read` ou da permissão específica de assistência |
| 404 | execução inexistente ou fora do escopo de qualquer uma das duas permissões |
| 409 | execução ativa ou geração em andamento |
| 422 | contrato inválido, inclusive campos extras no corpo |
| 503 | flag desligada ou runtime indisponível antes do início |
| 504 | orçamento total excedido após início |

Autorização precede estado/disponibilidade. 404 não expõe organização nem
existência. Capacidade é indicativa: guards devem ser reaplicados em todas as
rotas de leitura/geração, inclusive cache e resultados antigos.
`app/ai_assistance_errors.py` fixa os códigos `ai_assistance_execution_active`,
`ai_assistance_generation_in_progress`, `ai_assistance_invalid_contract`,
`ai_assistance_disabled`, `ai_assistance_runtime_unavailable` e
`ai_assistance_timeout`, com mensagens públicas sem detalhes do runtime.

## Permissões e capacidade

Migration `0037` concede explicitamente leitura/geração a `gestor` e `analista`.
`admin`, `operador` e `consulta` não recebem assistência por padrão. Não existe
privilégio implícito de administração. As duas permissões devem valer na mesma
organização. Gerar não concede leitura de resultados antigos.

`GET /me/ai-assistance-capability` é autenticado. Exige um escopo comum entre
`execution.read` e leitura ou geração de assistência; senão 403. Retorna somente
`{enabled, read, generate}`, sem endpoint, modelo, digest ou segredo. Flag
desligada retorna os três como `false` para atores autorizados. O serviço Angular
não consulta capacidade para perfis sem as permissões mínimas. Não há nova tela,
botão ou rota visual; os escopos organizacionais permanecem na sessão existente.

## Configuração e operação

Prefixo: `SYNERGIA_AI_ASSISTANCE_`. Variáveis em `.env.example` e Compose.
O entrypoint e `create_app` validam antecipadamente, inclusive ASGI direto.
Configuração inválida impede inicialização em todos os ambientes, incluindo
homologação/produção. Não se conecta ao runtime na inicialização; indisponibilidade
posterior não altera readiness nem as jornadas existentes.

| Sufixo | Padrão e validação |
| --- | --- |
| `ENABLED` | `false`; somente `true`/`false`; opt-in em todos os ambientes |
| `ENDPOINT` | vazio se desligado; obrigatório se ligado; origem HTTP local sem path, credencial, query ou fragmento |
| `ALLOWED_SERVICE` | vazio; opcional, um único nome DNS de serviço sem curingas |
| `MODEL` | vazio se desligado; identificador fixo obrigatório se ligado |
| `DIGEST` | vazio se desligado; `sha256:` + 64 hex obrigatório com modelo configurado |
| `TIMEOUT_SECONDS` | fixo `30`, orçamento total do pedido iniciado |
| `CONTEXT_MAX_BYTES` | fixo `8192`, JSON UTF-8 canônico antes de inferência |
| `RESPONSE_MAX_BYTES` | fixo `8192`, bytes brutos antes de parse |
| `MAX_CONCURRENCY` | fixo `1`, por processo/instância; segunda geração recebe 409 |
| `FOLLOW_REDIRECTS` | fixo `false`; 3xx do runtime será recusado na #187 |
| `RETENTION_DAYS` | `30`; inteiro 1–365; expiração/purga na #188 |

Endpoint aceita IP de loopback, `localhost` ou exatamente `ALLOWED_SERVICE`.
Endereços externos e de metadata são recusados. Serviço permitido exige rede e
DNS controlados pela operação; nunca pode vir da requisição. O digest deve ser
comparado aos pesos no runtime (#187): formato válido sozinho não prova identidade.
Placeholders são recusados mesmo com flag desligada. Helpers compartilhados
limitam contexto serializado e resposta bruta; concorrência/streaming/expiração
devem ser aplicados nas respectivas entregas, sem alegar runtime já implementado.

Ativação somente após #186–#192 e revisão. Esta entrega não inicia Ollama, baixa
modelos ou liga a flag. Rollback operacional: desligar a flag e reiniciar.
Rollback SQL revoga grants e desativa permissões, preservando o histórico.
Rollbacks de funcionalidades anteriores devem primeiro reverter `0037`, depois
`0036` e as demais migrations em ordem inversa. A adoção de uma base legada até
`0037` exige catálogo 1.6.0 ativo, ambas as permissões reservadas ativas para
`execution` e exatamente os quatro grants ativos de Gestor/Analista, com papéis
ativos. Catálogo/permissão/papel inativo, grant ausente, revogado ou indevido
impedem registrar o baseline; o histórico de migrations permanece vazio.

## Ameaças e evidências

| Ameaça | Controle desta entrega | Continuação |
| --- | --- | --- |
| acesso horizontal | interseção de escopos, guards 403/404, grants explícitos | consultas/resultados #186/#188/#189 |
| prompt do cliente | request vazio estrito e testes de extras/tipos | ligação às rotas #189 |
| XSS/instruções/refs inventadas | texto simples e validação referencial com contexto | fundamentação #187; renderização/evasões #190/#191 |
| SSRF/segredos | endpoint local, serviço explícito, redirects não configuráveis | HTTP sem proxy/redirect #187 |
| exaustão | limites fixos, helpers de bytes e tempos estritos | reserva/streaming #187/#189 |
| confusão PoC/produção | módulo/flag separados do `/ai/quality` | retirada da superfície sintética #192 |

Evidências: testes `test_ai_assistance_contract.py`, `test_ai_assistance_config.py`,
`test_ai_assistance_access.py`, snapshot `fixtures/ai_assistance_openapi_1_0_0.json`,
integração PostgreSQL de grants/rollback e teste Angular de capacidade. Mudança
incompatível exige nova versão, ADR e snapshot revisados.
