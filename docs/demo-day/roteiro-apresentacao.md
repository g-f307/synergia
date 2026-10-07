# Roteiro cronometrado — cinco minutos

Tempo-alvo: **4 min 50 s**, com margem de 10 s. Um único apresentador.

## Slide 1 — abertura — 15 s

“Este é o SYNERGIA, plataforma de consolidação de indicadores de Suprimentos.
Neste Demo Day apresentamos duas provas de conceito locais de IA, avaliadas com
dados sintéticos e sem alterar decisões ou dados do produto.”

## Slide 2 — equipe — 25 s

“Lucas Costa acompanha o projeto como PO da LG. Gabriel atua como PO e
fullstack; Rebecca em frontend e design; Marcelo em DevOps e QA; Carlos em RPA;
e Gustavo em backend. As PoCs reutilizam contratos e dados sintéticos já
versionados no projeto.”

## Slide 3 — produto e recorte — 30 s

“A plataforma pré-RPA em Angular, FastAPI e PostgreSQL já cobre ingestão,
normalização, consolidação, regras OQC e decisão humana. O levantamento inicial
citou 44 horas mensais, mas esse número ainda não foi validado por medição. Não
declaramos FTE. O planejamento vigente chega à Sprint 9, em 31 de dezembro.”

## Slide 4 — limites comuns — 30 s

“As duas PoCs rodam localmente com o modelo Qwen 2.5 de 3 bilhões de parâmetros,
quantizado em Q4 K M. O modelo não grava no banco, não aprova pendências e não
executa RPA. Baseline e agente recebem os mesmos casos. Toda saída passa por
schema e por validação de evidências.”

## Slide 5 — PoC 1 — 60 s

“A primeira proposta organiza ocorrências determinísticas de qualidade e sugere
a próxima verificação. Avaliamos 24 arquivos reservados, em CSV e XLSX, com 72
tentativas por modo. O schema passou em 100%, mas o agente teve F1 de 67,78%,
consistência de 29,17% e aceitação completa de 44,44%. O baseline atingiu 100%
nessas métricas estruturais. Foram observadas evidências sem fundamento,
perguntas incompatíveis com o estado e certeza indevida. A configuração não deve
ser promovida.”

## Slide 6 — PoC 2 — 60 s

“A segunda proposta investiga execuções por ferramentas somente de leitura e
produz um resumo com evidências. Na versão com contexto pré-carregado, o agente
teve F1 de 50% e consistência zero. Na versão que escolhe ferramentas, nenhuma
das 12 tentativas concluiu a resposta: todas atingiram o limite de chamadas. A
acurácia de escolha foi 15,48%, muito abaixo da meta de 95%. Nenhuma ferramenta
de escrita foi oferecida ou executada.”

## Slide 7 — comparação — 45 s

“As duas PoCs comprovam ingestão de CSV e XLSX, execução local, contratos
estruturados, telemetria e avaliação reproduzível. Também mostram que schema
válido não garante utilidade. A baseline determinística permaneceu superior. O
resultado correto desta rodada é preservar as regras atuais e não integrar os
agentes ao produto.”

## Slide 8 — encerramento — 25 s

“O próximo experimento precisa de novos casos reservados, sem retunar esta
avaliação. Também depende de validar licença, hardware e limites aceitáveis com
o cliente. Até lá, as PoCs ficam isoladas e consultivas. Os vídeos mostram o
pipeline completo, os resultados negativos e as limitações sem omissões.”

