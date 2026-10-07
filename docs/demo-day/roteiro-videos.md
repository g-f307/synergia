# Roteiros dos vídeos das PoCs

Cada vídeo deve mostrar a execução real em tela, sem dados corporativos, tokens,
caminhos pessoais ou arquivos fora de `data/synthetic/`. Não substituir uma
falha do agente pela saída da baseline.

## Vídeo 1 — diagnóstico de qualidade dos dados

1. **Caso de uso e dor:** explicar que ocorrências determinísticas exigem leitura
   conjunta para orientar a verificação humana.
2. **Modelo:** mostrar `qwen2.5:3b-instruct-q4_K_M`, Ollama 0.35.1, digest
   registrado, CPU Intel Core i5-1335U e pico RSS medido de 2,165 GiB.
3. **Conjunto:** mostrar 16 cenários sintéticos, quatro de desenvolvimento e 12
   reservados, cada um em CSV e XLSX; destacar gabaritos congelados.
4. **Baseline:** executar o template determinístico sobre os mesmos arquivos.
5. **Pipeline:** exibir um CSV e um XLSX, a ingestão, a normalização, a execução
   do agente e a validação da saída JSON.
6. **Resultados:** schema 100%; F1 67,78%; aceitação 44,44%; consistência 29,17%;
   latência média 55,865 s e P95 93,722 s.
7. **Erros:** mostrar exemplos sanitizados de `ungrounded_evidence`,
   `unexpected_open_question` e `unsupported_certainty`.
8. **Próximos passos:** manter a baseline, preparar novo conjunto reservado e
   estimar a nova iteração somente após revisar hipótese e prompt.

Comando e sequência detalhados: [`../ai-quality-demo.md`](../ai-quality-demo.md).

Checklist de gravação:

- [ ] CSV aparece na tela.
- [ ] XLSX aparece na tela.
- [ ] Modelo, quantização e memória aparecem na narração ou legenda.
- [ ] Baseline e agente usam os mesmos casos.
- [ ] Resultado abaixo da meta aparece sem corte.
- [ ] Nenhum dado real ou sensível aparece.
- [ ] Link final foi testado em janela anônima.

## Vídeo 2 — investigação e resumo operacional

1. **Caso de uso e dor:** explicar que uma investigação consulta execução,
   pendências, classificações, eventos e proveniência.
2. **Modelo:** mostrar `qwen2.5:3b-instruct-q4_K_M`, Ollama 0.35.1, digest
   registrado, CPU Intel Core i5-1335U e pico RSS v3 de 2.460.499.968 bytes.
3. **Conjunto:** mostrar OP-01 a OP-04 e os gabaritos congelados; informar três
   repetições do agente por caso.
4. **Baseline:** executar o resumo determinístico sobre os mesmos quatro casos.
5. **Pipeline:** demonstrar as entradas sintéticas, a seleção controlada de
   ferramentas somente de leitura e a validação do JSON final.
6. **Resultados:** no v3, 0% de respostas finais aceitas, F1 0%, acurácia de
   ferramentas 15,48%, latência média 96,779 s e P95 140,486 s.
7. **Erros:** mostrar repetição de consultas, filtros incorretos e encerramento
   por `tool_call_limit`, sem omitir as 12 falhas.
8. **Próximos passos:** simplificar a estratégia de ferramentas, criar novo
   protocolo e executar uma nova avaliação congelada antes de integração.

Comando reproduzível:

```bash
backend/.venv/bin/python scripts/evaluate_ai_operational.py \
  --mode both --repetitions 3 --runtime-metadata \
  --output /tmp/synergia-operational-demo.json
```

Checklist de gravação:

- [ ] Casos sintéticos e gabaritos aparecem sem conteúdo sensível.
- [ ] Baseline e agente são diferenciados claramente.
- [ ] Ferramentas exibidas são somente de leitura.
- [ ] Limite de chamadas e falhas aparecem sem corte.
- [ ] Nenhuma recomendação é apresentada como decisão automática.
- [ ] Link final foi testado em janela anônima.

