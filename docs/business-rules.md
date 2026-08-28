# Classificação de pendências e regras OQC

O motor `app.business_rules.classify` recebe somente o resultado consolidado e
não depende do mecanismo de coleta. Ele classifica evidências; não altera as
fontes, não libera materiais e não toma decisões em nome das áreas responsáveis.

## Catálogo versionado

Prioridades, áreas e limites ficam em
`backend/app/model/business_rules.json`. Cada evento informa `rule_id`, versão,
descrição, justificativa, evidência e fatores de prioridade, permitindo consultar
exatamente a regra aplicada. `rule_evaluations` também registra regras que não
foram acionadas, com resultado `not_matched` e a mesma versão do catálogo.

Exemplo de classificação aplicada:

```json
{
  "rule_id": "oqc_hold",
  "rule_catalog_version": "1.0.0",
  "state": "active",
  "workorder_number": "WO-001",
  "entity_type": "serial",
  "entity_id": "SER-001",
  "justification": "Aguardando decisão da Qualidade"
}
```

| Regra | Gatilho | Área padrão |
| --- | --- | --- |
| `oqc_pass` | aprovação/liberação ou flag OQC positiva | Qualidade |
| `oqc_pending` | estado OQC pendente, aberto ou em andamento | Qualidade |
| `oqc_hold` | estado/flag explícita de hold | Qualidade |
| `long_term_hold` | hold explícito de longo prazo ou acima de 30 dias | Qualidade |
| `rework` | estado/flag explícita de retrabalho | Produção |
| `ship_block` | estado/flag explícita de bloqueio de embarque | Logística |
| `pre_release_pending` | pendência/hold ativo sem quantidade liberada | Suprimentos |
| `post_release_hold` | hold ativo após alguma liberação | Qualidade |
| `aging` | pendência ativa há pelo menos 7 dias | Suprimentos |
| `container_impact` | pendência ativa ligada a container | Logística |
| `missing_reason` | pendência ativa sem razão | Qualidade |
| `source_divergence` | ocorrência contraditória da consolidação | Governança de Dados |

Os limites de 30 e 7 dias estão declarados no catálogo, não no algoritmo.
Quando há datas disponíveis, a data do evento é comparada com `released_at`
para separar pendência anterior e hold posterior. Sem datas, o motor usa a
quantidade liberada como evidência de fallback e mantém essa decisão rastreável.
Se a quantidade estiver ausente, não presume zero nem cria classificação
pré-liberação sem outra evidência.

## Categorias simultâneas e fila ativa

OQC Hold, Long Term Hold, Rework e Ship Block são eventos distintos. Quando uma
entidade atende a várias regras, todas são preservadas em
`current_classifications` e no histórico. A fila `active_items` contém uma única
linha por entidade com todos os `rule_ids`, evitando duplicar a pendência.

A fila padrão é ordenada primeiro pela data mais antiga. Prioridade é usada
somente como desempate e contexto operacional. O item informa a regra primária,
score, áreas, organizações e IDs dos eventos que o compõem.

Eventos resolvidos e OQC Pass ficam no histórico com `state=closed`; não entram
na fila ativa. A classificação hierárquica agrega as regras em Workorder, lote
e serial sem converter uma liberação parcial em integral.

## Aging, container e qualidade do dado

O aging usa a data de classificação fornecida pelo chamador, tornando o
resultado reproduzível. O impacto em container informa quantos seriais foram
observados, quantos estão afetados e se o impacto é parcial. Pendências sem
razão recebem `data_quality=partial` e a regra `missing_reason`.

Quando há uma única organização consolidada, ela é herdada. Organizações
divergentes não são escolhidas silenciosamente. A área vem da evidência quando
informada; caso contrário, usa o padrão do catálogo.

## Histórico e reprocessamento

`classify` exige `run_id` e `classified_at`. Um reprocessamento recebe
`previous_history`, copia os eventos anteriores e anexa uma nova execução com
novos IDs, sem modificar ou apagar evidências existentes. A API e a persistência
desse contrato pertencem à etapa de disponibilização do sistema.

## Pontos aguardando confirmação

A ordem relativa entre aging, impacto em container e tipos de hold continua
configurável até validação por Suprimentos e Qualidade. Categorias simultâneas
são preservadas, sem escolher automaticamente uma delas. Nenhuma tolerância
numérica adicional foi inferida para comparação com a planilha de referência.

## Massa sintética

`data/synthetic/rules_scenarios.json` cobre todas as regras, liberação parcial,
container parcialmente afetado, item encerrado, ausência de razão, divergência
de organização, fila ativa e reprocessamento histórico.
