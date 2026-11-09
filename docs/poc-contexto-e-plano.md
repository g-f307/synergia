# Synergia — Nova PoC de IA: contexto e plano

Consolidado em 08/11/2026, America/Manaus.

**Atualização de continuidade — 09/11/2026:** a issue [#183](https://github.com/g-f307/synergia/issues/183) foi criada.
O responsável autorizou consolidar as mudanças locais anteriores em um único commit
e publicá-las junto ao trabalho da issue. Este documento será versionado; as
evidências brutas das investigações anteriores continuam locais e ignoradas.
As decisões e o desenho experimental abaixo permanecem preservados.

**Execução — 09/11/2026:** o responsável autorizou os blocos 1 e 2, com resumo e
novo aceite antes do bloco 3. A implementação e os resultados ficam no
[guia da PoC #183](ai-knowledge-poc.md). Os estados de “não iniciada” abaixo
pertencem ao registro histórico de elaboração, não ao progresso atual.

**Novo checkpoint — 09/11/2026:** os blocos 3 e 4 também foram autorizados e
concluídos. O [checkpoint 3–4](ai-knowledge-poc-checkpoint-3-4.md) registra calibração,
três ciclos, validação desfavorável ao leitor e congelamento. Blocos 5/6 aguardam
novo aceite; nenhuma inferência reservada ou integração foi executada. O desenho
histórico abaixo não foi reescrito para acomodar os resultados.

Este documento reúne o histórico da discussão sobre o agente de qualidade anterior,
as hipóteses e evidências que orientaram a reformulação e o plano aprovado para a
nova prova de conceito. O contexto e o desenho experimental estão completos nas
partes abaixo; os relatórios originais permanecem referenciados como evidências.

**Status:** plano aprovado; nova campanha ainda não iniciada neste registro.
A integração ao produto continua fora do escopo da PoC. A consolidação preserva
as decisões e os critérios aprovados, sem acrescentar resultados experimentais.

- [Contexto: como chegamos até aqui](#contexto)
- [Plano aprovado: como executar e avaliar a PoC](#plano-aprovado)

## Contexto

Registro: 08/11/2026, America/Manaus.

Este documento recupera o percurso desde a conversa crítica sobre o agente de
qualidade anterior até a aprovação do [novo plano de PoC](#plano-aprovado). Foi escrito
para permitir a continuidade do trabalho sem perder as razões das decisões.

É uma síntese da conversa e das evidências locais, não uma transcrição integral.
As intenções e restrições do responsável estão identificadas como decisões da
conversa; resultados técnicos estão vinculados aos respectivos relatórios.

**Estado neste registro:** o plano da nova PoC foi aprovado. A solicitação seguinte
foi documentar este contexto. A nova campanha experimental ainda não foi iniciada;
não há autorização para integrar a proposta ao produto como consequência automática
da aprovação da PoC.

### 1. Ponto de partida: a experiência com o agente anterior

Depois de testar o agente de qualidade e concluir o vídeo demonstrativo, Marcelo
iniciou uma conversa sobre o pouco valor percebido na funcionalidade. A avaliação
foi que o resultado acrescentava pouco ao sistema e se parecia com a explicação
que uma rotina determinística já poderia apresentar.

O próprio responsável relacionou esse resultado à trajetória anterior: os modelos
tinham apresentado inconsistências e a reformulação havia privilegiado uma função
prática, simples e controlável. Isso ajudou a tornar a entrega funcional, mas pode
ter limitado sua contribuição para o usuário.

A questão deixou de ser apenas “o agente executa corretamente?” e passou a ser
“qual problema relevante ele resolve e qual parte precisa de IA?”.

#### O que sustenta essa crítica no código e nos relatórios

O [núcleo atual](../backend/app/ai_quality_core.py) prepara explicações permitidas
e só aceita respostas que copiem uma dessas frases completas. As verificações
também precisam pertencer a uma lista fechada. Classificação, agrupamento e
preservação das evidências são tarefas determinísticas.

Na rodada offline da #179, todas as **96 explicações aceitas foram textualmente
iguais às do baseline**. O modelo selecionou mais verificações, mas não foi medido
se isso ajudava a compreender a situação ou apenas aumentava a leitura. Esse dado
pertence à rodada registrada, não a uma nova medição feita durante a conversa.

Fonte: [resultado da explicação assistida — #179](ai-quality-explanation-report.md).

Portanto, funcionamento técnico e controles implementados não equivaliam a uma
vantagem demonstrada do modelo. Essa foi a razão concreta para reconsiderar a
finalidade e o desenho da funcionalidade.

### 2. Antecedentes: os problemas não começaram na última interface

Os relatórios anteriores serviram como contexto, sem serem tratados como uma única
série comparável de acurácia:

- **PoC original de diagnóstico, #125:** 72 tentativas do agente, todas com JSON
  válido, mas apenas 22 casos estruturalmente corretos. Houve diagnósticos sem
  fundamento, duplicidades e referências inadequadas.
- **Reavaliação, #148:** a qualidade com 4B alcançou 66/72 aceitações pelo contrato,
  porém ainda houve falhas de texto e interpretação. A proposta operacional com
  8B também apresentou erros de consulta e significado dos resultados.
- **Explicação controlada, #179:** as restrições reduziram o espaço de invenção,
  mas a explicação medida ficou igual à alternativa determinística.

Fontes: [#125](ai-quality-evaluation-report.md),
[#148](ai-reevaluation-final-report.md),
[#179](ai-quality-explanation-report.md).

Marcelo já havia esclarecido que as PoCs originais foram realizadas em outra
máquina. Hardware, modelos, prompts, runtime e arquitetura também mudaram ao longo
do trabalho. Uma melhora não pode ser atribuída exclusivamente a uma GPU melhor
ou ao número de parâmetros.

A conclusão que orientou a conversa foi evitar dois extremos: repetir uma função
com contribuição mínima do modelo ou voltar a delegar uma tarefa ampla que os
experimentos anteriores não sustentavam.

### 3. Primeiro debate: qual problema deveríamos tentar resolver?

Marcelo questionou se a escolha do problema do agente tinha sido um erro e como
preservar a funcionalidade com uma finalidade melhor.

Discutimos a possibilidade de orientar a investigação de ocorrências: reunir fatos,
mostrar o que está sustentado e indicar o que precisa ser esclarecido. Nesse ponto,
o assistente destacou que ainda não havia confirmação da frequência dessa dificuldade
no uso real e sugeriu levantar situações em que alguém precisou investigar registros.

Marcelo informou que não tinha como fornecer essas respostas. Ficou estabelecido
que a continuidade não poderia depender de ele reconstruir casos de uso pessoais
ou demonstrar previamente uma economia operacional que ainda não tinha sido medida.

Essa ausência não prova que a função é inútil, mas impede anunciar uma demanda ou
um ganho de produtividade como fato já comprovado.

### 4. Hipótese de RAG e dependência da capacidade do modelo

O responsável levantou uma preocupação central: a funcionalidade proposta poderia
continuar dependente demais da capacidade interpretativa do modelo local.

Em vez de apenas buscar um modelo maior, sugeriu usar uma arquitetura RAG com uma
boa documentação de referência. A pergunta passou a ser se poderíamos ampliar o
desempenho efetivo do modelo fornecendo conhecimento adequado e reduzindo o que ele
precisaria inferir sozinho.

Foram distinguidas duas funções diferentes de uma base:

1. Explicar campos e regras que o sistema já executa.
2. Registrar casos, indícios, exceções e verificações que ajudariam alguém a
   investigar uma situação operacional.

A segunda é a direção que ganhou relevância. Não bastava anexar documentação
técnica do código e pedir uma explicação mais extensa do mesmo alerta.

A documentação operacional desejada ainda não existia. Marcelo observou que isso
também abria uma possibilidade: ela poderia ser criada se a hipótese se mostrasse
viável.

### 5. Restrição inicial: investigar antes de atualizar o agente

Marcelo deixou explícito que não autorizava um novo ciclo de atualização do agente
de qualidade nem uma pipeline complexa sem indícios de utilidade e melhoria.
Autorizou investigar as hipóteses e buscar evidências favoráveis ou desfavoráveis.

Por isso, os ensaios subsequentes foram realizados como investigações locais e
isoladas, com dados sintéticos, sem integrar RAG à aplicação, alterar o banco ou
reescrever a funcionalidade existente.

Um primeiro ensaio forneceu fatos, documentação e documentação acompanhada de um
exemplo ao 4B. Foram **24 chamadas**, oito por condição. Nenhuma condição produziu
uma resposta completa correta segundo a rubrica daquele experimento. Houve sinais
parciais de uso da documentação e duas saídas truncadas no braço documental.

O resultado não autorizava concluir que RAG era inútil. Não havia recuperação
automática, a tarefa tinha limitações de desenho e o ensaio não media utilidade.
Mostrava que acrescentar documentação, naquele formato, não resolvia o conjunto.

Fonte: investigação de contexto documental — evidência local `.test-tmp/quality-context-investigation-20261108/relatorio.md` (não versionada).

### 6. Retorno aos dados reais e a limitação da ideia de chat

Marcelo reafirmou que uma funcionalidade de IA era necessária e pediu que o problema
fosse procurado nas planilhas reais. A inspeção local forneceu exemplos verificáveis:

| Achado | O que indica | O que não permite concluir |
| --- | --- | --- |
| 488 registros com OQC aprovado e OQC Hold marcado; 7 também com Ship Block | Indicadores distintos coexistem e precisam manter seu significado | Que há um erro ou que um indicador automaticamente anula o outro |
| Registros com retenção longa, OQC Hold comum desmarcado e motivo vazio | Olhar só para o hold comum pode perder uma restrição distinta | Por que a retenção existe ou por que o motivo está ausente |
| Carga parcial e indicador OQC em registros de container/modelo | Há dados dispersos que podem orientar uma investigação | Que a qualidade causou o saldo de carga |
| WO coincidente entre Total Decision e OWM sem igualdade literal de lote confirmada | É possível localizar registros relacionados à mesma ordem | Que são a mesma ocorrência, mesmo escopo ou mesmo momento |

Os dois arquivos WO Status disponíveis eram idênticos byte a byte. Não poderiam
ser tratados como dois snapshots temporais para reconstruir evolução.

A inspeção também revelou uma dependência importante: campos presentes no workbook,
como REASON e certas flags, não estavam todos disponíveis no contrato atual de
ingestão. A existência do dado na planilha não significa que o agente o recebe.

Uma ideia considerada foi um assistente de consultas com evidências. Marcelo não
se convenceu: o esforço de formular a pergunta parecia maior que o retorno. Esse
feedback conduziu à preferência por **orientação apresentada ao abrir a ocorrência**,
sem exigir que a pessoa descubra o que perguntar.

Fonte: levantamento do problema nas planilhas — evidência local `.test-tmp/quality-real-problem-20261108/relatorio.md` (não versionada).

### 7. Reformulação decisiva: conhecimento documentado para orientar a investigação

Marcelo propôs uma base com casos, indícios, explicações possíveis e procedimentos.
O modelo receberia os fatos, consultaria esse material e selecionaria uma explicação
documentada, com uma apresentação compreensível.

Isso reduziria a exigência de inventar uma interpretação sozinho. Também permitiria
registrar conhecimento que hoje depende da experiência informal de um funcionário
e disponibilizá-lo a alguém menos experiente.

Esse problema foi apresentado pelo responsável como real no setor de suprimentos.
Na investigação realizada, ainda não foram medidos sua frequência no Synergia ou
o tempo que uma função desse tipo economizaria.

A proposta passou a ter dois componentes de valor a distinguir:

- **Captura e organização do conhecimento**, que pode ser útil por si mesma.
- **Aplicação desse conhecimento pela IA**, cuja contribuição adicional precisa
  ser demonstrada sobre alternativas que tenham acesso à mesma base.

O termo “explicação mais provável” foi tratado com cuidado: sem estatísticas ou
evidência discriminante, compatibilidade com uma ficha não determina probabilidade
de causa. O modelo deve preservar hipóteses e desconhecimento.

### 8. Teste das fichas com 4B e 8B

O responsável autorizou testar a hipótese com os modelos locais de 4B e 8B.

Foram preparadas três fichas experimentais, contendo cinco explicações, e seis
situações sintéticas. O desenho solicitava várias avaliações na mesma chamada.

O resultado foi fraco:

- **4B:** 12 tentativas, nenhuma seleção integral das cinco explicações correta;
  30/60 estados individuais corretos.
- **8B:** sete tentativas registradas, seis respostas e um timeout; nenhuma seleção
  integral correta. As cinco chamadas restantes não foram executadas.

Os modelos confundiram condições documentais com fatos observados, ignoraram
precondições e chegaram a descrever retenção/carga parcial em um controle que não
as apresentava. O 8B também falhou nas referências exigidas.

O timeout não teve causa específica comprovada. Não foi atribuído automaticamente
a falta de RAM, GPU ou incapacidade lógica do modelo.

Esses resultados justificaram investigar a montagem da tarefa antes de generalizar
uma incapacidade dos modelos ou descartar a hipótese documental.

Fonte: teste de fichas de conhecimento — evidência local `.test-tmp/quality-knowledge-cards-20261108/relatorio.md` (não versionada).

### 9. Diagnóstico: havia uma limitação do desenho, além dos erros do modelo

Após questionar a qualidade dos resultados, Marcelo pediu uma investigação de suas
causas. Foram executadas **20 chamadas diagnósticas**, dez condições por modelo.

Os controles mostraram que ambos conseguiam copiar fatos corretamente e aplicar
uma condição simples. A falha aparecia na tarefa composta e era sensível à forma
de apresentar a documentação e os fatos.

No controle em que apenas a posição dos fatos mudou, de antes para depois das
fichas, a classificação passou:

- No 4B, de **0/5 para 4/5**.
- No 8B, de **1/5 para 4/5**.

Era uma observação por condição, em um controle conhecido, e não uma solução
generalizada. Ainda havia erros de texto e referências. Mesmo assim, demonstrou
que o desenho da requisição contribuía materialmente para o problema.

Trocar apenas endpoint, remover a restrição de JSON, acrescentar o schema ao prompt
ou mudar apenas temperatura não resolveu aquele controle. Não havia evidência de
uma causa única que explicasse tudo.

O diagnóstico corrigiu uma interpretação excessivamente ampla dos primeiros
resultados: eles não demonstravam que os modelos eram incapazes de aplicar qualquer
conhecimento documental. A atenção interna dos modelos não foi medida; explicações
por recência/atenção permaneceram hipóteses.

Fonte: diagnóstico controlado — evidência local `.test-tmp/quality-model-diagnosis-20261108/diagnostico.md` (não versionada).

### 10. Nova hipótese: uma explicação por chamada

Com autorização para continuar os testes, a tarefa foi reduzida: uma explicação
por chamada, critérios completos, fatos pertinentes ao final e schema explícito.

Em 48 chamadas, ambos os modelos acertaram **24/24 estados e referências**. A
comparação com os mesmos pares da primeira repetição anterior melhorou de 5/12
para 12/12 no 4B e de 6/12 para 12/12 no 8B.

A resposta completa, porém, continuou apresentando problemas:

| Medida | 4B | 8B |
| --- | ---: | ---: |
| Seleção e referências corretas | 24/24 | 24/24 |
| Resposta completa, incluindo texto e orientação | 20/24 | 17/24 |

Surgiram afirmações de ausência a partir de informação desconhecida, descrição
incorreta da própria documentação e verificações pouco pertinentes ou sem suporte.

O ganho foi importante: comprovou que uma reformulação podia melhorar bastante a
seleção nesse recorte. Não demonstrou estabilidade em casos novos, utilidade com
usuários ou que gerar texto já estivesse resolvido. Várias mudanças foram combinadas;
o ganho não foi atribuído exclusivamente a uma delas.

Fonte: uma explicação por chamada — evidência local `.test-tmp/quality-single-explanation-20261108/relatorio.md` (não versionada).

### 11. Extrair o conhecimento ou gerar uma explicação curta?

O passo seguinte comparou duas apresentações: seleção de trechos/procedimentos
documentados e a mesma tarefa acompanhada de redação curta. Marcelo concordou com
o teste, mas levantou uma preocupação legítima: retirar toda geração poderia tornar
a necessidade da IA menos evidente.

Foram executadas **64 chamadas**, com oito instâncias novas, duas alternativas,
duas repetições e dois modelos. Algumas instâncias variavam padrões conhecidos;
outras acrescentavam limites ainda não testados. Não era uma avaliação independente
de uso real.

| Medida | 4B extrativa | 4B curta | 8B extrativa | 8B curta |
| --- | ---: | ---: | ---: | ---: |
| Estado e trecho corretos | 14/16 | 12/16 | 16/16 | 16/16 |
| Verificação pertinente correta | 14/16 | 12/16 | 10/16 | 12/16 |
| Resposta factualmente completa | 14/16 | 10/16 | 10/16 | 10/16 |
| Resposta completa com separação estrita de procedimentos | 14/16 | 9/16 | 10/16 | 8/16 |

As diferenças entre as duas últimas linhas incluem repetir uma ação documentada
na prosa, contrariando a separação pedida. Isso foi distinguido de inventar um
procedimento novo; não se usou uma penalidade de formato para esconder a taxa
factual, que também permaneceu insuficiente.

Os procedimentos foram renderizados literalmente a partir de IDs. A proteção contra
alterar seu texto era arquitetural, não mérito do modelo. Ainda era possível indicar
o procedimento existente errado para aquele estado.

O 8B mostrou bom desempenho na seleção de estado/trecho, enquanto o 4B não repetiu
o resultado perfeito anterior nos casos novos. A geração curta acrescentou alguma
contextualização correta, mas também introduziu contradições e maior custo. Não
demonstrou vantagem suficiente nesse desenho.

Fonte: extrativa versus redação curta — evidência local `.test-tmp/quality-extractive-vs-short-20261108/relatorio.md` (não versionada).

### 12. O encerramento daquele ciclo não encerrou a necessidade de IA

Quando Marcelo perguntou se havia mais algo a testar ou se poderíamos fechar a
hipótese, a recomendação foi encerrar a sequência de ensaios semelhantes, preservando
três conclusões distintas:

1. Seleção documental em tarefa reduzida recebeu apoio técnico parcial.
2. Redação livre/curta não demonstrou vantagem suficiente naquela configuração.
3. Utilidade operacional permanecia sem medição.

Isso não descartava toda arquitetura RAG ou toda possibilidade de IA. Também não
justificava integrar o que havia sido testado.

Marcelo reafirmou que a funcionalidade de IA era necessária e pediu uma proposta
para melhorá-la. A direção apresentada foi um **orientador de investigação baseado
em conhecimento documentado**, disponível na ocorrência e sem a barreira de um chat.

O código organizaria os fatos; a recuperação localizaria o conhecimento; o modelo
avaliaria a correspondência; a apresentação mostraria indícios, lacunas e verificações.
A geração teria que demonstrar valor próprio, em vez de ser exigida apenas para
dar aparência de IA.

### 13. Ajuste solicitado por Marcelo: uma nova PoC, sem exigir base oficial

Ao explicar o piloto, o assistente propôs validação dos procedimentos por alguém da
operação. Marcelo corrigiu esse requisito para a fase atual:

- Os rascunhos podem ser fictícios ou representar explicações plausíveis.
- Documentação oficial validada só será necessária se a função for escolhida para
  implementação.
- A PoC deve indicar se há fundamento para reformular o agente atual, mudar a ideia
  ou descartar esta abordagem.
- Não é necessário exigir 99% de confiabilidade de uma prova de conceito.
- Deve haver ciclos de refinamento, pois as hipóteses anteriores já mostraram que
  mudanças no desenho podem melhorar o resultado.

Essas orientações foram incorporadas. A exigência antecipada de validação operacional
foi retirada desta fase. Continua necessário construir uma base internamente coerente
e identificar seu caráter fictício, para saber exatamente o que está sendo avaliado.

A PoC investigará capacidade no domínio simulado. Não precisará provar uma economia
produtiva antes de começar e não anunciará essa economia sem medi-la.

O compromisso com refinamento também foi combinado com proteção contra ajuste aos
exemplos: desenvolvimento pode orientar mudanças; a avaliação final deve permanecer
reservada até a configuração ser fixada.

### 14. Plano elaborado e aprovado

Marcelo pediu um plano completo, fundamentado no código, nos modelos anteriores,
nas hipóteses recentes e em pesquisa sobre aproveitamento dos modelos, documentação,
consultas e avaliação. O objetivo declarado foi chegar a uma conclusão bem sustentada,
preservando a necessidade de uma funcionalidade de IA útil.

Foi elaborado o [plano de orientação investigativa com conhecimento documentado](#plano-aprovado),
com seis blocos:

1. Protocolo, inventário, fichas e corpus sintético.
2. Recuperação lexical, semântica/híbrida e probes de infraestrutura.
3. Leitor 4B/8B e até três ciclos de refinamento.
4. Seleção das configurações e congelamento da avaliação.
5. Campanha final reservada e braço condicional de redação curta.
6. Auditoria, relatório e recomendação por capacidade.

O plano diferencia ganho de documentação, ganho de recuperação semântica, ganho
de interpretação pelo LLM e ganho de apresentação. Uma dessas contribuições pode
ser favorável mesmo se outra não for.

#### Compromissos concretos do plano

| Aspecto | Definição aprovada no plano |
| --- | --- |
| Escopo | Investigação de retenções e registros de aprovação, com assuntos vizinhos como controle |
| Base | Aproximadamente 12 fichas experimentais fictícias, com indícios, exceções e verificações |
| Corpus | 96 situações: 32 de desenvolvimento, 16 de validação e 48 finais reservadas |
| Modelos | 4B e 8B instalados, com comparação de configurações e thinking 8B apenas se justificado |
| Recuperação | BM25, embeddings locais e híbrida; documentos corretos fornecidos manualmente apenas como controle diagnóstico |
| Comparação | Mesmos fatos/base para regras/busca e candidatos de IA; sem baseline artificialmente fraco |
| Refinamento | Até três ciclos, com hipótese, mudança e resultados registrados |
| Final | Três seeds por modelo; falhas preservadas e nenhuma seleção de melhor resposta pelo gold |
| Metas | Precisão/cobertura/pertinência e ganho semântico separados; valores detalhados no plano |
| Orçamento | 992 chamadas planejadas no máximo, teto rígido de 1000 e 120 minutos de inferência ativa cumulativa |
| Integração | Fora do escopo; resultado favorável fundamenta outra decisão, não a executa |

O responsável aprovou explicitamente o plano e, em seguida, solicitou este histórico.

### 15. O que está estabelecido e o que permanece aberto

#### Estabelecido pela conversa e pelas evidências

- Precisamos buscar uma função de IA com retorno identificável para o usuário.
- A explicação controlada anterior teve contribuição limitada na rodada medida.
- A montagem da tarefa influencia materialmente o desempenho dos modelos locais.
- Houve melhora real na seleção após simplificação; isso justifica investigar
  refinamentos, sem transformar cada resultado parcial em aprovação de produto.
- A base pode ser fictícia nesta PoC; validação operacional não é pré-requisito.
- A próxima investigação será isolada, com comparação por etapa e limite de ciclos.
- Não podemos atribuir ao modelo os cálculos, restrições e textos que o código já
  garante por construção.

#### Ainda não demonstrado

- Que a recuperação automática encontrará as fichas pertinentes neste domínio.
- Que os ganhos de interpretação se manterão em situações reservadas e linguagem
  não canônica.
- Que a redação curta terá valor suficiente para compensar erros e custo.
- Que o fluxo completo caberá nos recursos e no tempo-alvo com desempenho adequado.
- Que a proposta reduzirá a dependência de especialistas ou o tempo de trabalho
  em uma operação real.

Essas questões não precisam de uma resposta presumida para iniciar a PoC. São
justamente o que o desenho experimental deve ajudar a esclarecer, cada uma dentro
de seu alcance.

### 16. Orientações para continuar sem perder o contexto

1. Usar o [plano aprovado](#plano-aprovado) como referência de execução e preservar este
   histórico como explicação das escolhas. Não substituir o plano por uma descrição
   retrospectiva adaptada aos resultados.
2. A aprovação autoriza a PoC definida, não uma atualização silenciosa do produto.
   Neste ponto da conversa, a ação solicitada foi registrar o contexto antes de
   prosseguir com a execução.
3. Manter o agente atual, o banco e os contratos de ingestão fora da investigação.
   Dependências de novos campos devem aparecer no relatório, não ser resolvidas
   implicitamente por ampliação do escopo.
4. Preservar a branch e as alterações preexistentes. A documentação e os ensaios
   deste dossiê permanecem locais e ignorados, sem commits, push ou PR implícitos.
5. Manter `docs/files/` ignorado e não enviar suas linhas/textos reais aos modelos.
   Casos experimentais serão sintéticos, ainda que inspirados em estruturas reais.
6. Reaproveitar os aprendizados anteriores, sem sobrescrever seus insumos e saídas.
   Casos já observados são regressão/desenvolvimento, não novo teste reservado.
7. Distinguir inferência observada, interpretação provável, procedimento fictício
   e fato real. Não declarar um estudo independente quando o assistente criou e
   avaliou o próprio material.
8. Comunicar o progresso por hipótese e checkpoint, com gasto/restante de orçamento.
   O usuário já manifestou insatisfação com trabalho prolongado sem explicação clara.
9. Não impor perfeição de produção, nem flexibilizar os critérios depois para
   fabricar um resultado favorável. Conclusões parciais são permitidas e úteis.
10. Ao terminar, indicar qual capacidade de IA merece continuidade, o que a evidência
    não cobre e quais condições seriam necessárias para uma eventual implementação.

### 17. Mapa das evidências

Os links abaixo apontam para arquivos existentes no computador no momento deste
registro. Os relatórios de investigação em `.test-tmp/` são locais e ignorados pelo
Git; não se deve supor que estarão disponíveis em outro clone.

| Documento | Papel no histórico |
| --- | --- |
| [Avaliação original #125](ai-quality-evaluation-report.md) | Limitações anteriores de classificação e evidência |
| [Reavaliação #148](ai-reevaluation-final-report.md) | Modelos/hardware alternativos e necessidade de reformulação |
| [Resultado #179](ai-quality-explanation-report.md) | Explicação controlada equivalente ao baseline na rodada |
| [Núcleo do agente](../backend/app/ai_quality_core.py) | Restrições efetivas de frases e verificações |
| Contexto documental — evidência local `.test-tmp/quality-context-investigation-20261108/relatorio.md` (não versionada) | Primeiro ensaio de documentação contextual |
| Planilhas reais — evidência local `.test-tmp/quality-real-problem-20261108/relatorio.md` (não versionada) | Exemplos verificáveis e limites de disponibilidade dos dados |
| Fichas compostas — evidência local `.test-tmp/quality-knowledge-cards-20261108/relatorio.md` (não versionada) | Falhas de várias decisões na mesma chamada |
| Diagnóstico — evidência local `.test-tmp/quality-model-diagnosis-20261108/diagnostico.md` (não versionada) | Efeito da organização do contexto e controles de causa |
| Explicação individual — evidência local `.test-tmp/quality-single-explanation-20261108/relatorio.md` (não versionada) | Melhora da seleção e falhas restantes de texto/orientação |
| Extrativa versus curta — evidência local `.test-tmp/quality-extractive-vs-short-20261108/relatorio.md` (não versionada) | Casos novos e separação entre seleção, procedimento e redação |
| [Plano aprovado](#plano-aprovado) | Desenho da próxima PoC e fontes externas pesquisadas |

Este registro não acrescenta novos resultados experimentais aos relatórios citados.

## Plano aprovado

Data: 08/11/2026, America/Manaus. Versão do plano: 1.0 (aprovada).

**Status atualizado:** plano aprovado pelo responsável na conversa de 08/11/2026.
A solicitação seguinte foi registrar o [contexto e a trajetória da decisão](#contexto).
A nova campanha ainda não foi iniciada neste registro; integração ao produto
continua fora do escopo. O desenho abaixo foi preservado.

**Elaborado originalmente como plano para aprovação. Este registro não executa
experimentos, integração, instalação, download ou atualização do agente atual.**
Foi elaborado após leitura do código, dos relatórios históricos e das investigações
locais, inventário do computador e pesquisa em fontes primárias. A versão inicial
foi elaborada em diretório ignorado pelo Git; este consolidado foi transferido
para `docs/` para versionamento com a issue #183.

### 1. Decisão que a PoC precisa permitir

Investigar se um sistema local consegue apresentar, ao abrir uma ocorrência,
**uma orientação pertinente para investigá-la**, usando fatos e uma base pequena
de conhecimento experimental. A pessoa não precisa formular uma pergunta.

A contribuição candidata da IA é reconhecer a correspondência entre uma situação
e conhecimento descrito de maneiras diferentes, selecionar explicações compatíveis
e destacar evidências/lacunas. A documentação não será apenas um catálogo de frases
equivalentes ao diagnóstico já emitido pelo código.

Três perguntas serão respondidas separadamente:

1. **Conhecimento:** registrar casos, exceções e verificações permite produzir uma
   orientação mais específica que a mensagem genérica atual?
2. **Modelo:** recuperação semântica e/ou interpretação por 4B/8B melhoram a seleção
   dessa orientação em comparação com busca textual e regras simples?
3. **Apresentação:** uma explicação curta gerada acrescenta informação útil e fiel
   à apresentação direta das evidências e do procedimento documentado?

Não é necessário que as três respostas sejam positivas. Por exemplo, a recuperação
semântica pode contribuir mesmo se a redação livre não contribuir. O resultado deve
identificar **qual função da IA merece continuidade**, em vez de aprovar ou reprovar
um pacote indivisível.

Precisamos viabilizar uma funcionalidade de IA, mas o protocolo não pressupõe que
esta arquitetura será aprovada. Se falhar, o relatório deverá indicar uma próxima
hipótese delimitada para essa necessidade, sem iniciar outra investigação sozinho.

#### Alcance da conclusão

O usuário autorizou documentação fictícia ou plausível, sem validação operacional
prévia. Toda ficha será identificada como **conhecimento experimental fictício**.
Uma hipótese plausível não será apresentada como fato descoberto nas planilhas.

Podemos avaliar coerência, aplicabilidade no domínio simulado, generalização entre
casos e contribuição técnica da IA. Não poderemos concluir que o procedimento é
oficial, que representa a experiência de um funcionário ou que há economia de tempo
em produção. Essas limitações não impedem a conclusão desta PoC.

### 2. Evidências que orientam o desenho

| Origem | Fato confirmado | Consequência para esta PoC |
| --- | --- | --- |
| #125, `docs/ai-quality-evaluation-report.md` | 72 tentativas do agente, todas com schema válido, mas só 22 estruturalmente corretas | Separar validade de formato, correção factual e resposta completa |
| #148, `docs/ai-reevaluation-final-report.md` | Qualidade 4B aceita em 66/72, com falhas textuais como posição de coluna apresentada como valor; operacional 8B apresentou consultas/interpretações incorretas | Código prepara fatos, cálculos e escopo; modelo não lê XLSX bruto nem escolhe consultas livres ao banco |
| #179, `backend/app/ai_quality_core.py` e relatório | Texto aceito só pode ser uma frase de uma lista; 96/96 explicações da rodada foram iguais ao baseline | Não repetir um teste em que o código já entrega toda a resposta e o modelo só a copia |
| Investigação de contexto, 08/11 | Acrescentar documentação e um exemplo não produziu respostas completas corretas naquele desenho | Mais texto não é uma melhoria presumida; testar conteúdo e organização separadamente |
| Teste de fichas, 08/11 | Várias explicações por chamada confundiram condições documentais e fatos; houve um timeout de 8B sem causa comprovada | Separar tarefas, limitar contexto e registrar falhas de execução separadas das semânticas |
| Diagnóstico, 08/11 | Copiar fatos/aplicar uma condição simples funcionou; mudar apenas a posição dos fatos melhorou o controle composto de 0/5 para 4/5 no 4B e 1/5 para 4/5 no 8B | Usar fatos destacados no fim como ponto de partida e testar resistência à ordem/distratores |
| Uma explicação por chamada, 08/11 | Ambos acertaram 24/24 estados/referências; respostas completas foram 20/24 e 17/24 | Seleção e redação precisam de avaliações separadas; resultado em casos conhecidos não é generalização |
| Extrativa versus curta, 08/11 | 8B acertou 16/16 estados/trechos por braço, mas errou verificações; curta ficou em 10/16 respostas factualmente completas em ambos | Delegar políticas triviais ao código; procedimentos por ID; redação livre precisa demonstrar ganho próprio |
| Mesmo teste | 4B não manteve os acertos anteriores em casos novos; `null` virou ausência e uma sequência temporal foi invertida | Casos novos, desconhecimento explícito, controles temporais e teste final reservado |

Esses denominadores representam tarefas diferentes. Não serão somados em uma
acurácia histórica única. Repetições, formatos e variações do mesmo caso não serão
contados como situações operacionais independentes. Hardware, runtime e variantes
de modelos históricos também diferem.

#### Situação das planilhas e do código

A análise local identificou 488 registros com aprovação e OQC Hold coexistentes,
7 também com Ship Block; exemplos de retenção longa com OQC Hold comum desmarcado;
e carga parcial com indicador OQC. Isso fornece estruturas de casos, **não causas**.

Os dois arquivos WO Status são idênticos byte a byte. Não fornecem dois momentos
para inferir cronologia. Coincidência de WO entre Total Decision e OWM não confirmou
vínculo de lote; não será transformada em relacionamento certo.

O adaptador OWM atual não ingere REASON, Long Term Hold, Rework, Ship Block ou
container por serial; CTNR não mapeia OQC Pending. A PoC não corrigirá o adaptador.
Haverá uma marcação por campo: disponível no contrato atual, presente apenas no
workbook, ou totalmente sintético. Resultados que dependam de informação adicional
serão reportados separadamente. Não esconder uma futura dependência de ingestão.

O agente atual trabalha com ocorrências sintéticas de qualidade de importação.
Este piloto amplia a investigação para orientação sobre retenções/inspeções.
É uma hipótese de reformulação de finalidade; não uma substituição equivalente já
decidida. O baseline atual ajuda a avaliar a apresentação, mas o comparador principal
de seleção terá o mesmo escopo e os mesmos dados da nova PoC.

### 3. Escopo e experiência simulada

#### Recorte principal

**Investigar retenções e sua relação com registros de aprovação.** Incluir diferenças
de escopo, sequência de registros, tipos distintos de retenção, motivo desconhecido
e observações textuais fictícias. Carga/OQC entra como assunto vizinho para verificar
se a busca/modelo rejeita documentos aparentemente parecidos e fora do escopo.

O recorte tem componentes estruturados que o código deve resolver e componentes
semânticos em que a IA pode contribuir. Isso permite avaliar ganho sem construir
um assistente genérico de suprimentos.

#### Saída pretendida

1. O que os registros efetivamente mostram, com fontes e granularidade.
2. Qual caso documentado é compatível e por quais evidências.
3. O que contradiz a hipótese ou ainda falta esclarecer.
4. Qual verificação documentada é pertinente e em qual fonte procurar.
5. Qual limite impede concluir mais.

Exemplo fictício: aprovação e retenção constam para um mesmo lote, mas o motivo não
foi exposto. A orientação deve identificar a lacuna e uma verificação documentada,
sem inventar o motivo nem declarar que a retenção foi encerrada. Se uma nota disser
“aguardando contraprova de amostra”, a busca deverá localizar uma ficha que trate
desse tipo de verificação mesmo sem repetir literalmente a nota.

Não será necessário gerar prosa para comprovar utilidade técnica: selecionar o
conhecimento certo e uma orientação específica já é uma capacidade candidata.
Também não excluiremos a redação por princípio; haverá uma comparação própria.

#### Fora do escopo

- Alterar backend/frontend, rotas, autenticação, banco, importação ou contratos.
- Implantar banco vetorial, serviços adicionais ou frameworks de agentes.
- Autorizar liberação, alterar registros ou executar procedimentos operacionais.
- Treinar/fazer fine-tuning dos modelos, adotar nuvem ou aumentar o porte do LLM.
- Enviar planilhas ou seus textos livres reais aos modelos.
- Produzir uma documentação oficial do setor.

### 4. Arquitetura experimental mínima

```text
Caso sintético com proveniência
  → normalização/cálculos/escopo por código
  → descrição de busca produzida a partir dos fatos
  → recuperação de fichas: lexical / semântica / híbrida
  → avaliação de até duas fichas, uma por chamada ao 4B ou 8B
  → validação de IDs, vínculos e restrições objetivas
  → orientação extrativa com fatos + ficha + verificação documentada
  → explicação curta opcional, avaliada separadamente
```

Scripts Python independentes, arquivos JSON/Markdown e um relatório HTML estático
local para comparar resultados. Sem servidor novo. Usar biblioteca padrão e as
dependências já disponíveis sempre que adequado. Uma coleção dessa dimensão pode
ser buscada em memória; não há motivo inicial para adicionar um serviço vetorial.

O runner de inferência não terá acesso ao gabarito. O avaliador recebe gabarito e
saídas depois. Nenhum validador de produção experimental consultará respostas
esperadas para corrigir o modelo.

#### Divisão explícita de responsabilidades

| Responsável | O que faz | O que não será atribuído ao modelo |
| --- | --- | --- |
| Código | Tipos, contas, datas, igualdade de IDs, origem, permissões simuladas, políticas simples de exibição | Cálculo de saldo, ordenação temporal e preservação de campos |
| Recuperação | Localizar conhecimento candidato sem conhecer o gabarito | Um candidato recuperado não é automaticamente aplicável |
| Modelo | Relacionar linguagem e critérios da ficha, identificar compatibilidade/contradições e referências | Não cria causa factual, valor ausente ou procedimento novo |
| Validador | Conferir schema/IDs, condições objetivas e referências disponíveis | Não é um verificador semântico universal de prosa |
| Apresentação | Mostrar fontes, limites e verificação literal | Um fallback ou trecho de template não será contabilizado como geração correta |

Se uma ficha só tiver uma verificação e a política de exibição for determinada pelo
estado, o código fará essa escolha. Testaremos o modelo apenas quando existirem
alternativas com distinção semântica real. Assim corrigimos a falha anterior de
pedir ao modelo uma política trivial e não vendemos o acerto do código como IA.

### 5. Produção da base de conhecimento

#### Composição inicial

Criar aproximadamente 12 fichas: 8 pertinentes ao recorte, 2 de assuntos vizinhos
e 2 versões antigas explicitamente arquivadas. Identificar a versão vigente por
metadados objetivos; documentos em conflito sem precedência conhecida exigirão
que a incerteza seja preservada. Não pressupor que o documento mais recente seja
sempre o correto sem uma política explícita.

Uma ficha deve representar uma explicação ou um caso investigável, não uma coleção
de várias decisões desconexas. Preferência por 250–450 tokens no conteúdo enviado
ao LLM; ficha completa preservada em Markdown. O tamanho será medido no runtime,
não estimado como número de caracteres equivalente a tokens.

#### Campos obrigatórios de cada ficha

| Campo | Conteúdo |
| --- | --- |
| Identidade | ID estável, título, versão, status experimental, assunto e escopo |
| Situação | Problema que a ficha ajuda a esclarecer e distinções relevantes |
| Vocabulário | Termos, sinônimos, abreviações e expressões operacionais fictícias |
| Indícios | Evidências favoráveis, sua origem e o que isoladamente não comprovam |
| Contradições | Condições que descartam essa explicação ou a deixam fora do escopo |
| Lacunas | O que continua desconhecido e qual informação pode discriminá-lo |
| Explicação | Interpretação permitida, sem escolher causa mais provável por intuição |
| Verificações | IDs de verificações, quando se aplicam, fonte consultada e resultado que ajudariam a esclarecer |
| Limites | Conclusões/ações que os indícios não autorizam |
| Exemplo | Um exemplo curto e um contraexemplo exclusivo de desenvolvimento |
| Rastreabilidade | IDs de trechos e relação com a situação real que inspirou a estrutura, quando existir |

As condições de aplicação devem ser autocontidas. Não exigir que o modelo lembre
uma precondição localizada em outra ficha. Separar visualmente conteúdo documental
de fatos do caso. Não incluir casos de avaliação ou respostas finais nas fichas.

Cada verificação deve reduzir uma incerteza concreta. Evitar “confira os dados”
como orientação universal. Exemplo fictício: “Localizar o registro da contraprova
vinculado ao mesmo lote e verificar se há conclusão registrada”; a sugestão depende
dos indícios da ficha, não é um procedimento real aprovado.

#### Documentação natural e representação estruturada

Manter uma fonte de verdade estruturada para IDs, relações, estados e procedimentos,
com Markdown legível gerado a partir dela ou verificado contra ela. Isso evita que
o prompt e a documentação descrevam regras diferentes.

Não converter todo o problema em booleanos que já tragam a classificação pronta.
Uma parte dos casos terá notas fictícias em linguagem natural, paráfrases, negações
e menções ambíguas. Essas notas precisam ser semanticamente relacionadas à base.
Condições objetivas continuarão codificáveis; a referência determinística será
um comparador legítimo, sem acesso ao gold ou a regras escritas para cada caso.

#### Verificação da base antes dos modelos

- IDs únicos, referências válidas, versões e escopos coerentes.
- Condições positivas/negativas completas e precedência explícita.
- Diferença entre desconhecido, ausente confirmado, falso e não aplicável.
- Não inventar cronologia, equivalência de lotes ou semântica de OQC Pending.
- Marcar causas experimentais como hipóteses e não como observações reais.
- Resolver ambiguidades da rubrica antes das chamadas; permitir múltiplas respostas
  equivalentes quando forem realmente aceitáveis.
- Executar testes de consistência e revisão editorial sem usar o modelo avaliado
  como única autoridade sobre a correção do material.

Não exigiremos especialista. A elaboração e revisão pelo mesmo assistente serão
identificadas como limitação. “Fictício” não significa que a lógica interna pode
ser contraditória ou adaptada para tornar uma resposta errada correta.

### 6. Recuperação e otimização das consultas

#### Entrada de busca

A busca é disparada pela ocorrência, sem esforço de formulação pelo usuário.
Usar duas projeções curtas, preparadas por código:

1. Resumo dos sinais e do contexto da entidade, preservando negações e desconhecidos.
2. Nota textual fictícia relevante, quando existir, com o contexto necessário.

IDs de lote/serial serão usados em relacionamentos exatos, não como pistas
semânticas para escolher uma ficha. Não transformar `reason desconhecido` em
`motivo ausente` na própria consulta. O texto não incluirá o título/ID correto do
gold nem um diagnóstico previamente preenchido que resolva a seleção.

#### Braços de recuperação, sobre os mesmos casos

| Braço | Papel |
| --- | --- |
| R0: filtros objetivos + BM25 | Referência lexical forte, com tokenização em português e aliases documentados |
| R1: embeddings locais | Verificar correspondência semântica com paráfrases e linguagem operacional |
| R2: BM25 + embeddings | Combinar precisão lexical e proximidade semântica, com fusão de rankings |
| R*: documentos pertinentes fornecidos pelo gabarito | Controle diagnóstico da etapa de interpretação; não concorrente implantável |

No R0, não remover automaticamente palavras como “não” ou tratar antônimos como
sinônimos. O BM25 pode recuperar documentos contraditórios; essa limitação precisa
aparecer na avaliação, não ser mascarada por um dicionário derivado do teste.

**Candidato de embeddings:** `qwen3-embedding:0.6b`, disponível no catálogo oficial
Ollama com aproximadamente 639 MB, Q8_0. Ainda não está instalado. É a opção inicial
por usar o runtime existente e oferecer suporte multilíngue. Registrar digest e
verificar a implementação real antes de fixar o experimento. [S6][S7]

Usar o formato de instrução de consulta recomendado pelo modelo de embeddings,
com a tarefa expressa de modo estável. Consultas e fichas em português; testar a
instrução curta em inglês conforme orientação do fornecedor, sem traduzir os fatos
livremente pelo LLM. Indexação e consulta usam os mesmos pesos e normalização.
Não usar o embedding interno do LLM gerador como se fosse um modelo de busca.

`multilingual-e5-small` foi considerado como alternativa pequena, mas exigiria um
caminho de execução/dependências diferente neste ambiente. Não entra junto com o
Qwen no plano inicial. Se necessário no futuro, respeitar seus prefixos `query:`/
`passage:` e limite de entrada; não comparar modelos mal configurados. [S8]

#### Indexação e recuperação

- Unidade inicial: ficha inteira ou seção semanticamente completa. Não cortar uma
  condição de sua exceção para obedecer a uma divisão fixa por caracteres.
- Incluir título, assunto, escopo e versão no texto indexado, com trechos de origem.
- Se uma ficha precisar ser dividida, cada trecho carrega contexto suficiente e
  permite recuperar a ficha pai completa. Não criar contexto com fatos inventados.
- Indexar documentos uma vez por versão; pré-calcular embeddings dos casos antes
  das rodadas do LLM e descarregar o embedder para não competir por VRAM.
- Armazenar os poucos vetores em arquivo e calcular similaridade em memória.
- Comparar `k=1, 3, 5` na recuperação; encaminhar ao LLM no máximo duas fichas,
  avaliadas separadamente. Registrar a perda entre recuperação e esse limite.
- R2: fusão por Reciprocal Rank Fusion, inicialmente com constante 60 e pesos
  iguais. Ajustar no desenvolvimento apenas se o diário de erros justificar.
- Limiares de abstenção e margens de ranking serão calibrados em desenvolvimento/
  validação. Similaridade e autoconfiança textual não serão tratadas como
  probabilidade de uma explicação estar correta.

Em uma base pequena, recuperar cinco documentos pode tornar Recall@5 trivial.
Por isso mediremos também precisão no topo, desempenho com documentos vizinhos,
Recall@2 efetivamente entregue e discriminação nos casos sem ficha aplicável.

**Reranking pelo LLM** será justamente a avaliação de uma ficha por chamada.
Um segundo modelo especializado de reranking não será instalado no início. Só
entra em um ciclo se a busca errar apesar de o leitor funcionar com R*, houver
orçamento e a contribuição esperada puder ser isolada. Não adicionar outra etapa
apenas porque costuma aparecer em diagramas de RAG.

Busca híbrida e contexto explícito são opções sustentadas por experimentos externos,
mas os ganhos publicados pela Anthropic não são metas transferíveis para esta base,
este português ou estes modelos. Aqui precisam ser medidos. [S5]

### 7. Como extrair mais capacidade dos modelos instalados

#### Modelos e controles

- 4B: Qwen3-4B-Instruct-2507, Q4_K_M, digest
  `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
- 8B: Qwen3-8B, Q4_K_M, digest
  `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.

São variantes diferentes; diferenças não isolam o efeito de 4 versus 8 bilhões
de parâmetros. O 4B Instruct-2507 é não-thinking segundo sua model card. Não
tentaremos habilitar thinking nele só porque o inventário genérico do runtime
lista essa capacidade. No 8B, thinking é uma variante experimental possível. [S1][S2]

#### Montagem inicial da chamada

1. Instrução de sistema curta: tarefa, limites e convenções.
2. Uma única ficha candidata, autocontida, claramente identificada como referência.
3. Schema compacto visível também no prompt, além de fornecido ao decodificador.
4. Fatos pertinentes no fim, identificados como observações e lacunas.
5. Uma decisão estruturada curta: estado da ficha, trechos/fatos que sustentam ou
   contradizem e informação discriminante ausente.

Estados iniciais: compatível com evidências, possível mas não confirmado,
contradito, fora de escopo. “Compatível” não comprova uma causa operacional nem
significa que é a explicação mais provável.

O nome da ficha já é conhecido pela chamada, portanto será anexado pelo código;
não exigir que o modelo o repita apenas para depois penalizar uma cópia errada.
IDs de evidência/trecho estarão restritos aos disponíveis, mas a correção de seu
uso ainda será avaliada. Um ID existente pode sustentar uma conclusão errada.

Ponto de partida: `/api/chat`, conversa nova por chamada e template original
preservado. A escolha facilita separar papéis; não implica que o endpoint tenha
resolvido erros anteriores, pois o diagnóstico já testou essa troca sem sucesso.

#### Parâmetros candidatos

| Perfil | Uso |
| --- | --- |
| P0 | Controle histórico com temperatura 0 e demais parâmetros explicitamente registrados |
| P1 | Configuração não-thinking recomendada: temperatura 0,7; top_p 0,8; top_k 20; min_p 0 |
| P2, condicionado | Somente 8B thinking: temperatura 0,6; top_p 0,95; top_k 20; min_p 0 |

P1 será comparado integralmente com P0. O ensaio anterior mudou apenas temperatura;
não testou o conjunto recomendado. P1 também é uma mudança em conjunto, portanto
um ganho não será atribuído isoladamente a um sampler. P2 só entra no orçamento de
refinamento se houver erro de interpretação que essa capacidade possa esclarecer.
As recomendações do fabricante orientam candidatos, não garantem resultado. [S1][S2]

Contexto inicial 4096, seis threads e um pedido por vez. Reservar margem real
para entrada/template/saída; prompt-alvo até aproximadamente 2800 tokens e saída
de classificação até 512. Medir `prompt_eval_count`, motivo de término e tokens
de geração. Se o orçamento não comportar o conteúdo, simplificar a chamada ou
registrar uma variante antes de executar, sem truncamento silencioso. [S3][S4]

O limite inicial de 512 não é uma recomendação universal do Qwen. É um limite de
uma tarefa curta, a ser validado no probe. Thinking precisa de orçamento próprio,
inicialmente até 2048 tokens e 90 segundos por chamada, no máximo 8 chamadas de
triagem. Verificar se o runtime separa corretamente thinking e JSON final. Se a
combinação falhar, registrar a limitação, não extrair um JSON por heurística e
declará-lo válido. Não usar o conteúdo de thinking como prova de raciocínio fiel.

#### Refinamentos prioritários e condicionais

| Técnica | Quando testar | Controle necessário |
| --- | --- | --- |
| Rótulos legíveis de desconhecimento | Ponto de partida para evitar `null` virar falso | Mesmas informações, sem preencher lacunas |
| Uma ficha por chamada | Ponto de partida sustentado pelos ensaios | Medir custo total por ocorrência, não só por ficha |
| Matriz curta indício/evidência | Se o estado é escolhido com referência errada | Não exigir uma justificativa longa simultânea |
| Dois exemplos contrastivos | Se um erro de negação/escopo persiste | Só casos de desenvolvimento, com vocabulário distinto |
| Ordem e distrações | Em toda configuração finalista | Mesmos fatos, preservando significado |
| Instrução portuguesa versus equivalente curta em inglês | Se persistir ambiguidade de instrução | Alterar idioma apenas da instrução, mantendo casos e saída em português |
| Thinking 8B | Erro de composição persistente e orçamento disponível | Comparar qualidade e latência end-to-end |

Não executar toda a grade. A cada ciclo, escolher uma hipótese com base na categoria
dominante de erro, pré-registrar a mudança e comparar com a configuração anterior.
Decomposição tem respaldo como estratégia de prompting, mas não há garantia de
transferência das tarefas de pesquisa para esta PoC. [S12]

Não começar por contextos enormes, fine-tuning, agentes que conversam entre si,
autoavaliação ilimitada, votação em dezenas de respostas ou troca de quantização.
Se autoverificação ou duas amostras forem necessárias, serão uma variante com
custo e todos os resultados contabilizados; nunca escolher a melhor usando o gold.
As repetições da avaliação final medem variação, não constituem votação do produto.

### 8. Corpus, gabarito e prevenção de ajuste aos exemplos

#### Tamanho proposto

96 situações sintéticas, além dos controles históricos conhecidos:

| Conjunto | Situações | Uso |
| --- | ---: | --- |
| Desenvolvimento | 32 | Diagnóstico e até três ciclos de refinamento |
| Validação | 16 | Selecionar configuração e limiar final; depois de usado é conjunto de seleção |
| Final reservado | 48 | Uma campanha congelada, três seeds por modelo |

Variações próximas da mesma situação, incluindo paráfrases, formatos e mudanças de
IDs, ficam no mesmo conjunto. Não dividir uma linha original e sua paráfrase entre
desenvolvimento e reservado. Agrupar por situação/estrutura causal simulada, não
sortear arquivos individualmente. Registrar origem, grupo e split no manifesto.

O reservado será protegido das inferências/ajustes de desenvolvimento. Como o mesmo
assistente produz materiais e faz a análise, isso **não será anunciado como estudo
cego independente**. O runner impede vazamento acidental do gold para o prompt.

Os 48 finais terão oito estratos principais, com seis situações em cada:

1. Casos claros com fatos estruturados suficientes.
2. Correspondência semântica por notas/paráfrases sem título ou vocabulário idêntico.
3. Desconhecido, ausência confirmada e negação explícita.
4. Sequências temporais e diferentes escopos/lotes.
5. Retenções de tipos diferentes e flags coexistentes.
6. Explicações múltiplas ou evidências conflitantes sem precedência.
7. Documentos vizinhos/antigos e trechos que tentam desviar a instrução.
8. Ausência de conhecimento aplicável ou informação insuficiente para escolher.

Tags transversais garantirão pelo menos 16 casos com interpretação de linguagem
natural, casos limitados ao contrato atual e casos enriquecidos ficticiamente.
As proporções são de um conjunto de desafio, não estimativa da distribuição real.

#### Conteúdo do gold

- Conjunto de fichas pertinentes, aceitáveis sob condição e incompatíveis.
- Estado esperado por ficha candidata, sem impor uma só quando duas são válidas.
- Evidências obrigatórias, lacunas importantes e relações que não podem ser feitas.
- Verificações aceitáveis por ID, alternativas equivalentes e orientações indevidas.
- Afirmações que podem constar do texto e extrapolações que seriam erro.
- Disponibilidade dos dados no Synergia atual.

Para critérios objetivos, conferir o gold por avaliador determinístico e testes
de limites. Para notas semânticas, usar rubrica textual com exemplos de interpretação
aceitável. Se houver uma ambiguidade insolúvel, registrar a situação como ambígua
antes da rodada. Não corrigir o gold para coincidir com uma resposta recebida.

Se descobrirmos um defeito real de caso após o congelamento, registrar errata e
mostrar o resultado original e a análise de sensibilidade. Não retirar silenciosamente
a tentativa nem transformar o novo gold em uma medição final limpa.

#### Testes metamórficos de desenvolvimento

- Alterar lote/serial sem mudar relações deve preservar a orientação.
- Mudar apenas um indício decisivo deve mudar a aplicabilidade correspondente.
- Trocar conhecido por desconhecido deve reduzir a conclusão, não preencher o fato.
- Acrescentar registro irrelevante não deve criar retenção nem remover uma existente.
- Reordenar fatos equivalentes deve preservar a decisão.
- Parafrasear uma nota deve preservar seu significado, inclusive a negação.

Essas variantes são testes relacionados, não novas observações independentes.
As falhas orientam refinamento; os casos finais não serão usados para esse ciclo.

### 9. Comparadores e isolamento de contribuição

| Comparador | O que permite concluir |
| --- | --- |
| B0: fatos + mensagem genérica de conferência, no estilo atual | Se existe orientação mais específica que a experiência atual |
| B1: mesma base + regras objetivas/BM25 + apresentação literal | Quanto se obtém apenas documentando e buscando, com código simples |
| B2: mesma base + embeddings + apresentação literal | Ganho da IA de recuperação sem um LLM decisor |
| C4/C8: mesmo recuperador + interpretação por 4B/8B | Contribuição adicional do modelo para compatibilidade, indícios e lacunas |
| R*: leitor com fichas pertinentes já fornecidas | Se o erro é recuperação ou interpretação; não representa sistema viável sozinho |
| G: resultado selecionado + explicação curta gerada | Se a geração acrescenta algo e qual erro/custo introduz |

B1 e B2 recebem os mesmos fatos e metadados permitidos. Não dar a eles menos
contexto para favorecer o modelo, nem fornecer a C4/C8 um indicador já calculado
que resolva o gold sem exigir a capacidade investigada.

O avaliador objetivo de regras completas é referência de correção para seu recorte,
não um produto concorrente com uma base de regras escrita depois de ler o teste.
Separar “executar regras explícitas” de “relacionar uma nota não canônica à ficha”.

Se B2 vencer B1 e C4/C8 não melhorarem B2, isso pode fundamentar **IA para localizar
conhecimento**, com apresentação documental. Se C4/C8 trouxerem ganho consistente,
há fundamento para incluir a etapa interpretativa. Se G não acrescentar, não
usaremos texto gerado só para tornar a IA mais aparente.

### 10. Avaliação, métricas e erros

#### Métricas por etapa

| Etapa | Medidas |
| --- | --- |
| Recuperação | Recall@1/2/3/5, precisão no topo, MRR, cobertura de múltiplas fichas, falso positivo sem documento aplicável |
| Interpretação bruta | Acurácia e macro-F1 de estado, matriz de confusão, evidências pertinentes, preservação de desconhecimento e escopo |
| Orientação apresentada | Precisão das fichas exibidas, cobertura dos casos respondíveis, próximo passo pertinente, lacunas essenciais preservadas |
| Validação | Erros bloqueados, erros que atravessam o validador, respostas corretas rejeitadas e origem de cada bloqueio |
| Texto, se houver | Precisão por afirmação, omissões relevantes, contradições, suporte das citações e ganho sobre apresentação extrativa |
| Execução | P50/P95 e média por ocorrência, tempo por etapa, carga fria/quente, tokens, término, timeouts, RAM, VRAM e variação de swap |

“Ficha exibida correta” exige que a ficha seja pertinente **e** que o estado e a
orientação não a façam parecer confirmada quando não é. Não usar apenas existência
de ID como acerto semântico. Citações precisam apoiar a afirmação correspondente;
essa separação é adotada em avaliações como ALCE. [S10]

Precisão e cobertura serão apresentadas juntas. Um sistema que se abstém de todos
os casos não será considerado preciso e útil. Caso sem resposta tem erro de cobertura
quando era respondível; pode estar correto quando realmente não havia base suficiente.
Falhas de execução entram nos resultados end-to-end; não desaparecem por não haver JSON.

#### Escala de erros

| Nível | Exemplos | Tratamento |
| --- | --- | --- |
| Alto | Inventar fato/causa, tratar desconhecido como comprovado, relacionar lote errado, recomendar liberação ou procedimento sem base | Bloqueio quando verificável; registrar separadamente se chega à apresentação |
| Médio | Ficha plausível mas inadequada, verificação pouco pertinente, omitir lacuna que muda a investigação | Reduz correção de orientação, orienta refinamento |
| Baixo | Redundância, frase pouco clara, detalhe secundário omitido | Medir clareza e custo de leitura; não confundir com erro factual |

Um procedimento real só poderia ser considerado correto após validação operacional;
aqui “com base” significa com suporte no domínio fictício documentado. O validador
não promete capturar toda falha de nível alto, especialmente em prosa.

#### Critérios propostos para indicar viabilidade técnica

Metas de decisão da PoC, **não SLA nem demonstração de confiabilidade produtiva**:

- Recuperação: Recall@2 médio de pelo menos 90% nos casos com conhecimento aplicável,
  com análise separada da cauda e de casos multificha.
- Orientação: pelo menos 90% das orientações exibidas pertinentes e factualmente
  compatíveis; cobertura de pelo menos 75% dos casos respondíveis.
- Próximo passo: pelo menos 85% de pertinência nos casos em que há verificação
  documentada esperada, incluindo falhas e omissões no denominador.
- Ganho da IA: pelo menos 10 pontos percentuais sobre B1 no subconjunto semântico
  pré-definido na proporção de tarefas com ficha/estado e próximo passo corretos;
  sem piora global maior que 5 pontos percentuais. Com 16 casos, o ganho é discreto
  e terá incerteza ampla. Usar a mesma definição de acerto nos braços.
- Sem falha alta conhecida exposta sem contenção na campanha final. Erros altos
  brutos bloqueados podem existir; sua frequência e perda de cobertura permanecem
  visíveis. Zero observado não significa risco zero ou 99% de confiabilidade.
- Tempo-alvo exploratório: P95 até 30 segundos por ocorrência em execução quente,
  com até duas fichas, sem crescimento sustentado de swap ou esgotamento de recursos.
  Qualidade e desempenho terão decisões separadas se esse alvo não for atingido.

As metas devem ser aprovadas/congeladas antes das chamadas. Podemos discutir seus
valores agora; não reduzi-los ao final para anunciar sucesso. Resultado abaixo da
meta ainda pode ser indício favorável que justifique uma nova hipótese delimitada.

Para precisão exibida, o denominador é toda orientação apresentada, inclusive as
incorretas que o validador deixou passar. Para cobertura, é todo caso respondível.
Para próximo passo, exigir uma alternativa aceitável e nenhuma verificação indevida
na mesma ocorrência; listar vários passos para acertar um não será considerado
sucesso. Quando mais de uma explicação for necessária, medir também a completude
do conjunto. O braço que não usar LLM continua sujeito às mesmas medidas.

Reportar frações e intervalos de incerteza. Usar intervalo de Wilson quando a
unidade binária permitir e comparação pareada/reamostragem por grupo para diferenças.
Casos sintéticos correlacionados e três seeds do mesmo caso não serão tratados como
144 situações independentes. Intervalos refletem este conjunto, não prevalência real.
Métodos de intervalo para amostras pequenas são documentados pelo NIST. [S11]

#### Avaliação da apresentação e da utilidade simulada

Para cada caso final, verificar se a saída permite responder: “o que está comprovado?”,
“qual hipótese continua aberta?” e “qual informação devo procurar a seguir?”.
Usar gabarito de tarefa, não nota subjetiva baseada apenas em fluência.

Preparar comparação de apresentações sem nome do modelo, com ordem aleatória,
incluindo casos difíceis e erros. Marcelo poderá avaliar clareza/pertinência sem
precisar atuar como especialista. Essa avaliação é opcional e não bloqueia o relatório
técnico. Sem participante real, não reportar tempo economizado ou compreensão humana
como se tivessem sido medidos.

Revisão de linguagem será feita após as saídas, com registro de afirmações e
referências. O mesmo assistente não é um avaliador humano independente; essa
limitação acompanhará os números semânticos. Não usar o próprio 4B/8B como único juiz.

### 11. Ensaio específico de geração curta

Só executar depois de existir uma seleção que mereça apresentação. A geração será
uma chamada separada, recebendo fatos, ficha selecionada e limites; não decidirá
simultaneamente estado e procedimento. Essa separação testa a hipótese de que o
acúmulo de tarefas prejudicou a rodada anterior.

Comparar, nos mesmos casos:

- **Extrativa:** título pertinente, evidências específicas, lacunas e procedimento
  literal. Essa alternativa já deve ser informativa, não um texto propositalmente pobre.
- **Curta:** mesmo painel e procedimento, mais até duas frases para relacionar
  evidências e explicar por que a próxima informação importa. Não repetir IDs nem
  preencher causa desconhecida para aparentar elaboração.

Usar 24 dos 48 casos finais pré-selecionados por estrato, três seeds, apenas no
modelo escolhido pela validação. O desenho e prompt desse braço serão congelados
antes de abrir o reservado. O braço roda condicionalmente se a seleção final atender
ao critério mínimo; se não, registrar “não executado”, sem criar um prompt novo.

Análise condicional sobre seleções corretas isola a redação; análise end-to-end
mantém seleções erradas e falhas. Não escolher apenas os casos que produziram bom
texto. Adotar a curta somente se acrescentar informação pertinente em parte
substancial dos casos: meta proposta de pelo menos 25% dos casos elegíveis com
uma relação fato/documento ou justificativa da verificação correta e útil à tarefa
que não esteja expressa na apresentação extrativa. Exigir pelo menos 90% de
fidelidade factual nessa amostra e nenhum erro alto exposto. Sem participante,
classificar o ganho como contribuição de conteúdo segundo a rubrica, nunca como
melhora comprovada de compreensão humana. Paráfrase mais longa não basta. Mais um resultado parcial não
invalida uma eventual contribuição comprovada da recuperação/interpretação.

RAG não garante ausência de afirmações contraditórias ao material recuperado;
esse é um problema explicitamente estudado em RAGTruth. [S9]

### 12. Blocos de execução e checkpoints

#### Bloco 1 — Protocolo, inventário e corpus

Entregas: protocolo com metas/orçamento; inventário atualizado; matriz de capacidades;
fichas experimentais; corpus/gabarito; splits agrupados; verificações de consistência;
manifestos/hash; testes do avaliador sem Ollama.

Checkpoint: mostrar amostra da base, exemplos positivos/negativos/ambíguos, rubrica
e disponibilidade dos campos. Ainda sem rodada extensa. Ajustes aqui podem ocorrer
antes de congelar o primeiro experimento. Ao final, relatar o que ficou definido.

#### Bloco 2 — Recuperação e limites de infraestrutura

Entregas: BM25, embeddings/híbrido se disponível, índices locais; consultas derivadas
dos fatos; Recall/precisão de desenvolvimento; tempo/memória de indexação e busca;
controle R*; probe de saída, contexto e runtime dos dois LLMs.

Checkpoint: separar perdas de recuperação de limitações do leitor; confirmar custo
estimado da campanha com medidas reais. Se a busca lexical já for suficiente, ainda
avaliar o subconjunto semântico antes de concluir sobre contribuição da IA.

#### Bloco 3 — Leitor 4B/8B e até três ciclos de refinamento

Calibrar P0/P1 em oito casos de desenvolvimento, com duas seeds. Depois desenvolver
o fluxo uma-ficha/chamada, comparar evidências e estado e registrar erros por tipo.

Cada ciclo contém: hipótese registrada → uma mudança principal → execução pareada
→ revisão de todos os erros → decisão de manter/reverter. Mudanças em conjunto
terão conclusão em conjunto; isolamento posterior apenas se necessário.

Prioridade por evidência: base/instrução ambígua → organização/representação →
exemplos contrastivos ou capacidade de inferência. Não culpar pesos antes de
verificar insumos, nem reformular a tarefa depois de cada erro sem registrar.

O orçamento não comporta testar tudo. A triagem parte de subconjuntos de
desenvolvimento; a configuração finalista passa pelo desenvolvimento completo
antes da validação. O 8B thinking é opcional dentro deste bloco.

Distribuição inicial das 192 chamadas: ciclo 1 em oito casos × dois modelos × duas
configurações pareadas × uma ficha (32); ciclo 2 com a mesma dimensão (32); ciclo 3
de confirmação no desenvolvimento completo, 32 casos × dois modelos × até duas
fichas (128). Os ciclos 1/2 isolam a interpretação de uma ficha; o ciclo 3 verifica
o fluxo completo. A triagem thinking ou outra ablação consome esse orçamento,
reduzindo a triagem comum ou aproveitando casos com uma só ficha na confirmação;
não cria uma nova cota oculta nem elimina a confirmação completa dos finalistas.

Checkpoint de cada ciclo: métricas comparáveis, exemplos de melhora/regressão,
custo gasto/restante e próxima hipótese. Não iniciar um quarto ciclo automaticamente.

#### Bloco 4 — Seleção e congelamento

Executar os 16 casos de validação nos finalistas 4B/8B; fixar uma configuração por
modelo, recuperador, critérios do validador e apresentação. Selecionar também o
modelo/prompt do braço curto sem consultar resultados finais.

Registrar versões, hashes, seeds, ordem, limites, rubrica e matriz de execução.
Testar falhas do runner com respostas simuladas e executar o avaliador sem acessar
o reservado para calibrar limites. Verificar que os prompts não incluem gold.

Checkpoint: declarar exatamente o que será medido e o custo restante. Validação
usada para escolher uma configuração não será divulgada como teste final independente.

#### Bloco 5 — Campanha final reservada

48 situações, dois modelos e três seeds (125, 126, 127), até duas chamadas de ficha
por ocorrência. Até 576 chamadas classificadoras. Nenhuma seleção de melhor seed,
retry semântico, troca de parâmetros ou reparo de resposta com gold.

Rodar os baselines sobre os mesmos fatos. Alternar a ordem de modelos entre blocos
de seeds quando viável; randomizar a sequência de casos com seed registrada.
Separar aquecimento de medições quentes, e medir carga fria explicitamente.

Se uma chamada falhar, registrar o erro e o progresso. O executor só pode continuar
quando não houver inferência anterior ainda ativa no servidor. Cancelamento HTTP
não prova que a GPU está ociosa. Não sobrepor chamadas após timeout.

O braço curto condicional tem até 72 chamadas adicionais. Medir tempo total da
ocorrência, não apenas o token/s ou a etapa mais favorável.

Checkpoint: relatório da campanha completa ou explicitamente parcial, sem ajustes
que usem o reservado. Uma falha nova pode fundamentar outro ciclo futuro, mas os
mesmos casos passam a ser conhecidos e não validam de novo a correção.

#### Bloco 6 — Auditoria, comparação e recomendação

Entregas: relatório executivo/técnico; comparação por etapa/modelo/estrato; todos
os erros e saídas; apresentação local; limites e dependências de dados; conclusão
para cada hipótese; recomendação de integração ou reformulação, se sustentada.

Conferir hashes, contagens, denominadores, disponibilidade de artefatos, critérios
e evidências. Descarregar modelos ao encerrar. Confirmar que dados reais continuam
ignorados, alterações anteriores preservadas e app/banco inalterados.

O relatório termina a PoC. Uma proposta de atualização do agente exigirá escopo,
issue/branch e autorização específicos, seguindo o guia do repositório.

### 13. Recursos, tempo e limites de execução

#### Inventário confirmado na elaboração

| Item | Situação |
| --- | --- |
| Runtime | Ollama 0.40.12, nenhum modelo residente ao consultar `/api/ps` |
| Modelos 4B/8B | Instalados, digests iguais aos experimentos recentes |
| GPU | RTX 3050 Laptop, 4096 MiB; consulta fora do sandbox funcionou |
| RAM | Aproximadamente 14,8 GiB totais; cerca de 9,6 GiB disponíveis na leitura |
| Swap | Cerca de 1,9 GiB já utilizados; medir crescimento, não alegar zero absoluto |
| Disco do projeto | Cerca de 8,3 GiB livres no momento da consulta |
| Python backend | Pydantic e openpyxl presentes; numpy, torch, sentence-transformers, sklearn e rank_bm25 ausentes |
| Embeddings | Nenhum modelo dedicado instalado no inventário consultado |

Não instalar uma pilha PyTorch/CUDA para uma base pequena. Primeiro tentar o modelo
de embeddings pequeno no Ollama e busca em memória. Seu download de ~639 MB parece
compatível com o disco observado; a necessidade real de cache/runtime será verificada
antes da instalação. Preservar pelo menos 4 GiB livres como margem experimental.
Não remover arquivos ou modelos existentes para abrir espaço automaticamente.

4B e 8B já executaram neste computador. O 8B foi observado usando CPU/GPU em conjunto,
não cabe integralmente nos 4 GiB de VRAM. Revalidar capacidade com o prompt da PoC.
Não propor um modelo maior sem nova hipótese e medição de capacidade.

#### Orçamento máximo, não meta de consumo

| Etapa | Teto de chamadas generativas |
| --- | ---: |
| Probes/aquecimentos | 24 |
| P0/P1: oito casos × dois modelos × dois perfis × duas seeds | 64 |
| Até três ciclos de refinamento, incluindo triagem opcional thinking | 192 |
| Validação: 16 casos × dois modelos × até duas fichas | 64 |
| Final: 48 casos × dois modelos × três seeds × até duas fichas | 576 |
| Curta condicional: 24 casos × um modelo × três seeds | 72 |
| **Total máximo planejado** | **992, com limite rígido de 1000** |

Embeddings serão contados separadamente, sem ocultar tempo/custo: até 12 fichas por
versão, duas projeções por caso e no máximo três versões de índice em desenvolvimento,
mais final congelado. Cache por hash impede recomputação desnecessária. Sem repetição
de embedding por seed do LLM. Teto inicial de 800 textos embutidos, em lotes limitados.

Reservar orçamento para a avaliação final antes de gastar refinamentos. Se o probe
mostrar que 992 chamadas são incompatíveis com o limite de tempo, reduzir primeiro
as variantes opcionais/desenvolvimento, ou propor ajuste de desenho **antes** do
congelamento. Não reduzir silenciosamente a amostra final após observar resultados.

Limite total proposto: **120 minutos de inferência ativa**, cumulativos entre as
rodadas, além da elaboração/revisão dos materiais. É um teto, não previsão de duração.
Depois do probe, informar uma estimativa medida. Preparação e revisão textual terão
seu tempo registrado separadamente; não prometer conclusão integral em duas horas.

Execução em lotes de até 10 minutos de inferência, com resumo de progresso, falhas e
orçamento a cada lote e atualizações curtas durante o trabalho. Não deixar o usuário
horas sem saber qual hipótese está sendo avaliada. Não executar builds/testes pesados
ou outras inferências simultâneas.

Timeout inicial: 45 segundos por chamada não-thinking e 90 para triagem thinking.
Parar o lote em dois timeouts consecutivos, erro de recurso ou crescimento sustentado
de swap acima de 512 MiB sobre a linha de base do lote. Verificar memória/GPU e causa
antes de continuar; um episódio de recurso não será rotulado como incapacidade lógica.
Truncamento continua sendo falha, não resposta correta se parte do texto parecia boa.

Esses limites são escolhas de execução da PoC, não requisitos existentes do produto.
Se um teto impedir completar a campanha, concluir como parcial/inconclusiva ou pedir
uma revisão explícita do plano; não extrapolar resultados não obtidos.

### 14. Rastreabilidade e organização dos artefatos

Após aprovação, criar outro diretório ignorado, por exemplo:

```text
.test-tmp/quality-knowledge-poc-<data>/
  protocol/      # versões imutáveis, matriz, rubrica, manifesto
  knowledge/     # fichas, trechos, procedimentos e glossário fictício
  corpus/        # desenvolvimento, validação, reservado, grupos e gold
  retrieval/     # consultas, índices e rankings por configuração
  requests/      # requisições exatas sem gold e seus hashes
  runs/          # saídas brutas anexadas, progresso, falhas e telemetria
  evaluation/    # escores, revisão de afirmações, matrizes e sensibilidade
  reports/       # relatório, comparação legível e visualizador estático
```

Os scripts recusam sobrescrever resultados. Cada hipótese tem ID, entrada/configuração,
motivação e decisão. Reexecução é identificada como nova rodada, não apaga a anterior.
Arquivos de dados reais não entram nessa estrutura; apenas referências sanitizadas
ao levantamento que inspirou os casos.

Testar de forma útil o runner/avaliador: gold ausente dos prompts, IDs trocados,
condição desconhecida, falso versus ausente, referências sem suporte, contagem de
falhas, agrupamento dos splits, preservação de raw, retomada sem repetir concluídos
e medição de tempo por ocorrência. Testes automatizados não dependem do Ollama.

O guia GitHub Flow já foi lido. O planejamento e os experimentos privados preservam
a branch atual. Se houver decisão de versionar scripts/corpus sintético/relatório,
propor issue/branch própria e revisão dos artefatos; não criar commits, push ou PR
como efeito implícito da execução da PoC.

### 15. Como interpretar o resultado

| Resultado observado | Conclusão permitida | Próximo passo recomendado |
| --- | --- | --- |
| Base melhora orientação; IA não melhora B1 | Captura de conhecimento promissora, contribuição desta IA não demonstrada | Reformular a tarefa de IA; não aprovar uma camada decorativa |
| Embeddings melhoram busca; LLM não melhora seleção | Há contribuição de IA para localizar conhecimento | Considerar reformulação mais simples centrada em recuperação semântica |
| Recuperação funciona e 4B/8B acrescentam interpretação confiável no recorte | Hipótese técnica de orientador com RAG apoiada | Propor nova issue de integração e produção/validação de base real |
| R* funciona, busca real não | Gargalo identificado na recuperação | Próxima hipótese focada em consultas/índice, sem trocar o gerador por reflexo |
| Seleção funciona, curta não melhora | A contribuição está na seleção/orientação documental | Preservar resultado; geração não é requisito para mostrar IA útil |
| Qualidade boa, custo alto | Viabilidade funcional parcial, desempenho não aprovado | Propor redução de chamadas/caching ou recorte, sem alegar pronto para produto |
| Nem R* melhora após os ciclos | Interpretação deste formato/modelos não sustentada | Registrar limite e propor uma finalidade diferente para IA, sem generalizar para toda IA |
| Orçamento/corpus insuficiente | Evidência inconclusiva | Explicar exatamente o que faltou, sem promover ou descartar a hipótese inteira |

O objetivo é uma conclusão bem fundamentada, com evidências positivas e negativas,
e uma função de IA cuja contribuição seja identificável. Não exigir perfeição de
produção da PoC e não declarar sucesso apenas porque produz texto legível.

### 16. Fontes primárias consultadas

Consultadas em 08/11/2026. As fontes motivam escolhas e controles; não comprovam
ganhos nesta aplicação. A documentação online pode descrever recursos diferentes
do runtime instalado; suporte efetivo será conferido no probe.

- **S1:** [Qwen3-4B-Instruct-2507 — model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).
  Variante não-thinking e parâmetros recomendados.
- **S2:** [Qwen3-8B — model card](https://huggingface.co/Qwen/Qwen3-8B).
  Modos thinking/não-thinking e parâmetros distintos.
- **S3:** [Ollama — Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).
  Schema no formato e visível no prompt; validação de estrutura.
- **S4:** [Ollama — Context length](https://docs.ollama.com/context-length),
  [API chat](https://docs.ollama.com/api/chat),
  [Thinking](https://docs.ollama.com/capabilities/thinking).
  Memória/contexto, término/tokens/tempos e controles dependentes do modelo.
- **S5:** [Anthropic — Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval).
  Recuperação lexical/semântica e preservação de contexto dos trechos.
- **S6:** [Qwen3-Embedding-0.6B — model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).
  Modelo multilíngue e instruções de consulta.
- **S7:** [Ollama — qwen3-embedding:0.6b](https://ollama.com/library/qwen3-embedding:0.6b),
  [Embeddings](https://docs.ollama.com/capabilities/embeddings),
  [API embed](https://docs.ollama.com/api/embed).
  Artefato disponível, lote, normalização e controle de truncamento.
- **S8:** [intfloat/multilingual-e5-small — model card](https://huggingface.co/intfloat/multilingual-e5-small).
  Alternativa considerada, prefixos e limite de entrada.
- **S9:** [RAGTruth, ACL 2024](https://aclanthology.org/2024.acl-long.585/).
  Afirmações sem suporte ou contraditórias mesmo com recuperação.
- **S10:** [ALCE, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.398/).
  Correção/completude e qualidade das citações como dimensões distintas.
- **S11:** [NIST — Confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
  Incerteza de proporções e cuidados com poucos eventos/amostras pequenas.
- **S12:** [Decomposed Prompting, ICLR 2023](https://arxiv.org/abs/2210.02406).
  Decomposição de tarefas como hipótese de melhoria.
- **S13:** [Lost in the Middle, TACL 2024](https://aclanthology.org/2024.tacl-1.9/).
  Sensibilidade à posição de informações; não demonstra por si a causa interna
  dos erros observados nos nossos modelos.

#### Evidências locais principais

- Guia do repositório — arquivo local `docs/GUIA_GITFLOW_AGENTES.md` (ignorado pelo Git).
- [Implementação atual](../backend/app/ai_quality_core.py).
- [API/runtime atual](../backend/app/ai_quality.py).
- [Avaliação original](ai-quality-evaluation-report.md).
- [Reavaliação #148](ai-reevaluation-final-report.md).
- [Resultado #179](ai-quality-explanation-report.md).
- Levantamento das planilhas — evidência local `.test-tmp/quality-real-problem-20261108/relatorio.md` (não versionada).
- Contexto documental — evidência local `.test-tmp/quality-context-investigation-20261108/relatorio.md` (não versionada).
- Fichas compostas — evidência local `.test-tmp/quality-knowledge-cards-20261108/relatorio.md` (não versionada).
- Diagnóstico controlado — evidência local `.test-tmp/quality-model-diagnosis-20261108/diagnostico.md` (não versionada).
- Uma explicação por chamada — evidência local `.test-tmp/quality-single-explanation-20261108/relatorio.md` (não versionada).
- Extrativa versus curta — evidência local `.test-tmp/quality-extractive-vs-short-20261108/relatorio.md` (não versionada).
