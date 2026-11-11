# Revisão do guia operacional — issue #167 / PR #174

Data da revisão original: 06/11/2026. Escopo de aceite alinhado em 10/11/2026
à issue #167 e à revisão do PR #174. A entrega documental foi atualizada para
a automação da #166 já presente na `main`, sem alteração no runtime da aplicação.

## Base e escopo

A branch do PR estava baseada em uma revisão anterior à automação. Foi
integrada a `main` `92263746f8a4559f5744563f1742fccd969dbf32`, resolvendo o
conflito do README com preservação dos links de implantação e auditoria.
O commit de atualização da base é `c9452eb80154c7f6ac288ebdf14d6be9327d3bcb`; os commits finais ficam no PR.

Foram revisados os sete guias de `docs/deployment/`, os pontos de entrada e
a matriz de rastreabilidade. A revisão substituiu a instalação/atualização
manual normal pelos comandos reais `diagnose`, `precheck`, `apply`, `verify`,
`rollback` e `reconcile`. Os procedimentos especializados de backup,
restauração e adoção de banco legado permanecem explícitos e separados.

## Correções principais

- Retirada da afirmação de que `scripts/deploy.py` ainda não existe.
- Instalação nova usa `apply --initialize`; atualização não usa initialize.
- Operações `running`/`uncertain`, primeira tentativa SQL e ledger parcial têm
  diagnóstico e próxima ação definidos, sem repetição manual de migrations.
- Rollback da aplicação não é apresentado como restauração de banco ou
  arquivos. Backup inclui o bundle de domínio e o ledger público no mesmo
  ponto consistente, pois o CLI de domínio não inclui esse ledger.
- O guia explicita que a CLI usa somente o Compose base, ignora variáveis de
  aplicação do shell e não admite overlays arbitrários.
- O exercício de configuração altera uma cópia privada, em vez de depender
  de variável de shell ignorada pela automação. O exemplo foi executado somente
  sobre arquivo sintético temporário e validado pelo código real do perfil.
- A referência cobre as quatro novas variáveis de configuração/cota da IA de
  qualidade, sem declarar que o Compose inclui o runtime do modelo.
- O inventário de migrations é comparado com a revisão, sem fixar um número
  que fica desatualizado com migrations novas.
- A seção LG registra a rodada relatada em 06/11/2026: configuração local
  aprovada, GET com timeout, JSON inacessível no navegador e TCP falso. Não
  houve POST no roteiro relatado; causa específica a confirmar com TI. O
  utilitário e o relato da #171 continuam referenciados pelo PR #180, sem
  presumir que já foram integrados à `main` ou que a #170 foi implementada.

## Padrão de escrita e testes documentais

Os 36 blocos de comandos possuem: onde executar, pré-condições, entradas,
efeito, resultado esperado, interpretação de falhas, próxima ação e evidência
permitida. São usados somente placeholders e destinos locais/reservados.

A suíte documental passou de 39 para 42 verificações. Além de links, âncoras,
variáveis, scripts, opções, sintaxe Bash e ausência de padrões de segredo,
ela agora verifica as ações e argumentos obrigatórios contra o parser real
de `deploy.py`, executa o snippet de falha em uma cópia sintética e confirma
o estado atual da automação e dos aceites externos. Os blocos de implantação
não são executados pelos testes documentais.

## Ajuste de escopo e validação em 10/11/2026

Removida a exigência de aceite independente do README, checklist, estado de
entrega deste relatório e matriz de rastreabilidade. O exercício foi mantido
como recomendação operacional; revisão por pares é opcional. Os testes deixaram
de exigir o estado pendente, preservando as verificações das dependências LG.

Nesta rodada, em Python 3.12.15: 42 testes de `test_deployment_docs.py` aprovados;
`ruff check` e `ruff format --check` desse arquivo aprovados com a configuração
do backend; compilação do teste e `git diff --check` aprovados. Não houve nova
execução de deploy ou integração nesta rodada de ajuste documental.

## Validações locais da revisão original

