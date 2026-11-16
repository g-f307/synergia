# Issue #191 — checkpoint final: segurança e recuperação

Data: 16/11/2026. Branch: `feature/191-ai-assistance-observability`.
Este documento completa os checkpoints [1](issue-191-checkpoint-1.md),
[2](issue-191-checkpoint-2.md) e [3](issue-191-checkpoint-3.md).
A ativação e o aceite de qualidade/utilidade continuam dependentes da #192.

## Segurança e documentação

Registro de riscos 1.4.0: oito jornadas, nove fronteiras e 43 riscos, preservando
os riscos e portões corporativos anteriores. R-32–R-43 cobrem as doze ameaças da
issue; cada uma declara origem, fronteira, prevenção, detecção, testes nomeados
e risco residual. O validador confere as operações contra OpenAPI/matriz de acesso,
exige todas as ameaças e resolve a existência das funções de teste por AST.
SSRF deixa de ser considerado globalmente não aplicável: o runtime configurado
é uma superfície ativa, com allowlist, rotas fixas, sem proxy ou redirect.

Novos testes verificam instruções maliciosas realmente persistidas antes da
projeção, saída HTML/URL/comando/afirmação sem fundamento/referência inválida,
ausência de conteúdo em resultado/auditoria/outbox e canários em logs/métricas.
Dois servidores locais comprovam que redirecionamento não acessa o segundo
destino e que proxy de ambiente não recebe a chamada. Os testes existentes
exercitam versão/digest adulterados, conteúdo grande/lento, prazos, concorrência,
rate limit, autorização, escopo, recuperação de leases e leitura em suspensão.
Na revisão final, a admissão do POST foi limitada a 1 KiB e três segundos:
antes ela lia o corpo inteiro, embora só aceite ausência ou `{}`. O teste
com stream verifica corte por tamanho/prazo sem consumir o restante e sem
chamar o provider. Preserva o erro 422 já existente, sem alterar o schema HTTP.

Guias de implantação, rollback, aceite e revisão de segurança foram atualizados.
Explicam capacidade/limites fixos, alias de digest, configuração privada,
dependências de monitoramento, manutenção finita, rollback sem apagar dados e
critérios de reabilitação. Os cinco runbooks específicos agora também seguem
as cinco seções obrigatórias do validador de governança.

## Exercício integrado com recibo real

Comando versionado: `scripts/validate_ai_assistance_operations.py`.
Usa PostgreSQL e Graylog exclusivos do laboratório existente, identidade
sintética com login/sessão/RBAC reais e aplicação ASGI com TestClient, sem
dependency overrides. O provider real se conecta a um servidor HTTP local
controlado, que simula o protocolo; não há pesos ou modelo real em execução.

| Fase | Sonda informativa | POST geração | Leitura anterior | Readiness / consulta da execução |
| --- | --- | --- | --- | --- |
| Baseline | healthy | 200 | 200 | 200 / 200 |
| Runtime indisponível | unavailable | 503 | 200 | 200 / 200 |
| Geração suspensa | suspended | 503 generation_disabled | 200 | 200 / 200 |
| Recuperação | healthy | 200 | 200 | 200 / 200 |

O exercício também confirmou:

- Sonda usa apenas metadados, sem `/api/chat`. Suspensão e leitura não acessam
  o runtime; nova aplicação é criada em cada fase para aplicar as flags.
- Reuso não infere; acesso a execução de outra organização é 404 sem runtime.
- Saída adversarial é rejeitada e substituída por fallback sem conteúdo bruto.
- Uma reserva deliberadamente expirada no banco sintético é recuperada após
  suspensão e término dos workers; prévia e lote efetivo não chamam o runtime.
- Retenção em prévia e lote efetivo vazio preserva os três resultados, e o
  lote efetivo gera sucesso auditável. Prévia não vira heartbeat de manutenção.
- Exatamente três chamadas de inferência sintética: baseline, recuperação e
  resposta rejeitada. Não há retry automático da geração.

[Resultado estruturado](issue-191-operations-validation.json): **20 recibos**,
16 de `ai_assistance_events` e quatro de `data_operation_events`. Incluem
requested/completed/rejected/reused/read/expired e início/sucesso das duas
manutenções. Cada event_id foi encontrado na pesquisa do **próprio Graylog**,
comparado por ação, origem, outcome e correlação com sua projeção PostgreSQL,
vinculado ao catálogo imutável e confirmado por operator_id/evidence_id UUID.
Repetir o exportador processou zero eventos e manteve uma ocorrência por ID.
Presença na outbox ou HTTP aceito, isoladamente, não foi usada como recibo.

## Capturas e procedência dos dados

- [Pesquisa Graylog com os 20 eventos](issue-191-graylog-events.png).
- [Painéis da assistência](issue-191-grafana-assistance.png) e
  [manutenção/recuperação](issue-191-grafana-maintenance.png).
- [Validação do navegador](issue-191-browser-validation.json).

Graylog 7.2.2 recebeu/indexou os eventos sintéticos reais do ensaio. Grafana
13.2.1 carregou o dashboard provisionado, com seus 29 painéis/14 de IA e acesso
Viewer. Para conferir renderização, Prometheus reproduziu uma **captura** das
métricas do ensaio, com Bearer privado; não era telemetria operacional contínua.
Counters estáticos não produzem tráfego ou p95 novos. Geração suspensa resulta
em disponibilidade sem dados, sem substituir ausência de medição por sucesso.
As consultas e alertas possuem os testes semânticos promtool do checkpoint 3.

