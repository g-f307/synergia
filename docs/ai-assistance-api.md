# Assistência por execução

A assistência exige `SYNERGIA_AI_ASSISTANCE_ENABLED=true` e as configurações de
runtime e retenção descritas em `ai-assistance-persistence.md` e no contrato
operacional. O banco deve estar migrado até `0039` e o segredo compartilhado do
limitador deve estar em `RATE_LIMIT_KEY_SECRET` (ou `AUTH_JWT_SIGNING_KEY`), com
pelo menos 32 bytes. A opção desligada responde `ai_assistance_disabled`.

`POST /executions/{execution_id}/ai-assistance` aceita corpo ausente ou `{}`.
Exige `execution.read` e `ai.assistance.generate` na organização da execução.
O contexto é montado no servidor; o cliente não fornece fatos ou configurações do
modelo. Resultados equivalentes são reutilizados. Saídas rejeitadas após a chamada
são substituídas por um resultado determinístico validado e persistido.

`GET /executions/{execution_id}/ai-assistance/latest` exige `execution.read` e
`ai.assistance.read` na mesma organização. Retorna apenas um resultado cujo hash
do contexto corresponde ao estado atual; não chama o runtime. A ausência e a
invisibilidade de uma execução retornam 404 sem identificar outra organização.

O POST limita ator e organização a dez tentativas em janela móvel de dez minutos;
um bloqueio compartilhado limita cada ator e organização a uma requisição em
andamento, enquanto o adaptador também limita a inferência por processo. As
consultas, reservas e finalizações usam transações curtas. A reserva abandonada
expira em dois minutos e é recuperada na próxima reserva para a mesma chave.
A resposta HTTP tem prazo de 30 segundos após autenticação; se o cliente cancelar
ou o prazo expirar, o trabalho já iniciado pode terminar em segundo plano, sujeito
aos limites do provider e à expiração da reserva. Os hashes de identidade no
limitador são HMACs, e as entradas antigas são removidas em lotes a cada tentativa.

| HTTP | Código | Situação |
| --- | --- | --- |
| 403 | `access_denied` | Permissão ausente |
| 404 | `ai_assistance_not_found` | Execução invisível ou resultado atual ausente |
| 409 | `ai_assistance_execution_not_terminal` | Execução ativa |
| 409 | `ai_assistance_in_progress` | Geração concorrente |
| 422 | `ai_assistance_invalid_contract` | Corpo diferente de objeto vazio |
| 429 | `rate_limit_exceeded` | Limite por ator ou organização; `Retry-After` informa a espera |
| 500 | `ai_assistance_integrity_error` | Registro persistido inválido |
| 503 | `ai_assistance_disabled` | Recurso desligado |
| 503 | `ai_assistance_runtime_unavailable` | Dependência ou runtime indisponível |
| 504 | `ai_assistance_timeout` | Prazo excedido |

Os eventos de persistência registram correlação, hashes e metadados, sem prompt,
contexto ou resposta bruta. As falhas de autorização usam a trilha de acesso
existente. Não se deve adicionar identificadores como rótulos de métricas.
