# Validação da automação de implantação — #166

## Escopo e rastreabilidade

O fluxo atende à instalação/atualização do Compose versionado, com configuração
externa, imagens por ID, migrations transacionais e promoção após verificação.
Rollback de aplicação não altera o banco; mudança de ledger exige correção para
frente ou recuperação de dados explicitamente aprovada.

| Critério da issue | Implementação | Evidência reproduzível |
| --- | --- | --- |
| Fluxo único de precheck, build, migrations, subida e smoke | `scripts/deploy.py apply`; `scripts/deploy_flow.py` | casos `initial_installation`, `repeat_update_preserves_data` |
| Falha de build, migration ou health interrompe | falhas de build ficam `failed`; falhas durante a inicialização ou manutenção ficam `uncertain`, sem promoção | casos `real_build_failure`, `real_migration_failure`, `real_health_failure`, `real_smoke_failure` |
| Preservar usuários e dados | sem bootstrap, seeds ou remoção de volumes no deploy; escritores pausados antes de SQL | usuário, arquivo e container PostgreSQL sintéticos preservados; ledger com datas inalteradas |
| Identificar commit implantado | manifesto, labels OCI e startup do backend | caso `source_metadata_non_root_and_worker_opt_in` |
| Rollback testado para a versão anterior | configuração e imagens retidas; bloqueio por ledger/lock/artefato divergente | caso `legacy_previous_version`; bloqueios de schema/artefatos e reconciliação sem repetir migrations |
| Ambiente equivalente à homologação | `SYNERGIA_ENV=homologation`, configuração externa privada, Docker e PostgreSQL reais | `scripts/validate_deploy.py`; job `deployment` da CI |

O executor também verifica leitura sem alterações, exclusão mútua entre clientes,
interrupção durante migration com advisory lock real e higiene dos artefatos.
Fixtures, dumps e credenciais de uso real não participam da validação.

## Comandos de validação

No diretório `backend`, com as dependências de desenvolvimento instaladas:

```bash
.venv/bin/ruff check . ../scripts
.venv/bin/pytest -q -m 'not integration'
.venv/bin/python -m compileall -q app ../scripts/deploy*.py ../scripts/validate_deploy.py
```

Na raiz, com checkout limpo e Docker acessível:

```bash
python3 scripts/validate_deploy.py --output artifacts/deploy-validation.json
```

O relatório gerado inclui hashes dos arquivos operacionais. Eles permitem
comparar o código exercitado com o checkout revisado mesmo quando somente a
documentação de evidências for atualizada depois do ensaio.

## Resultado local — 03/11/2026

| Verificação executada | Resultado |
| --- | --- |
| Ruff, no mesmo diretório e escopo da CI | aprovado |
| Suíte sem integração | 1.576 passaram; 672 testes de integração foram excluídos desse comando |
| Testes específicos da automação e entrypoint, incluídos na suíte | 157 passaram |
| Compilação dos módulos Python afetados | aprovada |
| YAML do workflow e configuração do novo job/artefato | parse e conferências locais aprovados |
| Scanner de segredos do projeto sobre a árvore pública preparada | 1.002 arquivos examinados; nenhum achado; dados reais ignorados excluídos |
| Bateria Docker versionada, perfil homologação | 22/22 cenários aprovados; limpeza aprovada |
| Compatibilidade com a `main` anterior à issue | adoção e rollback aprovados; limpeza aprovada |
| Integridade dos recursos preexistentes | containers, volumes e redes preexistentes preservados na bateria final |

A bateria final da revisão foi executada entre `2026-11-03T23:48:06.131226+00:00` e
`2026-11-03T23:58:45.068849+00:00` (UTC), com backend,
frontend e PostgreSQL reais e configuração sintética externa privada. Os casos
confirmaram usuário e arquivo preservados, o mesmo container PostgreSQL e as
datas originais do ledger nas atualizações repetidas e recuperações.

Os resultados completos e sanitizados estão em
[issue-166-deploy-validation.json](evidence/issue-166-deploy-validation.json).
Foram provocadas falhas reais de build, SQL, health e smoke; o resultado
`passed` desses cenários significa que a falha foi corretamente bloqueada e a
recuperação verificada, sem promoção da candidata falha. O cenário de migration
lenta usa uma tarefa sintética com o advisory lock do runner, sem novo DDL.

A bateria final usou a `main`
`04769a84423eac2544b7e3a81dfa48232e6e7344`, anterior à automação, para reproduzir
o caminho do PR na CI. O rollback restaurou os IDs exatos das imagens
construídas desse código; a imagem antiga não precisou conter os scripts novos.
A evidência resumida está em
[issue-166-previous-main.json](evidence/issue-166-previous-main.json): trata-se de
uma extração dos cenários de adoção, incluindo o banco parado, da mesma bateria
de 22 cenários, não outra execução.

