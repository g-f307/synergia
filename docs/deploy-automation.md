# Automação de implantação — issue #166

Os comandos disponíveis são `precheck`, `diagnose`, `apply`, `verify`,
`rollback` e `reconcile`. A validação técnica reproduzível está descrita no
[relatório da issue #166](deploy-validation-report.md); liberação em um destino
real ainda exige a configuração, os backups e os aceites operacionais do local.

## Pré-condições e identidade da instalação

Execute no host Linux com Python 3.11+, Git, Docker Engine acessível e Docker
Compose com suporte a `config --format json` e `ps --format json`. A CLI usa
somente a biblioteca padrão do Python; não precisa instalar as dependências
do backend no host. Use um checkout limpo do commit escolhido.

Escolha um nome estável de projeto Compose. Para a instalação existente com o
Compose padrão, ele é `synergia`. Trocar esse nome seleciona outros volumes;
um projeto sem containers **não prova** que esta seja a primeira instalação.
Confira o projeto e os volumes esperados no diagnóstico antes de prosseguir.
O diretório de checkout não determina o nome do projeto.

Prepare o arquivo externo conforme
[os perfis de ambiente](deployment-environments.md). Ele deve pertencer ao
operador e permitir leitura somente pelo proprietário, normalmente modo
`0600`. O diretório externo de histórico, quando existir, deve pertencer ao
operador e ter modo `0700`. Não coloque esses arquivos dentro do repositório,
mesmo em caminhos ignorados. Não inclua segredos na linha de comando.

A CLI usa explicitamente o arquivo externo e o Compose versionado; ignora o
`.env` implícito e variáveis de aplicação/Compose do shell. Mantém as variáveis
necessárias para selecionar o contexto Docker, suas credenciais e o SSH agent.
Não executa o arquivo de configuração como shell. Credenciais e a configuração
resolvida não são impressas no diagnóstico. Durante `apply`, cópias privadas
da configuração resolvida e do runtime anterior são preservadas no histórico
externo; **esses arquivos contêm segredos** e exigem os mesmos controles de
acesso e backup do arquivo de ambiente. Não os compartilhe como evidência.

## Comandos disponíveis

No host, a partir do checkout do Synergia, substitua os caminhos pelos arquivos
privados da instalação:

```bash
python3 scripts/deploy.py diagnose \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history

python3 scripts/deploy.py precheck \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history
```

Ambos executam as mesmas verificações somente de leitura: fonte versionada sem
alterações pendentes, disponibilidade das ferramentas, perfil de ambiente,
configuração resolvida, identidade do daemon/projeto/volumes, containers e
imagens locais. Containers existentes de PostgreSQL e backend devem montar os
volumes esperados. Configuração inválida, identidade divergente ou histórico
ilegível interrompe com saída `1` e indicação da etapa; corrija a causa local e
repita. A saída `0` traz um JSON com commit, ambiente, presença dos recursos e
última operação conhecida. Imagem ausente é informação de inventário; o build
será responsabilidade do fluxo de implantação.

O diagnóstico não cria diretórios de histórico/locks, containers, imagens ou
volumes; não executa migrations, sementes, bootstrap de usuários, worker de
e-mail ou chamadas HTTP. Não invoca `/health/ready`, pois essa sonda grava um
arquivo temporário de teste no armazenamento. Uma leitura bem-sucedida também
não confirma disponibilidade funcional nem ausência de uma operação em curso.

## Instalação e atualização

Execute no host, com o commit ou tag escolhido já obtido e em checkout limpo.
A CLI não faz `pull`, troca de branch ou descarte de alterações. Substitua o
marcador pelo SHA completo ou tag que identifica o checkout atual:

```bash
python3 scripts/deploy.py apply \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history \
  --revision SHA_OU_TAG_ESCOLHIDO
```

Somente na primeira instalação, sem containers ou volumes desse projeto,
acrescente `--initialize`. O parâmetro é rejeitado em instalações existentes.
Recursos parciais exigem reconciliação; a automação não cria silenciosamente
outro banco para substituir dados ausentes. Identidade, usuário ou senha do
PostgreSQL divergentes do container existente exigem procedimento próprio de
administração do banco; atualização de aplicação não rotaciona essas credenciais.
Alteração da porta publicada do PostgreSQL também exige esse procedimento;
o fluxo bloqueia a mudança antes do build, pois mantém o container do banco.

| Etapa | Efeito e resultado esperado |
| --- | --- |
| precheck | Confere ferramentas, commit, configuração, histórico e recursos; recusa worker, migration ou outro comando avulso em execução. |
| captura | Salva runtime anterior em arquivo privado e retém as imagens anteriores por ID e tags locais. |
| build | Constrói backend e web com tags únicas por operação e labels OCI com o commit; a aplicação existente continua disponível. |
| configuração | Fixa as imagens por ID, valida o entrypoint da candidata e aguarda PostgreSQL saudável sem recriar o container existente. |
| maintenance | Para web e backend; confirma que os processos pararam e registra o ledger anterior. PostgreSQL e volumes permanecem. |
| migrate | Executa uma única chamada explícita ao runner existente, com advisory lock, checksum e transação por migration; confere o ledger final contra a fonte. |
| start | Inicia backend e web separadamente, sem dependências automáticas, novo build ou pull; aguarda os health checks. |
| verify | Confere IDs das imagens, histórico de migrations, liveness, readiness, HTML e origem da configuração web. |
| confirm | Grava o manifesto e promove `active.json` somente depois de todas as verificações. |

O processo não executa bootstrap de usuários, sementes ou envio de e-mail. O
worker é finito: espere sua conclusão e suspenda agendadores externos durante a
janela de manutenção; a automação não interrompe uma entrega SMTP em andamento.
O build acontece antes da parada, mas migrations e inicialização exigem uma
janela de indisponibilidade. Não há promessa de atualização sem downtime.

O runner pode ser chamado novamente em outra atualização: migrations já
registradas são puladas, mantendo os mesmos registros e datas de aplicação.
Não há segunda migration implícita ao iniciar a API, porque `up` usa
`--no-deps`. O PostgreSQL existente mantém a mesma imagem e configuração; uma
atualização de versão do banco não faz parte desse fluxo.

O progresso informa etapa, quantidade de migrations verificadas e commit
confirmado. A saída JSON final contém o commit, IDs das imagens, inventário de
migrations e a referência da implantação anterior, sem credenciais. A API
também registra o commit no startup; as imagens backend/web possuem a label
`org.opencontainers.image.revision`. Isso não altera a versão funcional da API.

## Verificação de uma implantação confirmada

```bash
python3 scripts/deploy.py verify \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history
```

Saída `0` informa `verified: true` e o commit confirmado. O comando verifica os
containers e imagens efetivos, ledger, endpoints e configuração web usando a
configuração privada preservada. Não executa build, migration ou envio de
e-mail, mas invoca readiness e, portanto, faz a sondagem temporária de storage.
Para uma leitura sem essa escrita, use `diagnose`.
As portas publicadas também são comparadas com o runtime; uma origem interna
saudável não basta para aprovar uma exposição diferente da registrada.

## Falhas e controle das operações

Qualquer falha bloqueia o restante da sequência e retorna saída `1`, indicando
a etapa. Mensagens brutas de Docker, SQL ou da aplicação podem conter segredos
e não são reproduzidas pela CLI. Para investigação, consulte localmente o
journal e os logs privados do daemon, sem publicá-los. A migration usa um
container preservado, com nome `<projeto>-migration-<id-da-operação>`, inclusive
quando o cliente perde a conexão; isso permite conferir seu estado e seus logs.

Falhas anteriores à manutenção ficam `failed`; uma nova tentativa ainda exige
que os recursos passem novamente pelo precheck. A partir da pausa da aplicação,
falhas ou interrupções ficam `uncertain` e bloqueiam retries. A última referência
confirmada não é promovida, mas isso **não significa** que o runtime ou schema
tenham voltado à versão anterior. Não reinicie manualmente a migration nem
execute downgrade. Use os procedimentos explícitos abaixo.

O lock identifica o daemon Docker e o projeto, inclusive quando dois comandos
informam diretórios de histórico diferentes. A instalação deve ter um único
operador de sistema para executar a automação. O lock local fica em diretório
privado em `/tmp`; um diretório existente de outro proprietário bloqueia a
operação. A exclusão mútua é local ao host executor: operadores não devem
executar deploys concorrentes em máquinas diferentes contra o mesmo daemon.

O journal `operation.json` é escrito atomicamente com modo `0600`, inclui
identificador, identidade da instalação, ação, etapa, status e data UTC. Não
recebe saída de processos nem conteúdo de exceções. Uma interrupção tratada
fica `uncertain`; uma queda abrupta pode deixar `running`. Ambos bloqueiam
novas alterações até reconciliação explícita. Nunca apague o registro para
forçar um retry sem antes verificar containers e histórico de migrations.

Os diretórios por operação preservam configuração, imagens referenciadas,
runtime anterior e inventários de migrations. Não apague o histórico nem
execute limpeza de imagens retidas enquanto elas forem necessárias à
recuperação. A automação não remove volumes nem faz rollback destrutivo de banco.

## Rollback da aplicação

No host, use a mesma identidade de projeto e diretório de histórico:

```bash
python3 scripts/deploy.py rollback \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history
```

O comando escolhe a versão imediatamente anterior à referência ativa. Antes de
parar a aplicação, confere configuração protegida, imagens por ID, identidade
do PostgreSQL e igualdade exata entre o ledger atual e o ledger da versão de
destino. Também bloqueia se o advisory lock do runner estiver ocupado. Imagem
ausente, configuração alterada, perfil antigo inválido ou histórico divergente
impedem o rollback. Nenhuma imagem é baixada ou reconstruída.
Os dois volumes persistentes precisam existir. A ausência do volume de arquivos
bloqueia rollback e reconciliação, inclusive quando o container do backend foi
removido: a automação não cria um volume vazio para substituir arquivos perdidos.

Após as conferências, o comando para somente backend e web e os inicia pelas
imagens e configuração preservadas, com `--no-deps`, `--no-build` e `--pull never`.
Confere novamente o banco após a pausa e verifica runtime, ledger e smoke antes
de promover o rollback como uma nova implantação. Não inicia o PostgreSQL,
worker ou runner de migrations. A versão antiga precisa aceitar o schema
atual; igualdade do ledger é a política conservadora, não uma prova universal
de compatibilidade com DDL manual fora do runner.

Na primeira atualização de uma instalação sem histórico da automação, uma
baseline privada captura o runtime efetivo: imagens, ambiente, comandos,
portas, mounts, usuário, restart e health checks. Ela exige ledger existente
e válido. Se a imagem antiga não informava commit, `revision` permanece `null`;
seus IDs continuam identificando exatamente os artefatos restaurados. A CLI
envia o smoke versionado ao Python do container, sem depender de um script
que pudesse não existir na imagem anterior.

Uma falha após iniciar a manutenção deixa o rollback `uncertain`, preservando
a última referência confirmada. A aplicação pode estar parada ou parcialmente
restaurada; consulte o diagnóstico e reconcilie explicitamente.

## Reconciliação de operação interrompida

Primeiro leia `operation.id` no diagnóstico. No host, inspecione esse UUID:

```bash
python3 scripts/deploy.py reconcile \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history \
  --operation UUID_DA_OPERACAO
```

Sem `--resolution`, o comando é somente leitura: não toma lock de implantação,
não altera o journal, não inicia containers e não chama readiness. Informa
disponibilidade do banco, lock de migrations, operações ativas, correspondência
do ledger com a candidata e o resultado do container de migration:

| Estado | Significado e próxima ação |
| --- | --- |
| `running` | Container ainda em execução, pausado ou reiniciando; não iniciar nova migration nem reconciliar o runtime. |
| `completed` | Container encerrado com código zero; conferir também ledger e ausência de locks. |
| `failed` | Container encerrado com erro; podem existir migrations anteriores já confirmadas. O ledger determina o que foi aplicado. |
| `not_found` | Não há container com a identidade esperada; isso não prova que a migration nunca executou. |
| `unknown` | Container existe sem resultado conclusivo; manter o bloqueio e investigar localmente. |

Escolha uma resolução somente depois de examinar as evidências:

```bash
# Concluir a candidata cujas migrations já estão integralmente confirmadas:
python3 scripts/deploy.py reconcile \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history \
  --operation UUID_DA_OPERACAO --resolution resume

# Restaurar a aplicação anterior quando o ledger continuar compatível:
python3 scripts/deploy.py reconcile \
  --project synergia \
  --env-file /caminho/privado/homologation.env \
  --state-dir /caminho/privado/deploy-history \
  --operation UUID_DA_OPERACAO --resolution rollback
```

Após uma tentativa de migration, `resume` **não repete migrations**. Exige
igualdade completa do ledger com a candidata e ausência de processo/lock ativo ou desconhecido; então inicia e
verifica os serviços preservados. Mesmo sem container de migration, o ledger
transacional completo permite essa resolução explícita, sem inferir que o SQL
deva ser repetido. Se parte das migrations tiver falhado, a divergência bloqueia
`resume`. `rollback` exige o ledger da versão anterior; a instalação inicial
sem versão anterior não possui esse caminho de retorno.

Na primeira instalação, o candidato, a configuração congelada e a intenção
`initialization.json` são persistidos **antes** de qualquer comando Compose que
possa criar recursos. Se a configuração ou o readiness do PostgreSQL falhar,
a operação fica `uncertain`; repetir `apply`, com ou sem `--initialize`, é
bloqueado. O diagnóstico de reconciliação informa `initialization_pending: true`
sem consultar um banco que ainda pode estar indisponível.

Nesse caso, use o mesmo comando `reconcile ... --resolution resume`. A retomada
explícita valida imagens, configuração, projeto e daemon, toma o lock, aguarda
ou inicia o PostgreSQL com `--no-recreate`, preserva os volumes já criados e
executa a **primeira** tentativa das migrations. Um container PostgreSQL já
existente deve corresponder à imagem, ambiente e portas preservados. Escritores,
operações ativas, container de migration existente, lock ou ledger não vazio
bloqueiam essa retomada. Não há limpeza automática de recursos.

Antes de enviar SQL ao Docker, o executor persiste `migration-attempted.json`.
Depois desse ponto, inclusive se o cliente morrer antes de receber resposta,
a exceção de inicialização deixa de valer: aplicam-se as regras de ledger
completo descritas acima, sem repetir SQL. Falhas repetidas de readiness podem
ser retomadas com o mesmo UUID; a promoção continua dependendo de todas as
verificações. A retomada usa a configuração congelada, não alterações posteriores
no arquivo de ambiente externo.

As duas resoluções tomam o mesmo lock exclusivo da implantação e exigem o UUID
atual com status `running` ou `uncertain`. Cada tentativa preserva o journal
anterior e o resultado em `reconciliations/`, sem mensagens brutas ou segredos.
Uma resolução falha permanece `uncertain`. `resume` bem-sucedido marca a
operação como `succeeded`; retorno à versão anterior marca `reconciled`, sem
declarar a candidata implantada. Ambas exigem verificação antes de alterar a
referência ativa. Nunca edite o journal ou apague containers para forçar retry.

Artefato da candidata ausente ou corrompido bloqueia a recuperação automática.
Preserve as evidências, mantenha a manutenção e encaminhe o caso aos
responsáveis por aplicação e banco. A automação não adivinha o commit, o
resultado do SQL nem a configuração a partir de uma tag mutável.

## Quando o banco exige recuperação

Uma migration nova pode ter sido confirmada mesmo que a atualização falhe
depois. Nesse caso, o rollback de aplicação fica bloqueado por padrão. Escolha
uma correção para frente compatível com o schema ou uma recuperação conjunta
de banco e arquivos, com decisão explícita dos responsáveis e RPO/RTO aceitos.
Nenhum comando de deploy executa `.down.sql`, restaura dump ou remove volumes.

Antes de uma atualização com migrations, prepare e verifique o backup segundo
[data-recovery.md](data-recovery.md) e o
[runbook de backup e restauração](runbooks/backup-restore.md). O deploy não cria
esse backup automaticamente. **O bundle existente exporta somente o schema
`synergia`; não inclui `public.synergia_schema_migrations`.** O inventário de
arquivos SQL no manifesto não substitui os registros efetivamente aplicados.

Para recuperação completa da implantação, a operação de banco deve preservar
também o ledger público, suas datas e hashes, no mesmo ponto consistente do
backup de domínio e arquivos. Uma alternativa é um dump custom do banco
inteiro com `pg_dump` da mesma major version, sem restringir `--schema`, mais
os arquivos e configuração correspondentes, sob manutenção e sem migrations
concorrentes. Não exponha dumps, arquivos privados ou saídas SQL como evidência.

Restaure em banco e storage novos e vazios, mantendo os originais preservados.
Confirme a origem/versão das imagens, ledger público, constraints, usuários,
contagens, hashes e arquivos referenciados. O procedimento existente de
restauração de domínio não deve ser tratado como restauração automática de um
dump do banco inteiro. A operação de banco valida o procedimento apropriado ao
backup escolhido; só depois de verificação integral e aceite operacional deve
ocorrer a troca controlada dos destinos. Não marque uma operação como resolvida
nem libere tráfego apenas porque o PostgreSQL iniciou.

## Ensaio sintético e gate de CI

Em um checkout limpo, com Python 3.12+, Docker e os commits atual e anterior
disponíveis localmente, execute no host:

```bash
python3 scripts/validate_deploy.py --output artifacts/deploy-validation.json
```

O executor cria projetos `synergia-check-<identificador-aleatório>`, configuração
e histórico privados fora do Git e somente dados sintéticos. Exercita instalação,
atualização, falhas reais de build/SQL/health/smoke, concorrência, interrupções,
diagnóstico, proteção de artefatos e rollback de uma versão anterior. O backend
e a web dessa versão são construídos dos arquivos Git do commit `HEAD^`, com
seu SHA registrado nas imagens; use `--previous-revision SHA_OU_TAG` para escolher
outro commit já disponível. Não há download de código de terceiros, criação de
tags Git, credenciais de homologação ou uso de SMTP no ensaio.

O teste mantém um advisory lock real durante a simulação de migration lenta,
interrompe o cliente abruptamente e exige reconciliação sem repetir SQL. Uma
falha de SQL é provocada somente no PostgreSQL sintético. Mudanças temporárias
no ledger e nos artefatos também ficam restritas aos projetos do teste e são
desfeitas antes da conferência de integridade.

Na conclusão, inclusive em falha, o executor remove somente seus containers,
volumes e redes e compara o inventário com o estado anterior. **Essa limpeza
destrutiva é exclusiva do executor sintético; `deploy.py` não remove volumes.**
Imagens e cache de build não são limpos globalmente. Históricos privados de
teste permanecem em diretórios temporários protegidos para diagnóstico local;
não os publique como evidência.

Saída `0` e `result: passed`, com `cleanup: passed`, confirmam o ensaio.
O JSON público contém cenários, resultados, durações, commits e hashes do código;
nunca configuração, dumps, arquivos importados, logs brutos ou segredos. Falha
retorna `1` e identifica o cenário no mesmo relatório. Execute em um daemon
sem alterações concorrentes de outros operadores, pois o gate exige que os
recursos preexistentes permaneçam idênticos.

O job **Deploy — homologação, atualização e recuperação** executa esse comando
na CI e publica somente `artifacts/deploy-validation.json`. Se o commit anterior
tiver outro inventário de migrations, o ensaio deve comprovar o bloqueio do
rollback por schema; ele não executa downgrade para satisfazer o teste. A
validação local equivalente à homologação não representa implantação na LG.

A consolidação do conjunto completo de runbooks corporativos continua no
escopo da #167; este documento define o contrato executável da automação #166.
