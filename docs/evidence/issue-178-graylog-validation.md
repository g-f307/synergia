# Issue #178 — implementação e validação local do coletor Graylog

Data: 2026-11-06. Base: `main` `92263746f8a4559f5744563f1742fccd969dbf32`.
Branch local: `feature/178-graylog-integration`, em worktree separado.
Os ensaios foram executados antes da organização dos commits. A base acima
antecede esta implementação; os commits do código testado estão registrados
no [resumo das verificações](issue-178-graylog-checks.json). Nenhum input ou
credencial da LG foi utilizado. Publicação e status da CI são informados no PR.

Este documento registra o primeiro ciclo, com testes de protocolo em receptor
HTTPS de teste. Após esclarecimento do usuário, o foco é avaliar funcionalidade
e utilidade em Graylog convencional, sem pressupor infraestrutura da LG.
O [laboratório real](../graylog-laboratorio.md) foi executado posteriormente,
com resultado registrado abaixo; implantação corporativa é uma possibilidade
futura e não condiciona essa avaliação.

## Resultado da revisão final

A integração está funcional no laboratório local com Graylog Open real.
A auditoria permanece transacional no PostgreSQL; o worker entrega somente
campos aprovados por HTTPS, sem colocar o Graylog no caminho das requisições.
O ensaio foi repetido com novos dados sintéticos e a pesquisa foi conferida
também na interface web, por Chrome headless no Windows.

| Pergunta de investigação | Resultado observado | Evidência visual |
| --- | --- | --- |
| A falha foi senha incorreta ou falta de permissão? | Três ações na mesma correlação: falha de login, login válido e autorização negada, em ordem temporal | [Acesso](issue-178-graylog-access.png) |
| Quais eventos pertencem à mesma importação rejeitada? | Transição de execução, arquivo rejeitado e falha da execução na mesma correlação | [Importação](issue-178-graylog-import.png) |
| O evento retido apareceu após recuperar o input? | Uma ocorrência pesquisável da falha de login produzida durante a interrupção | [Recuperação](issue-178-graylog-recovery.png) |
| Quais campos permitem rastrear o evento? | Detalhe com ambiente, origem, resultado, correlação e ID estável | [Campos](issue-178-graylog-fields.png) |
| O mesmo ID aparece mais de uma vez após repetir o worker? | Consulta por ID com uma ocorrência no ensaio | [ID estável](issue-178-graylog-event-id.png) |

Esses resultados demonstram a possibilidade de reconstruir ocorrências e
distinguir suas etapas sem consultar o conteúdo do arquivo ou credenciais.
Não foram medidos redução do tempo de investigação ou ganho de produtividade.

Evidências estruturadas: [ingestão e reconciliação](issue-178-graylog-lab-validation.json),
[pesquisas no navegador](issue-178-graylog-browser-validation.json) e
[comandos do worker](issue-178-graylog-cli-validation.json).
Os comandos `check`, `status` e `run --allow-network` foram executados no banco
do ensaio: 12 aceitos, nenhum retido e zero processados na repetição.

As cinco capturas são da interface real do Graylog, em pesquisas autenticadas
com dados sintéticos. Não são mockups e não exibem senhas, tokens ou o arquivo
de configuração privado. O teste de repetição comprova o comportamento deste
ensaio; não é uma garantia de unicidade física em qualquer falha de rede.

### Verificações finais

| Comando/verificação | Resultado |
| --- | --- |
| `pytest -q -m "not integration" --tb=short` | 1.764 aprovados; 800 não selecionados; 15 avisos de depreciação |
| `pytest -q -m integration --tb=short`, em banco sintético novo | 800 aprovados; 1.764 não selecionados; cinco avisos de depreciação |
| `ruff check backend scripts`, `compileall`, configuração Compose | Aprovados |
| Validadores de acesso, jornadas, HTTP, matriz de segurança e observabilidade | Aprovados |
| `security_release.py validate` e `security_release.py secrets` | Aprovados; busca adicional pelas credenciais locais nos arquivos alterados sem correspondências |
| Build final do backend por Podman | Aprovado; imagem `fd04af84bb33`, fonte local sem commit e revision label `unknown` |
| Smoke da imagem sem rede | UID `10001`; init/check/run desabilitado aprovados |

