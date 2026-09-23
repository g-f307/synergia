# Validação administrativa e operacional pré-RPA

## Resultado técnico

O cenário `web/e2e/operational-flow.spec.ts` usa o Angular publicado, a API
FastAPI e um PostgreSQL migrado em banco descartável. As identidades, arquivos e
mensagens são sintéticos. Nenhuma resposta de sucesso é interceptada ou criada
no navegador; a única interceptação simula indisponibilidade de rede e exige que
a recuperação seguinte volte a consultar a API real.

## Jornadas reproduzíveis

- **Administração:** autenticação administrativa; criação e edição de usuário;
  criação de grupo e papel; concessão de permissão; associações com escopo;
  leitura das permissões efetivas; bloqueio, desbloqueio, desativação e
  reativação; revogação da associação; conferência ordenada das mutações em
  `identity_access_events` com o ator esperado.
- **Operação:** autenticação; catálogo paginado de execuções; filtro temporal
  convertido de `America/Manaus` para UTC; detalhe e retorno com contexto;
  preferências persistidas; duas sessões reais e revogação da outra; leitura
  individual e em lote das notificações.
- **Templates:** rascunho, prévia sintética, publicação, evento persistido,
  notificação real, nova revisão e leitura da revisão publicada anterior como
  imutável.

## Cenários negativos

| Cenário | Evidência automatizada |
| --- | --- |
| sem `access.admin` | Playwright comprova redirecionamento de `/admin` e resposta `403` da API com o token do papel de consulta |
| organização fora do escopo | `test_authorization_persistence.py`, `test_queries.py` e busca E2E isolada |
| identificador inexistente | `test_users.py`, `test_queries.py` e `test_notification_templates.py` |
| mass assignment | contrato `extra="forbid"` e teste HTTP dedicado em `test_users.py` |
| versão desatualizada | `test_user_persistence.py`, `test_profile_persistence.py` e testes de templates |
| sessão revogada | `test_auth_persistence.py` e Playwright com dois navegadores |
| último administrador | `test_user_persistence.py`, inclusive concorrência PostgreSQL |
| template malicioso | teste HTTP e tentativa real no Playwright |
| alteração de versão publicada | teste PostgreSQL, teste Angular e leitura E2E da versão anterior |
| filtro organizacional arbitrário | `test_rate_limiting.py` e `test_queries.py` |
| backend indisponível | Playwright valida erro explícito e recuperação sem sucesso simulado |

## Evidências publicadas pela CI

O artefato `fluxo-web-e2e` contém relatório HTML, resultados Playwright/Axe e
capturas sanitizadas do catálogo com contexto, ciclo administrativo, templates,
notificações, perfil móvel, relatório e aprovação. O resumo de auditoria expõe
somente quantidade e nomes de eventos; não contém token, hash ou credencial.

Os jobs de frontend, backend, PostgreSQL, protótipo e segurança continuam sendo
barreiras obrigatórias. `validate_web_journey_map.py`, a matriz de acesso, lint,
build, testes Angular, testes FastAPI/PostgreSQL e `git diff --check` completam a
matriz técnica.

## Itens adiados

RPA, serviços corporativos definitivos, dados reais, implantação em produção,
Modo TV e administração global de sessões permanecem fora do escopo. Eles não
são apresentados como capacidades concluídas.

## Aceite humano

A automação comprova a prontidão técnica, mas não substitui homologação. Antes
do merge, o PR deve registrar separadamente:

- aceite funcional do PO, com riscos residuais conhecidos;
- aceite do responsável técnico, confirmando a evidência e os itens adiados.

Até os dois registros existirem, a decisão da milestone permanece **pronta para
homologação**, e não “aceita”.
