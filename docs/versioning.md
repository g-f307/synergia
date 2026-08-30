# Convenções de versionamento

O repositório usa GitHub Flow, releases com versionamento semântico e artefatos
de domínio versionados junto ao código. A versão permite responder qual
contrato, schema e conjunto de regras produziram um resultado.

## Aplicação e releases

Tags de release seguem `vMAJOR.MINOR.PATCH`:

- `MAJOR`: mudança incompatível para usuários, integrações ou operação;
- `MINOR`: capacidade nova compatível;
- `PATCH`: correção compatível, documentação ou manutenção sem quebra.

Uma release só pode partir da `main`, com CI verde, documentação coerente e sem
issue bloqueadora conhecida. O título e as notas relacionam issues e PRs. Tags
publicadas não são movidas ou recriadas; uma correção gera nova versão.

Antes da primeira release estável, a fundação pode permanecer em `0.x.y`, mas
toda incompatibilidade ainda deve ser destacada no PR e nas notas.

## API e OpenAPI

A versão da API fica em `backend/app/main.py` e aparece em `info.version` de
`/openapi.json`. A documentação humana complementar fica em
[api-contracts.md](api-contracts.md).

- endpoint, campo ou resposta compatível adicionada: `MINOR`;
- correção que mantém o contrato: `PATCH`;
- remoção, renomeação, mudança de tipo/semântica ou novo requisito obrigatório:
  `MAJOR` e plano de migração/depreciação;
- mudança de contrato exige atualização simultânea de modelos, OpenAPI,
  documentação e testes.

Enquanto só houver uma versão pública, as rotas permanecem sem prefixo. Antes
de introduzir quebra, deve-se decidir entre convivência de rotas (`/v1`, `/v2`)
ou janela explícita de migração. Não se altera silenciosamente o significado de
um campo existente.

## Migrations PostgreSQL

Arquivos seguem `NNNN_descricao_em_snake_case.sql` e são executados em ordem
lexicográfica. O próximo arquivo usa um número maior que o último publicado.

> Uma migration presente na `main` ou em release publicada é imutável. Nunca a
> reescreva para corrigir um ambiente existente; crie uma nova migration.

Cada migration deve:

- partir corretamente do schema produzido pelas anteriores;
- ser válida em PostgreSQL 16;
- preservar dados ou documentar claramente a transformação necessária;
- atualizar modelo, testes de persistência e documentação afetada;
- ser aplicada pela CI desde um banco vazio.

Correções de dados não podem embutir dados reais ou sensíveis. Rollback, quando
necessário, é uma decisão operacional explícita; não se presume que todo DDL
seja reversível automaticamente.

## Catálogo de regras de negócio

`backend/app/model/business_rules.json` possui campo `version` em SemVer. O
evento de classificação registra essa versão.

- ajuste textual sem mudar resultado: `PATCH`;
- nova regra ou parâmetro compatível: `MINOR`;
- mudança que reclassifica entradas existentes ou remove regra: `MAJOR`.

Toda mudança inclui cenários em `rules_scenarios.json`, testes e atualização de
[business-rules.md](business-rules.md). O catálogo não deve ser alterado para
“corrigir” resultados históricos; eles permanecem ligados à versão aplicada.

## Regras de normalização

`backend/app/model/normalization_rules.json` é declarativo e validado no
carregamento. Na fundação atual, sua versão reproduzível é a tag da aplicação ou
o SHA do commit. Quando for necessário manter catálogos simultâneos, deve-se
adicionar um campo SemVer e persistir essa versão no resultado antes de criar a
segunda variante.

- novo alias equivalente: mudança compatível;
- mudança de representação canônica ou interpretação de estado/flag: mudança
  incompatível;
- qualquer alteração acompanha `normalization_example.csv`, testes e
  [normalization.md](normalization.md).

O arquivo original e o valor original do campo nunca são reescritos.

## Massas sintéticas

Massas em `data/synthetic/` são artefatos de teste, não dados reais. Uma mudança
compatível pode ajustar o arquivo existente junto com seu teste. Quando um
cenário antigo ainda for necessário ou a estrutura mudar de forma incompatível,
crie uma nova fixture com sufixo de versão ou cenário, em vez de apagar a
evidência anterior.

O README do diretório descreve finalidade, fonte simulada e resultado esperado.
JSON deve ser válido e CSV/XLSX deve manter cabeçalho não vazio; a CI verifica
os três formatos. Conjuntos gerados possuem `generator_version`,
`schema_version`, seed, configuração, contagens e hashes no `manifest.json`.
Uma alteração incompatível no algoritmo ou contrato incrementa a versão
correspondente. A tag/commit da aplicação identifica a versão exata das
fixtures mínimas; perfis maiores são regenerados sob demanda e não versionados.

## Protótipo navegável

O protótipo é versionado fora da `main`:

- branch publicada: `prototype-pages`;
- versões imutáveis: `prototype-vMAJOR.MINOR`;
- `MAJOR`: mudança de fluxo ou estrutura de navegação;
- `MINOR`: refinamento visual compatível.

Uma nova versão exige issue/PR próprios na branch de publicação, nova tag e
validação do Pages. A aplicação Angular não herda automaticamente a versão do
protótipo.

## Registro mínimo de uma mudança versionada

O PR deve informar versão anterior e nova, compatibilidade, migrations ou
contratos afetados, testes executados e instruções de migração. A
[matriz de rastreabilidade](traceability-matrix.md) é atualizada quando uma
capacidade ou regra muda.
