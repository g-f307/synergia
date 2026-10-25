# ADR 0002: contrato de identidade corporativa e transição do login local

- **Estado:** aceita como contrato; a ativação do adaptador corporativo permanece
  bloqueada pelos portões `ID-P01` a `ID-P07`
- **Data:** 25/10/2026
- **Decisores:** equipe SYNERGIA
- **Revisão independente:** pendente no pull request
- **Referências:** [ADR 0001](0001-identity-strategy.md), issue #144,
  [contrato](../corporate-identity-contract.md) e
  [registro de decisões](../corporate-identity-decisions.json)

## Contexto

A ADR 0001 adotou uma arquitetura híbrida com núcleo neutro e deixou em aberto o
que depende da LG: provedor, protocolo, claims, MFA, grupos, escopos, segredos e a
permanência do login local. Esses dados ainda não foram fornecidos e a
homologação não pode esperar por eles. É preciso fixar o que o SYNERGIA exige de
qualquer provedor e provar esse contrato offline, sem inventar dados externos.

## Alternativas consideradas

| Alternativa | Resultado |
| --- | --- |
| Esperar os dados da LG para só então desenhar a integração | Rejeitada: bloqueia a homologação e arrisca redefinir o domínio quando os dados chegarem |
| Mapear grupos corporativos diretamente a papéis, inclusive globais | Rejeitada: um grupo mal nomeado ou mal atribuído viraria privilégio; viola o menor privilégio |
| Provisionar usuários automaticamente (JIT) no primeiro login | Rejeitada: cria identidade e acesso sem ação administrativa auditável |
| Manter login local como contingência quando o IdP cair | Rejeitada em produção: contorna MFA e política corporativa |
| **Contrato lógico neutro, mapeamento revisado e fail-closed** | Adotada |

## Decisão

1. O SYNERGIA define um **contrato de claims lógico** com nomes configuráveis, e o
   exercita com um provider falso offline e exemplos sintéticos. Os valores reais
   (emissor, audiência, claims, grupos) são entradas externas pendentes.
2. **Fail-closed:** qualquer erro, claim ausente ou inválida rejeita a identidade;
   a resposta ao cliente é genérica e o código específico vai à auditoria.
3. **Grupos não são privilégios.** Só uma tabela de mapeamento revisada transforma
   grupo em papel; papel global exige marca explícita de revisão; organização ou
   grupo desconhecido não concede nada; identidade sem escopo é rejeitada.
4. **Sem provisionamento automático.** O vínculo `(provider_key, subject)` é criado
   por administrador. O e-mail da asserção não vincula nem cria usuário.
5. **Login local** continua proibido em produção por código. Em homologação é
   temporário: exige data de término de até 90 dias e é recusado após ela. Sua
   remoção é passo do aceite do adaptador corporativo. O provider falso só existe
   em desenvolvimento e teste.
6. **Segredo** do cliente do IdP somente por arquivo montado na API; a
   configuração não o lê. Nenhum segredo corporativo é versionado.
7. **Indisponibilidade do IdP** impede novos logins sem fallback local em
   produção; sessões válidas continuam até expirar e a renovação não depende do IdP.
8. Cada decisão obrigatória tem responsável e estado no registro canônico, validado
   automaticamente. As pendências externas permanecem `pending_external` até a LG
   responder.

## Consequências

### Positivas

- a homologação segue com identidades sintéticas e sem acesso a diretório real;
- a implementação futura começa pela verificação da asserção, sem redefinir o
  domínio de identidade, de organização ou de papéis;
- uma troca de IdP altera configuração e mapeamento, não o código de autorização.

### Custos e riscos

- até o ID-P03 ser decidido, o desligamento depende de ação administrativa no
  SYNERGIA, e uma desativação só no IdP não encerra sessões já emitidas (no máximo
  15 minutos para o access token e até 8 horas ociosas para o refresh);
- os nomes reais das claims podem exigir ajuste de configuração e de mapeamento;
- o contrato permanece **proposta** (`ID-P09`) até a TI confirmar tipos e nomes.

## Portões

| ID | Responsável | Estado | Bloqueia |
| --- | --- | --- | --- |
| ID-P01 | TI/Segurança LG | pendente externa | adaptador corporativo |
| ID-P02 | TI/Segurança LG | pendente externa | homologação da política de sessão |
| ID-P03 | TI/Gestor LG | pendente externa | administração de acessos corporativos |
| ID-P04 | TI/Segurança LG e Gestor | pendente externa | adaptador local de produção |
| ID-P05 | TI/DevOps LG | pendente externa | emissão de tokens e ativação |
| ID-P06 | Gestor LG | pendente externa | carga de escopos de produção |
| ID-P07 | DPO/TI/Gestor LG | pendente externa | política de retenção |
| ID-P08 | Equipe SYNERGIA | decidida | — |
| ID-P09 | Equipe SYNERGIA | proposta | adaptador corporativo |
| ID-P10 | Equipe SYNERGIA | decidida | — |
| ID-P11 | Equipe SYNERGIA | decidida | — |

Os portões `ID-P01` a `ID-P07` são os da ADR 0001; esta ADR acrescenta
`ID-P08` a `ID-P11` e não altera as decisões já aceitas.
