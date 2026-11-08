# Experimentar o SYNERGIA com Graylog Open

O objetivo deste laboratório é avaliar **funcionamento e utilidade** da
integração, em um Graylog convencional. Nenhum servidor corporativo, acesso LG,
licença Enterprise ou credencial de terceiros é necessário. Não se presume que
a LG utilize o Graylog; uma possível implantação é uma decisão futura.

O laboratório executa Graylog Open, MongoDB, OpenSearch e PostgreSQL reais.
O exercício chama as rotas reais do backend pelo cliente de teste, com banco
próprio e autenticação/autorização efetivas. O frontend do SYNERGIA não precisa
estar iniciado. Isso permite verificar os registros na interface real do Graylog
sem misturar dados de negócio ou configurações de outra instalação.

## O que será demonstrado

| Situação sintética | O que procurar no Graylog | Para que ajuda |
| --- | --- | --- |
| Senha incorreta | `auth.login_failed` e resultado `failure` | Distinguir falha de autenticação |
| Login correto seguido de tentativa de administração sem permissão | `auth.login_succeeded` e `authorization.denied`, com a mesma correlação | Reconstruir a sequência e distinguir falta de permissão de senha incorreta |
| Importação de arquivo vazio | Eventos da execução e `file_rejected`, em outra correlação | Acompanhar uma importação recusada sem copiar células ou conteúdo do arquivo |
| Input parado durante uma nova tentativa de login | Resposta de negócio preservada e evento retido no PostgreSQL | Verificar que o Graylog não bloqueia a aplicação |
| Input retomado e evento reconciliado | Evento pesquisável com ID estável | Conferir recuperação e ausência de reenvio dos eventos já aceitos |

O Graylog ajuda a localizar e relacionar acontecimentos. Não deduz a causa de
uma pendência de suprimentos nem substitui os relatórios de qualidade e a trilha
transacional do SYNERGIA. Um teste sintético não comprova ganho de produtividade;
o roteiro de avaliação humana ao final serve para você julgar sua utilidade.

## 1. Preparar as ferramentas

Use o checkout que contém `scripts/graylog_lab.py`, Python 3.12, Git e um engine
de containers ativo: Docker Desktop/Engine ou Podman. São necessárias imagens
grandes, vários GB livres em disco e aproximadamente 8 GB de RAM disponíveis.
O primeiro download pode demorar, dependendo da conexão. Não há cobrança de
serviço de nuvem neste procedimento.

As versões configuradas são Graylog Open `7.2.2`, MongoDB `7.0`, OpenSearch
`2.19.6` e PostgreSQL `16-alpine`. OpenSSL é usado para gerar um certificado
local. No Windows, o script também procura o OpenSSL fornecido pelo Git na
instalação padrão, se ele não estiver no PATH.

No PowerShell, dentro do checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
docker info
```

Se usar Podman, conferir `podman info` e trocar `--runtime docker` por
`--runtime podman` em todos os comandos seguintes. O preparo e os testes locais
nesta estação usam Podman no WSL; a receita Windows/Docker é fornecida para reprodução,
não deve ser confundida com uma execução já comprovada nesse outro ambiente.

## 2. Criar os arquivos privados

```powershell
$Lab = 'C:\DadosPrivados\synergia-graylog-lab-178'
New-Item -ItemType Directory $Lab -Force
$Owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls $Lab /inheritance:r /grant:r "$($Owner):(OI)(CI)F"
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker init
```

O script gera senhas e chaves aleatórias em `access.json`, configurações privadas
e um certificado local, fora do Git. Não é necessário criar conta no site do
Graylog ou pedir credenciais à empresa. Use sempre o mesmo diretório: os
containers são vinculados a ele, para preservar credenciais e dados.

No Linux/WSL, com Python 3.12 e OpenSSL disponíveis:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
LAB="$HOME/.local/share/synergia-graylog-lab-178"
.venv/bin/python scripts/graylog_lab.py --workspace "$LAB" --runtime podman init
```

O diretório privado usa permissão `0700`; os arquivos de acesso usam `0600`.
O certificado do input é local, para testes, e não instala uma CA no sistema
operacional. O coletor confia nesse certificado por arquivo e mantém a
verificação TLS ativa. O certificado gerado tem validade de 30 dias.

## 3. Iniciar e configurar o Graylog

```powershell
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker start
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker configure
```

`start` cria uma rede e volumes exclusivos, baixa imagens ausentes e inicia os
serviços. `configure` aguarda a API e cria um input GELF HTTPS com autenticação.
As configurações de outro Graylog ou do Compose principal do SYNERGIA não são
alteradas. Recursos existentes sem os rótulos do laboratório são recusados.

Somente portas de loopback são publicadas:

| Finalidade | Endereço local |
| --- | --- |
| Interface e API do Graylog | `http://localhost:19000` |
| Recebimento GELF com TLS | `https://127.0.0.1:12202/gelf` |
| PostgreSQL exclusivo do laboratório | `127.0.0.1:15479` |

