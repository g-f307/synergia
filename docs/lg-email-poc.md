# PoC da API de e-mail da LG — issue #171

Este roteiro prepara e executa a validação **no Windows da LG**, com Python
3.11 ou superior. Não precisa instalar bibliotecas, executar `pip`, Node,
Docker, PostgreSQL, backend ou frontend. O utilitário é isolado e não altera
o transporte de e-mail da aplicação. A rede interna só é acessada nos comandos
`spec --allow-network` e `probe --send --allow-real-send`.

**Estado inicial: não executado na LG; #170 aguardando contrato e decisão.**
Testes automatizados sintéticos comprovam o comportamento da ferramenta,
não conectividade, autenticação ou entrega corporativa. Não encerrar a #171
como validada antes da execução interna e revisão das evidências.

## 1. Combinar a janela com os responsáveis da LG

Antes de qualquer envio, obtenha em canal interno autorizado:

- autorização para executar a PoC e transferir o código ao computador;
- URL exata de `POST /SMTP` e URL do JSON OpenAPI (a página Swagger HTML
  não é o JSON); hosts, portas, rota de rede/proxy e certificados exigidos;
- conta/identidade autorizada, mecanismo de autenticação e nomes dos headers;
- remetente efetivo do serviço, domínios internos e lista **nominal** de caixas
  destinatárias aprovadas; os proprietários devem acompanhar o recebimento;
- formato autorizado para múltiplos `To`/`CC`, regras de HTML, CC e conteúdo;
- limites conhecidos de assunto, corpo, destinatários e requisição;
- permissão individual para casos negativos e timeout; não fazer carga ou
  descobrir limites por tentativa e erro;
- acesso ao responsável pelos logs para correlacionar aceitação, entrega,
  rejeição e possível duplicidade;
- pasta privada autorizada, ACL, política de retenção e autorização para
  retirar **somente** o relatório sanitizado da rede interna.

Não invente autenticação com base no Swagger. Se exigir Windows integrado
(NTLM/Kerberos), OAuth interativo ou certificado em store não exportável, este
cliente não implementa esses fluxos. Combine com a equipe um mecanismo
aprovado compatível (headers já emitidos ou mTLS PEM), ou registre bloqueio e
adapte a ferramenta antes de enviar. Não converter nem exportar chaves sem
autorização. HTTP sem TLS requer autorização expressa; nunca desative a
verificação de certificados para contornar um erro.

## 2. Obter o código sem depender de internet na LG

### Opção A — GitHub liberado ou espelho Git interno

No PowerShell da máquina com acesso ao repositório:

```powershell
git clone https://github.com/g-f307/synergia.git
Set-Location synergia
git switch feature/171-lg-email-poc
git rev-parse HEAD
Test-Path scripts\lg_email_poc.py
```

Use a branch publicada acima; após o merge do PR, a `main` também conterá o
kit. Um clone da `main` antes do merge **não** conterá esses arquivos.
Se usar espelho interno,
substitua a URL pela fornecida pela LG, mantendo-a fora da documentação pública.
Autentique pelo mecanismo aprovado; não coloque token na URL nem no terminal.

### Opção B — transferência aprovada, recomendada na rede restrita

Ainda na máquina de preparação, depois de obter a revisão correta, crie um
kit que contém só o utilitário, os testes sintéticos e os dois documentos.
Também funciona com as alterações locais ainda não commitadas:

```powershell
$Kit = Join-Path $env:TEMP ("synergia-171-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path "$Kit\scripts", "$Kit\backend\tests", "$Kit\docs" | Out-Null
Copy-Item scripts\lg_email_poc.py "$Kit\scripts\"
Copy-Item backend\tests\test_lg_email_poc.py "$Kit\backend\tests\"
Copy-Item docs\lg-email-poc.md, docs\lg-email-api-contract.md "$Kit\docs\"
git rev-parse HEAD | Set-Content -Encoding ascii "$Kit\BASE-COMMIT.txt"
Push-Location $Kit
Get-ChildItem scripts, backend, docs -File -Recurse | ForEach-Object {
    $Relative = $_.FullName.Substring($Kit.Length + 1)
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
    "$Hash  $Relative"
} | Set-Content -Encoding ascii SHA256SUMS.txt
Pop-Location
$Zip = "$Kit.zip"
Compress-Archive -Path "$Kit\*" -DestinationPath $Zip
Get-FileHash -Algorithm SHA256 -LiteralPath $Zip
Write-Output $Zip
```