Nenhuma imagem mostra formulário com credenciais preenchidas, prompt, contexto
ou saída de modelo. IDs nas evidências são exclusivamente sintéticos e pertencem
à auditoria autorizada; não foram adicionados como labels ou conteúdo de logs.

## Resultados das validações

| Verificação | Resultado real |
| --- | --- |
| Backend completo, após o limite de corpo, sem integration | **2.257 aprovados**, 907 desmarcados, 16 subtestes, 102,17 s |
| Integrações de assistência, auditoria/Graylog, observabilidade e migrations | **133 aprovadas**, 93,48 s |
| Campanha focada inicial: novas fronteiras, threat model e laboratório | **51 aprovados**, 9,94 s; conjunto sobreposto às regressões |
| Complemento após limitar leitura do corpo: HTTP, telemetria, riscos, CLI e governança | **69 aprovados**, 2,42 s; conjunto sobreposto |
| Reteste HTTP/persistência e dados adversariais após o limite de corpo | **16 aprovados**, 5,32 s; conjunto sobreposto às 133 integrações |
| Novos testes no filtro dedicado security, sem integration | **7 aprovados**, 2,68 s; conjunto sobreposto |
| Angular: componente, cliente e capability da assistência | **61 aprovados**, Chromium 153; inclui output injection e kill switch |
| Exercício real Graylog/PostgreSQL | **20 eventos indexados e reconciliados**, reexportação zero |
| Threat model e governança de dados/runbooks | Aprovados |
| Ruff lint e format dos Python afetados | Aprovados |
| Regras/configuração Prometheus e consultas do dashboard | Ver checkpoint 3 e conferência final dos ativos |
| git diff --check | Aprovado |

O reteste completo encontrou a falta das seções padronizadas nos cinco runbooks
novos; elas foram acrescentadas sem afrouxar o validador. A primeira invocação da
campanha PostgreSQL não forneceu PG* e schema base exigidos pelos testes legados;
o reteste com esses pré-requisitos no banco descartável aprovou os 133 casos.
Uma rodada do backend recebeu sinal 143 antes de terminar e não foi contada
como aprovação. Os avisos conhecidos Starlette/httpx e constantes HTTP continuam.
As contagens de rodadas sobrepostas não devem ser somadas. O recibo Graylog
e as capturas precedem o complemento da admissão; esse complemento foi validado
depois nas regressões completas e nas 16 integrações HTTP/persistidas.

## Reproduzir o exercício opcional

Python do backend, Docker, OpenSSL e recursos locais disponíveis; diretório
privado externo ao Git. As imagens são as já fixadas em `graylog_lab.py`.
Executar somente em laboratório, sem credenciais corporativas:

```bash
backend/.venv/bin/python scripts/graylog_lab.py \
  --workspace /tmp/synergia-private-191 --runtime docker start
backend/.venv/bin/python scripts/validate_ai_assistance_operations.py \
  --workspace /tmp/synergia-private-191 --runtime docker
backend/.venv/bin/python scripts/graylog_lab.py \
  --workspace /tmp/synergia-private-191 --runtime docker stop
```

Resultado esperado: `validated_ai191_real_graylog`, com `receipts: 20`.
`ai191-validation.json` contém a prova; `ai191-private-run.json`, `access.json`
e demais configurações ficam privados, 0600, fora do Git. Não publicar o
diretório inteiro. O comando cria um banco novo a cada execução e não usa a
conexão operacional. Credenciais/corpos de erro não vão para stdout.
Os testes automatizados normais não exigem esse laboratório, seus segredos ou
qualquer modelo/serviço externo.

## Ajustes do laboratório e limites

Nesta estação Linux/Docker 29.9.3, o journal padrão de 5 GB impediu o início do
Graylog. O laboratório agora usa 256 MB e watermarks OpenSearch de espaço livre
1 GB/512 MB/256 MB; não desativa controles de disco. Portas solicitadas em rede
somente interna não foram efetivadas pelo Docker: uma bridge exclusiva de acesso
do host foi acrescentada somente a Graylog/PostgreSQL, com binds explícitos em
127.0.0.1. MongoDB/OpenSearch permanecem na rede interna. Essa bridge permite
egress dos dois serviços; não é perfil corporativo ou isolamento absoluto.
Referências: [rede interna Docker](https://docs.docker.com/reference/cli/docker/network/create/)
e [publicação de portas](https://docs.docker.com/engine/network/port-publishing/).

Os ajustes atingiram apenas recursos identificados pelo laboratório; volumes
foram preservados. Ao finalizar, serviços do laboratório/painel foram parados
e o PostgreSQL efêmero das integrações foi removido. O ambiente em uso não foi
reiniciado nem recebeu migrations/configuração. Planilhas reais continuam no
gitignore; nenhuma dependência de aplicação ou migration foi acrescentada aqui.

Pin anunciado não atesta host comprometido; grounding lexical não prova verdade
ou qualidade. Compartilhamento de CPU/RAM/banco e possibilidade de trabalho remoto
após timeout permanecem riscos residuais. A #191 não aprova capacidade produtiva,
provedor corporativo de observabilidade, qualidade de modelo ou ativação da #192.
CI remoto, publicação da branch e PR dependem da etapa seguinte no GitHub.
