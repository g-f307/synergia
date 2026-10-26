# Contribuindo com o SYNERGIA

O projeto usa GitHub Flow: issue, branch, commits lógicos, testes, pull request,
CI, revisão, merge por squash e limpeza. A `main` deve permanecer estável.

## Antes de desenvolver

Leia a [arquitetura vigente](docs/architecture.md), as
[convenções de versionamento](docs/versioning.md) e a
[matriz de rastreabilidade](docs/traceability-matrix.md). Para preparar a
máquina, siga [local-environment.md](docs/local-environment.md).

Mudanças no frontend devem seguir obrigatoriamente a
[norma de implementação visual](docs/frontend-implementation-standard.md), o
[design system](docs/web-design-system.md) e os contratos de
[internacionalização e acessibilidade](docs/web-internationalization-accessibility.md).
Uma exceção visual precisa ser justificada na issue e no PR e aprovada na
revisão; não deve surgir apenas como variação local de uma tela.

Não inclua credenciais, `.env`, dados pessoais ou dados reais. Use somente as
massas controladas de `data/synthetic/` em testes e evidências.

## Definition of Ready

Uma issue está pronta para desenvolvimento somente quando possui:

- contexto e problema compreensíveis;
- objetivo expresso como resultado verificável;
- escopo e itens fora do escopo;
- dependências técnicas e de outras issues identificadas;
- critérios de aceite observáveis;
- contratos de entrada/saída ou decisões arquiteturais necessários;
- massa de teste sintética disponível ou plano explícito para criá-la;
- cenários de sucesso, erro e regressão esperados;
- riscos, dúvidas e decisões pendentes de negócio registrados;
- responsável e prioridade definidos quando aplicável.

Se uma dúvida puder mudar contrato, regra de negócio, segurança, persistência ou
escopo, a issue não está pronta até a decisão ser registrada. Descobertas
menores podem ser documentadas durante o desenvolvimento sem ampliar o escopo.

## Branch e commits

Atualize a base e crie uma branch com o número da issue:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune origin
git switch -c <tipo>/<numero>-<descricao-curta>
```

Tipos usuais: `feature`, `fix`, `docs`, `ci`, `test`, `chore` e `hotfix`.
Commits seguem Conventional Commits e referenciam a issue:

```text
docs(architecture): registrar componentes vigentes refs #21
test(import): cobrir arquivo vazio refs #6
```

Cada commit representa uma responsabilidade lógica completa. Não misture
mudanças sem relação nem fragmente artificialmente um mesmo bloco.

## Validação e pull request

Execute as verificações proporcionais à mudança. A sequência completa está em
[local-environment.md](docs/local-environment.md). No mínimo, revise:

```bash
git diff --check
git status --short
```

O PR deve conter:

- `Closes #<issue>`;
- resumo executivo com o resultado e o valor da entrega;
- problema anterior e comportamento esperado depois da mudança;
- escopo organizado por responsabilidades lógicas, com fluxo ou tabela quando
  houver três ou mais etapas relacionadas;
- relação entre critérios de aceite, implementação e evidências;
- comandos realmente executados, quantidade de testes e resultados;
- roteiro reproduzível para validação manual, integrada ou operacional;
- limitações, itens fora do escopo, decisões pendentes e passos manuais;
- impacto em API, dados, migrations, segurança, observabilidade, frontend,
  compatibilidade e documentação;
- arquivos ou áreas principais e uma ordem sugerida de revisão quando o PR
  atravessar mais de uma responsabilidade;
- atualização da matriz quando uma capacidade ou estado mudar;
- checklist de ausência de segredos, dados reais, caches e temporários.

A profundidade da descrição deve ser proporcional à mudança:

| Impacto do PR | Descrição mínima esperada |
| --- | --- |
| baixo e localizado | resultado, arquivos afetados, validação e limitações |
| médio ou entre camadas | problema, fluxo, impactos, critérios de aceite, evidências e roteiro de revisão |
| alto, transversal ou de release | resumo executivo, arquitetura/fluxo, contratos, segurança, operação, rollout/rollback, matriz de critérios, testes, portões e decisões pendentes |

Quantidade de texto não substitui qualidade. A descrição deve permitir que o
revisor entenda o comportamento, encontre os pontos de risco e reproduza a
validação sem reconstruir o contexto pela leitura integral do diff. Não use
frases genéricas como “ajustes diversos”, não cole apenas a lista de commits e
não declare validações que não foram executadas.

Se uma seção do template não for aplicável, registre `Não se aplica` e uma
justificativa curta. Se o PR mudar de escopo durante a revisão, atualize a
descrição antes de solicitar nova análise.

Quando houver alteração visual, o PR também deve informar a tela equivalente
usada como referência e preencher o checklist da
[norma visual](docs/frontend-implementation-standard.md#checklist-de-aceite-do-pull-request).

Não faça merge antes da revisão e dos quatro jobs da CI aprovados. O autor não
deve ser o único aprovador quando houver outra pessoa disponível.

## Definition of Done

Uma issue pode ser encerrada quando todos os itens aplicáveis forem verdadeiros:

- implementação concluída sem itens de escopo omitidos;
- commits separados por responsabilidades lógicas;
- testes de sucesso, erro e regressão criados ou atualizados;
- lint, testes e builds relevantes aprovados;
- migrations novas adicionadas sem reescrever migrations publicadas;
- contratos OpenAPI, catálogos e documentação atualizados quando afetados;
- CI com os quatro jobs verdes;
- nenhuma credencial, segredo, dado real ou informação pessoal incluída;
- nenhum cache, ambiente virtual, relatório local ou temporário versionado;
- descrição do PR proporcional ao escopo, atualizada e suficiente para que o
  revisor compreenda os riscos e reproduza a validação;
- PR revisado e conversas bloqueantes resolvidas;
- critérios de aceite comprovados no PR;
- norma visual atendida ou desvios explicitamente justificados e aprovados,
  quando houver mudança no frontend;
- matriz de rastreabilidade atualizada;
- merge realizado por squash e issue encerrada pelo PR;
- ambiente local sincronizado e branches obsoletas limpas após o merge.

Item não aplicável deve ser marcado e justificado no PR, não simplesmente
ignorado.

## Alterações versionadas

- migrations publicadas são imutáveis; correções usam novo arquivo numerado;
- contratos incompatíveis exigem versão maior e plano de migração;
- regras de negócio atualizam a versão do catálogo e seus cenários;
- mudanças de normalização preservam o valor original e atualizam fixtures;
- protótipo é alterado apenas no fluxo próprio de `prototype-pages`.

Consulte [versioning.md](docs/versioning.md) antes de modificar qualquer um
desses artefatos.
