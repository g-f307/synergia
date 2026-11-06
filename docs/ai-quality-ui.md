# IA — Qualidade na interface do SYNERGIA

## Acesso e uso

Entre normalmente no SYNERGIA com uma conta que tenha `execution.read` e abra
**IA — Qualidade** no menu lateral, rota `/ai/quality`.

1. Selecione um dos seis cenários sintéticos. As evidências do pipeline
   aparecem imediatamente, sem inferência.
2. Quando o modelo estiver disponível, clique em **Gerar explicação**.
   A aplicação chama o backend, que consulta o Qwen local e valida a resposta
   antes de devolvê-la.
3. Compare fatos e evidências à esquerda com a explicação e as verificações
   humanas à direita. A origem do texto e o estado de validação são explícitos.
4. Abra **Comparar com o baseline determinístico** para conferir a contribuição
   do modelo. Trocar de cenário remove a resposta anterior.

Há cenários de serial ausente, ocorrências repetidas, quantidade inválida,
referência ausente, dois códigos simultâneos e arquivo sem ocorrências. No
último, o botão fica desabilitado e o modelo não é chamado.

Esta entrega fornece a funcionalidade e suas referências visuais dentro da
aplicação. A gravação fica a cargo da pessoa responsável; gerar vídeo não faz
parte da entrega.

## Execução local

Use a inicialização normal de backend, banco e Angular descrita em
[local-environment.md](local-environment.md). O recurso usa a sessão e as
permissões existentes, sem criar conta, credencial ou desvio de autenticação.

O Qwen precisa estar previamente instalado e o Ollama disponível no loopback
do **processo do backend**. O endereço padrão é `http://127.0.0.1:11434`;
`SYNERGIA_AI_QUALITY_ENDPOINT` pode indicar outra porta HTTP de loopback,
sem caminho, credenciais, redirecionamento ou proxy. Não há download de pesos.

A geração fica **desabilitada por padrão**. O Compose padrão não inclui Ollama:
nesse ambiente, mantenha `SYNERGIA_AI_QUALITY_MODEL_ENABLED=false`. A tela informa
a desativação, bloqueia **Gerar explicação** e mantém fatos e baseline acessíveis.
Não é necessário instalar o modelo para consultar o demonstrador.

Para uma demonstração com geração, execute o backend no mesmo host do Ollama
previamente provisionado, conforme o guia local, e defina
`SYNERGIA_AI_QUALITY_MODEL_ENABLED=true` no ambiente do backend antes de iniciá-lo.
O catálogo verifica versão e digest sem inferência: `model_status` será
`available`, `unavailable` ou `disabled`. Só `available` habilita o botão.
**Verificar disponibilidade** consulta novamente o catálogo, sem gerar texto.
Uma instalação ausente ou divergente fica identificada como indisponível.
Habilitar a variável em um container não torna o Ollama do host alcançável;
o runtime precisa continuar no loopback do processo do backend.