Dependências do backend foram instaladas em ambientes temporários fora do
checkout, sem nova dependência no projeto. As verificações usaram WSL/Fedora,
Python 3.12.15 e, na rodada exploratória inicial, Python 3.14.8.

| Comando ou verificação | Resultado |
| --- | --- |
| `pytest -q backend/tests/test_deployment_docs.py backend/tests/test_container_entrypoint.py backend/tests/test_compose_secret_isolation.py backend/tests/test_deploy.py backend/tests/test_deploy_flow.py backend/tests/test_deploy_recovery.py backend/tests/test_deploy_validation.py` | 207 aprovados na rodada direcionada em Python 3.14; sem implantação real |
| `ruff check backend scripts` | Aprovado |
| `ruff format --check backend/tests/test_deployment_docs.py` | Aprovado |
| `python -m compileall -q backend/app scripts/deploy*.py scripts/validate_deploy.py backend/tests/test_deployment_docs.py` | Compilação aprovada no escopo equivalente executado com os módulos explícitos |
| `python scripts/security_release.py validate` | Aprovado |
| `docker compose --env-file .env.example config --quiet` | Aprovado; validação estática sem daemon |
| Validadores de acesso, jornadas, ameaças, Etapa 5, Etapa 6, HTTP e `security_matrix.py --check` | Aprovados |
| `python scripts/deploy.py --help` | Interface real conferida, sem operação de implantação |
| Suíte `pytest -q -m "not integration"`, Python 3.12 | 1.732 aprovados, 783 de integração não selecionados e 15 avisos de depreciação; execução em 73,35 s |
| `git diff --check` e revisão do staging | Conferidos antes de cada commit; nenhum arquivo protegido incluído |

### Diferença de ambiente observada

A suíte ampla inicial no Python 3.14 terminou com 1.729 aprovados, três falhas
e 783 testes de integração não selecionados. As falhas foram de reprodução
de bytes/hashes de XLSX: duas em `test_ingestion_corpus.py` e uma em
`test_total_decision_spec.py`. Os mesmos três testes falharam na `main` limpa,
no mesmo ambiente, e passaram no Python 3.12 usado pela CI. Isso demonstra
que não foram introduzidos pelas alterações documentais deste PR; não
determina isoladamente a causa de baixo nível da diferença de bytes.

Nenhum fixture, hash congelado, gerador ou teste foi alterado/desativado para
contornar essas falhas. O resultado amplo no ambiente alinhado à CI deve ser
lido separadamente da rodada em Python 3.14.

## Não executado e dependências externas

- Não houve nova implantação Docker real nesta estação: o cliente Compose
  está disponível, mas não existe daemon acessível no socket padrão.
- Não foram executados testes locais que exigem banco/containers reais, nem
  restore contra dados reais. A CI possui os próprios jobs de integração,
  containers e implantação; consultar os resultados do novo head do PR.
- A bateria sintética de 22 cenários da #166 é evidência histórica da
  automação, descrita em [deploy-validation-report.md](../deploy-validation-report.md),
  não uma nova execução operacional deste guia.
- Recomenda-se exercitar instalação, atualização e diagnóstico de falha simulada
  em ambiente de ensaio, pelo próprio operador ou em revisão por pares opcional,
  registrando evidência sanitizada. Essa recomendação não condiciona a conclusão
  da #167. Nenhum teste estático ou relato de acesso ao e-mail comprova uma
  implantação real.
- A conectividade e o contrato da API LG continuam dependências da #171; o
  provider HTTP da #170 não está implementado por este PR.

## Estado de entrega

Implementação documental e testes concluídos no escopo da issue #167 e
disponíveis para revisão. A descrição do PR usa `Closes #167`, em conformidade
com os critérios atuais da issue, que não exigem um executor independente.
O encerramento da entrega documental não constitui autorização de produção
nem comprovação de execução dos passos registrados como não executados.

Recomendação operacional: usar o
[checklist pós-implantação](../deployment/post-deployment-checklist.md)
a cada implantação, anexar somente resultados sanitizados e registrar os
aceites reais do ambiente. Revisão por pares é opcional e não impede o
encerramento da #167.