[Resumo estruturado das verificações](issue-178-graylog-checks.json).
As duas seleções amplas são disjuntas; as rodadas focadas abaixo se sobrepõem
a elas e não devem ser somadas. A primeira tentativa da rodada final de
integração teve 736 aprovados e 64 erros de preparação porque alguns fixtures
usam `PGHOST`/`PGPORT`, não apenas `DATABASE_URL`. O ambiente foi corrigido e a
seleção inteira foi repetida em banco novo, sem desativar testes ou mudar suas
expectativas para contornar o erro.

Na primeira CI do PR #182, o lint identificou nove linhas longas em scripts:
a execução local anterior, feita na raiz, não lhes aplicava a configuração de
`backend/pyproject.toml`. As linhas foram divididas sem alterar o comportamento.
O comando exato do pipeline, `cd backend && ruff check . ../scripts`, passou,
assim como 41 testes focados de laboratório e fluxo de implantação.
O resultado remoto final deve ser consultado nos checks do PR.

## Resultado e arquitetura

Implementado cliente GELF 1.1 HTTPS, fila PostgreSQL, checkpoint transacional
por origem, histórico append-only de tentativas/decisões, janelas históricas
retomáveis, reconciliação individual, métricas persistidas e perfil opt-in de
container. Sem nova dependência de runtime.

Treze fontes do inventário geram snapshots canônicos na mesma transação do
evento. Inserts tardios não dependem de avançar um relógio de polling. Joins
de captura usam chaves primárias, sem varrer a view consolidada por ID
concatenado a cada insert. A sanitização SQL remove valores aninhados ou fora
dos tipos aprovados; o sanitizador da #169 é reaplicado antes do GELF.

O worker registra intenção antes do POST, mantém exclusão mútua por lock de
sessão PostgreSQL e não abre transação durante a chamada de rede. `202` e
confirmação pesquisável são estados/evidências diferentes. Falha ambígua ou
interrupção mantém o evento para decisão, sem retry cego. Recusas com garantia
de não aceitação podem usar backoff/jitter, conforme contrato privado aprovado.
Não há retry infinito, exclusão silenciosa de esgotados ou reenvio de aceitos.

O ID inclui origem, identificador nativo e instante UTC normalizado do evento,
evitando confundir uma ocorrência futura com sequência numérica reutilizada.
A versão da aplicação no GELF identifica a release do coletor; a versão original
do emissor histórico permanece `unknown`, sem inferência retrospectiva.

Foi adicionada trilha mínima para pedidos/resultados da geração LLM existente,
incluindo fallback, duração, modelo/digest e executor. Tokens não são inventados;
prompts, respostas, hashes de respostas e fatos do demonstrador não são copiados.
RPA Smart Office e ferramentas autônomas LLM continuam `not_implemented`.
Negações do limitador possuem projeção mínima, sem seus identificadores HMAC.

## Validações executadas

Ambiente: WSL Fedora, Python 3.12.15, PostgreSQL 16 em container Podman com acesso
restrito a loopback. Bancos sintéticos de teste, sem acesso a dados corporativos.
Os testes do coletor/migration runner criam bancos temporários próprios.

| Verificação | Resultado observado |
| --- | --- |
| `pytest -q -m "not integration"` em `backend` | 1.751 aprovados, 798 não selecionados; 15 avisos de depreciação existentes |
| `pytest -q -m integration -x --tb=short` em banco sintético novo | 798 aprovados, 1.751 não selecionados; cinco avisos de depreciação |
| Rodada focada final: `test_graylog.py`, `test_graylog_https.py`, `test_graylog_persistence.py`, `test_ai_quality_api.py`, `test_deploy_flow.py` | 133 aprovados após os ajustes finais; inclui casos acrescentados depois das rodadas amplas, não somar os totais como testes distintos |
| HTTPS real em loopback | Quatro casos aprovados: CA/nome válidos e cabeçalho, rejeição de CA/nome, redirect bloqueado e autenticação por certificado de cliente |
| `ruff check backend scripts` | Aprovado na revisão; reexecutar após qualquer alteração posterior |
| `compileall` da aplicação e scripts modificados | Aprovado |
| `security_release.py validate` | Aprovado |
| `docker compose --env-file .env.example config --quiet` | Aprovado, validação estática |
| Validadores de acesso, jornadas, HTTP, matriz de segurança, ameaças, etapas 5/6 e observabilidade de homologação | Aprovados; decisões de piloto/produção continuam não aprovadas |
| `validate_project_assets.py` em banco sintético vazio | 36 migrations e 178 arquivos sintéticos validados |
| Build do backend com Podman | Aprovado usando o Dockerfile do repositório, Python 3.14 Alpine |
| Smoke da imagem: CLI `process_graylog.py --help`, init/check/run desabilitado e usuário | Aprovados; execução não root `10001:10001`; smoke final com rede do container desabilitada |
| `git diff --check` | Aprovado na revisão; nenhum commit/staging necessário para os testes |

A rodada focada foi repetida após fortalecer sanitização do checkpoint,
backfill histórico, identidade temporal e contenção de erros na fronteira CLI.
Os testes HTTPS criam certificados temporários; não são um servidor Graylog.
OpenSSL foi preparado fora do checkout, sem adicionar dependência de produção.
Resultados das rodadas amplas e da rodada final são registrados separadamente.

### Falhas encontradas e correções

1. Testes de downgrade antigos removiam recursos da #169 antes da nova camada
   dependente. A sequência agora aplica o rollback `0036` primeiro, preservando
   filas, recibos e histórico; o inventário de objetos foi atualizado.
2. A adoção de baseline agora também recusa contrato parcial da #178, incluindo
   trigger desabilitado, histórico ausente e snapshot removido.
3. No host havia ferramentas PostgreSQL 18 para servidor 16; o primeiro restore
   falhou por configuração emitida pela versão mais nova. Os testes posteriores
   usaram os binários 16 do próprio container, através de wrappers temporários
   restritos aos bancos sintéticos desta tarefa. Nenhum downgrade ou adaptação
   da aplicação foi feito para contornar essa diferença de ambiente.
4. Com ferramentas compatíveis, apareceu uma diferença real de contagens:
   restore/verificação geram eventos de auditoria que também criam checkpoints.
   O verificador admite exatamente o delta desses eventos. Um checkpoint extra
   indevido continua sendo recusado por teste automatizado.
5. Repetir a suíte sobre um banco já usado causou colisão de versão de política
   e seleção de notificações residuais. A rodada ampla aprovada foi executada
   sobre banco novo; não foram alteradas políticas de negócio nem desativados
   testes para contornar esse resíduo.

## Avaliação funcional e eventual implantação

O escopo atual é experimentar o Graylog convencional. Foram preparados um
laboratório reproduzível, credenciais locais aleatórias e um roteiro de pesquisa
para avaliar sua utilidade. O ensaio preliminar das rotas reais, em PostgreSQL
isolado e sem substituições de autenticação, obteve `401`, `200`, `403` e `422`
nos cenários de senha incorreta, login válido, administração sem permissão e
importação vazia. Os respectivos eventos chegaram à fila transacional.

Na revisão anterior, `pytest -q -m "not integration"` obteve 1.760 aprovados
e 799 não selecionados. Isso inclui os testes de isolamento e privacidade do
laboratório; não equivale a uma execução do servidor Graylog. Na ocasião, o
download das imagens ainda estava pendente. A rodada real posterior está
registrada a seguir. Não há conclusão de ganho de produtividade a partir
desses testes automatizados.

### Rodada com Graylog Open real

Na repetição final de 2026-11-06, das 21:50:28 às 21:50:42 UTC,
`graylog_lab.py validate`
retornou `validated_real_graylog` com Graylog `7.2.2+94adc86`, MongoDB 7,
OpenSearch 2.19.6 e PostgreSQL 16 em Podman/WSL. A
[evidência sanitizada](issue-178-graylog-lab-validation.json) registra:

- 12 IDs distintos aceitos e encontrados na pesquisa do próprio Graylog,
  com igualdade entre os conjuntos da fila e do índice;
- três eventos correlacionados de acesso, três da importação recusada e um
  recuperado após interrupção, além dos eventos de identidade e notificação;
