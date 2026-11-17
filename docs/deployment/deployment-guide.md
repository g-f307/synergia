# Primeira implantação

Comece pelo [mapa e pré-requisitos](README.md). O fluxo usa a automação da
#166 para homologação assistida em instalação nova. Instalação existente
segue [atualização e recuperação](update-and-rollback.md). Use Bash no host
Linux, configuração externa privada e o mesmo projeto em toda a operação.

## 1. Host e revisão

```bash
git --version
python3 --version
docker compose version
docker info --format '{{.ServerVersion}}'
```

- **Onde executar:** terminal do host Linux autorizado.
- **Efeito:** somente leitura; verifica ferramentas e acesso ao daemon.
- **Resultado esperado:** saída 0 em cada comando; Python >= 3.11 e Compose com config/ps em JSON.
- **Interpretação de falhas:** ferramenta ausente ou acesso ao daemon negado impede prosseguir.
- **Próxima ação:** plataforma corrige o host; depois obtenha o checkout.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

```bash
git clone https://github.com/g-f307/synergia.git
cd synergia
git switch --detach REVISAO_APROVADA
git status --short
git diff --exit-code
git rev-parse HEAD
```

- **Onde executar:** host, diretório de trabalho; substituir REVISAO_APROVADA por tag/SHA aprovado.
- **Efeito:** cria checkout e seleciona código; não modifica instalação existente.
- **Resultado esperado:** comandos com 0, status vazio e SHA igual ao aprovado.
- **Interpretação de falhas:** revisão ausente, acesso negado ou mudanças locais; não sobrescrever trabalho existente.
- **Próxima ação:** preparar configuração com checkout limpo; a CLI não faz pull nem troca a revisão.
- **Pré-condições:** Destino novo, acesso autorizado ao repositório e revisão aprovada conhecida; não sobrescrever checkout existente.
- **Entradas:** Repositório e tag/SHA aprovados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Se já houver clone, confira o estado antes de trocar a revisão. O precheck
recusa alterações rastreadas ou arquivos não ignorados. Não guarde configuração,
histórico ou backups no checkout, mesmo em diretórios ignorados. Não habilite
`set -x` nem publique configuração ou logs brutos.

## 2. Configuração privada

```bash
install -d -m 0700 /caminho/privado/synergia-config /caminho/privado/deploy-history
test ! -e /caminho/privado/synergia-config/homologation.env && install -m 0600 .env.homologation.example /caminho/privado/synergia-config/homologation.env
```

- **Onde executar:** host, raiz do checkout; preparação inicial em diretórios autorizados, sem configuração anterior no destino.
- **Efeito:** cria diretórios e copia modelo 0600. Não gera usuários nem configura credenciais reais.
- **Resultado esperado:** saída 0; arquivo e histórico pertencem ao operador e ficam fora do Git.
- **Interpretação de falhas:** destino já existente, caminho ou permissões inválidos exigem parar; não substituir configuração anterior.
- **Próxima ação:** editar a cópia com editor autorizado, conforme [referência de ambiente](environment-reference.md).
- **Pré-condições:** Diretórios externos aprovados e destino ausente; não sobrescrever configuração existente.
- **Entradas:** Modelo ou cópia privada indicada e diretórios autorizados fora do Git.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Substitua os placeholders por segredos independentes, origens acessíveis ao
navegador e abas autorizadas. Login local temporário exige data futura com fuso
e até 90 dias. Mantenha e-mail desabilitado. IAM deve fornecer uma identidade
autorizada; o deploy não faz bootstrap de contas.

A CLI usa somente o Compose base versionado. `.env` implícito, variáveis de
aplicação no shell e overlays arbitrários não alteram esse fluxo. Dependência
de mounts/configurações ausentes exige extensão aprovada da automação,
não edição ad hoc de arquivos ou containers.

## 3. Diagnóstico e pré-validação

