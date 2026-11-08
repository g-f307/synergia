# Graylog: integração padrão GELF e operação

**Escopo atual: avaliar funcionamento e utilidade em um Graylog convencional.**
Comece pelo [laboratório com Graylog Open real](graylog-laboratorio.md), que gera
suas próprias credenciais e usa somente dados sintéticos no computador local.
Não há premissa de que a LG utilize essa ferramenta, nem decisão de implantação
corporativa. Essa possibilidade é futura e separada da avaliação funcional.
Este documento é independente do guia de
implantação em revisão no PR #174; após sua integração, manter uma única
referência para operação e atualizar as duas branches antes dos respectivos merges.

## 1. Entender a integração e escolher um destino

O Graylog centraliza registros pesquisáveis. O SYNERGIA continua guardando sua
auditoria no PostgreSQL; um processo separado envia uma projeção aprovada em
GELF 1.1 por HTTPS. A aplicação não instala nem administra o servidor Graylog.
Metadados booleanos aprovados são mapeados para números `0`/`1`, pois campos
adicionais GELF portáveis aceitam strings e números; valores nulos são omitidos.

O laboratório permite verificar ingestão, pesquisa, correlação e recuperação
sem servidor de terceiros. Não é necessário obter credenciais corporativas.
**Somente se houver uma decisão futura de adoção em outra infraestrutura**, os
itens abaixo orientam a preparação com seus responsáveis:

1. Responsável pelo Graylog e versão instalada; ambiente de homologação autorizado.
2. URL completa do **input GELF HTTP** terminado em `/gelf`, com HTTPS. A URL
   da interface de pesquisa não é o input. Solicitar nome DNS e porta liberados
   da estação ou host que executará o coletor.
3. Autenticação do input: nome e valor de **um** cabeçalho de autorização, ou
   certificado de cliente e chave PEM. Usuário/senha da interface web não são
   automaticamente credenciais de ingestão. Não enviar segredos pelo chat.
4. Cadeia de CA corporativa em PEM, se não estiver no repositório de confiança
   do Python, e certificados de cliente quando exigidos. A chave deve permanecer
   privada. Não há opção de desabilitar validação TLS ou de usar HTTP.
5. Confirmação do código de aceitação `202`, limite de mensagem de pelo menos
   16 KiB e timeout permitido. Solicitar quais recusas, se houver, garantem que
   **nenhuma mensagem foi aceita** antes da resposta. Sem esse contrato,
   `retryable_statuses` permanece vazio.
6. Stream de auditoria, índice, retenção, permissões de pesquisa e operador para
   investigar recebimento; política separada para logs técnicos.
7. Organizações autorizadas, permissão para eventos globais e aprovação específica
   de UUIDs de ator/recurso, se necessários. Nomes, e-mails e IPs não são enviados.
8. Procedimento de deduplicação e reconciliação por `event_id`, com janela de
   espera para indexação. Definir responsáveis por operação, investigação,
   rotação de credenciais e revisão periódica de acesso.

Modelo de solicitação para essa etapa futura, sem dados privados:

