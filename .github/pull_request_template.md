## Issue relacionada

Closes #

## Resumo executivo

<!--
Explique o resultado entregue e por que ele importa. A descrição deve ser
proporcional ao escopo: mudanças amplas precisam apresentar visão integrada,
não apenas uma lista de arquivos.
-->

## Problema e resultado

<!--
Descreva o comportamento anterior, a necessidade atendida e o comportamento
esperado depois deste PR. Não repita somente o título da issue.
-->

## Escopo da entrega

<!--
Organize por responsabilidade lógica. Para fluxos com três ou mais etapas,
inclua uma sequência curta, tabela ou diagrama textual.
-->

### Implementação

-

### Contratos, dados e integrações

-

### Operação, segurança e observabilidade

-

## Critérios de aceite

<!-- Relacione cada critério da issue à implementação e à evidência. -->

| Critério | Como foi atendido | Evidência |
| --- | --- | --- |
|  |  |  |

## Impactos e compatibilidade

| Área | Impacto, decisão ou justificativa de não aplicabilidade |
| --- | --- |
| API e contratos |  |
| Banco, migrations e persistência |  |
| Segurança e privacidade |  |
| Observabilidade e operação |  |
| Frontend, UX e acessibilidade |  |
| Documentação e rastreabilidade |  |
| Compatibilidade e rollout |  |

## Validações executadas e resultados

<!-- Informe comandos realmente executados, quantidade de testes e resultado. -->

| Validação | Resultado |
| --- | --- |
| `git diff --check` |  |
| testes aplicáveis |  |
| lint e build aplicáveis |  |
| validação manual ou E2E |  |
| CI |  |

### Checklist de integridade

- [ ] `git diff --check`
- [ ] testes, lint e build aplicáveis
- [ ] ausência de segredos, dados reais, caches e temporários
- [ ] contratos e documentação sincronizados
- [ ] matriz de rastreabilidade atualizada ou justificada como não aplicável
- [ ] comandos e resultados acima correspondem ao que foi realmente executado

## Como validar

<!--
Forneça o menor roteiro reproduzível para o revisor observar o resultado,
incluindo pré-condições, comandos, rota/tela e comportamento esperado.
-->

1.

## Fora do escopo, limitações e decisões pendentes

<!--
Liste o que foi deliberadamente excluído, dependências externas, passos manuais,
riscos aceitos e follow-ups. Escreva "Não se aplica — <motivo>" quando vazio.
-->

-

## Arquivos ou áreas principais para revisão

<!-- Direcione o revisor aos pontos de maior risco ou maior valor. -->

| Área | Arquivos ou componentes | O que conferir |
| --- | --- | --- |
|  |  |  |

## Roteiro sugerido para revisão

<!-- Ordene a revisão quando o PR atravessar mais de uma responsabilidade. -->

1.

## Alteração de frontend

Preencha quando houver mudança visual. Consulte a
[norma de implementação visual](../docs/frontend-implementation-standard.md).

- [ ] não se aplica
- [ ] informei a tela equivalente usada como referência
- [ ] não dupliquei título, badge, breadcrumb ou paginação
- [ ] preservei o shell, o contêiner principal e o scroll interno
- [ ] reutilizei tokens e componentes compartilhados
- [ ] validei estados vazio, preenchido, longo, erro e carregamento
- [ ] validei os temas claro e escuro
- [ ] validei desktop, viewport estreito, teclado, foco e contraste
- [ ] atualizei `pt-BR` e `en-US` quando acrescentei texto
- [ ] executei as validações visuais e o E2E aplicáveis
- [ ] documentei abaixo qualquer exceção à norma e sua justificativa.

Tela de referência:

Exceções ou limitações:
