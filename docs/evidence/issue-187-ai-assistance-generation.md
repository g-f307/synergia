# Geração assistiva — issue 187

Base: contrato e contexto 1.0.0 de #185 e #186. O gerador é interno; não há rota,
persistência ou alteração no frontend. O validador aplica regras de linguagem e
uma gramática factual conservadora, compara contagens e valida de uma a três
referências por achado contra o contexto autorizado. Um filtro lexical sozinho não
comprova fundamentação; por isso o serviço rejeita redações fora dessa gramática.
O fallback é construído em módulo separado, sem depender do prompt ou da resposta.
A resposta bruta não faz parte do resultado ou dos logs.

## Manifesto

- Runtime de referência: Ollama 0.40.15; modelo e digest vêm da configuração de #185.
- Inferência: até uma requisição `/api/chat`, sem ferramentas, temperatura 0,
  seed 42, `think=false`, 512 tokens, resposta e contexto limitados a 8192 bytes.
- Prazo: processo isolado e prazo de 30 segundos; no encerramento o processo cliente
  é terminado e o lock local é liberado. A parada da computação no servidor depende
  do runtime respeitar o cancelamento da conexão.
- A inferência identifica o manifesto local diretamente por `sha256-<digest>`,
  suportado pelo runtime fixado, e não pela tag mutável. O nome configurado também
  é conferido antes e depois, e o digest carregado é conferido após a chamada.
  A proteção depende de um runtime confiável e de seu armazenamento verificado.
  Referência: https://github.com/ollama/ollama/blob/v0.40.15/manifest/paths.go
- O runtime deve ser isolado de rede e protegido contra alteração de modelos por
  outros processos. O adaptador não fornece ferramentas ou URLs ao modelo; não pode
  impor isolamento de rede ao processo externo do runtime.
- `system.txt` SHA-256: `a9d2013df304a6851e6835c4c1fb15b8d0ed8ccec18340293afe2947558e20bd`.
- `template.txt` SHA-256: `c5bf4cf4423aa0617f934b77928399af6abaf47481f3e22bea5be17c6f59037e`.
- `output.schema.json` SHA-256 do arquivo: `161cd39811ca63ff76e4a431221e38282f25ea8dd2259275cdc8a9531152ccac`.
- SHA-256 do schema JSON canônico: `5b48b0e799ab28ea45ffa0e3b078ce766b8ae65ab7ac94f39a5a741e22916dd9`.
- O hash de prompt inclui mensagem de sistema e prompt montado; o contexto é validado
  e seu hash conferido antes da chamada. O hash da resposta bruta é metadado interno.

## Exemplos sanitizados

Com o fixture completo, um resumo aceito é `A execução registra 1 erros, 0 avisos e
1 pendências.` e um achado permitido contém título `Divergência registrada`, texto
`Há um registro disponível para conferência.` e a referência existente do fixture.
O texto `<b>falha</b>` no resumo é rejeitado integralmente, com origem
`deterministic` e código `invalid_schema`; a resposta devolvida é produzida a partir
das contagens e referências autorizadas, sem copiar a saída rejeitada.

## Validação

Em Python 3.12, os testes direcionados usam provider fake e servidor HTTP local
simulado. Cobrem saída aceita, JSON e UTF-8 inválidos, duplicação de chave e referência,
campos extras, limites, referência ausente, linguagem proibida, campos de injeção
excluídos pelo contrato do contexto, indisponibilidade, modelo divergente,
redirecionamento, resposta grande, concorrência, timeout, cancelamento, liberação
do lock, zero chamadas quando insuficiente e uma chamada no caminho válido.

