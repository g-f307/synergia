# Avaliação offline da explicação assistida — PoC #179

O uso principal agora ocorre na [área Agente de qualidade do SYNERGIA](ai-quality-ui.md),
com geração real pelo backend. Este documento descreve apenas a avaliação
offline e seus contratos sintéticos; não é o roteiro de uso da interface.
Não há decisão ou alteração automática de dados operacionais.

## Fluxo e contratos

1. O leitor e o validador puros existentes produzem as ocorrências dos arquivos
   sintéticos da #148. Os quatro casos adversariais adicionais são fixtures de
   **saída do pipeline**, incluindo serial ausente e severidades diferentes.
2. `project()` agrupa por código e preserva todas as referências, severidades,
   motivos e localizações. Rejeita referência duplicada, perda de ocorrência,
   alteração de fato e diagnóstico repetido. Não recebe os rótulos esperados
   como instruções de inferência.
3. Cada grupo contém `field`, `column`, `row`, `sheet`, `known_value` e
   `unknown_value`. Uma posição tem estado `known` ou `not_provided`. Um valor
   tem estado `observed` ou `unavailable`; o desconhecimento é `missing`,
   `not_exposed` ou `not_applicable`. Nenhum `null` ambíguo entra no envelope.
   `column` preserva o localizador do pipeline, que pode ser letra ou nome
   semântico de campo; ele jamais é usado como valor da célula.
4. O runtime recebe um único grupo e redige somente `explanation` e
   `human_checks`. O envelope nunca integra o schema da resposta. Uma chamada
   por grupo impede o modelo de duplicar, omitir ou reagrupar diagnósticos.
5. O schema limita tamanho, propriedades e quantidade de verificações. A
   política semântica aceita apenas frases completas autorizadas para o grupo,
   incluindo abstenção causal obrigatória e abstenção sobre valor ausente.
   Validar apenas palavras isoladas permitiria recombiná-las em afirmações
   falsas; por isso a política compara frases completas.
6. JSON inválido, chaves repetidas, prosa fora da política, timeout ou runtime
   indisponível acionam o baseline. Há uma única tentativa, sem retry.
   Retêm-se código de recusa e SHA-256 da resposta, nunca o texto recusado.
   Erros inesperados de implementação continuam visíveis, sem captura genérica.

Contratos versionados:

- [Envelope factual v1](schemas/ai-quality-explanation-v1-input.schema.json).
- [Saída textual v1](schemas/ai-quality-explanation-v1-output.schema.json).
- [Prompt](../scripts/ai_poc_prompts/quality-explanation-v1.txt).
- [Configuração](../scripts/ai_quality_explanation_config.json).
- [Adversariais](../data/synthetic/ai-quality-explanation-v1/adversarial.json).

O vocabulário restrito é uma limitação deliberada: o modelo escolhe entre
formulações e verificações já consideradas seguras pelo código. A PoC não
demonstra explicação livre, capacidade de descobrir causas ou vantagem sobre
templates. Nenhuma causa é comprovada neste corpus; todas as explicações dizem
explicitamente que ela não pode ser determinada.

## Execução reproduzível

Use Python 3.11+ e as dependências de desenvolvimento já existentes:

```bash
python -m pip install -r backend/requirements-dev.txt
python scripts/run_ai_quality_explanation.py --freeze artifacts/quality-explanation-freeze.json
python scripts/run_ai_quality_explanation.py \
  --execute artifacts/quality-explanation-freeze.json \
  --output-dir artifacts/quality-explanation-run
python scripts/render_ai_quality_explanation.py \
  artifacts/quality-explanation-run artifacts/quality-explanation-demo.html
```

Abra o HTML gerado diretamente no navegador. Não há servidor, porta, API,
`fetch`, ferramenta de mutação ou acesso ao produto. A política CSP bloqueia
conexões. Todo texto é inserido por `textContent`; dados JSON embutidos têm
caracteres HTML escapados. O tema usa os tokens compartilhados do SYNERGIA,
com layout responsivo e controles de teclado. Por ser um artefato experimental
offline, não utiliza shell autenticado, rotas ou catálogos Angular.

O demonstrador apresenta os fatos e evidências à esquerda, texto e verificações
à direita, origem de cada informação e estado de validação. O baseline pode
ser expandido para comparação. Permite selecionar caso e repetição registrada.
Os controles de recusa, timeout e indisponibilidade são **simulações sintéticas
identificadas**, separadas dos resultados medidos do modelo. A apresentação
reproduz o resultado registrado, sem esperar nova inferência.

O runtime precisa estar previamente disponível em loopback. A ferramenta não
inicia serviços nem baixa modelos. O nome instalado `qwen3:4b-instruct` deve
corresponder exatamente ao digest do `qwen3:4b-instruct-2507-q4_K_M` avaliado
na #148. O runtime também é fixado em Ollama 0.40.12. Modelo ou versão
divergente resulta em fallback, registrado como indisponibilidade e explicado
nos metadados da rodada. Não altera os pesos ou parâmetros para buscar
resultados favoráveis.

O congelamento incorpora configuração, prompt, schemas, código, arquivos de
regressão, versões dos pacotes e envelopes factuais. A execução recalcula o
snapshot antes da primeira geração. Mudanças recusam a rodada. Diretórios de
execução e arquivos de congelamento existentes não são sobrescritos.
Cada tentativa é gravada separadamente antes da próxima, preservando falhas.
O resultado final contém todos os casos, incluindo os sem ocorrência e sem
chamada ao modelo. Uma falha de recurso suspende as gerações seguintes e usa
fallback; os casos planejados continuam no denominador.

## Avaliação e limites

São 24 arquivos CSV/XLSX dos 12 cenários da #148 e quatro fixtures adversariais,
com três repetições: 84 tentativas por braço. Não são uma nova amostra
reservada; os pares CSV/XLSX não são sujeitos independentes. O baseline e o
candidato recebem exatamente os mesmos envelopes. Os seis casos históricos
de duplicidade correspondem ao cenário `QD3-E06`, dois formatos vezes três
repetições. O adversarial `QE-A02` acrescenta duas ocorrências do mesmo código
com severidades diferentes para conferir preservação integral.

Aceitação é contada por grupo efetivamente gerado. Casos vazios são registrados
como tais, sem inflar o denominador de respostas aceitas. Cobertura e
duplicidade são calculadas comparando as referências e códigos apresentados
com os envelopes planejados. Afirmações aceitas fora da política são contadas
por grupo; essa medida não é uma anotação humana independente por afirmação.
Recusas ficam identificadas por código, com hash e fallback.

Latência por caso soma todas as chamadas dos seus grupos, incluindo custo de
validação e carga do modelo quando ocorrer. Não houve aquecimento excluído
neste protocolo curto. O pico Python mede alocações de cada explicação, não
RSS do modelo. RSS somado e VRAM total são amostrados durante a rodada com a
telemetria existente; VRAM inclui desktop e RSS pode contar páginas
compartilhadas. Métrica indisponível permanece `null` e tem motivo explícito.
Os limites de RAM, swap, disco e margem de GPU são os da #148.

Consulte o [relatório da execução](ai-quality-explanation-report.md) para os
resultados completos, negativos e a decisão. A ausência de afirmações fora
das frases permitidas comprova o funcionamento dessa restrição; não comprova
qualidade produtiva, compreensão do modelo ou facilidade de uso.

## Referências para gravação

A funcionalidade para demonstração fica dentro do SYNERGIA. Consulte
[a tela integrada e suas capturas](ai-quality-ui.md) para preparar a gravação.
Não há vídeo como entregável desta implementação.