Registre o hash do ZIP pelo canal de transferência aprovado. `BASE-COMMIT`
identifica a base; os hashes dos arquivos identificam alterações locais do kit.
Não copie `.env`, `.git`, arquivos de agentes, pasta privada ou respostas reais.
Se precisar de todo o histórico e houver Git na LG, a alternativa é criar um
`git bundle` **da revisão já commitada**, transferi-lo pelo canal autorizado e
clonar o bundle; um bundle não inclui alterações locais não commitadas.

O Python já disponível na LG deve ser 3.11+. Se não for, a TI deve fornecer
um instalador Windows offline aprovado, da arquitetura correta, com hash e
assinatura conferidos, pelo mesmo canal permitido. Não dependa de baixar o
Python dentro da rede restrita.

No computador da LG, usando os caminhos aprovados pela TI:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath C:\Transferencia\synergia-171.zip
# Compare com o hash recebido antes de extrair; interrompa se divergir.
Expand-Archive -LiteralPath C:\Transferencia\synergia-171.zip -DestinationPath C:\Trabalho\synergia-171
Set-Location C:\Trabalho\synergia-171
$ManifestRoot = (Get-Location).Path
Get-Content SHA256SUMS.txt | ForEach-Object {
    $Expected, $Relative = $_ -split '  ', 2
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ManifestRoot $Relative)).Hash
    if ($Expected -ne $Actual) { throw "Integridade do kit divergente" }
}
python --version
python -m unittest discover -s backend/tests -p test_lg_email_poc.py -v
python scripts/lg_email_poc.py --help
```

Se o executável se chama `py`, use `py -3.11` no lugar de `python` em todos os
comandos. Não use `Invoke-WebRequest`, `curl` ou scripts obtidos da internet
como parte de uma instalação improvisada. Os testes acima não acessam rede,
não enviam e-mail e não dependem de `pytest`.

## 3. Criar a área privada e configurar

Na raiz do clone ou kit, escolha uma pasta **nova**, fora do repositório,
não sincronizada, aprovada para evidências privadas. Os caminhos abaixo são
exemplos locais; substitua-os conforme a política da LG:

```powershell
$Poc = 'C:\DadosPrivados\synergia-email-poc-171'
python scripts/lg_email_poc.py --workspace "$Poc" init
# Quando permitido pela TI, restrinja a herança ao usuário atual:
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls "$Poc" /inheritance:r /grant:r "${Identity}:(OI)(CI)F"
icacls "$Poc"
notepad "$Poc\config.json"
```

Se a LG exigir grupos de TI/backup na ACL, peça à TI para aplicar a política
correta em vez de remover essas permissões. O Python aplica modo `0600/0700`
em sistemas POSIX; no Windows a proteção depende da ACL. Não preencha dados
reais antes de a pasta estar protegida. Não use transcrição de terminal nem
capturas de tela com configuração ou respostas.

O arquivo gerado tem todos os campos. Edite **somente** essa cópia privada:

| Campo | Como preencher na LG |
| --- | --- |
| `endpoint` | URL exata, sem credencial/query, terminando em `/SMTP`; prefixo de implantação é permitido |
| `openapi_url` | URL do JSON OpenAPI na mesma origem (esquema, host e porta) |
| `approved_internal_hosts` | Hosts internos exatos, minúsculos, autorizados pela equipe |
| `approved_internal_domains` | Domínios internos exatos dos destinatários, minúsculos |
| `approved_recipients` | Lista de caixas internas aprovadas, no máximo 10 |
| `to` | Subconjunto aprovado; primeiro será usado em `single`, todos em `to_multiple` |
| `cc` | Subconjunto aprovado; enviado somente no caso `cc` |
| `recipient_format` | `comma`, `semicolon`, `repeated` ou `json_array`, conforme autorização |
| `authorization_confirmed` | `true` somente após confirmar autorização e identidade |
| `headers_env` | Mapeia nome de header para **nome de variável de ambiente**, nunca para o segredo |
| `ca_file` | `null` para CAs padrão; ou caminho privado do PEM de CA corporativa |
| `client_cert_file`, `client_key_file` | `null` ou caminhos privados dos PEM mTLS aprovados |
| `use_system_proxy` | `false` por padrão; `true` somente se o proxy corporativo for necessário e autorizado |
| `allow_http` | `false`; `true` só com aprovação de HTTP na rede interna |
| `timeout_seconds` | Timeout normal de socket entre 1 e 120 segundos |
| `short_timeout_seconds` | Entre 0,1 e 5 segundos, apenas para o caso `timeout` |
| `known_body_limit_bytes` | `null` ou limite do Body **em bytes**, confirmado pelo responsável, até 65.536 |

Hosts e domínios são declarações da equipe, não uma descoberta automática de
rede interna. A ferramenta recusa destinos fora dessas listas; não consegue
comprovar sozinha que uma caixa ou domínio pertence à LG. Limites locais: 10
caixas por lista, requisição de 128 KiB, captura de resposta de 1 MiB e OpenAPI
JSON de 8 MiB. Não são limites descobertos da API. Se o limite corporativo
for maior que o orçamento local, registre-o por documentação/confirmação e
deixe o caso `over_limit` não executado, sem aumentar carga para descobri-lo.

Os cabeçalhos não recebem valores literais no JSON. Por exemplo, se o
mecanismo autorizado usar um header `Authorization`, configure privadamente
`"headers_env": {"Authorization": "LG_EMAIL_POC_AUTH"}` e carregue seu valor
sem gravá-lo no histórico do PowerShell:

```powershell
$CredentialValue = Read-Host 'Valor completo do header autorizado (inclua o esquema, se houver)' -AsSecureString
$env:LG_EMAIL_POC_AUTH = [System.Net.NetworkCredential]::new('', $CredentialValue).Password
Remove-Variable CredentialValue
python scripts/lg_email_poc.py --workspace "$Poc" check
```

Se não houver header, mantenha `{}`. O modo `network_only` significa apenas
que este cliente não adicionou headers de autenticação: o mecanismo real
(restrição de rede, identidade, mTLS etc.) precisa ser descrito no contrato.
O cliente não solicita nem renova tokens. Variáveis existem somente nesse
processo; limpe-as ao terminar. Para chave PEM criptografada/fluxo SSO não
suportado, registre bloqueio em vez de tentar remover a proteção.
Use `headers_env` somente para os headers aprovados. Não reutilize uma chave
de idempotência estática entre cenários: este kit não gera nem presume esse
contrato. Se a API exigir chave por envio, confirme o contrato e adapte o
cliente antes da rodada, mantendo a decisão sobre deduplicação pendente.

## 4. Capturar a especificação e confirmar a conectividade

`check` só valida configuração e material TLS local; **não** prova conexão.
Para fazer uma única leitura autorizada:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" spec --allow-network
```

