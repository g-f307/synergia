# Perfis de ambiente da implantação

O ambiente deve ser escolhido explicitamente. O Compose não assume mais
`development` quando `SYNERGIA_ENV` está ausente. Isso impede que uma instalação
destinada à homologação ou à produção inicie com controles locais.

`POSTGRES_PASSWORD` também é obrigatória na interpolação do Compose em todos os
perfis. Assim, a configuração falha ainda em `docker compose config`, antes da
criação do PostgreSQL ou da publicação de sua porta. O valor local conhecido
existe somente em `.env.example`; homologação e produção devem fornecê-lo por
arquivo privado.

## Desenvolvimento

Use `.env.example` apenas na estação local:

```bash
cp .env.example .env
docker compose --env-file .env config
docker compose --env-file .env up --build
```

O resultado esperado é o backend registrar
`synergia startup: environment=development`. Os valores locais conhecidos são
aceitos somente em `development` e `test`.

## Homologação assistida

Copie `.env.homologation.example` para um arquivo protegido fora do Git,
substitua todos os `CHANGE_ME` e execute:

```bash
docker compose --env-file /caminho/privado/synergia-homologation.env config
docker compose --env-file /caminho/privado/synergia-homologation.env up --build
```

O login local temporário exige `AUTH_LOCAL_LOGIN_EXPIRES_AT` em ISO 8601, com
fuso, no futuro e no máximo 90 dias à frente. HTTP é aceito somente neste perfil
transitório quando a rede interna ainda não oferece TLS. Senhas locais padrão,
origens `localhost` e chaves de desenvolvimento interrompem a inicialização.

## Produção

`.env.production.example` descreve o contrato, mas não autoriza uma implantação.
Produção exige HTTPS, cookie seguro, autenticação local desabilitada, provedor
corporativo e arquivos de segredo/mapeamento montados por caminho absoluto.
Enquanto o adaptador corporativo e esses mounts não estiverem disponíveis, o
perfil suportado para validação interna é `homologation`, não `production`.

## Diagnóstico

Falha antes do comando do container aparece como:

```text
invalid deployment configuration: NOME_DA_VARIAVEL ...
```

Corrija a variável indicada no arquivo privado e execute `docker compose config`
novamente. Não edite `docker-compose.yml`, imagens ou fontes para inserir IPs,
URLs ou segredos. A configuração efetiva pode ser inspecionada com `config`, mas
não deve ser anexada a tickets porque pode conter valores sensíveis.
