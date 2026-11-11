# Corpus sintético de orientação investigativa — #183

Base fictícia, elaborada pelo assistente, sem experiência de funcionário coletada
ou homologação operacional. Não contém linhas/textos de workbooks reais.

- `knowledge.json`: fonte das 12 fichas, dez vigentes e duas arquivadas.
- `<split>.json`: entradas sem rótulos para desenvolvimento/validação/avaliação.
- `<split>-gold.json`: referência editorial separada, nunca incluída nos prompts.
- `field-origins.json`: disponibilidade no contrato atual, no workbook ou apenas
  simulada. Todos os valores são sintéticos, inclusive os de campos existentes.
- `manifest.json`: hashes dos arquivos, quantidades e limites de interpretação.

São 96 instâncias em 48 grupos de duas variantes. Desenvolvimento tem 16 grupos
(32 instâncias), validação oito (16) e reservado 24 (48). Formas relacionadas não
atravessam splits e não contam como amostras independentes. O reservado tem 20
instâncias marcadas para a comparação semântica, incluindo controles negativos.

As entradas D19/D20 representam somente o contrato atual: campos não ingeridos
ficam `not_exposed`, sem pressupor flags falsas. As outras 94 instâncias são
enriquecidas artificialmente. Assim, sucesso no reservado não demonstrará que
o agente atual já possui os dados necessários para funcionar dessa maneira.

Há oito estratos de desafio equilibrados por split. Essa distribuição foi
construída, não representa a frequência dos problemas no uso real.

O gabarito das condições objetivas foi conferido com relações literais e datas;
as anotações de notas são editoriais. Conhecer todos os casos durante a autoria
não equivale a avaliação cega independente. Nenhuma inferência pode alterar esses
bytes para coincidir com sua própria resposta. Erratas devem ser identificadas.

Verificar sem serviço externo:

```bash
backend/.venv/bin/python scripts/prepare_ai_knowledge.py verify
```

Renderizar uma nova cópia das fichas para conferência, sem sobrescrever evidências:

```bash
backend/.venv/bin/python scripts/prepare_ai_knowledge.py render --output /tmp/fichas-183.md
```

O diretório contém somente insumos sintéticos permitidos. Pesos, cache e execuções
ficam fora do Git. A campanha final requer configuração congelada e autorização
da etapa correspondente, conforme `docs/ai-knowledge-poc-protocol.json`.
