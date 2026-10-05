# Propostas e contratos das PoCs de IA do Demo Day

Este documento define o escopo de duas provas de conceito locais para o Demo
Day. Ele não declara uma integração de IA já implementada no produto. As PoCs
devem usar exclusivamente dados sintéticos ou sanitizados e respeitar o escopo
organizacional já aplicado pelo SYNERGIA.

## Limites comuns

- Validação, normalização, consolidação, classificação OQC, prioridade e estado
  permanecem determinísticos e são a fonte de verdade.
- O modelo não grava no banco, não altera arquivos, não aprova pendências e não
  dispara reprocessamento, notificação ou RPA.
- Toda afirmação deve apontar para identificadores e evidências recebidos na
  entrada. Ausência de evidência deve resultar em `insufficient_evidence`.
- A saída é JSON e deve validar contra os schemas versionados em
  [`docs/schemas/`](schemas/).
- O processamento é local, sem envio de dados a serviços externos. Credenciais,
  caminhos internos, tokens e dados pessoais não entram no contexto.
- Decisões operacionais e de negócio continuam sob responsabilidade humana.

## PoC 1 — Diagnóstico assistido de qualidade dos dados

### D — Define

**Problema:** erros e avisos determinísticos já são produzidos pelo pipeline,
mas a leitura conjunta de ocorrências, origem e impacto pode exigir inspeção
manual de várias linhas e arquivos.

**Hipótese:** um modelo local consegue organizar as ocorrências existentes,
explicar o impacto e sugerir a próxima verificação sem inventar fatos nem
substituir as regras do pipeline.

**Fora do escopo:** detectar erros que o pipeline não registrou, corrigir dados,
classificar OQC, decidir prioridade ou alterar a origem.

### E — Explore

**Usuário:** operador ou responsável por qualidade de dados.

**Entradas:** identificação da execução, resumo de contagens, ocorrências de
validação e divergências, além das referências de proveniência autorizadas. O
contrato está em
[`ai-quality-diagnosis-input.schema.json`](schemas/ai-quality-diagnosis-input.schema.json).

**Saída:** diagnóstico por ocorrência, impacto, ação de verificação e lista de
evidências. O contrato está em
[`ai-quality-diagnosis-output.schema.json`](schemas/ai-quality-diagnosis-output.schema.json).

**Ferramentas somente de leitura previstas para a PoC:**

- `get_execution(execution_id)`: estado, versões e contagens;
- `get_validation_report(execution_id)`: erros e avisos determinísticos;
- `get_divergences(execution_id)`: divergências e localização de origem;
- `get_workorder_detail(execution_id, workorder_number)`: resultado consolidado
  e proveniência, quando necessário.

Esses nomes descrevem capacidades já expostas pelos contratos HTTP; não criam
novos endpoints nem concedem acesso além das permissões vigentes.

### E — Experiment

1. Montar casos sintéticos independentes dos exemplos usados no prompt.
2. Executar a baseline determinística e o modelo local sobre o mesmo conjunto.
3. Validar o JSON, as referências de evidência e a repetibilidade.
4. Revisar manualmente erros factuais e sugestões sem suporte.

**Baseline:** template que agrupa ocorrências por `severity` e `code`, copia a
mensagem determinística e apresenta contagens, sem interpretação por modelo.

### P — Productionize

A PoC só avança para integração após atingir os critérios do
[plano de avaliação](ai-poc-evaluation-plan.md), operar sem dados sensíveis e
demonstrar ganho sobre a baseline. Uma integração futura deverá usar um
adaptador isolado, autorização existente e auditoria; não haverá acesso direto
do modelo ao PostgreSQL.

## PoC 2 — Investigação e resumo operacional com evidências

### D — Define

**Problema:** a investigação de uma execução pode envolver estado, contagens,
classificações, pendências, eventos e proveniência em consultas distintas.

**Hipótese:** um agente local, restrito a ferramentas de leitura, consegue
produzir um resumo rastreável e perguntas úteis para investigação humana.

**Fora do escopo:** decidir liberação/retenção, aprovar pendências, modificar
prioridades, inferir causas não registradas ou executar ações no sistema.

