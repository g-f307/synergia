# Contribuindo com o SYNERGIA

O projeto usa GitHub Flow: issue, branch, commits lógicos, testes, pull request,
CI, revisão, merge por squash e limpeza. A `main` deve permanecer estável.

## Antes de desenvolver

Leia a [arquitetura vigente](docs/architecture.md), as
[convenções de versionamento](docs/versioning.md) e a
[matriz de rastreabilidade](docs/traceability-matrix.md). Para preparar a
máquina, siga [local-environment.md](docs/local-environment.md).

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
- resumo objetivo do que mudou;
- comandos realmente executados e seus resultados;
- limitações e passos manuais;
- impacto em API, dados, migrations, regras e documentação;
- atualização da matriz quando uma capacidade ou estado mudar;
- checklist de ausência de segredos, dados reais, caches e temporários.

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
- PR revisado e conversas bloqueantes resolvidas;
- critérios de aceite comprovados no PR;
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