O comando faz GET, recusa redirecionamentos e não segue `$ref`, `servers` ou
links da especificação. Grava o JSON **privado** e o SHA-256 dos bytes recebidos.
Exige `POST /SMTP` com `multipart/form-data` declarado; isso confirma a forma
documentada, não a semântica do envio. Verifique campos, autenticação e schema
de resposta com o responsável, inclusive quando houver `$ref`.

Se o documento estiver em outra origem, só existir no navegador autenticado
ou estiver em YAML, obtenha **exportação JSON** aprovada e salva privadamente:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" spec --file "$Poc\exportacao-openapi.json"
```

O hash passa a identificar exatamente o JSON exportado. Nesse modo não houve
GET pelo utilitário; confirme conectividade separadamente pelo primeiro POST
aprovado e registre o método de obtenção no contrato. O `openapi_url` na
configuração continua na mesma origem do endpoint, mesmo que não seja usado.
Não substitua especificação já registrada na sessão. Se houver mudança de
versão, combine nova sessão preservando a anterior.

## 5. Executar o primeiro envio e confirmar recebimento

Faça a prévia; não há rede nem impressão de destinatários:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" probe --case single
```

Com os destinatários acompanhando e a autorização confirmada:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" probe --case single --send --allow-real-send
```

São enviados somente `Subject`, `Body` e `To`, sem `CC` nem `Files`.
Cada mensagem possui um UUID sintético no assunto/corpo para correlação.
O script não permite informar conteúdo de negócio nem anexos.

1. Anote o `marker` retornado. Se o processo foi interrompido, consulte
   privadamente `attempt-single.json` para recuperar o marcador.
2. Peça ao destinatário confirmar **esse marcador**, conteúdo, codificação,
   remetente, caixa correta e número de cópias; correlacione com os logs quando
   disponíveis. Confira todos os destinatários/CC no respectivo cenário.
3. Só após confirmação real, registre:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" reconcile --case single --outcome received --source recipient
```

