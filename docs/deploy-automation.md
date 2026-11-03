# Automação de implantação — issue #166

Implementação em andamento. Este primeiro bloco disponibiliza somente
`precheck` e `diagnose`; instalação, atualização, verificação HTTP e rollback
serão entregues nos próximos blocos. Os comandos deste documento não implantam
uma versão nem substituem ainda o procedimento de execução existente.

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
resolvida ficam somente em memória, sem impressão no diagnóstico.

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

## Controle das operações — fundação interna

O primeiro bloco inclui a infraestrutura de exclusão mútua e journal para os
comandos de alteração dos próximos blocos. Ela ainda não tem comando público
de aplicação ou reconciliação.

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

Essa fundação não declara a issue concluída. O ensaio equivalente à homologação,
a preservação de dados durante atualização e o rollback serão validados nos
blocos seguintes, sem acesso a dados reais ou serviços SMTP externos.
