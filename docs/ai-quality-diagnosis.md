# Diagnóstico consultivo de qualidade — issue #125

## Estado e decisões

Implementação e avaliação local concluídas em 05/10/2026: contratos v2, adaptador
determinístico, corpus sintético, executor rastreável e comparação real. A revisão
humana do gold foi confirmada pelo usuário. A rodada reservada completou 72
tentativas por modo. O agente obteve F1 de 67,78%, contra 100% do baseline;
**esta configuração não está homologada para uso no produto**.
As métricas, a análise de erros e a decisão estão no
[relatório de avaliação](ai-quality-evaluation-report.md); a demonstração tem
[roteiro reproduzível](ai-quality-demo.md).

Decisão aprovada: preservar os contratos 1.1.0 e os casos QD-01–04 da #123,
introduzindo contratos específicos 2.0.0 sem quebrar a PoC operacional da #126.
O runtime compartilhado da #124 permanece compatível; parâmetros e schema são
opcionais. Não há endpoint, migration, dependência de banco ou integração na web.

## Contratos e limites

- Entrada: SHA-256 do arquivo sintético, fonte, contagens e ocorrências
  determinísticas com ID, código, severidade, aba, linha e coluna.
- Saída: categoria, explicação, causa **hipotética**, verificação recomendada,
  confiança qualitativa e revisão humana obrigatória por diagnóstico.
- Categorias: leitura, layout, completude, formato, consistência, referência e
  desconhecido; códigos de validação existentes são preservados.
- Confiança não é probabilidade calibrada. Ausência de ocorrências não significa
  aprovação OQC nem comprova completude de negócio.
- JSON/schema/case ID, duplicidades e associação código/evidência são verificados.
  Um ID existente de **outra** ocorrência não fundamenta o diagnóstico.
- Diagnósticos omitidos são falsos negativos a medir, não preenchidos pelo
  baseline. Validação mecânica não comprova o texto livre: hipóteses e orientações
  ainda precisam da rubrica e revisão humana.

O adaptador usa as funções puras de leitura, validação e normalização de
produção. Não corrige arquivos nem executa consolidação persistida, decisão OQC
ou transição de estado. Células arbitrárias e registros brutos não são enviados
ao modelo. O contexto contém ocorrências, contagens e uma projeção dos registros
normalizados: aba, linha, estado canônico conhecido, flag OQC booleana e quantidades
válidas. Identificadores, texto livre e valores sem mapeamento não são expostos.

Falhas de leitura geram `read_error`, separadas de layout e conteúdo.
Linhas com erros e abas com layout inválido não entram na normalização;
advertências são preservadas. `rows_valid` significa linha não vazia sem erro
bloqueante de validação, não aprovação de negócio.
`references_available=false` representa referência não fornecida, nunca consulta
externa; exige abstenção e pergunta de esclarecimento.

Limites locais: CSV/XLSX, 2 MiB por arquivo, XLSX expandido até 20 MiB,
10 mil linhas e 500 ocorrências. Excesso é rejeitado, não truncado.
O CLI aceita somente arquivos/bytes presentes no manifesto sintético.

## Corpus e gold revisado

`data/synthetic/ai-quality-v2/scenarios.json` contém especificação manual e
inteiramente fictícia, com rótulos e posições esperadas independentes do baseline.
São **16 cenários / 32 arquivos**: quatro de desenvolvimento e doze de avaliação,
cada um em CSV e XLSX. Pares de formatos não são amostras estatísticas independentes.

Cobertura: válido, campo vazio, quantidade negativa/fracionária/zero, data
limítrofe, duplicidade, referência conflitante, coluna ausente, erros mistos,
estado/OQC ambíguos, referência incompleta, instrução maliciosa em célula,
fórmula quebrada e leitura impossível. O caso de instrução maliciosa verifica a
exclusão de texto arbitrário do contexto; sozinho não comprova resistência de um
modelo a todo prompt injection.

O manifesto congela bytes dos arquivos e da especificação. A CI verifica hashes
em Linux/Windows; finais de linha são LF e XLSX é binário. O gerador estabiliza
timestamps ZIP. Não regenerar o manifesto após avaliar respostas para esconder
alterações: mudanças exigem nova versão de dataset e rodada identificada.

Anotações incluem categoria, código, posição, abstenção esperada, hipóteses
aceitáveis e afirmações proibidas. `gold_review` registra a confirmação explícita
do usuário responsável em 05/10/2026, após fiscalização do parecer técnico.
Nenhum rótulo foi alterado; não se atribui a revisão a um colaborador fictício.
Não usar casos de avaliação no prompt ou ajustá-lo após observar respostas sem
identificar uma nova rodada exploratória.

Baseline e agente recebem o mesmo contexto, sem rótulos ou rubrica. O baseline
agrupa códigos com regras fixas. Durante a verificação, o arquivo de cenários é
lido apenas como bytes para hash; seu gold nunca entra no contexto do modelo.

## Execução

Com dependências de desenvolvimento instaladas, na raiz:

```bash
backend/.venv/bin/python scripts/build_ai_quality_dataset.py --verify
backend/.venv/bin/python scripts/run_ai_quality.py \
  --input data/synthetic/ai-quality-v2/development/QD2-D02.csv \
  --case-id QD2-D02 --mode baseline --synthetic-only \
  --output-dir /tmp/synergia-quality-v2
```

Baseline não requer Ollama. Com o runtime/modelo instalado, o mesmo comando
admite `--mode both --repetitions 3`. Modelo via
`SYNERGIA_POC_MODEL`; endpoint HTTP loopback, sem credenciais, query, fragmento
ou redirecionamento. Não há download automático.
Parâmetros: temperatura 0, seed 125, contexto 4096 e 2048 tokens máximos de geração.
O CLI aceita `--timeout-seconds` de 1 a 900, padrão 300, registrado por tentativa.
O limite original de 120 segundos foi insuficiente no primeiro teste real em CPU;
o timeout da fundação genérica permanece inalterado.
Seed fixa não garante determinismo entre hardware e versões.

Cada tentativa tem diretório UUID, `attempt.json` e, somente se validado,
`output.json`. Registra modo, modelo solicitado/reportado, parâmetros, horário,
hashes de contexto/prompt/schemas/código/regras, duração e resultado.
Falhas JSON/contrato/evidência/runtime são explícitas e geram exit code não zero.
Nunca há substituição silenciosa pelo baseline. Respostas inválidas ficam
registradas apenas por hash, sem texto potencialmente sensível.

`python_peak_memory_bytes` mede alocações do cliente Python, **não** RAM/VRAM do
modelo. O executor `evaluate_ai_quality.py` registra a identidade do modelo,
versão do runtime, RSS amostrado dos processos, média/P95, repetições, consistência,
schema válido, leitura, classificação e referências estruturadas. Fidelidade
de texto livre não deve ser confundida com validade de IDs.

## Validação

```bash
cd backend
.venv/bin/ruff check . ../scripts
.venv/bin/pytest -q -m "not integration"
cd ..
node web/scripts/validate_ai_poc_schemas.mjs
git diff --check
```

Testes com runtime simulado verificam contratos, isolamento e registro de falhas.
**Não são inferência real nem demonstram as metas de qualidade da issue.**
Resultados reais e limitações são registrados separadamente no relatório.

## Rodada de desenvolvimento — 2026-10-05

Ollama 0.35.1, modelo `qwen2.5:3b-instruct-q4_K_M`, digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`,
CPU, contexto 4096, uma requisição por vez e recursos de nuvem desativados.
O modelo usa Qwen Research License; esta entrega não autoriza uso produtivo.

O teste inicial QD2-D02 excedeu 120 s. Repetido com timeout de 300 s, produziu JSON
válido em 125,141 s e pico residente observado de aproximadamente 2,09 GiB no
processo do modelo. Ainda assim, classificou `required_field` como `layout`,
absteve-se indevidamente e repetiu o fato no campo de hipótese. Portanto, sucesso
do executor não equivale a acerto semântico.

O prompt `quality-v2.1.txt` esclarece a taxonomia, o significado de completed e
a diferença entre fato e hipótese. A versão anterior foi preservada, assim como
suas evidências em `/tmp/synergia-quality-v2-smoke*`. Nenhum caso reservado à
avaliação foi usado para ajustar esse prompt. Naquela rodada, o gold ainda era
candidato; posteriormente recebeu a confirmação humana registrada acima.

O [roteiro de revisão do gabarito](ai-quality-gold-review.md) reúne os casos e
critérios para confirmação humana antes da homologação da avaliação.

### Resultado do prompt v2.1 em desenvolvimento

Uma execução por CSV de desenvolvimento, sem utilizar os casos de avaliação:

| Caso | Duração | Resultado observado |
|---|---:|---|
| D01 | 155,663 s | Evidência inventada; rejeitado pelo validador |
| D02 | 58,820 s | Categoria completeness e estado completed corretos |
| D03 | 60,971 s | Categoria format correta, mas completed com pergunta pendente |
| D04 | 58,945 s | Categoria unknown correta, mas faltou insufficient_evidence |

Artefatos originais em `/tmp/synergia-quality-v21-development`, identificados por
UUID e hashes. O baseline concluiu os quatro casos. O modelo concluiu três
contratos mecânicos na versão então executada, mas isso **não** significa três
respostas semanticamente aprovadas. Hipóteses continuam genéricas e, por vezes,
apenas repetem o fato observado.

Após inspecionar D03/D04, o validador passou a rejeitar completed com perguntas
pendentes e a exigir abstenção para códigos sem mapeamento, além de referência
ausente. Não corrige respostas nem substitui pelo baseline. Os registros antigos
não foram reescritos; novas rodadas devem registrar o novo hash da implementação.
Esta amostra de desenvolvimento não é uma estimativa de qualidade final nem
substitui as três repetições por caso da avaliação reservada.
