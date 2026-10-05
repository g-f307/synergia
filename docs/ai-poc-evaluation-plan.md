# Plano de avaliação das PoCs locais de IA

Este plano separa o conjunto de avaliação dos exemplos de prompt. Nenhum caso
de avaliação poderá ser incluído em instruções, exemplos *few-shot* ou ajustes
manuais feitos após observar a resposta do modelo.

## Conjuntos

- **Desenvolvimento:** casos sintéticos usados para elaborar prompt e pipeline.
- **Avaliação:** casos sintéticos distintos, identificados e congelados antes
  da medição final.
- **Gabarito:** fatos e evidências esperados revisados por pelo menos uma pessoa
  que não tenha produzido a resposta do modelo avaliado.

Cada caso deve registrar hash dos dados, versão do pipeline, catálogo de regras,
schema, prompt, modelo e parâmetros.

## Casos mínimos

| ID | PoC | Cenário | Resultado essencial esperado |
|---|---|---|---|
| QD-01 | qualidade | execução sem ocorrências | lista vazia, sem diagnóstico inventado |
| QD-02 | qualidade | erros e avisos em fontes diferentes | cobertura por código, severidade e origem |
| QD-03 | qualidade | campos conflitantes com proveniência | impacto e evidências corretos, sem correção automática |
| QD-04 | qualidade | evidência incompleta | `insufficient_evidence` e pergunta objetiva |
| OP-01 | operacional | execução concluída sem pendência | resumo fiel e ausência de alerta inventado |
| OP-02 | operacional | execução parcial com pendências | achados ligados às pendências e prioridades recebidas |
| OP-03 | operacional | execução falha com histórico | estado, motivo registrado e eventos corretos |
| OP-04 | operacional | evidência contraditória ou ausente | incerteza explícita e validação humana solicitada |

## Métricas e metas de decisão

| Métrica | Cálculo | Meta para continuar |
|---|---|---|
| JSON válido | saídas aprovadas pelo schema / total | 100% |
| Fidelidade factual | fatos suportados / fatos emitidos | >= 99% |
| Cobertura de fatos | fatos esperados citados / fatos do gabarito | >= 95% |
| F1 de achados | média harmônica de precisão e cobertura | >= 95% |
| Referência correta | referências que apontam para entrada existente / total | 100% |
| Ferramenta correta | chamadas necessárias com argumentos válidos / total esperado | >= 95% |
| Consistência | execuções equivalentes sem contradição / repetições | >= 95% |

Latência, tempo de carregamento e pico de memória devem ser medidos e
comparados, mas os limites só serão fixados depois de confirmar o hardware do
Demo Day. A PoC deve ser rejeitada se melhorar fluência às custas de fidelidade,
mesmo que outras médias atinjam a meta.

## Procedimento reproduzível

1. Validar arquivos e schemas antes da inferência.
2. Executar a baseline no conjunto congelado.
3. Executar cada configuração do modelo no mesmo conjunto, com parâmetros
   registrados e no mínimo três repetições para consistência.
4. Validar schema e referências automaticamente.
5. Comparar fatos e achados com o gabarito; registrar falsos positivos,
   omissões e chamadas incorretas.
6. Publicar tabela agregada e resultados por caso, sem dados sensíveis.
7. Registrar decisão: seguir, ajustar ou descartar, com justificativa.

## Critérios de interrupção

- qualquer vazamento de dado não permitido;
- alteração de regra determinística ou decisão operacional pelo modelo;
- referência inexistente apresentada como evidência;
- saída inválida ou sem possibilidade de rastreamento;
- resultado não reproduzível com versões e parâmetros registrados.
