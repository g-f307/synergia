# #171 — preparação e rodada interna bloqueada por conectividade

## Resultado e decisão

Em **2026-11-06**, o operador relatou a execução da preparação no Windows
conectado à rede da LG. A leitura do JSON privado e o comando `check` foram
aprovados. A consulta GET da documentação terminou com `TimeoutError`, o JSON
não abriu no navegador e o teste TCP retornou `False` para o destino
configurado. **Não foi possível estabelecer a conectividade necessária para
prosseguir com a PoC nessa estação.**

A rodada foi interrompida antes dos cenários de envio. Não houve POST de envio
no roteiro relatado, nem recebimento comprovado. **A #171 permanece aberta e
dependente de acesso; a #170 continua aguardando contrato e decisão.** A decisão
de integrar, integrar com restrições ou não integrar continua pendente. O
bloqueio de acesso não constitui decisão definitiva de rejeitar a integração.

O resultado não identifica isoladamente firewall, rota, rede da estação, proxy,
endereço desatualizado ou indisponibilidade do serviço. A causa específica deve
ser confirmada pela TI ou responsável pela API. Não foi caracterizada resposta
HTTP, falha de autenticação ou comportamento de envio da API.

## Origem e limites da evidência

- Fonte: comandos e resultados relatados pelo operador durante a execução
  assistida por conversa; o responsável pela implementação não acessou a
  estação, a rede interna nem os arquivos privados.
- Data do relato: 2026-11-06, contexto America/Manaus; horários exatos de cada
  tentativa não foram coletados.
- Ambiente: Windows com Python na rede da LG; versão do Python e revisão Git
  efetivamente executadas na estação não foram coletadas.
- Referência da preparação publicada antes da rodada:
  `5be58aef7d6cf8169b80f3648ad525609b795c65`, PR #180. Essa referência não
  substitui a conferência da revisão usada na estação.
- Não foi obtida especificação pela PoC; seu hash/versão e a semântica do
  serviço continuam sem comprovação.
- Este registro contém somente resultados sanitizados. Não reproduz IP, URL,
  porta corporativa, domínio, endereço de e-mail, senha, configuração privada,
  conteúdo da especificação, resposta bruta, screenshot ou caminho da estação.
- Não há atestado independente de conectividade, autenticação, autorização,
  entrega ou aceite corporativo. `authorization_confirmed` é uma declaração
  local e não comprova autorização perante o serviço.

## Preparação entregue

1. Cliente isolado em `scripts/lg_email_poc.py`, com biblioteca padrão Python,
   sem alterações no transporte de e-mail da aplicação.
2. Manual Windows desde a clonagem, alternativa de kit ZIP com hashes,
   configuração privada e proteção da área de evidências.
3. Cenários individuais sem anexos ou dados de negócio; opt-in de envio,
   allowlists, tentativa persistida antes da chamada, lock, ausência de retries
   e reconciliação humana.
4. Exportação de metadados permitidos e modelo de contrato com critérios ainda
   pendentes; HTTP 200 não equivale a entrega.