- respostas reais `401`, `200`, `403` e `422`; durante a interrupção, o login
  continuou retornando `401` e o evento ficou retido até reconciliação;
- credencial incorreta do input recusada com `401`;
- duas repetições do worker sem processamento/reenvio de eventos já aceitos.

O primeiro startup falhou porque o script fornecia `plugins.security.disabled`
diretamente e também por `DISABLE_SECURITY_PLUGIN`, cujo entrypoint repete a
opção. Foi removida a configuração redundante. Somente o container parado
do OpenSearch deste laboratório foi recriado, preservando o volume.

O ensaio também revelou que os eventos explícitos de autenticação não
persistiam a correlação HTTP já disponível no contexto. O repositório agora
grava esse UUID, sem copiar cabeçalhos ou credenciais e sem inventar correlação
para operações fora de requisição. Um teste de persistência verifica também
que a correlação não vaza para a chamada seguinte.

A espera de parada do input passou a consultar a API do Graylog: uma porta
publicada pelo Podman pode continuar aceitando conexão TCP com o input parado.
Quando o estado desaparece do registro do nó, sua configuração persistida é
conferida antes de considerar a parada concluída. `configure` agora informa
imediatamente quando uma dependência está parada.

Após as correções, 95 testes focados de autenticação, persistência, laboratório
e transporte Graylog passaram em banco sintético novo. Os 11 casos de isolamento
e estados do laboratório também passaram em sua rodada final; esses totais
se sobrepõem e não devem ser somados. As três pesquisas na interface foram
aprovadas separadamente, com contagens de três, três e uma mensagens.
A avaliação humana de usabilidade/produtividade, instalação Windows/Docker,
desempenho em produção e implantação corporativa não foram validados.

As informações de implantação abaixo são apenas planejamento futuro. Não
condicionam a avaliação local e não pressupõem adoção da ferramenta pela LG.

O [manual](../graylog.md) inclui solicitação à TI, clonagem, bundle/wheels para
Windows sem internet, arquivo privado, certificados, escopo, verificação local,
implantação controlada, envio, pesquisa, reconciliação, incidentes e rotação.
O perfil fica desabilitado por padrão. Aplicar a migration inicia a manutenção
dos checkpoints, mesmo antes de habilitar envios; monitorar armazenamento.

Caso uma implantação corporativa venha a ser decidida, será necessário definir
com os responsáveis pelo ambiente:

- versão/input aprovado, rota, TLS/autenticação e códigos/limites;
- organizações, eventos globais e identificadores autorizados;
- credencial técnica de banco com mínimo privilégio e homologação isolada;
- streams, retenção, responsáveis, permissões e revisão de acesso;
- recebimento e pesquisa de eventos sintéticos de login/negação;
- exercício corporativo de indisponibilidade, recuperação e reconciliação;
- confirmação da política de deduplicação e de eventuais recusas retentáveis.

GELF HTTP e um ID estável não garantem unicidade física nem indexação por si
sós. Não há evidência corporativa de deduplicação, pesquisa ou entrega. Foi
provisionado somente o laboratório local descrito acima, sem deploy LG,
alteração de banco corporativo ou autorização de produção. O fluxo completo
do frontend SYNERGIA e a CI remota não foram executados nesta tarefa; a interface
de pesquisa do Graylog foi validada pelo navegador conforme evidência acima.

## Integração com PRs abertos

O PR #174 permanece independente e aberto. Esta implementação adiciona
`GRAYLOG_CONFIG_DIR` ao template e `graylog-worker` ao Compose/deploy; seu guia
próprio evita antecipar arquivos ainda ausentes da `main`.
Ao incorporar o #174, atualizar sua referência de ambiente com uma linha para
essa variável e a lista de serviços/tarefas com o coletor. Executar também
`test_deployment_docs.py`: a nova variável precisa entrar no catálogo central
para satisfazer seu contrato. README/matriz são pontos de possível sobreposição.
Esse ajuste documental conjunto não foi publicado em outra branch nesta tarefa.

O PR #180 não é dependência funcional. Não foi presumido acesso ao Graylog a
partir do resultado de conectividade da API de e-mail. Atualizar a branch com a
`main` vigente e repetir as verificações relevantes antes da futura integração.