```bash
python3 scripts/deploy.py diagnose --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history
python3 scripts/deploy.py precheck --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host, raiz da revisão limpa, configuração preenchida e acesso ao Docker.
- **Efeito:** somente leitura; confere configuração, ferramentas, daemon, projeto, volumes e histórico; não executa HTTP, build, SQL ou worker.
- **Resultado esperado:** saída 0 e JSON sanitizado com revisão, perfil e inventário. Imagens ausentes podem ser informação esperada antes do build.
- **Interpretação de falhas:** saída 1 identifica a etapa; ausência de containers não comprova instalação nova se volumes já existem. Não criar outro projeto para ocultar recursos anteriores.
- **Próxima ação:** revisar inventário; usar --initialize somente sem containers ou volumes desse projeto. Recursos parciais seguem [reconciliação](update-and-rollback.md#operação-interrompida-e-reconciliação).
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Diagnose/precheck não confirmam saúde funcional nem criam histórico.
Confirme capacidade de build/registry: em rede restrita, dependências e imagens
precisam estar disponíveis por meio aprovado. O deploy não provisiona acesso.

## 4. Instalar uma única vez

```bash
python3 scripts/deploy.py apply --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history --revision "$(git rev-parse HEAD)" --initialize
```

- **Onde executar:** host, raiz da revisão aprovada, após precheck e autorização de instalação nova.
- **Efeito:** mutável; constrói imagens, valida perfil, inicializa PostgreSQL/volumes, aplica migrations, inicia e verifica backend/web antes de confirmar o manifesto.
- **Resultado esperado:** saída 0, operação confirmada com revisão/IDs e referência ativa gravada somente após verify; sem bootstrap de usuários ou envio de e-mail.
- **Interpretação de falhas:** saída 1 interrompe o fluxo. Em running/uncertain preserve recursos e histórico; não repita apply nem rode migrate manualmente. A inicialização pode ter criado volumes antes da falha.
- **Próxima ação:** em sucesso executar verify/checklist; em falha consultar diagnose e reconcile em inspeção antes de decidir retomada.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador. Precheck aprovado, janela e backup recuperável; initialize somente em instalação nova.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

A automação chama o runner uma vez e sobe serviços sem dependências
automáticas. Não execute `docker compose up` ou `run migrate` paralelamente.
Falha após intenção de inicialização e antes da primeira tentativa SQL possui
retomada explícita no guia de recuperação. `--initialize` não é adotado em
instalação existente.

## 5. Verificação e entrega

```bash
python3 scripts/deploy.py verify --project synergia --env-file /caminho/privado/synergia-config/homologation.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host, raiz do checkout, com a mesma identidade de instalação e histórico da operação confirmada.
- **Efeito:** verifica imagens efetivas, portas, ledger, endpoints e runtime web; readiness faz escrita temporária no storage. Não executa migration, build ou envio.
- **Resultado esperado:** saída 0, verified: true e revisão confirmada.
- **Interpretação de falhas:** divergência de runtime, ledger ou sondas impede aceite; não editar active.json para declarar sucesso.
- **Próxima ação:** executar [checklist pós-implantação](post-deployment-checklist.md), incluindo login e navegador de outra estação; falhas seguem [diagnóstico](troubleshooting.md).
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Verify usa a configuração congelada no histórico; mudanças posteriores no
env-file não reconfiguram containers. Para aplicar configuração nova, faça uma
atualização pela automação. Desenvolvimento local segue o [roteiro local](../getting-started.md).

## 6. Operação opcional da assistência de IA

Ativar somente após a validação final da #192 e autorização do ambiente. O
runtime não é dependência obrigatória da aplicação. A configuração é privada,
conforme a [referência](environment-reference.md); não baixar pesos ou substituir
pin automaticamente durante deploy, precheck ou healthcheck.

- Fixar versão do runtime e nome/digest aprovados. O provider chama o alias
  `sha256-` seguido dos 64 hex do digest; ele deve existir no runtime e anunciar
  esse digest instalado/carregado. A sonda confere o anúncio, sem atestar o host.
- Usar loopback quando backend/runtime estão no mesmo host, ou serviço exato
  permitido em rede controlada. `127.0.0.1` dentro do backend em container é o
  próprio container. Não abrir o runtime à rede de usuários, habilitar
  redirect/proxy ou enviar destinos vindos do POST.
- Preservar contexto/resposta de 8 KiB, prazo de 30 segundos, uma chamada por
  processo e uma reserva processing global no banco compartilhado. O limite é
  dez novas tentativas por usuário e organização em dez minutos; reuso não
  infere. Isso não equivale a cota diária ou reserva de CPU/RAM/GPU. Dimensionar
  host/modelo junto das jornadas principais; a #191 não homologa throughput,
  hardware ou qualidade do modelo.
- Aplicar migrations pelo runner da automação, incluindo 0040 para auditoria
  das manutenções. Planejar retenção explícita em homologação/produção e rotina
  finita por identidade técnica existente: [prévia e lote efetivo](../runbooks/ai-assistance-retention.md).
- Provisionar os ativos existentes de Prometheus/Grafana e exportação Graylog
  autorizada. Token de métricas/sonda é técnico e privado, sem acesso do browser.
  Não é repassado pelo Compose base: mounts/overlays necessários exigem fluxo
  operacional aprovado, sem edição manual que desvie do ledger.
- Acompanhar flags/coleta, latência, rejeições, in-flight, reservas e manutenção
  nos [painéis e cinco alertas](../ai-assistance-observability.md#alertas-e-painel).
  Sincronizar relógios de banco/Prometheus. Ausência de amostra não é saúde;
  regras locais não criam canal externo de notificação.

Usar a [sonda informativa](../runbooks/ai-assistance.md#sonda-informativa) sem
dados reais; `/health/ready` continua baseado nos serviços essenciais. Conferir
leitura autorizada e caso sintético na janela aprovada. Implantar configuração
nova em todas as instâncias pelo fluxo com histórico, não somente editar env-file.

Para incidente, seguir [suspensão e recuperação](../runbooks/ai-assistance.md)
e [rollback de operação](update-and-rollback.md#assistência-de-ia-suspensão-e-rollback).
O [threat model](../threat-model.md) registra os doze riscos e limites residuais.
