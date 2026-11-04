# Consulta e exportação de auditoria

A API 0.10.0 exporta eventos de auditoria em JSON e CSV, sob demanda, sem
coletar stdout, logs de containers ou métricas. O inventário versionado está em
[audit-event-inventory.json](audit-event-inventory.json): onze fontes, seus
emissores, ações, atribuição organizacional e lacunas históricas.

## Finalidades e cobertura

| Informação | Finalidade | Disponibilidade |
| --- | --- | --- |
| Evento de auditoria | ação, recurso, ator, organização e resultado | consulta e exportação autenticadas desta entrega |
| Log técnico | diagnóstico do processo e falhas | logs estruturados descritos em [observability.md](observability.md) |
| Métrica | contagem, latência e disponibilidade agregadas | Prometheus, com credencial técnica própria |
| Evidência operacional | comprovação de teste, recuperação ou aceite | artefatos sanitizados e runbooks; não são automaticamente eventos |

O inventário cobre execução, inspeção de upload, processamento, reprocessamento,
identidade, sessão, autorização, perfil, administração de acesso, relatórios,
aprovações, notificações, templates, tentativas e reconciliação de e-mail,
backup, restauração, retenção, ativação de políticas e a própria exportação.
Transições de execução já representadas por eventos não são duplicadas.
Eventos de aprovação existentes em duas trilhas preservam suas origens e IDs.

Foram corrigidas duas lacunas: preparação de download de evidência agora emite
`artifact.export_prepared`; exportações de auditoria emitem solicitação e
resultado. Preparação significa que o servidor validou e disponibilizou o
artefato, não que o navegador recebeu todos os bytes. Fontes históricas sem
ator UUID ou correlação continuam com `null`/`unknown`; não se inventam valores.
Eventos sem organização permanecem globais, sem inferir organização pelo papel
atual do ator. Identificadores técnicos legados em texto livre não são exportados
como identidade pessoal.

## Autorização e escopo

| Operação | Permissão | Papéis iniciais |
| --- | --- | --- |
| `GET /audit/events` | `audit.read` | admin, gestor, analista |
| `GET /audit/events/export` | `audit.read` e `audit.export`, no mesmo escopo | gestor, analista |

A migration `0034` publica o catálogo de permissões 1.4.0. Administração de
identidade, isoladamente, não concede exportação. Concessões diretas e de grupo
continuam sujeitas à autorização vigente e à revisão da equipe.

Rollback de aplicação não exige downgrade do banco. O rollback SQL manual
`0034_create_audit_export.down.sql`, quando aprovado e executado sem a API
0.10 ativa, remove a visão e desativa a permissão, preservando a tabela
append-only e o catálogo histórico. Deve preceder rollbacks de suas fontes.
Remover identidades referenciadas exige plano próprio de preservação;
nunca se apaga a trilha para viabilizar um downgrade.

`organization_id` seleciona **uma** organização; o servidor confirma a concessão
antes de ler ou contar eventos. UUID existente, inexistente ou fora do escopo
produz a mesma negação `403` quando não autorizado. A negação é auditada como
evento global, sem usar o UUID não confiável como chave estrangeira.

Omitir `organization_id` exige concessão global e seleciona exclusivamente
eventos cujo escopo é global (`organization_id IS NULL`). Nunca significa
agrupar organizações. Exportação global exige ambas as concessões globais.
`GET /history` permanece compatível e limitado à trilha operacional anterior;
o contrato sanitizado e consolidado é o novo recurso `/audit/events`.

## Filtros, paginação e limites

Consulta e exportação usam exatamente os mesmos filtros:

| Parâmetro | Contrato |
| --- | --- |
| `occurred_from`, `occurred_to` | instantes com fuso explícito; convertidos para UTC; início inclusivo e fim exclusivo |
| período omitido | últimas 24 horas, terminando no instante da requisição |
| `actor_id` | UUID interno do ator, sem nome, e-mail ou endereço de rede |
| `action` | ação exata, por exemplo `auth.login_failed` |
| `resource_type`, `resource_id` | tipo e identificador exatos; limites de tamanho e caracteres |
| `outcome` | `started`, `success` ou `failure` |
| `sort` | `oldest` (padrão) ou `newest` |
| `page`, `page_size` | consulta: página a partir de 1 e até 100 itens por página |
| `format` | exportação: `json` (padrão) ou `csv` |

A ordem é `occurred_at` e ID com collation `C`, ambos na direção solicitada.
IDs possuem prefixo de origem e são distintos entre tabelas. Contagem e seleção
de uma resposta usam o mesmo snapshot PostgreSQL `REPEATABLE READ`.
Requisições distintas não mantêm transação aberta: fixe os dois limites de
tempo para reconciliar páginas e formatos; inserções históricas posteriores
podem alterar o resultado de uma nova consulta.

O período máximo é 31 dias. Consulta e exportação recusam mais de 10.000 eventos;
o arquivo tem limite de 8 MiB e cada comando SQL de leitura tem timeout de 5 s.
Não há truncamento silencioso. Para volumes maiores, divida a janela em
intervalos adjacentes `[início, fim)` ou refine os filtros. Exportação entrega
todo o conjunto filtrado dentro desses limites, independentemente da página da
consulta; não há job assíncrono ou exportação ilimitada.

