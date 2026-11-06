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