Antes das correções da revisão, foram feitas quatro tentativas reais com o fixture completo, Ollama 0.40.15 e o
modelo local `qwen3.5:4b`, digest
`sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`.
A primeira terminou em `runtime_timeout` após 30037 ms, antes do ajuste de margem.
A segunda terminou em `runtime_response_too_large` após 28807 ms. Depois da troca
para `/api/chat`, mais duas tentativas terminaram em `runtime_timeout` em 29033 e
29036 ms. Em todos os casos a origem foi `deterministic` e não houve resposta bruta
exposta. Estas medições não demonstraram uma saída real aceita e não comprovam o
cancelamento do runtime. A validação do caminho real continua pendente de ambiente
capaz de executar o modelo dentro do prazo.

Ainda antes das correções da revisão, duas chamadas adicionais usaram um contexto sintético reduzido com uma divergência,
sem pendências, classificações, evidências ou histórico no snapshot. Ambas foram
aceitas pelo validador. A última, após incluir a limitação de dados ausentes,
retornou `state=ready`, `origin=model`, em 14212 ms. Hashes: contexto
`841bd8fd503bd3c5adebaaef6cbd8c254427b230ecfac4438c90026ac1ed6ee3`, prompt
`c931188d61eb263278a07cd4815f49eafc8099c266ecf3752b31219e2b6ce0ef` e resposta
`a478f4aabe8a6ff00b308b55a2fad56bd2a839a669bdd48db2c0d33902df67ac`.
A primeira levou 18955 ms antes desse ajuste. A saída bruta não foi registrada.
O contexto completo continua sujeito ao fallback por timeout nesta máquina.


Após as correções da revisão, o contexto reduzido foi novamente enviado ao modelo
local. A resposta foi recusada por `ungrounded_limitations` em 11945 ms, com fallback
determinístico. Hashes: prompt
`0bba3e98f5171a1705a603e28275c662af26823ed3a0b2cee50f2abf3c8318d7`, resposta
`6358b6a35eee40ab4a8e1bf92a0cca1753a7f5e260199c37fb954d43ed430041`.
Essa execução valida a rejeição controlada, mas não demonstra uma saída real aceita
com o prompt revisado. Nenhum texto bruto foi registrado.
Uma tentativa adicional de esclarecer as limitações no prompt também foi recusada
(`ungrounded_limitations`, 20639 ms, hash de resposta idêntico). A alteração
experimental no prompt foi revertida; nenhuma resposta bruta foi registrada.

## Revisão do PR #218: schema e validação finais

O schema de entrada ao runtime agora restringe `limitations` às limitações
constatadas no contexto, sem alterar o schema versionado base. A gramática e a
validação posterior continuam recusando fatos não fundamentados. Os hashes do prompt
incluem esse schema específico do contexto.

Com Ollama 0.40.15 e o modelo `qwen3.5:4b` fixado pelo digest acima, o script
`scripts/validate_ai_assistance_187.py` gerou `ready`, `origin=model` em 10622 ms.
O contexto e o resultado validados estão em
`docs/evidence/issue-187-real-model-sanitized.json`, SHA-256
`80f9fa4a3b171726fd2aeefd4e4bad8080ea3336e97eacb3d933a7e194ec36a6`.
A resposta bruta não é armazenada. Este resultado foi obtido após as alterações
do schema por contexto e substitui as tentativas anteriores como evidência do
fluxo atual. O fixture completo não foi reexecutado nesta revisão; o timeout
anterior permanece um limite conhecido desta máquina.

Reprodução a partir da raiz, com o runtime e digest fixados instalados:

```bash
SYNERGIA_AI_ASSISTANCE_ENABLED=true \
SYNERGIA_AI_ASSISTANCE_ENDPOINT=http://127.0.0.1:11434 \
SYNERGIA_AI_ASSISTANCE_MODEL=qwen3.5:4b \
SYNERGIA_AI_ASSISTANCE_DIGEST=sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04 \
PYTHONPATH=backend python scripts/validate_ai_assistance_187.py
```

Falhas inesperadas geram evento estruturado com tipo e localizações de frames;
texto da exceção, dados locais, prompt e resposta não são registrados. O fallback
continua sanitizado e o teste direcionado verifica o evento serializado.