O limitador compartilhado também cobre estas operações: por padrão, 60 consultas
e 10 exportações por 60 s, com recusa fechada se o armazenamento de cotas falhar.
Overrides opcionais são `RATE_LIMIT_AUDIT_READ_LIMIT`,
`RATE_LIMIT_AUDIT_READ_WINDOW_SECONDS`, `RATE_LIMIT_AUDIT_EXPORT_LIMIT` e
`RATE_LIMIT_AUDIT_EXPORT_WINDOW_SECONDS`. O operador deve repassá-los ao processo
ou em overlay privado do Compose; não estão interpolados no Compose base.

## Formato 1.0.0 e proteção de conteúdo

Cada evento possui somente: `id`, `occurred_at`, `organization_id`, `actor_id`,
`actor_type`, `action`, `resource_type`, `resource_id`, `outcome`,
`correlation_id`, `metadata` e `origin`. Atores são `user`, `system` ou
`unknown`; correlação e atribuição ausentes são nulas. Resultado indica a
execução da ação: uma decisão humana de rejeitar uma aprovação pode ser uma
ação concluída com sucesso, com o estado `rejected` nos metadados.

Os metadados são uma allowlist de inteiros não negativos, booleanos, estados
conhecidos e formatos JSON/CSV. Justificativas, nomes, e-mails, endereços,
credenciais, tokens, cookies, caminhos, configurações privadas, células,
arquivos, stack traces e payloads arbitrários nunca são copiados. Identificadores
fora do contrato ou com marcadores de conteúdo sensível são substituídos por
`[redacted]`. Dados de origem malformados impedem a geração.
Tipos técnicos, como `refresh_token`, permanecem identificáveis e filtráveis;
identificadores de recursos de credenciais são sempre redigidos, mesmo quando
possuem sintaxe válida. O nome do tipo não autoriza expor seu valor.

JSON contém `format_version`, `timezone`, `generated_at`, `event_count`,
`filters` (incluindo período, organização e ordenação) e `events`.
CSV contém cabeçalho fixo e uma linha inicial `record_type=manifest`, seguida
de linhas `record_type=event`. O manifest contém as mesmas informações gerais;
`filters` e `metadata` são JSON em células CSV. Assim, até um arquivo vazio
preserva período, filtros, contagem e versão. Coletores devem distinguir os dois
tipos de linha; a contagem exclui o manifest.

Ambos usam UTF-8, MIME explícito, `Content-Disposition: attachment`,
`Cache-Control: no-store` e `nosniff`. Valores CSV que possam iniciar fórmulas
ou controles de linha recebem apóstrofo, inclusive após espaços Unicode.
O nome do arquivo é gerado com UUID pelo servidor; filtros não são caminhos.
Exemplos exclusivamente sintéticos estão em
[data/synthetic/audit-export](../data/synthetic/audit-export/README.md).

## Rastreabilidade, falhas e validação operacional

A solicitação é persistida antes da leitura. O servidor exclui os eventos da
exportação corrente do conjunto, valida e gera o arquivo em memória, registra
`succeeded` e só então devolve os bytes. Uma falha após a solicitação registra
`failed` e não entrega conteúdo parcial. A trilha é append-only, com no máximo
um resultado terminal por UUID. Eventos de exportações anteriores podem ser
exportados normalmente; isto não dispara novas gerações.

`X-Audit-Export-Id` identifica a geração. Os eventos guardam ator, sessão,
correlação, organização, formato, filtros validados e contagem no sucesso.
Nunca guardam o conteúdo exportado ou a mensagem da exceção.
Se o processo for interrompido abruptamente, pode restar apenas `requested`;
não se declara sucesso nem falha sem evidência. Reconciliação operacional usa
UUID e correlação. Não há arquivo público ou temporário para limpar.

Para validar, use conta com as duas permissões e uma organização sintética.
Mantenha a autenticação em arquivo privado do curl, fora do Git, com permissão
`0600`; não informe tokens na linha de comando. Execute da máquina cliente:

```bash
curl --config "$AUDIT_CLIENT_CONFIG" --get \
  'https://api.example.invalid/audit/events/export' \
  --data-urlencode 'organization_id=44444444-4444-4444-8444-444444444444' \
  --data-urlencode 'occurred_from=2026-09-01T00:00:00Z' \
  --data-urlencode 'occurred_to=2026-09-02T00:00:00Z' \
  --data-urlencode 'format=json' --output audit.json
```

Troque apenas `format=csv` e o destino do arquivo para reconciliar IDs, ordem e
contagem. Repita os mesmos filtros em `GET /audit/events`. `401` indica sessão
inválida; `403`, falta de concessão; `422`, filtro inválido; `413`, janela ou
volume que precisa ser reduzido; `429`, cota temporária. Em falhas internas,
use correlação e logs sanitizados; não publique o arquivo de autenticação.
Os arquivos baixados ficam sob controle do destinatário: retenção e entrega
posterior exigem política aprovada.

## Contrato para coletor e decisões da LG

Um coletor futuro deve autenticar com concessão específica, selecionar um escopo
por requisição, consumir a versão declarada, deduplicar por `origin` e `id`,
manter as janelas UTC e verificar `event_count`. Deve refinar uma janela
recusada, sem assumir sucesso parcial. Formatos incompatíveis exigem nova
versão; a API e o catálogo de permissões têm versões independentes.

SIEM, Loki, Splunk ou outro destino, conectividade, identidade técnica, TLS,
retenção corporativa e envio automático dependem de decisão e autorização da
LG. Esta entrega não escolhe plataforma, instala coletor ou envia eventos para
endpoint externo. Uma interface Angular dedicada continua adiada.
