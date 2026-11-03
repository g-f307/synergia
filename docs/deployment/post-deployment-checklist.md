# Aceite pós-implantação

Execute após primeira instalação, atualização e recuperação. Use as portas,
origens e overlays aprovados; exemplos `.invalid` exigem substituição privada.

- [ ] SHA aprovado, checkout limpo e tags imutáveis retidas.
- [ ] Perfil efetivo confirmado como homologation (ou perfil autorizado).
- [ ] Backend UID 10001 e web nginx, ambos sem root.
- [ ] Migration retornou 0; ledger contém filenames e SHA-256 correspondentes ao checkout.
- [ ] PostgreSQL, backend e web healthy; config-check termina com 0.
- [ ] Liveness 200, readiness 200 com status ready; web e runtime-config 200.
- [ ] API pública acessível pelo navegador, CSP e CORS corretos.
- [ ] Login, refresh e permissão/escopo confirmados com identidade autorizada.
- [ ] Jornada com massa sintética aprovada, sem mutações de dados reais.
- [ ] Canal e-mail no estado aprovado; desabilitado inicialmente; não inferir envio a partir de saída 0.
- [ ] Backup recuperável, versão anterior e plano de retorno registrados.

## Código, perfil, processos e ledger

```bash
git status --short
git diff --exit-code
git rev-parse HEAD
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env ps --all
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env logs --tail 80 backend
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env exec -T backend id -u
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env exec -T web id
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env exec -T postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT filename, sha256 FROM public.synergia_schema_migrations ORDER BY filename"'
sha256sum database/migrations/*.sql
```

- **Onde executar:** host, raiz do checkout implantado, terminal restrito.
- **Efeito:** somente leitura; consulta código, processos, logs e ledger; calcula hashes locais.
- **Resultado esperado:** status Git vazio, diff 0, SHA aprovado; log `synergia startup: environment=homologation`; backend 10001, web nginx sem UID 0; cada SQL com filename/hash idêntico no ledger (atualmente 0001 a 0033).
- **Interpretação de falhas:** migrate descartável não aparece após run --rm; conferir retorno da execução. Hash/arquivo ausente ou extra bloqueia aceite; não editar ledger.
- **Próxima ação:** se aprovado seguir sondas; caso contrário usar [diagnóstico](troubleshooting.md).

## Sondas e navegador

```bash
python3 scripts/smoke_containers.py --backend-url http://127.0.0.1:8000 --web-url http://127.0.0.1:8080 --expected-api-origin http://api.homolog.example.invalid:8000
curl --fail --silent --show-error --head http://127.0.0.1:8080/
curl --fail --silent --show-error --output /dev/null --dump-header - --request OPTIONS http://127.0.0.1:8000/auth/login --header 'Origin: http://web.homolog.example.invalid:8080' --header 'Access-Control-Request-Method: POST'
```

- **Onde executar:** host, raiz do checkout; substituir origem web/API por valores aprovados e portas publicadas.
- **Efeito:** sondas HTTP; readiness verifica escrita temporária, OPTIONS não faz login.
- **Resultado esperado:** smoke 0 com quatro alvos ok, CSP com origem API; preflight 200 e Access-Control-Allow-Origin igual à origem web permitida.
- **Interpretação de falhas:** 400 no preflight indica origem/método não autorizado; smoke não valida login nem acesso da estação remota.
- **Próxima ação:** conferir no navegador autorizado login/refresh, console sem bloqueio CSP/CORS e jornada sintética de [primeiros passos](../getting-started.md). Não compartilhar cookies/tokens/headers brutos.

## Exercício independente de configuração

Executar por pessoa diferente do autor, somente em homologação de ensaio.
Registrar primeiro baseline saudável. O cenário abaixo não altera o arquivo
principal nem inicia dependências; exige imagem da revisão já construída.

```bash
install -m 0600 /caminho/privado/synergia-config/homologation.env /caminho/privado/synergia-config/fault.env
SYNERGIA_API_ORIGIN=http://localhost:8000 docker compose --project-name synergia --env-file /caminho/privado/synergia-config/fault.env run --rm --no-deps config-check
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env run --rm --no-deps config-check
```

- **Onde executar:** host de ensaio, raiz do checkout; fault.env deve ser destino novo e privado.
- **Efeito:** mutável apenas na cópia e tarefas temporárias; sobreposição de origem dura um comando. Banco e serviços existentes permanecem.
- **Resultado esperado:** comando de falha retorna não zero com `invalid deployment configuration: SYNERGIA_API_ORIGIN must not use a local address outside development`; execução final válida retorna 0.
- **Interpretação de falhas:** se falhar em outro campo, baseline não está válido; se localhost passar, perfil/revisão incorretos. `config --quiet` sozinho não detecta esta falha de perfil.
- **Próxima ação:** segundo executor identifica a causa usando Ambiente no diagnóstico, registra correção e repete o smoke saudável; remover cópia privada depois conforme retenção local.

## Exercício de dependência

Requer janela aprovada e **instância descartável sem dados reais**, com tráfego
isolado. Não executar esse bloco na homologação compartilhada em uso.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env stop postgres
curl --silent --show-error --write-out '\n%{http_code}\n' http://127.0.0.1:8000/health/live
curl --silent --show-error --write-out '\n%{http_code}\n' http://127.0.0.1:8000/health/ready
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env start postgres
```

- **Onde executar:** host de ensaio descartável, raiz do checkout; porta ajustada.
- **Efeito:** mutável; interrompe temporariamente banco e depois o reinicia preservando volume.
- **Resultado esperado:** liveness 200, readiness 503 indicando postgresql; após reinício e banco healthy, smoke volta a passar com readiness 200.
- **Interpretação de falhas:** falha adicional ou suspeita de dados reais exige interromper exercício e restaurar serviço; HTTP 503 não torna curl não zero sem --fail.
- **Próxima ação:** executar smoke acima e [runbook de exercícios](../runbooks/homologation-observability.md), registrar tempos e diagnóstico antes de liberar ambiente.

## Registro sanitizado de aceite

Preencher em chamado protegido: data UTC; SHA/tag; perfil; executor; segundo
executor; checks aprovados/falhos/não executados; cenário; mensagem/código
sanitizado; diagnóstico; correção; tempo de recuperação; decisão e pendências.
Não anexar `.env`, saída expandida do Compose, URLs/IPs internos, destinatários,
tokens, senhas, dump, manifesto privado ou logs brutos.

**Estado desta documentação:** roteiro preparado. O critério da issue #167
“uma pessoa não envolvida executa um deploy de homologação e diagnostica uma
falha simulada” permanece pendente até evidência dessa execução independente.
Testes documentais não substituem esse aceite.
