# Aceite pós-implantação

Execute após primeira instalação, atualização e recuperação. Use portas,
origens e histórico aprovados; exemplos `.invalid` exigem substituição privada.

- [ ] SHA aprovado, checkout limpo e tags imutáveis retidas.
- [ ] deploy.py verify aprovado; referência ativa, IDs das imagens e portas coincidem com o runtime.
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
python3 scripts/deploy.py verify --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history
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
- **Efeito:** verify inclui readiness com escrita temporária; demais inspeções consultam código/processos/logs/ledger e calculam hashes locais, sem migrations.
- **Resultado esperado:** verified: true, Git limpo, SHA aprovado e label org.opencontainers.image.revision correspondente; backend 10001, web nginx sem UID 0; filenames/hashes iguais ao inventário SQL da revisão, sem fixar número de migrations.
- **Interpretação de falhas:** use journal/reconcile para conferir a tentativa SQL e seu container preservado. Hash/arquivo ausente ou extra bloqueia aceite; não editar ledger nem active.json.
- **Próxima ação:** se aprovado seguir sondas; caso contrário usar [diagnóstico](troubleshooting.md).
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

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
- **Pré-condições:** Instalação disponível para sondas e portas/origens ajustadas; readiness requer permissão de escrita temporária.
- **Entradas:** Portas efetivas, origem API/web e configuração de implantação aprovada.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

## Exercício recomendado de configuração

Recomenda-se executar somente em homologação de ensaio, pelo próprio operador
ou, opcionalmente, em revisão por pares. Registrar primeiro baseline saudável.
O cenário abaixo não altera o arquivo
principal nem inicia dependências; exige imagem da revisão já construída.

```bash
test ! -e /caminho/privado/synergia-config/fault.env && install -m 0600 /caminho/privado/synergia-config/homologation.env /caminho/privado/synergia-config/fault.env
python3 -c "from pathlib import Path; p=Path('/caminho/privado/synergia-config/fault.env'); rows=p.read_text().splitlines(); assert any(r.startswith('SYNERGIA_API_ORIGIN=') for r in rows); p.write_text('\n'.join('SYNERGIA_API_ORIGIN=http://localhost:8000' if r.startswith('SYNERGIA_API_ORIGIN=') else r for r in rows)+'\n')"
python3 scripts/deploy.py precheck --project synergia --env-file /caminho/privado/synergia-config/fault.env --state-dir /caminho/privado/deploy-history
python3 scripts/deploy.py precheck --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host de ensaio, raiz do checkout; fault.env deve ser destino novo e privado.
- **Efeito:** mutável somente na cópia privada; precheck é leitura. A CLI ignora variáveis de aplicação exportadas no shell, por isso a falha é inserida no arquivo de ensaio.
- **Resultado esperado:** precheck de falha retorna 1 indicando SYNERGIA_API_ORIGIN local fora de development; precheck com arquivo original retorna 0. Não executar apply com fault.env.
- **Interpretação de falhas:** se falhar em outro campo, baseline não está válido; se localhost passar, perfil/revisão incorretos. `config --quiet` sozinho não detecta esta falha de perfil.
- **Próxima ação:** operador identifica a causa usando Ambiente no diagnóstico, registra correção e repete verify/smoke saudáveis; reter cópia privada conforme política local, sem publicá-la.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

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
- **Pré-condições:** Baseline saudável, janela autorizada e instância descartável sem dados reais ou outros usuários.
- **Entradas:** Configuração da instância de ensaio e portas efetivamente publicadas.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

## Registro sanitizado de aceite

Preencher em chamado protegido: data UTC; SHA/tag; perfil; executor;
revisor opcional; checks aprovados/falhos/não executados; cenário; mensagem/código
sanitizado; diagnóstico; correção; tempo de recuperação; decisão e pendências.
Não anexar `.env`, saída expandida do Compose, URLs/IPs internos, destinatários,
tokens, senhas, dump, manifesto privado ou logs brutos.

**Estado desta documentação:** entrega documental da issue #167 concluída.
Os exercícios são recomendações operacionais e não condicionam o encerramento
da #167, nem exigem execução por pessoa diferente do autor. Registrar os
resultados reais a cada implantação; testes documentais não comprovam a saúde
do ambiente nem autorizam produção.
