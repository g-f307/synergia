# Primeira implantação

Comece pelo [mapa e pré-requisitos](README.md). Este procedimento instala
homologação assistida com banco novo. Banco existente exige o procedimento de
[atualização e adoção de legado](update-and-rollback.md). Os caminhos abaixo
são exemplos: substitua `/caminho/privado` por um diretório autorizado fora do
checkout. Execute em Bash e não habilite rastreamento de comandos (`set -x`).

## 1. Host e revisão

```bash
git --version
python3 --version
docker compose version
docker info --format '{{.ServerVersion}}'
```

- **Onde executar:** terminal do host Linux autorizado.
- **Efeito:** somente leitura; verifica ferramentas e acesso ao daemon.
- **Resultado esperado:** saída 0 em cada comando; Python >= 3.11, Compose v2.
- **Interpretação de falhas:** ferramenta ausente ou acesso ao daemon negado.
- **Próxima ação:** plataforma corrige o host; depois obtenha o checkout.

```bash
git clone https://github.com/g-f307/synergia.git
cd synergia
git switch --detach REVISAO_APROVADA
git status --short
git diff --exit-code
git rev-parse HEAD
```

- **Onde executar:** host, diretório de trabalho; substitua `REVISAO_APROVADA` por tag/SHA aprovado.
- **Efeito:** mutável; clona e seleciona código, depois inspeciona estado e SHA.
- **Resultado esperado:** comandos com 0, status vazio e SHA igual ao aprovado.
- **Interpretação de falhas:** revisão ausente, acesso negado ou alterações locais; não sobrescrever trabalho existente.
- **Próxima ação:** resolver acesso/revisão e usar checkout limpo; preparar configuração.

Se o clone já existir, comece pela conferência do estado; não repita clone nem
troque de revisão com mudanças locais. Todos os próximos comandos Compose são
executados na raiz desse checkout, com o mesmo projeto e arquivo externo.

## 2. Configuração privada

```bash
install -d -m 0700 /caminho/privado/synergia-config /caminho/privado/deploy-history
install -m 0600 .env.homologation.example /caminho/privado/synergia-config/homologation.env
```

- **Onde executar:** host, raiz do checkout, somente na primeira preparação (destino ausente).
- **Efeito:** mutável; cria diretórios e copia modelo sem segredos reais. Não sobrescrever configuração existente.
- **Resultado esperado:** saída 0; arquivo 0600 fora do Git.
- **Interpretação de falhas:** caminho ou permissão inválidos; interromper antes de iniciar containers.
- **Próxima ação:** editar o arquivo privado com editor autorizado e seguir a referência de ambiente.

Preencha senhas e chaves independentes, origens acessíveis pelo navegador,
tag imutável ligada ao SHA e abas permitidas. Remova todos os placeholders.
Para login local temporário, defina expiração com fuso. Nenhum usuário é criado
automaticamente por estes comandos: o responsável por IAM deve fornecer uma
identidade autorizada conforme [autenticação](../authentication.md).
Mantenha o e-mail desabilitado na instalação inicial.
Veja [variáveis e geração de chaves](environment-reference.md).

## 3. Pré-validação sem iniciar banco

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env config --quiet
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env build
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env run --rm --no-deps config-check
```

- **Onde executar:** host, raiz do checkout.
- **Efeito:** mutável; valida interpolação, constrói imagens e executa tarefa isolada sem dependências. Não inicia PostgreSQL.
- **Resultado esperado:** 0 em cada comando; `synergia startup: environment=homologation` e `deployment configuration valid`.
- **Interpretação de falhas:** `config --quiet` só valida Compose; o entrypoint de config-check também valida o perfil. Build pode falhar por rede/registry.
- **Próxima ação:** só prosseguir após todos passarem; em erro seguir [diagnóstico](troubleshooting.md).

O shell pode sobrepor valores de `--env-file`. Use terminal operacional sem
variáveis exportadas conflitantes; não carregue `.env` do Compose como script
shell. Não publique saída de `docker compose config` sem `--quiet`.

## 4. Banco, migrations e aplicação

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env up -d postgres
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env run --rm --no-deps migrate
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env up -d --no-deps backend web
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env ps --all
```

- **Onde executar:** host, raiz do checkout; execute um comando por vez, interrompendo em falha.
- **Efeito:** mutável; cria volumes/banco, aplica SQL e inicia API/web. A migração é uma tarefa descartável.
- **Resultado esperado:** banco healthy antes de migrar; migrate retorna 0 com `apply`/`skip`; API/web tornam-se healthy.
- **Interpretação de falhas:** banco pode ainda estar iniciando; se migrate falhar, não iniciar a aplicação. Não há container migrate persistente após `run --rm`.
- **Próxima ação:** se PostgreSQL ainda não estiver healthy, aguardar e consultar diagnóstico antes de repetir migrate; após sucesso executar aceite.

`--no-deps` impede repetir migrations indiretamente; torna obrigatória a
ordem acima. `config-check` pode aparecer como Exited (0), o que é esperado.
Não confundir saída 0 da tarefa com saúde dos serviços permanentes.

## 5. Sondas e entrega

```bash
python3 scripts/smoke_containers.py \
  --backend-url http://127.0.0.1:8000 \
  --web-url http://127.0.0.1:8080 \
  --expected-api-origin http://api.homolog.example.invalid:8000
```

- **Onde executar:** host, raiz do checkout; ajustar portas e origem para os valores privados aprovados.
- **Efeito:** sondas HTTP; readiness também verifica escrita temporária no storage.
- **Resultado esperado:** saída 0, quatro linhas `ok:` e readiness `status=ready`.
- **Interpretação de falhas:** timeout, tipo de conteúdo incorreto ou origem runtime divergente; o script não carrega o arquivo passado ao Compose.
- **Próxima ação:** executar [checklist pós-implantação](post-deployment-checklist.md), incluindo acesso pelo navegador de outra estação; se falhar usar diagnóstico.

Para desenvolvimento local, use [primeiros passos](../getting-started.md).
A automação #166 com `precheck` e `apply --initialize` depende da entrega de
`scripts/deploy.py`, indisponível neste checkout.
