# Roteiro cronometrado do pitch

Tempo-alvo: **4 min 40 s**, com margem de 20 s. Um único apresentador.

## Slide 1 — abertura — 15 s

“O SYNERGIA já organiza o fluxo de indicadores de Suprimentos. Este pitch traz
duas propostas de IA para ampliar a capacidade de análise sem retirar das
pessoas o controle sobre as decisões.”

## Slide 2 — equipe — 20 s

“Lucas Costa acompanha o projeto como PO da LG. Gabriel atua como PO e
fullstack; Rebecca em frontend e design; Marcelo em DevOps e QA; Carlos em RPA;
e Gustavo em backend.”

## Slide 3 — contexto do projeto — 35 s

“Hoje, plano, produção, recebimento e qualidade chegam de fontes distintas. O
SYNERGIA centraliza ingestão, normalização, consolidação, regras OQC, relatórios
e decisão humana. O levantamento inicial citou 44 horas mensais, mas ainda não
tratamos esse número como ganho comprovado nem declaramos FTE.”

## Slide 4 — arquitetura proposta — 35 s

“A nova camada de IA fica ao lado da API, sem substituir os módulos existentes.
O FastAPI continua aplicando permissões e escopo organizacional, consulta
execuções, qualidade, pendências e auditoria, e envia somente o contexto
autorizado ao modelo local. Toda resposta volta por um validador antes de chegar
à interface.”

## Slide 5 — assistente de qualidade — 50 s

“O assistente de qualidade recebe erros, avisos e divergências selecionados pelo
backend. Ele explica o impacto e sugere a próxima conferência, sempre citando as
evidências. Trata-se de um assistente de fluxo fixo: o backend escolhe os dados e
a IA apenas explica. As regras OQC continuam responsáveis pela classificação.”

## Slide 6 — integração da proposta 1 — 35 s

“O fluxo começa no operador, passa pela interface e chega ao FastAPI. O backend
monta o contexto mínimo, o modelo produz a explicação e o validador confere
schema e evidências. O modelo não escolhe ferramentas e não acessa o banco
diretamente.”

## Slide 7 — assistente de investigação — 50 s

“A segunda proposta começa como assistente, com o contexto preparado pelo
backend. Na fase seguinte, ela passa a ser um agente consultivo porque o modelo
escolhe ferramentas de leitura para investigar uma execução. Cada afirmação
continua ligada a uma evidência e nenhuma ação operacional é autorizada.”

## Slide 8 — integração da proposta 2 — 35 s

“A PoC deve responder à principal incerteza técnica: se o modelo local consegue
selecionar a ferramenta correta, usar argumentos válidos, evitar ciclos e
respeitar limites de chamadas. O gateway reaplica RBAC e organização em cada
consulta e mantém apenas ferramentas de leitura na lista permitida.”

## Slide 9 — encerramento — 25 s

“O próximo passo é escolher a proposta prioritária, confirmar o hardware local
e autorizar uma PoC controlada. Para o agente, mediremos especialmente a
acurácia de seleção de ferramentas, os ciclos, as evidências, a latência e a
memória antes de considerar integração ao produto.”
