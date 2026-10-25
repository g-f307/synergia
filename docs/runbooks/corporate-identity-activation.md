# Ativação da identidade corporativa e remoção do login local

## Responsável e escalonamento

Plataforma executa; segurança valida os portões; o gestor confirma os escopos; a
TI da LG fornece os dados externos. Um portão aberto bloqueia a etapa seguinte. O
contrato e as decisões estão em
[corporate-identity-contract.md](../corporate-identity-contract.md) e no
[registro](../corporate-identity-decisions.json); a regra de segredos e de
credenciais é a do repositório: nada real é versionado ou colado em chamados.

## Pré-condições (todas obrigatórias)

- [ ] `ID-P01`, `ID-P02` e `ID-P05` fechados pela TI/Segurança e TI/DevOps da LG;
- [ ] `ID-P03` e `ID-P06` fechados: fonte dos grupos, desligamento e escopos;
- [ ] `ID-P04` decidido formalmente (proibição ou autorização do login local);
- [ ] `ID-P07` com os prazos de retenção;
- [ ] arquivo de mapeamento revisado por quem concede escopo e assinado no chamado;
- [ ] suítes de autenticação, sessão, papéis e isolamento organizacional aprovadas
      com o provider falso (`python -m pytest -q -m security`);
- [ ] `python scripts/validate_identity_contract.py` sem erros e registro atualizado.

## Ativação em homologação

1. Montar o segredo do cliente como **arquivo** apenas no serviço da API, fora do
   repositório e com leitura restrita ao usuário do contêiner; nunca em variável.
2. Definir `AUTH_IDENTITY_PROVIDER=corporate` e as variáveis `AUTH_CORPORATE_*` e
   `AUTH_CLAIM_*` com os valores informados pela TI, mais o arquivo de mapeamento.
3. Iniciar a API: configuração inválida torna a autenticação indisponível
   (`auth_configuration_invalid`) em vez de usar um padrão inseguro.
4. Executar a bateria de aceite com contas de teste do IdP:
   asserção válida entra; emissor, audiência, MFA, expiração e escopo inválidos são
   recusados; grupo desconhecido não concede papel; desativação e bloqueio revogam
   as sessões.
5. Registrar o resultado no chamado sem tokens, claims reais ou e-mails.

## Remoção do login local (aceite do adaptador)

1. Confirmar a aprovação do aceite acima e que os administradores corporativos
   conseguem entrar.
2. Definir `SYNERGIA_LOCAL_AUTH_ENABLED=false` e remover `AUTH_LOCAL_LOGIN_EXPIRES_AT`;
   reiniciar a API. Em produção a variável já é ignorada por código.
3. Aguardar o fim das sessões locais: o refresh expira em no máximo 24 horas (limite
   absoluto). Para encerrar antes, cada usuário usa `POST /auth/logout-all`; um
   usuário específico pode ser encerrado por `POST /admin/users/{id}/block`, com
   justificativa. Confirmar em `GET /auth/sessions` que não restam sessões locais.
4. Solicitar à equipe de dados a remoção auditada dos hashes locais pelo
   procedimento de [dados](../data-recovery.md), sem editar tabelas manualmente.
5. Remover contas técnicas de homologação do IdP e confirmar que
   `POST /auth/login` responde `503 identity_adapter_unavailable`.

Sem o item 5, o aceite não está concluído. O login local temporário também se
encerra sozinho na data de término.

## Rotação do segredo do cliente

1. A TI/DevOps emite o novo segredo no cofre e o disponibiliza como novo arquivo.
2. Atualizar o arquivo montado na API e reiniciar o serviço (janela combinada).
3. Validar um login de teste; revogar o segredo anterior no IdP.
4. Registrar data e responsável no chamado, sem o valor.

Suspeita de vazamento: revogar o segredo no IdP primeiro, depois rotacionar e
revogar as sessões do SYNERGIA dos usuários afetados.

## IdP indisponível

- Sintoma: logins novos falham com `503`; usuários com sessão válida continuam.
- Ação: confirmar o status com a TI da LG; **não** habilitar o login local em
  produção. Em homologação, a regra de data de término continua valendo.
- Comunicar que novos acessos dependem do IdP; as renovações de sessão seguem.
- Após a recuperação, validar um login de teste e registrar o incidente.

## Reversão

Defina `AUTH_IDENTITY_PROVIDER=local` somente em homologação, enquanto o login
local temporário estiver dentro da data de término. Em produção não há reversão
para login local; o cenário é tratado como indisponibilidade do IdP.