> Estamos avaliando uma futura implantação da integração SYNERGIA–Graylog (#178).
> Precisamos de um input GELF HTTP com TLS e autenticação, acesso de rede a partir
> do executor aprovado, cadeia de confiança, limites/códigos de resposta e um
> stream pesquisável para eventos sintéticos. Poderiam indicar os responsáveis,
> a retenção/controle de acesso e o procedimento de reconciliação/deduplicação?
> Credenciais e endereços serão recebidos somente pelo canal corporativo aprovado.

## 2. Preparar o código e Python no Windows

Use Python 3.12 de 64 bits e a revisão aprovada que contenha esta implementação.
`REF_APROVADA` é um marcador a substituir pela branch/tag publicada ou revisão
entregue pela equipe; não é uma branch que este documento presume já publicada.

Em computador com acesso autorizado ao GitHub, no PowerShell:

```powershell
git clone https://github.com/g-f307/synergia.git
Set-Location synergia
git checkout REF_APROVADA
git rev-parse HEAD
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Se o computador de destino não acessa GitHub/PyPI, **não dependa de downloads nele**.
Prepare antes, em Windows com a mesma versão/arquitetura do Python:

```powershell
New-Item -ItemType Directory C:\KitSynergia178\wheels -Force
py -3.12 -m pip download --only-binary=:all: -r backend\requirements.txt --dest C:\KitSynergia178\wheels
git branch entrega-178 REF_APROVADA
git bundle create C:\KitSynergia178\synergia.bundle entrega-178
Get-ChildItem C:\KitSynergia178 -Recurse -File | Get-FileHash -Algorithm SHA256
```

Transfira o bundle, as wheels, o instalador Python se necessário e o manifesto
de hashes pelo meio aprovado para o ambiente. Configuração e certificados ficam fora
desse kit. Na estação, confira os hashes e faça:

```powershell
git clone --branch entrega-178 C:\KitSynergia178\synergia.bundle C:\Trabalho\synergia
Set-Location C:\Trabalho\synergia
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links C:\KitSynergia178\wheels -r backend\requirements.txt
git rev-parse HEAD
.\.venv\Scripts\python.exe --version
```

Registrar revisão, versão Python e horário UTC em evidência sanitizada. O bundle
contém a referência local `entrega-178`, criada a partir da revisão escolhida.
Esse preparo não cria commit nem publica a branch. Não sobrescrever uma branch
local existente com esse nome: conferir sua revisão antes de reutilizá-la.

## 3. Criar a configuração privada, ainda sem rede

```powershell
$Graylog = 'C:\DadosPrivados\synergia-graylog-178'
New-Item -ItemType Directory $Graylog -Force
icacls $Graylog /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
.\.venv\Scripts\python.exe scripts\process_graylog.py init --output "$Graylog\config.json"
notepad "$Graylog\config.json"
```

O `init` recusa sobrescrever arquivo e exige localização externa ao checkout.
No Windows, o operador deve conferir a ACL; a biblioteca padrão não comprova
todas as permissões efetivas do Windows. No Linux, o arquivo deve ser regular,
ter no máximo 64 KiB e permissão `0600`. Diretório privado: `0700`.

Alterar somente após receber as informações da seção 1:

| Campo | O que preencher |
| --- | --- |
| `endpoint` | URL HTTPS aprovada do input, caminho `/gelf`; sem usuário, senha ou query |
| `environment` | `test` no laboratório; ambiente real da instalação quando houver implantação |
| `application_version` | Hash completo de `git rev-parse HEAD`; em imagem, deve corresponder a `SYNERGIA_BUILD_REVISION` |
| `host` | Identidade técnica lógica aprovada, por exemplo `synergia`; não nome de pessoa ou IP |
| `headers` | `{ "NOME_APROVADO": "VALOR_PRIVADO" }`; nome `Authorization` ou `X-...`; manter privado |
| `ca_file` | Caminho local da CA PEM, ou `null` quando o Python já confia nela |
| `client_cert_file`, `client_key_file` | Caminhos PEM quando houver mTLS; ambos presentes ou ambos `null` |
| `organization_ids` | Lista de UUIDs das organizações explicitamente autorizadas |
| `include_global_events` | `true` somente com autorização para os eventos globais |
| `include_actor_id`, `include_resource_id` | Permanecem `false` sem aprovação específica |
| `authorization_confirmed` | `true` após autorizar o envio ao destino escolhido; no laboratório, refere-se à própria instância local. É declaração local, não teste de autenticação |
| `enabled` | `true` somente na etapa de envio autorizada |
| `retryable_statuses` | `[]` até existir contrato de não aceitação para códigos `429` e/ou `503` |
| Demais limites | Manter inicialmente 10 s, lote 50, cinco tentativas e base de 30 s |

Não colocar credenciais em variáveis digitadas no histórico, argumentos,
README, screenshots ou Git. O exemplo não pressupõe credencial de administração.

```powershell
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" check
```

Esperado: `configuration_valid_no_network`. Valida estrutura, limites e leitura
local de certificados; não faz GET/POST nem confirma conectividade ou autenticação.
O processo ignora proxies de ambiente. Se houver proxy obrigatório, solicitar
rota corporativa aprovada ou evolução testada; não improvisar bypass TLS.

Para localizar falhas sem expor segredos: se `check` falhar, conferir JSON, ACL e
caminhos/formatos de certificados; esse comando não usa o banco nem a rede. Se
`check` passar e `status` falhar, pedir ao responsável que confira acesso ao banco
e migration `0036`. Se ambos passarem e o envio ficar retido, investigar o
`last_code` do evento com a TI: `http_401`/`http_403` indicam recusa de autorização,
`http_302` indica redirecionamento bloqueado e `network_result_unknown` exige
conferência de recebimento antes de qualquer reenvio. Códigos HTTP são mantidos,
sem copiar corpo/cabeçalhos de resposta. Não publicar a configuração para depurar.

## 4. Banco e implantação: responsabilidade do operador autorizado

O coletor precisa de `DATABASE_URL` privada e acesso ao PostgreSQL da implantação
de homologação. Ela **não é** a URL do Graylog. O responsável pelo SYNERGIA deve
aplicar a migration `0036` pelo fluxo controlado existente, após backup e parada
dos escritores previstos pelo [guia de automação](deploy-automation.md).
Esta seção trata de uma instalação persistente. O laboratório usa banco próprio
e automatiza seu preparo; não depende de uma infraestrutura corporativa.

A migration cria fila, janelas, histórico e registro de execução LLM. Treze
triggers enfileiram a projeção canônica da auditoria na própria transação de
origem. Não copiam células, arquivos ou o payload integral da origem. O snapshot
interno permanece privado e ainda passa pela sanitização Python antes do envio.
O histórico anterior à migration exige `backfill` explícito; não é enviado
automaticamente. Nenhuma conexão Graylog participa da transação de negócio.
Os checkpoints começam a ser registrados após a migration mesmo com o envio
desabilitado; monitorar crescimento enquanto o input não estiver aprovado.
Geração por modelo passa a exigir auditoria PostgreSQL disponível, com falha
`503 model_audit_unavailable` antes da inferência se não puder registrar intenção.
Isso não exige acesso ao Graylog. O baseline determinístico continua disponível
sem criar evento LLM. Um `llm.requested` sem resultado após interrupção não deve
ser interpretado como sucesso de execução.

O DBA deve fornecer credencial técnica de banco com o menor privilégio
necessário: leitura da view canônica; leitura/inserção/atualização de controle,
fila e janelas; leitura/inserção do histórico e uso de sua sequência. Não
conceder exclusão da trilha, administração do banco ou alteração dos produtores.
Criar papéis e distribuir essa credencial são tarefas externas autorizadas;
nenhuma conta corporativa é criada pela implementação.

Mapeamento versionado:

| Origem/valor | GELF | Regra |
| --- | --- | --- |
| GELF 1.1 / identidade lógica | `version`, `host` | Valores fixo/aprovado |
| Ação canônica | `short_message` | Ação estável; sem texto de exceção |
| Instante do evento | `timestamp` | UTC em segundos desde epoch; não horário do envio |
| Origem e ID | `_event_id`, `_origin` | Hash estável e nome de fonte permitido |
| Contrato da #169 | `_format_version` | `1.0.0`; mesma estrutura, fontes/metadados adicionais aprovados |
| Resultado/correlação | `_outcome`, `_correlation_id` | Correlação ausente é omitida, nunca inventada |
| Organização/ator/recurso | `_organization_id`, `_actor_type`, `_actor_id`, `_resource_type`, `_resource_id` | Escopo/identificadores sujeitos às aprovações |
| Ambiente/serviço | `_environment`, `_service` | Ambiente aprovado e `synergia-audit-projector` |
| Revisão do coletor | `_application_version`, `_version_context` | Versão configurada/verificada do coletor; contexto `collector_release` |
| Revisão histórica do emissor | `_emitter_version` | `unknown`: as fontes não persistem essa revisão; não atribuir retrospectivamente a versão do coletor |
| Metadados permitidos | `_meta_CHAVE` | Inteiros, strings enumeradas, digest e booleanos 0/1; nenhum objeto aninhado |

O formato exportado preserva campos conhecidos; a adição de fontes não autoriza
aceitar nomes arbitrários de campos, streams ou índices. Routing e retenção
continuam sendo configuração administrativa do Graylog.

Em containers existe o perfil opt-in `graylog`, com tarefa finita
`graylog-worker`, sem restart/agendamento automático. `GRAYLOG_CONFIG_DIR` é um
diretório privado externo contendo `config.json` e certificados referenciados
por caminhos **dentro do container**, como `/run/synergia-graylog/ca.pem`.
O bind é somente leitura e chega exclusivamente ao coletor. Preparar acesso ao
UID/GID `10001:10001` sem abrir permissões para outros usuários; não usar `777`.
O default `/dev/null` não habilita uma instalação funcional do coletor.

Depois de um `apply`/`verify` aprovado, agendar lotes com a mesma revisão/imagem e
configuração da release. A CLI de deploy reconhece o serviço, fixa sua imagem
e bloqueia atualização enquanto um coletor estiver ativo. Pausar o agendador,
aguardar o lote terminar e só então atualizar/recuperar a aplicação.
O deploy não inicia nem testa a disponibilidade do Graylog.

```bash
docker compose --project-name synergia --env-file /caminho/privado/homologation.env --profile graylog run --rm --no-deps graylog-worker
```

Esse comando é uma operação especializada após deploy; conferir que
`SYNERGIA_IMAGE_TAG` resolve a imagem confirmada da release antes de executá-lo.
Não usar a tag `local` para inferir qual imagem foi validada pela automação.
Na execução Windows pelo Python do host, um responsável deve injetar
`DATABASE_URL` pelo mecanismo privado aprovado e manter o banco inacessível
externamente. Não existe API pública para reenvio ou administração do coletor.

## 5. Rodada de integração em um ambiente escolhido

Solicitar primeiro uma instância/banco de homologação isolado com identidades e
dados exclusivamente sintéticos. O coletor envia os eventos pendentes do escopo
aprovado; lote 1 não seleciona automaticamente um usuário de teste. Não usar o
primeiro ensaio para consumir uma fila compartilhada com eventos reais. O DBA
deve preparar o isolamento e o input/stream de teste antes do opt-in.

1. Registrar autorização, versão, hash do código, executor e horário UTC.
2. Com a TI, testar DNS/TCP da porta aprovada e confiança do certificado. Falha
   aqui não permite concluir qual equipamento bloqueou o acesso.
3. O operador do SYNERGIA gera eventos exclusivamente sintéticos: login inválido
   e uma autorização negada em conta/organização de teste. Registrar correlações;
   não usar senhas reais nem publicar identificadores de usuários.
4. Conferir `check`. Habilitar somente o escopo aprovado; iniciar com lote 1.
5. Executar um lote autorizado:

```powershell
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" run --allow-network
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" status
```

Para a etapa TCP, usar somente a configuração privada já conferida:

```powershell
$ConfigGraylog = Get-Content "$Graylog\config.json" -Raw | ConvertFrom-Json
$InputGraylog = [Uri]$ConfigGraylog.endpoint
Test-NetConnection -ComputerName $InputGraylog.DnsSafeHost -Port $InputGraylog.Port
```

Esse teste não autentica, não envia evento e não confirma a confiança TLS. Não
publicar sua saída bruta: ela pode conter endereços da rede interna.

6. Solicitar ao operador Graylog uma pesquisa por `event_id`, `short_message`,
   `correlation_id`, `origin`, `environment` e período. Campos adicionais GELF
   enviados com `_` são pesquisados no Graylog normalmente sem esse prefixo.
7. Reconciliar os IDs e contagens de **eventos distintos**. `202` significa
   aceitação HTTP para processamento, não prova de indexação, pesquisa ou retenção.
8. Registrar evidência de recebimento pesquisável, indisponibilidade controlada,
   recuperação e ausência de duplicidade lógica; aplicar o roteiro abaixo.

## 6. Falhas, reinício, reenvio e deduplicação

| Estado | Significado e próxima ação |
| --- | --- |
| `pending` | Não enviado ou recusa comprovadamente sem aceitação; aguardar prazo do próximo lote |
| `inflight` | Intenção persistida antes do POST; se o processo parar, vira `uncertain` no próximo lote |
| `accepted` | Input retornou `202`, ou operador confirmou recebimento; não é reenviado |
| `uncertain` | Timeout, falha de rede, interrupção ou resposta ambígua; pesquisar antes de decidir |
| `blocked` | Contrato inválido, escopo não aprovado, redirect ou recusa; corrigir causa antes de reabrir |
| `exhausted` | Orçamento de tentativas terminou; permanece persistido e exige decisão autorizada |

Timeout pode ocorrer **depois** da aceitação: não existe retry automático nesses
casos. Apenas os códigos incluídos em `retryable_statuses`, após confirmação de
não aceitação no contrato, entram em backoff exponencial com jitter, limitado a
uma hora. Um lote tem até 100 itens; tentativas entre 1 e 20; timeout até 30 s.
Não há laço infinito. O agendador executa lotes posteriores e deve alertar sobre
eventos retidos. Outro coletor não obtém o lock enquanto um lote estiver ativo.

Inspecionar uma janela (UTC, até 31 dias) ou um ID:

```powershell
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" status --from INICIO_ISO_COM_FUSO --to FIM_ISO_COM_FUSO
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" status --event-id ID_SHA256
```

A listagem é limitada aos primeiros 100 resultados; reduzir o período quando
necessário. Contagens da fila são globais. `event_id` é SHA-256 de origem, ID e
instante UTC imutável do evento, normalizado com microssegundos. Assim, uma
ocorrência futura com sequência numérica reutilizada não assume o ID da antiga.
O identificador permanece
estável entre tentativas e sem reutilizar o campo reservado GELF `_id`.

Depois da pesquisa e da janela de espera acordada, escolher **uma** resolução:

```powershell
.\.venv\Scripts\python.exe scripts\process_graylog.py --config "$Graylog\config.json" reconcile --event-id ID_SHA256 --resolution confirm_received --operator-id UUID_OPERADOR_APROVADO --evidence-id UUID_EVIDENCIA_PRIVADA --authorize
```

- `confirm_received`: evento incerto/aceito encontrado; registra a confirmação
  pesquisável em `confirmed_at` e não faz POST.
- `confirm_absent`: somente evento incerto, após evidência de ausência avaliada
  pelo responsável; libera nova tentativa com o mesmo ID.
- `requeue`: somente bloqueado/esgotado, depois de corrigir a causa.

Toda decisão registra UUID técnico do operador e referência UUID à evidência
mantida no repositório corporativo privado. Não usar nome, e-mail ou URL no
argumento. O orçamento é renovado explicitamente; o histórico anterior permanece.

**GELF HTTP não oferece por si só confirmação de indexação nem exatamente uma
vez.** Um ID estável não ativa deduplicação automática no Graylog. A projeção
local impede reenvio de IDs aceitos e mantém ambiguidades para reconciliação;
um `confirm_absent` incorreto pode duplicar fisicamente uma mensagem. O operador deve
validar pesquisa/contagem por ID distinto e, se exigir unicidade física mesmo
após perda de resposta, um mecanismo corporativo idempotente antes da ingestão.
Esse aceite externo permanece pendente; não declarar deduplicação corporativa
comprovada apenas pelos testes locais.

Para recuperar histórico anterior à migration, usar `backfill --origin ORIGEM
--from INICIO --to FIM --operator-id UUID --evidence-id UUID --authorize`.
Cada chamada processa um lote e persiste cursor por origem/janela; repetir até
`completed=true`. Janelas são `[início,fim)`, até 31 dias. IDs já existentes,
inclusive aceitos, não são duplicados. Inserts futuros são capturados pelos
triggers mesmo se o horário do evento for antigo ou o commit terminar depois.
Não apagar controles, checkpoints ou histórico para reenviar.

O primeiro uso vincula destino e política de escopo/identificadores ao banco.
Alteração posterior é recusada; rotação de credencial/CA e mudança de versão da
aplicação são permitidas. Mudança de destino/escopo exige plano aprovado de
migração e reconciliação, fora de uma simples edição do arquivo. Não apagar o
vínculo para contornar a proteção. Restore de um backup antigo pode perder
recibos recentes: manter o coletor parado até reconciliar esses IDs com o destino.

## 7. Métricas, logs técnicos e governança

`/metrics` mantém sua autenticação técnica existente. O scrape lê somente o
PostgreSQL; nunca lê a credencial do input nem consulta a rede Graylog:

- `synergia_graylog_queue{state}`: pendências e estados retidos;
- `synergia_graylog_oldest_age_seconds`: idade da pendência mais antiga;
- `synergia_graylog_delivery_results_total{result}`: intenções, aceitações,
  recusas, retentativas (`pending`), falhas esgotadas, ambiguidades e decisões;
- `synergia_graylog_last_run_timestamp_seconds`: último lote concluído;
- `synergia_graylog_collection_success`: disponibilidade da coleta dessas métricas.

Criar alertas corporativos para atraso, ausência de execução, fila crescente e
qualquer `uncertain`/`blocked`/`exhausted`. Não colocar IDs ou dados pessoais nas
labels. O histórico do coletor não entra no inventário exportado, evitando
recursão. A saída do worker contém apenas contagens/códigos; nenhum corpo de
resposta, segredo ou erro bruto. Exit 0: comando concluído/desabilitado; exit 1:
falha local ou lote com eventos retidos; exit 2: contrato/opt-in inválido.

O stream de auditoria recebe somente o contrato sanitizado. Logs técnicos
`synergia` em JSON, sem URL crua/query, podem ser coletados por infraestrutura
aprovada em **outro** stream, com allowlist própria e retenção definida na operação.
Não instalar envio indiscriminado de stdout/stderr de API, banco, proxy ou
containers. Stack traces e mensagens de bibliotecas não passam automaticamente
pelo sanitizador. Prometheus continua responsável pelas métricas agregadas.

O inventário registra a realidade: LLM do demonstrador sintético implementada,
modelo/digest, executor, operação, ferramenta `none`, duração e fallback.
Tokens não são disponibilizados pelo adaptador atual. RPA Smart Office e uso
autônomo de ferramentas LLM permanecem `not_implemented`; só há contrato futuro,
sem emitir eventos fictícios. Baseline determinístico não emite execução LLM.

Em uma implantação futura, registrar retenção e descarte, revisão periódica de acesso,
responsáveis e procedimento de incidente. Não há purge automático da fila ou
histórico nesta entrega; monitorar crescimento e manter backup consistente.
Em incidente: suspender o agendador, preservar trilhas, restringir a credencial,
investigar por ID/correlação, rotacionar pelo canal privado e testar um lote
sintético antes da retomada. Não apagar trilhas nem exportar conteúdo bruto.

## 8. Validação e limites

Os testes automatizados usam PostgreSQL sintético e um receptor HTTPS em
loopback; esse receptor **não é um servidor Graylog**. Eles validam persistência,
TLS, campo permitido, falha e retomada. O teste TLS usa OpenSSL apenas para criar
certificados temporários; nenhum certificado/chave de teste é versionado.

Separadamente, o [laboratório](graylog-laboratorio.md) foi executado com Graylog
Open 7.2.2 real: 12 eventos reconciliados entre fila e pesquisa, credencial
incorreta recusada, recuperação após interrupção e repetição sem reenvio.
As pesquisas dos cenários também foram verificadas no navegador. Consulte o
[relatório e as evidências](evidence/issue-178-graylog-validation.md) para
resultados, screenshots e limites; isso não constitui aceite de implantação.

```bash
cd backend
pytest -q tests/test_graylog.py tests/test_graylog_https.py
pytest -q -m integration tests/test_graylog_persistence.py
```

Os testes de persistência precisam de `DATABASE_URL` **de teste** e permissão
de criar um banco sintético temporário; não apontar testes para produção.
Nenhum comando deste manual constitui autorização de deploy ou de acesso LG.
Evidências corporativas devem ser sanitizadas e registrar aprovação, revisão,
janela, IDs técnicos, contagens distintas, resultado e limitações, sem input real,
credenciais, configuração privada, nomes, e-mails, IPs ou payloads.

Referências primárias: [GELF HTTP e respostas](https://go2docs.graylog.org/current/getting_in_log_data/gelf.html),
[formato GELF](https://go2docs.graylog.org/current/getting_in_log_data/gelf_format.html),
[auditoria do SYNERGIA](audit-export.md) e
[inventário de eventos](audit-event-inventory.json).