MongoDB e OpenSearch não têm portas publicadas no host. A UI HTTP é restrita ao
computador local; os eventos usam HTTPS com certificado verificado. Este perfil
é de laboratório e não é um modelo de implantação corporativa.

## 4. Executar a validação automática

```powershell
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker validate
```

O exercício cria um banco novo e isolado, aplica as migrations, prepara uma
identidade sintética e executa os cenários da tabela inicial. Ele confirma os
eventos pela **API de pesquisa do próprio Graylog**, não apenas pela resposta
HTTP de ingestão. Também testa credencial incorreta do input, interrupção,
reconciliação e repetição de lote.

Durante o cenário de falha, o input criado pelo laboratório é parado e retomado.
Nenhum serviço de outra instalação é interrompido. A retomada do evento incerto
é uma decisão explícita do ensaio, após verificar o input parado e a ausência
do ID na pesquisa; isso não habilita retry cego na aplicação.

Esperado: `validated_real_graylog` e caminho de `validation.json`. Esse arquivo
contém os resultados e as correlações para a inspeção visual. `last-run.json`
contém a conexão privada do banco do ensaio; mantê-lo privado. Uma nova chamada
de `validate` cria outro banco sintético para não contaminar a demonstração com
políticas e notificações de execuções anteriores.

## 5. Conferir na interface, sem conhecer Graylog

1. Abra `http://localhost:19000` no navegador.
2. Abra `access.json` localmente para consultar `username` e `password`. São as
   credenciais desta instância de laboratório; não as publique em screenshots.
3. Faça login e entre em **Search**.
4. Escolha **Last 1 hour**. Para um ensaio antigo, selecione um período absoluto
   que inclua `started_at` e `finished_at` de `validation.json`.
5. Pesquise:

```text
service:synergia-audit-projector
```

6. Para inspecionar o cenário de acesso, copie `correlation_id` de
   `validation.json` e substitua o marcador:

```text
correlation_id:"CORRELACAO_DO_ENSAIO"
```

7. Abra as mensagens. Compare `message`, `outcome`, `origin`, `timestamp` e
   `event_id`. O nome `short_message` enviado em GELF aparece como `message`
   na pesquisa. Campos adicionais são pesquisados sem o `_` inicial.
8. Repita com `import_correlation_id` e depois `recovery_correlation_id`.
9. Para filtrar falhas:

```text
service:synergia-audit-projector AND outcome:failure
```

10. Escolha um `event_id` e pesquise `event_id:"ID_COPIADO"`. Depois da
    repetição controlada, ele deve continuar com uma ocorrência neste ensaio.

Se a lista parecer vazia, conferir primeiro o período selecionado e o resultado
da validação. O histórico de vários ensaios permanece na instância; filtrar pela
correlação evita misturar demonstrações diferentes.

## 6. Julgar a utilidade para o SYNERGIA

Tente responder apenas com a pesquisa:

- A solicitação falhou na autenticação ou na autorização?
- Houve login bem-sucedido antes da negação de acesso?
- Quais eventos pertencem à mesma importação recusada?
- O evento produzido durante a indisponibilidade apareceu depois da recuperação?
- Uma segunda execução do worker criou mensagens repetidas?

Registre quais respostas encontrou, quais campos fizeram falta e se a pesquisa
foi compreensível. Essa é a avaliação de utilidade a fazer agora. Não é preciso
decidir onde implantar, contratar infraestrutura ou descobrir se a LG já usa
Graylog para concluir essa avaliação.

## 7. Consultar estado e parar

```powershell
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker status
.\.venv\Scripts\python.exe scripts\graylog_lab.py --workspace "$Lab" --runtime docker stop
```

`stop` encerra somente os containers identificados do laboratório e mantém
volumes, arquivos privados e evidências para retomar depois. Não remove bancos
ou volumes de outra instalação. Para reiniciar, usar o mesmo `start` e diretório.

Falhas retornam código estável, sem imprimir credenciais, payloads ou configurações
de containers. Se `configure` disser que o servidor não está pronto, conferir
primeiro `status`, recursos disponíveis e término do download. Códigos como
`opensearch_not_running` indicam qual dependência está parada; nesse caso,
não adianta apenas repetir `configure` sem corrigir a inicialização. Em Windows/WSL,
o encaminhamento de localhost deve estar funcional para abrir a UI no navegador.

Referências: [instalação oficial](https://go2docs.graylog.org/current/downloading_and_installing_graylog/docker_installation_os.htm),
[compatibilidade de versões](https://go2docs.graylog.org/current/downloading_and_installing_graylog/compatibility_matrix.htm),
[API de pesquisa](https://go2docs.graylog.org/current/making_sense_of_your_log_data/simple_search_scripting_api.htm)
e [operação do coletor](graylog.md).