`received` significa que o operador confirmou o caso completo, inclusive
**todas** as caixas previstas e ausência de destino inesperado. Não basta
receber em uma das caixas. A ferramenta não lê caixas postais nem valida a
declaração humana. Registre contagens e duplicidade no contrato sanitizado.

HTTP 200 resulta em `http_accepted_unconfirmed`: não equivale a entregue.
Mesmo HTTP 4xx/5xx requer reconciliação, pois a semântica do serviço está em
avaliação. Se os logs corporativos comprovarem **não aceitação**, use:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" reconcile --case single --outcome not_accepted --source corporate_log
```

`not_received` e `unknown` **não** comprovam não aceitação e encerram a sessão
como inconclusiva, bloqueando novos envios. Um resultado `unexpected_delivery`
também bloqueia a sessão: interrompa a validação e acione o responsável.
Não preencha `received` por inferência de um código HTTP.

## 6. Matriz: executar um caso por vez

Não use laços, execução paralela ou automação em lote. Antes de cada POST,
faça a prévia, confirme autorização e, depois, reconcilie o resultado antes
de passar ao próximo. Um caso só pode ser enviado **uma vez por sessão**.
O arquivo `send.lock` também impede processos concorrentes na mesma pasta.

| Caso `--case` | O que confirmar |
| --- | --- |
| `single` | Um destinatário; CC/Files omitidos; remetente efetivo |
| `unicode` | Assunto e corpo UTF-8 com acentos, japonês e duas quebras de linha |
| `to_multiple` | Pelo menos duas caixas distintas aprovadas; formato autorizado |
| `cc` | CC aprovado; confirmar todas as caixas e a forma de múltiplos CC |
| `cc_empty` | Mesmo conteúdo básico com campo CC presente e vazio |
| `html` | HTML estático sem links/imagens; distinguir renderização e texto literal |
| `subject_missing` / `subject_empty` | Subject omitido versus presente vazio |
| `body_missing` / `body_empty` | Body omitido versus presente vazio |
| `to_missing` / `to_empty` | To omitido versus presente vazio; verificar ausência de fallback inesperado |
| `invalid_recipient` | Valor fixo sintaticamente inválido `invalid@@invalid.invalid`; nenhum domínio externo válido |
| `over_limit` | Body ASCII de limite conhecido + 1 byte; sem busca de limite |
| `timeout` | Conteúdo básico com timeout curto previamente aprovado |

Exemplo de próximo caso positivo, após reconciliar `single`:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" probe --case unicode
python scripts/lg_email_poc.py --workspace "$Poc" probe --case unicode --send --allow-real-send
# Confirme primeiro o recebimento e o conteúdo no destino:
python scripts/lg_email_poc.py --workspace "$Poc" reconcile --case unicode --outcome received --source recipient
```

