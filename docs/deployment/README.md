# Implantação e operação do SYNERGIA

Esta é a entrada única para primeira implantação, diagnóstico, atualização,
verificação e recuperação. Os contratos conceituais continuam nos documentos
referenciados; siga os procedimentos desta área na ordem indicada.

A [revisão da issue #167](../evidence/issue-167-deployment-guide-validation.md)
registra verificações realmente executadas, limites de ambiente e o aceite
independente ainda pendente.

| Guia | Público | Quando usar |
| --- | --- | --- |
| [Referência de ambiente](environment-reference.md) | Plataforma e segurança | Preparar configuração privada e entender quais variáveis chegam aos containers |
| [Primeira implantação](deployment-guide.md) | Operador de homologação | Instalar uma revisão aprovada em ambiente novo |
| [Atualização e rollback](update-and-rollback.md) | Plataforma e banco | Preservar versão anterior, migrar e recuperar |
| [Diagnóstico por sintoma](troubleshooting.md) | Suporte | Identificar causa e próxima ação |
| [Aceite pós-implantação](post-deployment-checklist.md) | Operador e segundo executor | Verificar entrega e exercitar falha controlada |
| [E-mail e API LG](lg-email-api.md) | Integrações e suporte | Operar worker e preparar validação da API interna |

## Perfis e limites atuais

- `development` e `test`: uso local, com [.env.example](../../.env.example).
  Não usar em ambiente compartilhado. O roteiro local está em
  [primeiros passos](../getting-started.md).
- `homologation`: perfil suportado para validação interna assistida. Usa
  [.env.homologation.example](../../.env.homologation.example) como modelo;
  permite HTTP transitório e login local com término explícito, até 90 dias.
- `production`: [.env.production.example](../../.env.production.example)
  expressa o contrato, não uma liberação. Depende de HTTPS, secrets montados e
  adaptador corporativo aprovado. Veja o [contrato de identidade](../corporate-identity-contract.md).

`scripts/deploy.py`, entregue pela #166, é o fluxo principal de implantação:
`diagnose`/`precheck` → `apply` → `verify`, com `rollback` e `reconcile`
para recuperação. Os contratos detalhados permanecem em
[automação de implantação](../deploy-automation.md); os procedimentos por tarefa
estão nos guias acima. O aceite por pessoa independente continua pendente,
conforme o [checklist](post-deployment-checklist.md).

## Host, acesso e topologia

Host Linux com Git, Python >= 3.11, curl, Docker Engine e Compose v2 com
`config --format json` e `ps --format json`; acesso autorizado ao daemon,
registry/fontes de build e espaço para reter duas versões. As portas padrão
são 5432 (banco), 8000 (API) e 8080 (web), parametrizáveis. Restrinja o acesso
pela política de rede do ambiente; o Compose base publica essas portas no host.
O navegador do usuário precisa alcançar a origem pública da API.

Guarde configuração externa em arquivo `0600`, diretório `0700`, fora do Git.
Reserve também diretórios privados para histórico e backups. Para recuperação,
o host operacional precisa de clientes PostgreSQL 16, dependências Python do
backend e acesso aos volumes, conforme [atualização](update-and-rollback.md).

| Serviço | Execução e dependências |
| --- | --- |
| `config-check` | Valida perfil sem conectar ao banco; termina com 0 |
| `postgres` | PostgreSQL 16 Alpine; inicia após config-check |
| `migrate` | `scripts/apply_migrations.py`; termina antes da API |
| `backend` | FastAPI/Uvicorn, UID/GID 10001; depende de banco e migrations |
| `web` | Angular/Nginx, usuário nginx, porta interna 8080 |
| `email-worker` | Perfil opt-in `email`, tarefa finita, sem agendamento automático |

Volumes lógicos `synergia-postgres` em `/var/lib/postgresql/data` e
`synergia-application-data` em `/var/lib/synergia` (`imports`, `avatars`,
`email-capture`). Seus nomes físicos recebem o prefixo do projeto Compose.
Use sempre `--project synergia` na automação e `--project-name synergia` nas
inspeções Compose; trocar o projeto pode criar volumes vazios.
Nunca use remoção de volumes para resolver falha operacional.
Detalhes: [contrato de containers](../container-deployment.md).

## Estações com Podman

Uma verificação anterior usou Podman 5.8.9 e podman-compose 1.6.0 para
interpolação do Compose base. O comando de inspeção correspondente é:

```bash
podman-compose --env-file .env.example config --quiet
```

- **Onde executar:** host com Podman, raiz do checkout; modelo exclusivamente local.
- **Efeito:** somente leitura; valida configuração sem iniciar containers.
- **Resultado esperado:** saída 0, sem saída de configuração expandida.
- **Interpretação de falhas:** conferir instalação, acesso rootless e variáveis obrigatórias; no sandbox, acesso a /run/user pode estar bloqueado.
- **Próxima ação:** para homologação, preparar arquivo privado e validar o ciclo completo no ambiente de ensaio antes do aceite.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Esse resultado não comprova implantação completa com Podman. Os procedimentos
principais usam Docker Compose; o podman-compose
1.6.0 não oferece `config --format json`. Não usar alias como prova de
compatibilidade. Migrações, condições de dependência, saúde, secrets e permissões
dos volumes rootless ainda precisam de validação com Podman. A seleção do
provider externo de `podman compose` também deve ser conferida no host.