Modelo: `qwen3:4b-instruct`, digest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`,
equivalente ao nome longo avaliado na #148; Ollama 0.40.12. Temperatura zero,
seed 125, seis threads, contexto 4096, geração máxima 2048 e thinking desativado.
O fluxo interativo compartilha um prazo de 30 segundos entre os grupos de um
cenário e permite uma geração por processo de backend de cada vez. Outra
solicitação recebe fallback imediatamente. Não há retries automáticos.

Se o modelo estiver indisponível, divergente, ocupado, exceder o prazo ou
produzir texto recusado, a resposta usa o baseline e explica o motivo.
Em containers, o loopback pertence ao container. Se a geração for habilitada
sem runtime nessa rede, o catálogo informa indisponibilidade e desabilita o botão;
chamadas diretas ao POST usam fallback. Esta entrega não altera redes, inicia
Ollama, publica portas do modelo ou configura uma implantação corporativa.

O POST possui cota própria `ai_quality_generate`: três solicitações a cada
300 segundos, compartilhadas por origem, usuário e sessão, independentemente do
cenário. `RATE_LIMIT_AI_QUALITY_GENERATE_LIMIT` e
`RATE_LIMIT_AI_QUALITY_GENERATE_WINDOW_SECONDS` ajustam os valores. Todos os modos
do POST consomem a cota; consultar fatos e baseline no GET não a consome.
Uma recusa retorna `429 rate_limit_exceeded` e `Retry-After`, antes de chamar o
modelo. Se o armazenamento da cota falhar, retorna `503 rate_limit_unavailable`.
As recusas usam o registro existente `synergia.rate_limit_events`, com HMAC da
chave, operação e correlation ID, sem prompt ou texto gerado. A permissão
`execution.read` é preservada; a ativação explícita do modelo e a cota específica
restringem o consumo sem alterar o catálogo de papéis ou exigir migração.

## Contratos e limites

| Operação | Permissão | Comportamento |
| --- | --- | --- |
| `GET /ai/quality/scenarios` | `execution.read` | Seis cenários sintéticos com grupos e baseline; sem inferência |
| `POST /ai/quality/scenarios/{scenario_id}/explanations` | `execution.read` | Corpo `{"mode":"model"}` ou `{"mode":"baseline"}`; devolve fatos, texto, origem, estado, tempo, motivo e hash |

Os contratos completos são publicados no OpenAPI. Sem sessão: `401`; sem
permissão: `403`; cenário inexistente: `404`; corpo fora do contrato: `422`.
Falha do modelo retorna `200` com `fallback_deterministic`, preservando as
evidências. Falha HTTP da API é exibida como erro, sem inventar uma explicação
aceita ou disfarçar acesso negado como fallback.
Com a geração desabilitada, um POST em `mode: model` retorna
`503 ai_quality_disabled` sem contatar o runtime; `mode: baseline` continua
disponível sob a mesma cota. Se o runtime deixar de responder depois da consulta
ao catálogo, a tentativa habilitada continua usando o fallback identificado.

O backend aceita somente IDs cadastrados. Não recebe planilha, caminho,
Workorder, execução operacional, prompt, ferramenta, endpoint ou modelo do
cliente. Os cenários são projeções congeladas dos fixtures sintéticos;
não há consulta nem alteração do banco operacional e não há persistência
de resposta do modelo no recurso. Código, categorias, severidades e posições
continuam sendo dados do pipeline, nunca campos gerados pelo modelo.

A política comum em `app/ai_quality_core.py` aceita somente frases completas
autorizadas, limites de tamanho e até três verificações distintas. Uma recusa
preserva somente código e SHA-256, sem retornar ou registrar o texto recusado.
Os scripts de avaliação reutilizam essa mesma política. O vocabulário atual
é português: os rótulos da interface têm pt-BR/en-US, e o idioma da resposta
avaliada é informado explicitamente.

O resultado é uma área experimental integrada à aplicação, com dados
sintéticos. Não representa aprovação para uso sobre ocorrências reais. A
avaliação anterior continua sem demonstrar vantagem do modelo sobre templates.

## Padrão visual e referências para gravação

Referências: moldura das telas de execuções e catálogo de relatórios.
Shell, marca, sidebar, topbar, fontes e tema são os existentes; a área de
conteúdo usa o mesmo raio de 28 px, escala, superfície, borda e espaçamento.
Estados, badges e tabela responsiva reutilizam `shared/ui/ui-kit.ts`.
Não foi criado um segundo layout ou uma página independente como interface
principal. O scroll fica dentro da área de conteúdo.

Os textos novos pertencem aos catálogos pt-BR/en-US. O cenário selecionado
fica bloqueado durante a geração, evitando associar resposta a outro conjunto
de fatos. Controles têm label, foco e tamanho adequados; a tabela admite scroll
horizontal identificado em tela estreita.

Capturas sanitizadas da tela integrada, sem vídeo:

- [Agrupamento e resposta do modelo](evidence/issue-179-quality-explanation/integrated-grouped-light.png).
- [Valor ausente e abstenção](evidence/issue-179-quality-explanation/integrated-missing-light.png).
- [Tema escuro](evidence/issue-179-quality-explanation/integrated-missing-dark.png).
- [Tela estreita](evidence/issue-179-quality-explanation/integrated-mobile.png).

Para gravar: mostre o agrupamento, gere a explicação, mude para o cenário de
serial ausente e compare com o baseline. Mostre os estados realmente obtidos;
não apresente um teste simulado como resposta real do modelo. Não exiba
terminal, prompts, credenciais ou dados do cliente.

## Verificação

Testes automatizados da API cobrem geração, fatos imutáveis, recusa, hash,
timeout, indisponibilidade, concorrência, cenário vazio, ausência de sessão,
permissão, modelo fixado e bloqueio de entradas arbitrárias. Testes Angular
cobrem serviço HTTP, carregamento, botão, duplicidade de chamada, troca de
cenário, estados, erro, vazio, idioma e referência visual.

O ensaio local de navegador usou o shell e o router reais e duas gerações com
o Qwen fixado. Somente a identidade de teste foi substituída para não depender
de banco ou usuário reais; nenhum bypass integra o código da aplicação.
Resultado: [verificação integrada](evidence/issue-179-quality-explanation/integrated-browser-checks.json).
O teste `web/e2e/ai-quality.spec.ts` usa o login real e os fixtures da suíte
geral quando o ambiente PostgreSQL de E2E estiver disponível, sem gravar vídeo.