Casos negativos (todos a partir de `subject_missing` na tabela, incluindo
`timeout`) exigem autorização adicional do responsável e a flag:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" probe --case subject_missing
python scripts/lg_email_poc.py --workspace "$Poc" probe --case subject_missing --send --allow-real-send --approved-negative-case
# Somente se o responsável confirmar não aceitação por logs:
python scripts/lg_email_poc.py --workspace "$Poc" reconcile --case subject_missing --outcome not_accepted --source corporate_log
```

Não execute os exemplos de reconciliação como se fossem resultados esperados:
substitua-os pelo resultado realmente confirmado. Não force 429/500, erro de
autorização ou indisponibilidade contra o serviço; caracterize-os pelos códigos
observados, documentação e confirmação do responsável. Limites de assunto,
HTML, taxa e destinatários também devem ser confirmados sem carga/fuzzing.

Para formatos alternativos, `comma` usa vírgula; `semicolon`, ponto e vírgula;
`repeated`, partes multipart repetidas; `json_array`, array JSON como valor
textual do campo. São hipóteses de formato, não suporte já comprovado. Teste
somente os autorizados. Se precisar experimentar outro formato após a primeira
rodada, combine nova sessão, com pasta e configuração próprias e resultados
anteriores preservados; não apague tentativas para permitir reenvio.

### Timeout, desconexão e duplicidade

O timeout é de operações de socket, **não um prazo total rígido**: uma resposta
que chega lentamente pode demorar mais. A leitura é limitada em bytes.
`timeout` pode retornar normalmente; isso não comprova comportamento sob
timeout. Nunca cause interrupção de rede compartilhada para induzir a falha.
Se for necessário exercitar desconexão, combine com a equipe um mecanismo
controlado e isolado e documente o resultado manualmente.

`timeout_uncertain`, `transport_uncertain` ou tentativa sem resultado (processo
interrompido) significam que a mensagem **pode ter sido aceita**. Não há retry,
nem chave de idempotência inventada. Peça consulta ao destinatário e logs pelo
marcador. Ausência na caixa não autoriza repetir. Só `received` ou
`not_accepted` comprovado por log permite passar a outro caso; o mesmo caso
continua bloqueado. Registros de reconciliação são finais e não sobrescritos.
Se registrar `unknown`/`not_received`, mantenha o bloqueio e conclua a rodada
como inconclusiva; não abra outra sessão para contornar incerteza.

Se houver encerramento forçado e `send.lock` permanecer: pare as instâncias
do utilitário, confira a tentativa e reconcilie com o responsável. Só depois
de comprovar aceitação/recebimento ou não aceitação e ausência de processo
em execução, a operação pode remover **apenas o lock**, mantendo toda evidência.
Na dúvida, preserve o bloqueio. Não apague `attempt-*`, `result-*` ou `receipt-*`.

## 7. Examinar respostas de forma privada e gerar relatório

A pasta contém os arquivos abaixo. **Todos permanecem internos**, exceto
uma cópia do relatório sanitizado após revisão e autorização:

- `config.json`: configuração privada e nomes de variáveis, sem segredos literais;
- `openapi-private.json`: especificação com hosts, schemas e outros detalhes;
- `specification.json`: hash dos bytes originais e tamanho;
- `attempt-<caso>.json`: intenção durável, marcador e metadados lógicos;
- `result-<caso>.json`: código HTTP, classificação, duração e ausência de retry;
- `response-private-<caso>.json`: headers e corpo em hexadecimal, limitado a
  1 MiB; **hexadecimal não protege nem sanitiza**;
- `receipt-<caso>.json`: confirmação humana, origem e horário;
- `sanitized-report-<uuid>.json`: exportação reconstruída com campos permitidos.

Para abrir o corpo privado no terminal autorizado, sem gravar texto extra:

```powershell
python -c "import json,sys; from pathlib import Path; r=json.loads(Path(sys.argv[1]).read_text()); print(bytes.fromhex(r['body_hex']).decode('utf-8',errors='replace'))" "$Poc\response-private-single.json"
```

Não faça isso em sessão gravada, compartilhada ou com transcrição. Interprete
privadamente o código, estrutura do corpo e headers de correlação, erro,
`Retry-After` etc. Guarde identificadores reais apenas na área aprovada;
publicamente descreva o **tipo** do campo e vínculo lógico, sem seus valores.
Se `truncated` for `true`, a captura está incompleta. Não use seus bytes como
evidência de resposta completa. Em timeout/desconexão pode não existir captura.

Gere um novo relatório a qualquer momento depois de capturar a especificação:

```powershell
python scripts/lg_email_poc.py --workspace "$Poc" export
Get-ChildItem -LiteralPath "$Poc" -Filter sanitized-report-*.json
```

A exportação não inclui URL, domínios, destinatários, nomes de header,
respostas, mensagens de exceção nem conteúdo. Inclui hash, marcadores
sintéticos, horários, timeout, duração, formatos, campos lógicos, códigos e
confirmações declaradas. Cenários não tentados ficam `not_executed`.
`decision` permanece `pending_human_review`; o relatório não aprova a #170.
O validador recusa metadados fora dos valores/tipos permitidos. Isso não
substitui revisão humana nem comprova autenticidade da execução.

## 8. Concluir o contrato e a decisão da #170

Use [lg-email-api-contract.md](lg-email-api-contract.md) como modelo. Preencha
somente após a execução, usando dados agregados e termos lógicos. Anexe a
cópia revisada de `sanitized-report-*.json` quando a LG permitir sua retirada.
Não versione a pasta privada, logs brutos, prints ou especificação completa.

A equipe deve registrar explicitamente:

1. hash/versão da especificação, data, ambiente lógico e revisão/hash do kit;
2. autenticação, transporte, remetente e autorização, sem identificadores reais;
3. campos obrigatórios/vazios, formatos To/CC, texto/HTML/Unicode e limites;
4. cada código observado, schema lógico de resposta e evidência de recebimento;
5. semântica de 200, correlação e recurso aprovado de confirmação de entrega;
6. idempotência/deduplicação, quantidade de cópias, timeout e política de retry;
7. rate limit, retenção e políticas corporativas;
8. cenários não executados, dúvidas, riscos e responsáveis pelas pendências;
9. decisão `integrar`, `integrar com restrições` ou `não integrar` e se #170
   pode iniciar. Enquanto não houver evidência suficiente, manter `pendente`.

Não concluir "entregue" só por 200 nem concluir "idempotente" porque uma
mensagem chegou uma vez. Uma rodada sem duplicatas não comprova deduplicação.
Se não for possível confirmar timeout, políticas ou semântica, mantenha a
pendência ou restrição explícita, com decisão do responsável técnico.

Ao encerrar a sessão, limpe os valores de autenticação carregados:

```powershell
Remove-Item Env:\LG_EMAIL_POC_AUTH -ErrorAction SilentlyContinue
```

Repita para outros nomes usados em `headers_env`. Retenção e descarte dos
arquivos privados seguem a política da LG; não há limpeza automática.

## Códigos de saída e diagnóstico

| Código | Significado |
| --- | --- |
| `0` | Operação local concluída ou resposta 2xx capturada; não comprova entrega |
| `1` | POST sem 2xx completo, erro HTTP ou transporte incerto; não repetir |
| `2` | Pré-condição/operação recusada; conferir código lógico e pasta privada |

No PowerShell consulte `$LASTEXITCODE` logo após o comando. Mensagens de erro
são genéricas de propósito: não imprimem a exceção que pode conter segredo,
URL ou resposta. `previous_attempt_unresolved` exige reconciliação;
`case_already_attempted` impede reenvio; `negative_case_opt_in_required` exige
autorização individual; `specification_contract_not_found` exige conferir o
JSON/rota/multipart com o responsável. Erro de CA, autenticação ou proxy deve
ser resolvido com a equipe sem desativar TLS ou improvisar outro destino.