5. Preparação verificada no WSL com 28 testes sintéticos, lint, formatação,
   extração do kit e conferência de hashes. Não foi relatada execução desses
   28 testes na estação da LG. A CI da referência de preparação foi aprovada:
   [execução 350](https://github.com/g-f307/synergia/actions/runs/42040946417).

## Sequência da rodada interna

| Etapa | Execução e resultado relatados | Alcance da conclusão |
| --- | --- | --- |
| Área privada | `init`, ajuste de permissões e edição local do JSON | Pasta e arquivo preparados; não é evidência de envio ou auditoria completa de ACL |
| Configuração inicial | `check`, `spec --allow-network` e prévia `probe --case single` retornaram erro genérico | Nenhum desses retornos comprova sucesso de consulta ou de prévia |
| Leitura e sintaxe | Diagnóstico local retornou `JSON_VALIDO`; Python confirmou acesso ao arquivo | JSON legível e sintaticamente válido |
| Validação local | `check` retornou `configuration_valid_no_network` | Regras locais aprovadas; não comprova rede ou autenticação |
| Certificados no JSON | `ca_file`, `client_cert_file` e `client_key_file` sem arquivos configurados | Descartada a hipótese de referência explícita inexistente nesses campos |
| Correção do diagnóstico auxiliar | O primeiro snippet passava o arquivo a `load_config`, que espera a pasta; foi corrigido para receber a pasta | O `FileNotFoundError` desse snippet era um erro do diagnóstico fornecido, não evidência de falha da API nem causa comprovada do erro inicial do CLI |
| Consulta à documentação | `spec --allow-network` retornou erro genérico; o operador estimou cerca de 10 segundos em uma tentativa | Duração aproximada relatada; sem medição formal nem resposta HTTP registrada |
| Diagnóstico GET corrigido | Configuração aprovada, etapa de consulta à documentação, `TimeoutError` | A operação não concluiu a consulta dentro do tempo de espera |
| Navegador | O endereço do JSON OpenAPI não abriu na mesma estação | Consulta também não concluída pelo navegador |
| Conexão TCP | `Test-NetConnection` retornou `TCP_OK=False` | Conexão TCP não estabelecida para o destino configurado naquele teste |
| Envio e reconciliação | Não executados | Não há aceitação, entrega ou recebimento comprovados |

O timeout observado ocorreu na consulta GET da documentação. **Não foi
executado o cenário `timeout` de POST**, nem foi ensaiada desconexão após uma
mensagem possivelmente aceita. Não há evidência corporativa de idempotência,
duplicidade, retry, limites ou semântica de HTTP 200.

## Estado dos critérios da issue

| Critério | Estado ao encerrar a rodada |
| --- | --- |
| Conectividade e autorização confirmadas internamente | Bloqueado: conexão não estabelecida; autorização no serviço não comprovada |
| Mensagem sintética recebida e correlacionada | Não executado |
| Formatos To/CC, Unicode e campos obrigatórios comprovados | Não executado |
| Semântica de 200 e principais erros caracterizada | Não comprovado; nenhum código HTTP coletado |
| Timeout de envio e risco de duplicidade com decisão segura | Não executado; somente timeout de GET observado |
| Limites e restrições corporativas relevantes registrados | Pendentes de confirmação |
| Evidência pública sanitizada | Este relato não inclui os valores privados; revisão corporativa e aceite permanecem pendentes |
| Decisão sobre iniciar a #170 | Não iniciar enquanto acesso, contrato e decisão estiverem pendentes |
| Contrato baseado em execução além do Swagger | Não aprovado; nenhuma validação de envio realizada |

## Dependência externa e retomada

A TI ou responsável pelo serviço deve confirmar, pelo canal interno:

1. Destino e porta atuais, disponibilidade do serviço e origem de rede
   autorizada para essa estação.
2. Requisitos de rota, firewall, VPN, rede específica ou proxy, conforme o
   diagnóstico da equipe; este registro não afirma qual deles causou a falha.
3. Mecanismo de autenticação/autorização e acesso ao JSON OpenAPI.
4. Conta, caixas de teste, regras e janela autorizadas para o primeiro envio.

Responsáveis nominais e prazo de liberação não foram informados. Não há
previsão de retomada registrada. Depois da confirmação de acesso:

1. Conferir revisão da ferramenta, configuração privada e permissões; preservar
   as evidências existentes.
2. Validar conexão TCP e acesso à documentação. Se a solução exigir proxy,
   confirmar a configuração aprovada com a equipe.
3. Executar `check` e `spec --allow-network`; obter e registrar o hash da
   especificação antes de qualquer POST.
4. Seguir a prévia e o envio individual de `single`, com destinatário
   acompanhando e reconciliação pelo marcador; só então avançar aos demais
   cenários autorizados.
5. Preencher o contrato e a matriz com resultados efetivamente observados,
   revisar a exportação sanitizada e registrar decisão explícita para a #170.

A preparação e o relato do bloqueio podem ser revisados no PR sem encerrar a
#171 como validada. Este registro complementa o
[manual](../lg-email-poc.md) e o [contrato](../lg-email-api-contract.md).