### E — Explore

**Usuário:** operador, gestor ou revisor de uma execução.

**Entradas:** execução, pendências, classificações e eventos autorizados. O
contrato está em
[`ai-operational-summary-input.schema.json`](schemas/ai-operational-summary-input.schema.json).

**Saída:** resumo, achados priorizados, questões em aberto e próximos passos
para validação humana. O contrato está em
[`ai-operational-summary-output.schema.json`](schemas/ai-operational-summary-output.schema.json).

**Ferramentas somente de leitura previstas para a PoC:**

- `get_execution(execution_id)`: ciclo de vida, versões e contagens;
- `list_pending_items(execution_id)`: pendências e evidências públicas;
- `get_workorder_detail(execution_id, workorder_number)`: classificações,
  avaliações de regras e proveniência;
- `get_history(execution_id)`: eventos auditáveis da execução.

### E — Experiment

1. Preparar casos sintéticos com execução concluída, parcial, falha e com
   evidência insuficiente.
2. Comparar o agente com uma baseline de resumo por template.
3. Conferir chamadas de ferramenta, cobertura dos fatos e referências.
4. Repetir cada caso para medir consistência e registrar latência e memória.

**Baseline:** template com estado, contagens, quantidade de pendências por
categoria e prioridade e últimos eventos, sem interpretação por modelo.

### P — Productionize

O agente só poderá ser integrado após avaliação reproduzível, definição do
modelo local e aprovação dos limites operacionais. Uma versão de produto deverá
exibir as evidências e exigir confirmação humana para qualquer ação posterior.

## Modelo e execução local

A escolha do modelo permanece aberta até o experimento comparativo. O notebook
ou script da issue de pipeline deve registrar, no mínimo:

- nome, versão, quantização e licença do modelo;
- versão do prompt e dos schemas;
- hardware, tempo de carregamento, latência por caso e pico de memória;
- seed e parâmetros de geração, quando suportados;
- resultado da baseline e métricas por caso;
- falhas de validação, recusas e respostas sem evidência.

O critério não é usar o maior modelo, mas selecionar o menor modelo local que
atenda às metas com execução reproduzível no equipamento disponível.

## Dependências e decisões pendentes

| Item | Estado | Responsável pela decisão |
|---|---|---|
| Modelo local e licença compatível | A validar por experimento | equipe técnica |
| Hardware disponível no Demo Day | A confirmar | equipe/organização |
| Conjunto sintético de avaliação e gabarito | Planejado | responsáveis pelas PoCs |
| Limite de latência e memória | A medir antes de fixar | equipe técnica |
| Uso futuro de dados corporativos | Fora desta PoC; exige autorização | cliente/PO |
| Integração com a aplicação | Fora da issue #123 | produto/equipe técnica |

## Mapa de conteúdo para o modelo de apresentação do kickoff

A apresentação da issue #127 deve reutilizar identidade visual, tipografia,
cores, margens e hierarquia do modelo fornecido em `Kickoff/`, mas atualizar o
conteúdo técnico histórico: o produto atual usa Angular, FastAPI e PostgreSQL.

| Slide | Conteúdo mínimo |
|---|---|
| Capa | SYNERGIA, desafio de Suprimentos e Demo Day de IA |
| Equipe | integrantes, papéis e interlocução com o cliente |
| Contexto | produto atual, problema e indicadores disponíveis; não inventar FTE ou prazo |
| Escopo | duas PoCs locais, dados sintéticos e limites comuns |
| Proposta 1 | D.E.E.P, fluxo, baseline e métricas do diagnóstico de qualidade |
| Proposta 2 | D.E.E.P, ferramentas, baseline e métricas da investigação operacional |
| Avaliação | resultados medidos, falhas, recursos e comparação com baseline |
| Próximos passos | decisão de seguir ou não, dependências e autorização necessária |

O material deve caber em cinco minutos e mostrar apenas métricas realmente
medidas. Capturas de tela e vídeos entram como evidência, não como substitutos
dos contratos e da avaliação.
