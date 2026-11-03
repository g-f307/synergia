# Recomendações para o próximo ciclo das PoCs de IA

Estas recomendações decorrem da [avaliação da issue #148](ai-reevaluation-final-report.md),
cuja decisão foi reformular as duas propostas. São insumos para o próximo
planejamento; não autorizam implementação, novos experimentos ou integração.

## Prioridade e organização

Abrir duas issues independentes, começando pelo diagnóstico de qualidade.
O próximo ciclo deve demonstrar confiabilidade e utilidade sobre um baseline
determinístico atualizado antes de planejar integração ao produto.

| Ordem | Proposta de issue | Resultado a demonstrar |
| --- | --- | --- |
| 1 | Reformular a explicação assistida de ocorrências de qualidade | Explicações e verificações humanas corretas, sem inventar valores ou causas, com benefício sobre o template |
| 2 | Reformular a síntese operacional baseada em evidências recuperadas | Consultas válidas, conflitos e severidades preservados, com síntese factual útil |

Os títulos e critérios definitivos devem ser acordados no planejamento de cada
issue. Esta recomendação não cria issues nem amplia o escopo da #148.

## Diagnóstico de qualidade: delimitar a contribuição do modelo

O pipeline já identifica ocorrências. Recomenda-se manter classificação,
agrupamento, localização e valores conhecidos sob responsabilidade determinística,
limitando o modelo à explicação e à sugestão de verificações humanas.

- Retirar a obrigação de produzir uma causa provável. Quando não há evidência
  causal, a resposta deve explicitar essa limitação, sem atribuir intenção.
- Separar metadados de posição e valores de célula; nunca apresentar a letra
  da coluna como valor, nem inferir um valor que não foi fornecido.
- Preservar todas as ocorrências e agrupar códigos conforme contrato, sem
  depender da geração livre para construir essa estrutura.
- Comparar com um baseline que já forneça uma explicação e um encaminhamento
  claros. Mais texto, por si só, não demonstra benefício.

Essa divisão muda o papel experimental do modelo. O novo protocolo deve
identificar quais campos pertencem ao código e quais são gerados, sem atribuir
ao modelo acertos determinados pelo pipeline. Mudanças em contratos publicados
exigem versionamento e preservação das versões usadas na #148.

## Operacional: validar consultas e preservar significado

Antes de ampliar o modelo, recomenda-se tratar as falhas de consulta e
interpretação observadas:

- Validar parâmetros e distinguir identificador do caso de identificador da
  execução, mantendo o escopo autorizado.
- Impedir que uma consulta filtrada vazia seja apresentada como ausência global;
  confrontar cobertura da consulta com as contagens e evidências disponíveis.
- Tratar explicitamente classificações conflitantes, sem escolher uma como
  vigente quando a entrada não define precedência.
- Preservar severidade e vínculo com a evidência correspondente; um alerta
  crítico genérico não substitui a pendência crítica documentada.
- Delimitar a contribuição do modelo à síntese das evidências recuperadas e
  manter distintas a conclusão do diagnóstico e a conclusão da execução.

Os controles devem continuar restritos a leitura. Sua contribuição deve ser
medida separadamente das escolhas efetivas do modelo, inclusive se o próximo
desenho substituir parte da investigação por coleta determinística.

## Avaliação do benefício e critérios de decisão

Definir antes da rodada uma rubrica de afirmações sustentadas, omissões,
referências, severidades e instruções indevidas, com denominadores explícitos.
A revisão humana deve identificar o que efetivamente foi revisado e como
divergências foram resolvidas; métricas não medidas permanecem indisponíveis.

Comparar baseline e candidato com usuários representativos quanto a correção,
clareza e ajuda para identificar o próximo passo. Hipóteses e recomendações
devem ser distinguidas de fatos comprovados. Se a geração não acrescentar
benefício suficiente, o template determinístico pode ser a entrega escolhida.

As metas e a regra de decisão devem ser fixadas antes da medição, sem reduzi-las
depois de observar falhas para obter um resultado positivo.

## Dados, modelos e recursos

Usar os casos da #148 como regressão e desenvolvimento. A próxima decisão deve
usar **novos casos reservados**, congelados com gabaritos revisados antes da
inferência; a amostra já observada não pode ser apresentada como novo reservado.
Preservar resultados e bytes históricos. Manter dados reais de `docs/files/`
fora dos experimentos e do Git.

Começar com os modelos já instalados: 4B Instruct para qualidade e 8B como
candidato operacional. A #148 demonstrou capacidade de execução local, mas não
demonstrou que aumentar o porte resolverá os erros. Um modelo maior só deve
entrar mediante hipótese explícita, licença e capacidade verificadas, orçamento
e probe de recursos próprios. O 8B observado usa CPU/GPU; 4 GiB de VRAM não
garantem residência integral, concorrência ou desempenho produtivo.

Manter baseline e candidatos nos mesmos casos, aquecimento separado, pelo menos
três repetições, hashes, diário de falhas e telemetria. Integrar ao produto
somente após evidência suficiente de confiabilidade e benefício e o aceite
específico dessa integração.
