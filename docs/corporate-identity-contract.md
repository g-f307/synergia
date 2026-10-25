# Contrato de identidade corporativa

Contrato de integração e plano de transição para a identidade corporativa da LG,
vinculado à issue [#144](https://github.com/g-f307/synergia/issues/144) e à
[ADR 0002](adr/0002-corporate-identity-contract.md). Versão do contrato:
`corporate-identity/1.0.0-draft`.

## Estado

O contrato está **definido do lado do SYNERGIA** e **aguarda dados externos**. Não
existe adaptador corporativo ativo: o provedor, o protocolo, o emissor, as claims
reais, a política de MFA e o processo de provisionamento ainda não foram
informados, e nenhum deles foi inventado. A homologação não depende deles, porque
o contrato é exercitado por um provider falso offline com identidades
sintéticas. A ativação de um adaptador real continua sendo um portão de
implantação separado (ver [runbook](runbooks/corporate-identity-activation.md)).

## Registro de decisões

Cada decisão tem responsável e estado. O registro canônico é
[`corporate-identity-decisions.json`](corporate-identity-decisions.json), validado
por `scripts/validate_identity_contract.py`. Estados: **pendente externa**
(depende da LG), **proposta** (da equipe SYNERGIA, aguardando confirmação) e
**decidida** (vigente, com evidência no repositório).

| ID | Decisão | Responsável | Estado | Comportamento provisório |
| --- | --- | --- | --- | --- |
| ID-P01 | IdP, protocolo, issuer, audience e discovery | TI/Segurança LG | pendente externa | modo corporativo desabilitado; `AUTH_IDENTITY_PROVIDER=local` |
| ID-P02 | MFA, acesso condicional, VPN e sessão máxima | TI/Segurança LG | pendente externa | MFA exigido por padrão e não desativável em produção; sessão de 15 min / 8 h / 24 h |
| ID-P03 | Origem dos grupos, provisionamento e desligamento | TI/Gestor LG | pendente externa | vínculo administrativo; desligamento por `deactivate` ou `block` |
| ID-P04 | Login local em produção | TI/Segurança LG e Gestor | pendente externa | recusado em produção por código |
| ID-P05 | Segredo, rotação, cofre e responsáveis | TI/DevOps LG | pendente externa | arquivo montado só na API; nunca no repositório |
| ID-P06 | Organizações e quem concede escopo | Gestor LG | pendente externa | claim ausente ou desconhecida rejeita a identidade |
| ID-P07 | Retenção de sessões, eventos e identificadores | DPO/TI/Gestor LG | pendente externa | política de retenção vigente |
| ID-P08 | Login local temporário em homologação e sua remoção | Equipe SYNERGIA | decidida | exige data de término de até 90 dias |
| ID-P09 | Claims, nomes configuráveis e mapeamento | Equipe SYNERGIA | proposta | contrato lógico abaixo |
| ID-P10 | Logout, revogação e indisponibilidade do IdP | Equipe SYNERGIA | decidida | fail-closed, sem fallback local em produção |
| ID-P11 | Configuração e provider falso offline | Equipe SYNERGIA | decidida | `FakeIdentityProvider` |

`ID-P01` a `ID-P07` são os portões da ADR 0001; `ID-P08` a `ID-P11` fecham o que o
SYNERGIA pode decidir sozinho.

## Princípios fail-closed

1. Qualquer erro de configuração, claim ausente, claim inválida ou falha do IdP
   **rejeita** a identidade; nunca cria uma sessão parcial nem amplia acesso.
2. O domínio recebe apenas o `ActorContext`; claims, SDKs e objetos do IdP não
   atravessam a porta `IdentityProvider`.
3. O usuário interno é resolvido por `(provider_key, subject)`. O e-mail da
   asserção é só validado; não vincula nem cria usuário.
4. Um grupo do IdP não concede privilégio por si: só a tabela de mapeamento
   revisada o transforma em papel, e papel global exige marca explícita de revisão.
5. A resposta ao cliente é genérica; o código estável específico vai para auditoria.
6. Nenhum segredo, token ou dado real é versionado.

## Contrato do provedor (a confirmar)

| Item | Requisito do SYNERGIA | Quem informa |
| --- | --- | --- |
| Protocolo | OIDC com fluxo de código e PKCE (preferido) ou SAML 2.0 | ID-P01 |
| `issuer` | URL `https` exata; comparada por igualdade | ID-P01 |
| `audience` | valor registrado para o SYNERGIA; aceita lista | ID-P01 |
| Descoberta | URL `https` no mesmo host do `issuer` | ID-P01 |
| Assinatura | algoritmo assimétrico verificado contra o JWKS; `none` e HS* recusados | ID-P01 |
| Relógio | tolerância de 30 s; `exp` obrigatório | — |
| MFA | `amr` com método de múltiplos fatores (padrão: `mfa`, `otp`, `hwk`, `swk`, `fpt`, `pop`) | ID-P02 |

A verificação de assinatura e o protocolo pertencem ao adaptador (futuro). O
módulo `app/auth/identity_provider.py` já aplica o restante do contrato sobre as
claims verificadas.

## Contrato de claims

Os **nomes** são configuráveis (`AUTH_CLAIM_*`) porque os nomes reais não são
conhecidos; os padrões abaixo são os do OIDC.

| Claim lógica | Padrão | Tipo | Obrigatória | Validação | Ausente ou inválida |
| --- | --- | --- | --- | --- | --- |
| emissor | `iss` | texto | sim | igual ao `issuer` configurado | `identity_issuer_mismatch` |
| audiência | `aud` | texto ou lista | sim | contém uma audiência configurada | `identity_audience_mismatch` |
| expiração | `exp` | inteiro (epoch) | sim | não vencida, com tolerância | `identity_assertion_expired`; tipo inválido, não finito ou fora do intervalo, `identity_claims_invalid` |
| início e emissão | `nbf`, `iat` | inteiro | não | não futuros além da tolerância | `identity_assertion_expired`; tipo inválido, não finito ou fora do intervalo, `identity_claims_invalid` |
| assunto | `sub` | texto | sim | 1 a 255 caracteres, sem espaço nas bordas nem controle | `identity_subject_invalid` |
| e-mail | `email` | texto | sim | endereço válido; normalizado | `identity_email_invalid` |
| e-mail verificado | `email_verified` | booleano | sim por padrão | exatamente `true` | `identity_email_invalid` |
| nome | `name` | texto | não | até 200 caracteres | `identity_claims_invalid` |
| organizações | `organizations` | lista de texto | sim, para escopo | até 100; só as presentes no mapeamento contam | escopo vazio: `identity_scope_missing` |
| grupos | `groups` | lista de texto | não | até 200; comparação exata sem diferenciar caixa | grupo desconhecido é ignorado |
| métodos | `amr` | lista de texto | sim com MFA exigido | interseção com os métodos de MFA | `identity_mfa_required` |
| autenticação | `auth_time` | inteiro | não | idade máxima de 24 h e não futuro além da tolerância | `identity_assertion_expired` |

Claims adicionais são ignoradas. Exemplos **exclusivamente sintéticos**, que também
são executados como teste, estão em
[`corporate-identity-claims-examples.json`](corporate-identity-claims-examples.json).

### Mapeamento

- **Usuário:** `(provider_key, subject)` → `user_id` pelo vínculo interno
  (`user_external_identities`). Sem vínculo, a identidade não entra; o vínculo é
  uma ação administrativa auditável. Não há provisionamento automático (JIT).
- **Organização:** valor do IdP → código interno por tabela revisada. Valor
  desconhecido é descartado; nenhum valor desconhecido concede acesso.
- **Papéis:** grupo → `role_key` por entrada `{group, role_key, organization_code}`.
  O papel só vale se `organization_code` estiver entre as organizações da
  asserção. Entrada **sem** `organization_code` é global e só carrega com
  `global_reviewed: true`.
- **Escopo vazio:** sem organização válida e sem papel global revisado, a
  identidade é rejeitada (`identity_scope_missing`), mesmo autenticada.

O arquivo de mapeamento é privado, absoluto (`AUTH_CORPORATE_MAPPING_FILE`) e
revisado por quem concede escopo (ID-P06); nenhum mapeamento real é versionado.

## Sessão, MFA e rede

O SYNERGIA emite a própria sessão depois da autenticação, com os parâmetros da
ADR 0001 (access de 15 minutos; refresh de 8 horas ocioso e 24 horas absoluto;
rotação obrigatória). A duração corporativa máxima (ID-P02) só pode **reduzir**
esses limites. Acesso condicional e VPN são aplicados pelo IdP; o SYNERGIA não
decide por localização informada pelo cliente nem por cabeçalhos repassáveis.

## Provisionamento, desativação e remoção de acesso

Sem SLA corporativo definido (ID-P03), o SYNERGIA não presume sincronização:

1. o vínculo e a concessão de papéis são feitos por administrador;
2. o desligamento usa `POST /admin/users/{id}/deactivate` ou `/block`, que
   revogam as sessões imediatamente (o access já emitido expira em até 15 minutos);
3. a desativação no IdP impede apenas novos logins; uma integração por evento ou
   SCIM exige decisão e contrato próprios.

## Login local

| Ambiente | Regra | Aplicação |
| --- | --- | --- |
| `development`, `test` | permitido por `SYNERGIA_LOCAL_AUTH_ENABLED` | configuração |
| `homologation` | permitido **somente** com `AUTH_LOCAL_LOGIN_EXPIRES_AT` (data com fuso, no máximo 90 dias à frente); recusado após a data | configuração e a cada tentativa de login |
| `production` | nunca; a variável é ignorada | código |

Data de término ausente na homologação mantém o login local **desligado**; data
inválida, sem fuso ou acima de 90 dias é erro de configuração
(`auth_configuration_invalid`). A **remoção** é um passo do aceite do adaptador
corporativo e consta do [runbook](runbooks/corporate-identity-activation.md). O
provider sintético (`AUTH_IDENTITY_PROVIDER=fake`) só existe em `development` e
`test`.

## Segredos

O segredo do cliente do IdP (ID-P05) é lido de um **arquivo** montado somente no
processo da API (`AUTH_CORPORATE_CLIENT_SECRET_FILE`, caminho absoluto). Não vai
para variável de ambiente, imagem, repositório, log nem artefato, e a validação de
configuração não abre o arquivo. Rotação, cofre e responsáveis serão registrados
pela TI/DevOps; o procedimento de troca está no runbook.

## Logout, revogação e indisponibilidade

- **Logout e revogação** encerram a sessão do SYNERGIA sem depender do IdP.
  Logout no IdP (iniciado pelo cliente ou por canal de retorno) é opcional e
  depende de o IdP oferecê-lo.
- **IdP indisponível:** nenhum login novo é concluído
  (`IdentityProviderUnavailable`; a resposta `503 identity_provider_unavailable` é
  reservada ao adaptador).
  **Não há fallback para login local em produção.** Sessões válidas seguem até
  expirar e a renovação não consulta o IdP.
- **Falha de autorização:** o adaptador responderá a uma identidade rejeitada com `401` genérico para
  asserção inválida e `403` genérico para escopo ou vínculo ausente (formato de erro
  atual); o código específico vai somente para a auditoria.

## Configuração

| Variável | Padrão | Observação |
| --- | --- | --- |
| `AUTH_IDENTITY_PROVIDER` | `local` | `local`, `fake` (apenas development e test) ou `corporate` |
| `AUTH_CORPORATE_ISSUER` | — | `https` |
| `AUTH_CORPORATE_DISCOVERY_URL` | — | `https`, mesmo host do emissor, sem credenciais |
| `AUTH_CORPORATE_AUDIENCE` | — | lista separada por vírgula |
| `AUTH_CORPORATE_CLIENT_ID` | — | identificador, não segredo |
| `AUTH_CORPORATE_CLIENT_SECRET_FILE` | — | caminho absoluto de arquivo montado |
| `AUTH_CORPORATE_REQUIRE_MFA` | `true` | não pode ser `false` em produção |
| `AUTH_CORPORATE_MAPPING_FILE` | — | JSON privado `{organizations, group_roles}` |
| `AUTH_CLAIM_SUBJECT`, `_EMAIL`, `_EMAIL_VERIFIED`, `_NAME`, `_ORGANIZATIONS`, `_GROUPS`, `_METHODS`, `_AUTHENTICATED_AT` | padrões OIDC | nomes das claims |
| `AUTH_LOCAL_LOGIN_EXPIRES_AT` | — | só em `homologation` |

Qualquer valor inválido torna a autenticação indisponível (`503
auth_configuration_invalid`) em vez de usar um valor padrão inseguro.

## Início da implementação

A implementação do adaptador pode começar sem redefinir o domínio: ela precisa
apenas (1) verificar a asserção do protocolo escolhido, (2) entregar as claims a
`map_claims`, (3) resolver o vínculo e (4) emitir a sessão existente. Isso requer
fechar `ID-P01`, `ID-P02` e `ID-P05`; os demais portões bloqueiam a ativação
em produção, não o desenvolvimento.
