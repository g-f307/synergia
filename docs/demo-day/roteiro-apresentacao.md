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

## Slide 4 — oportunidades — 35 s

“A primeira proposta explica ocorrências de qualidade já detectadas. A segunda
reúne fatos de uma execução em um resumo rastreável. As duas trabalham somente
com leitura, respeitam permissões e mantêm validação humana.”

## Slide 5 — assistente de qualidade — 50 s

“O assistente de qualidade recebe erros, avisos e divergências selecionados pelo
backend. Ele explica o impacto e sugere a próxima conferência, sempre citando as
evidências. A IA não refaz a classificação determinística. O valor esperado é
tornar o diagnóstico mais claro e reduzir a leitura manual.”

## Slide 6 — integração da proposta 1 — 35 s

“O FastAPI prepara um contexto mínimo, remove campos desnecessários e chama um
modelo local com prompt e schema versionados. Um validador rejeita referências
inexistentes e contradições. Só avançamos após comparação com baseline,
avaliação independente e aceite do cliente.”

## Slide 7 — assistente de investigação — 50 s

“O segundo assistente reúne execução, pendências e Workorders dentro do escopo
da sessão. Ele organiza achados, perguntas em aberto e próximos passos humanos.
Cada afirmação leva a uma evidência consultável. O objetivo é reduzir a
navegação entre telas sem autorizar ações automáticas.”

## Slide 8 — integração da proposta 2 — 35 s

“A integração começa com o backend entregando o contexto pronto. Somente depois
avaliamos seleção restrita de ferramentas de leitura. Cada consulta reaplica
RBAC e organização, possui limites de chamadas e deixa uma trilha sanitizada.”

## Slide 9 — encerramento — 25 s

“O próximo passo é escolher a proposta prioritária, definir usuários da
validação e confirmar o hardware local. Em seguida, congelamos novos casos,
comparamos modelos e medimos qualidade, latência e memória antes de qualquer
integração ao produto.”