Os JSONs registram o commit exercitado antes da atualização exclusivamente
documental das evidências e os hashes dos arquivos operacionais selecionados.
Esses hashes foram conferidos contra o código final. Nenhuma migration
publicada foi alterada e nenhum dado real ou configuração privada foi incluído.
Os 15 avisos da suíte são depreciações já existentes de Starlette/httpx e nomes
de status HTTP; não houve falha na suíte final.

A CI do commit anterior à revisão (`3dd375b`) foi consultada no PR #173 e
estava integralmente aprovada. As correções desta rodada exigem nova execução
remota e nova revisão antes do merge. Nenhum resultado equivale à implantação
na infraestrutura da LG.

## Ajustes confirmados na revisão final

Foram identificadas e corrigidas duas lacunas nos caminhos de segurança:

- Recuperação sem o volume de arquivos poderia permitir a criação de um volume
  vazio pelo Compose. Rollback e reconciliação agora exigem os dois volumes
  persistentes antes de parar serviços e repetem essa checagem após a pausa.
- A mudança da porta publicada do PostgreSQL podia ser registrada sem ser
  aplicada, pois seu container é preservado. A atualização agora bloqueia essa
  mudança antes do build; a verificação também compara as portas efetivas de
  PostgreSQL, backend e web com a configuração registrada.

As regressões cobrem rollback normal, as duas resoluções de reconciliação,
interfaces e portas publicadas. A bateria real também provoca perda deliberada
do volume **sintético**, depois das verificações de preservação, para comprovar
que a recuperação recusa a criação de um substituto vazio. Essa falha de
infraestrutura faz parte do teste descartável; não afeta dados ou volumes reais.

## Correção solicitada na revisão do PR #173

O timeout de readiness na primeira instalação podia ocorrer depois da criação
de containers e volumes, antes da existência do candidato, deixando a operação
`failed` e sem retomada suportada. Agora o candidato, a configuração congelada
e a intenção inicial são persistidos antes dos comandos Compose que criam
recursos. A falha deixa a operação `uncertain`, bloqueia novas tentativas de
`apply` e permite `reconcile --operation UUID --resolution resume`.

Essa retomada preserva o UUID, aguarda ou inicia o PostgreSQL com
`--no-recreate` e só permite a primeira tentativa de SQL quando não houver
escritores, processo de migration, lock ou ledger não vazio. O marcador
`migration-attempted.json` é persistido antes do envio ao Docker; depois dele,
a recuperação exige o ledger completo e nunca repete SQL com resultado incerto.
Nenhum volume é apagado automaticamente.

As novas regressões cobrem recursos criados antes do timeout, estados
`running`/`created`/`exited`, ausência de container, falhas repetidas,
configuração/imagens/portas alteradas, worker ativo, lock, ledger e bloqueio
de repetição de SQL. A captura do baseline de uma instalação anterior continua
ocorrendo depois do readiness, permitindo adotar um PostgreSQL parado.

A bateria Docker final acrescenta dois cenários aos 20 anteriores:

- `initial_readiness_failure_after_creation`: prazo real de readiness de 1s,
  recursos efetivamente criados, bloqueio das duas formas de retry e retomada
  explícita com o mesmo container PostgreSQL e UUID, até verificação e promoção.
- `unmanaged_stopped_postgres_update`: dentro do ensaio com a `main` anterior,
  pausa o PostgreSQL sintético antes da adoção, confirma o reinício do mesmo
  container, captura o baseline e depois verifica o rollback e os dados.

A suíte final sem integração foi executada sequencialmente: 1.576 testes
aprovados, incluindo os 157 específicos de deploy/entrypoint. Uma execução
anterior simultânea disputou o lock sintético entre suítes; a repetição
sequencial eliminou essa interferência. Os 672 testes marcados como integração
não fazem parte desse comando; o ensaio Docker foi executado separadamente.

## Limites e portões externos

- Evidência técnica local usa dados sintéticos; não equivale à implantação LG.
- A CI remota e a revisão do PR ainda são necessárias antes do merge.
- Banco gerenciado, registry corporativo, DNS/ingress, TLS, secrets e identidade
  corporativa permanecem sujeitos ao contrato do destino.
- A exclusão mútua de deploy é local ao host executor; a operação deve manter
  um operador e coordenar agendadores e outros hosts.
- Backup não é criado automaticamente. O backup de domínio existente exclui o
  ledger público; recuperação completa precisa preservar banco, ledger e
  arquivos no mesmo ponto consistente, conforme o roteiro operacional.
- Rollback com schema alterado é bloqueado; nenhum `.down.sql` é automatizado.
- A documentação operacional consolidada da #167 permanece fora deste escopo.
