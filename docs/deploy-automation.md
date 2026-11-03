# Automação de implantação — issue #166

Implementação em andamento. Os blocos 1 e 2 disponibilizam `precheck`,
`diagnose`, `apply` e `verify`. O rollback, a reconciliação de operações
interrompidas e a bateria integrada de falhas pertencem aos blocos seguintes.
Não use esta entrega parcial para uma liberação assistida antes desses gates.

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
execute downgrade. A reconciliação e o rollback serão entregues no bloco 3.

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

Essa entrega não declara a issue concluída. O rollback e a bateria completa do
ensaio equivalente à homologação ainda precisam dos blocos 3 e 4, usando
somente dados sintéticos e sem serviços SMTP externos.
