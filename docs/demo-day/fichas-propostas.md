# Fichas das propostas de integração com IA

Estas fichas apoiam o pitch. Elas descrevem propostas futuras e não afirmam que
os agentes já estão integrados ao produto.

## Proposta 1 — assistente de qualidade dos dados

**Problema:** ocorrências determinísticas podem exigir leitura conjunta de
mensagens, origem e impacto antes da conferência humana.

**Usuário principal:** operador ou responsável por qualidade dos dados.

**Entrada controlada:** execução, validações, divergências e IDs de proveniência
selecionados pelo backend dentro da organização autorizada.

**Saída esperada:** explicação curta, impacto, próxima verificação sugerida,
evidências e indicação explícita de informação insuficiente.

**Integração proposta:** FastAPI monta contexto mínimo; runtime local gera JSON;
validador confere schema e evidências; Angular apresenta o resultado ao lado do
dado determinístico.

**Limites:** sem alterar dados, classificar OQC, priorizar pendências, aprovar ou
executar RPA.

**Critérios de avaliação:** comparação com baseline, correção das evidências,
abstenção, consistência, latência, memória e revisão humana independente.

## Proposta 2 — assistente de investigação operacional

**Problema:** investigar uma execução exige consultar estado, pendências,
Workorders, eventos e proveniência em pontos diferentes da aplicação.

**Usuário principal:** operador no fluxo restrito; gestor ou analista quando o
histórico de auditoria fizer parte da investigação.

**Entrada controlada:** dados recuperados por ferramentas somente de leitura,
sempre com as permissões e o escopo organizacional da sessão.

**Saída esperada:** resumo, achados com evidências, perguntas em aberto e
próximos passos para validação humana.

**Integração proposta:** primeira fase com contexto pronto; segunda fase com
seleção restrita de ferramentas; piloto com usuários somente após avaliação.

**Limites:** sem alterar prioridade, liberar ou reter item, aprovar pendência,
notificar, reprocessar ou executar RPA.

**Critérios de avaliação:** fidelidade aos fatos, escolha de ferramentas,
evidências, consistência, limites de chamadas, latência, memória e utilidade
avaliada pelos usuários.

## Aprendizados aproveitados no novo desenho

- manter regras determinísticas como fonte de verdade;
- começar com contexto preparado pelo backend antes de ampliar a autonomia;
- usar modelo local compatível com o hardware disponível;
- validar evidências e saídas antes de exibi-las;
- congelar casos e gabaritos antes da comparação;
- separar avaliação técnica de autorização para integração.

