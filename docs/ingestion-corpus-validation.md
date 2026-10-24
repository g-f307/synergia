# Corpus, reconciliação e volume de ingestão

A issue #141 verifica os adapters WO Status e Total Decision já implementados.
Os casos reproduzem somente a estrutura pública dos contratos: todos os valores
das fixtures são inventados. Arquivos reais continuam ignorados em `docs/files/`.
Esta entrega não confirma semântica corporativa, não aumenta limites padrão e
não autoriza liberação assistida ou produção.

## Corpus e gabaritos

O corpus `data/synthetic/ingestion-v1/` contém onze XLSX mínimos e seus gabaritos:

| Caso | Cobertura |
| --- | --- |
| `wo-composite` | quatro abas contratadas, abas derivadas/ocultas, fórmulas espelhadas, lacuna, quantidade negativa, duplicata, estado desconhecido e cauda de fórmulas |
| `wo-nfp`, `wo-owm`, `wo-container`, `wo-blocked` | abas isoladas, fonte lógica e política de bloqueio |
| `wo-drift` | cabeçalho alterado; demais abas continuam processáveis |
| `td-clean`, `td-edge` | dois níveis de cabeçalho, totais, IDs textuais, dados restritos, quantidade negativa, fórmula, ausência de chave e estado/data desconhecidos |
| `td-mixed` | duplicata literal, linha vazia, data serial Excel, data textual e erro `#REF!` em quantidade |
| `td-drift`, `td-additional` | deriva estrutural, coluna sem título e aba desconhecida |

O manifesto congela seed nominal 141, versões do gerador/schema 1.0.0,
configuração, inventário e SHA-256 de cada XLSX e JSON. O gabarito congela
contagens, códigos e um digest dos valores normalizados sintéticos, originais
minimizados e transformações. Verificação não escreve nem atualiza gabaritos.
O gerador fixa timestamps do documento e do ZIP; uma mudança de dependência que
altere os bytes exige revisão explícita. A verificação também recusa arquivos
extras, inclusive em subdiretórios.
Configuração divergente do gerador também é recusada. Um teste altera um
gabarito e atualiza seu hash para comprovar que a comparação semântica continua
detectando a divergência, independentemente da integridade dos bytes.

```bash
backend/.venv/bin/python scripts/build_ingestion_corpus.py
# Apenas para uma mudança intencional, seguida de revisão dos diffs:
backend/.venv/bin/python scripts/build_ingestion_corpus.py --write
```

## Reconciliação e política de duplicatas

Cada aba contratada declara se está presente e relaciona linhas lidas,
ignoradas, importadas, rejeitadas, normalizadas/aceitas e duplicadas:

```text
lidas = ignoradas + importadas
importadas = normalizadas + rejeitadas
aceitas = normalizadas
```

As linhas de cabeçalho e totais excluídas pelo contrato não entram em "lidas".
Duplicadas são uma dimensão adicional: duplicata de linha pode permanecer
normalizada com aviso; conflito de serial pode ser rejeitado pelo pipeline.
Não se subtrai uma duplicata duas vezes nem se inventa deduplicação de negócio.
Rejeições por capacidade são terminais e não são reconciliações parciais bem-sucedidas.

Os testes PostgreSQL comparam gabarito, contagens de `imported_records`,
`normalized_records`, estado de rejeição, hash do arquivo e proveniência.
Também comparam o conteúdo integral persistido de originais, valores normalizados
e transformações com o resultado do pipeline. Testes de corrupção mantêm as
contagens e alteram os valores no banco, exigindo que a reconciliação falhe.
Incluem onze casos congelados, duas famílias disputando o mesmo arquivo,
arquivos distintos em organizações distintas, lotes gerados concorrentes e
pedidos concorrentes de reprocessamento seguidos do processamento efetivo.

A política existente de reserva usa arquivos e versões do pipeline/catálogo.
Uma disputa pelo mesmo arquivo admite um proprietário; o concorrente não
persiste um segundo resultado. Reprocessamento explícito cria uma tentativa,
replay do pedido retorna a mesma tentativa e o processamento mantém a execução
original intacta. Não se altera o escopo dessa política nesta issue.

Testes pela API usam autorização sintética, com banco e armazenamento reais e
isolados. Rejeições por linhas e memória deixam estado `failed`, sem registros
operacionais, arquivos aceitos ou reservas residuais; reenviar após remover o
limite forçado funciona. A limpeza desativa logicamente usuários/organizações
de teste, conforme as regras de IAM.

## Volume e medição

O runner gera massas temporárias e abre um novo processo por cenário. Cada
família tem seis cenários: processamento dentro do orçamento e rejeição por
linhas, células/dimensão, estimativa de memória, quantidade de ocorrências e
tempo. Os limites de rejeição são deliberadamente baixos e específicos da
fonte; o cenário normal usa a configuração efetiva do ambiente.

```bash
# Perfil da CI: 1.000 linhas base por família; doze cenários.
backend/.venv/bin/python scripts/run_ingestion_validation.py \
  --profile ci --output /tmp/ingestion-ci.json

# Perfil local: 10.000 linhas base por família.
backend/.venv/bin/python scripts/run_ingestion_validation.py \
  --profile local --output /tmp/ingestion-local.json
```

WO Status gera NFP e OWM com N linhas, CTNR com N/2 e as linhas constantes de
LOT PENDING_OQC; Total Decision gera N linhas operacionais. Quantidades da
massa limpa permanecem não negativas ao ampliar o volume. A geração acontece
fora do worker medido e seus arquivos não são versionados.
A geração consome memória no processo operador e não está coberta pelo
watchdog de ingestão. Os perfis medidos não atestam valores arbitrários de
`--rows`; a medição RSS do relatório descreve somente o worker de ingestão.

O relatório informa CPU, arquitetura, CPUs lógicas, memória física e limite
cgroup disponível, SO/kernel, versões Python/dependências, limites efetivos,
bytes de entrada, duração e pico RSS. No Linux usa `VmHWM` de `/proc/self/status`:
`getrusage` pode herdar o pico pré-exec do processo gerador. Em outros sistemas
com `resource`, há fallback `getrusage`; a evidência validada desta entrega é Linux.

Um watchdog externo encerra um worker que exceda `--timeout` (padrão 900 s).
Timeout, erro de processo e erro de validação não contam como rejeição segura:
o comando retorna falha. O cenário normal exige reconciliação equilibrada e
ausência de bloqueio estrutural e compara todas as contagens por aba com a
massa gerada; cada cenário negativo exige seu código exato. O timeout precisa
ser positivo e finito; `NaN` e infinito não desabilitam o watchdog.

RSS é o pico do processo, não consumo marginal por fase. O limite de memória
da aplicação é uma estimativa preventiva, não um teto RSS imposto pelo kernel.
Tempos/RSS são observações em máquina de desenvolvimento compartilhada, sem
afinidade de CPU ou isolamento de carga; não são SLA nem teste de capacidade
corporativa. A CI verifica resultados e códigos, sem limiares frágeis de duração.

## Arquivo integral restrito e evidência pública

O runner nunca descobre automaticamente arquivos reais. A seleção exige caminho,
fonte explícita e `--allow-real`, é recusada quando `CI=true`/`CI=1` e não aceita
redução com `--rows`. Não há persistência nem conexão ao banco nesse modo.

```bash
backend/.venv/bin/python scripts/run_ingestion_validation.py \
  --real-workbook '<arquivo local autorizado>' --source 'WO Status' \
  --allow-real --profile local --output /tmp/ingestion-restricted.json
```

As restrições de CI/opt-in são proteções da ferramenta operacional, não uma
fronteira de autorização contra quem já tem acesso ao arquivo e ao Python.
Somente executar onde o acesso ao exemplar estiver autorizado. Ambientes com
políticas mais restritivas podem rejeitar o exemplar sem alterar os padrões.

Relatórios usam allowlist de métricas, códigos, configuração numérica e nomes
de abas do contrato. Não incluem caminho/nome/hash do workbook real, nomes de
abas desconhecidas, identificadores, usuários, observações ou conteúdo de
células. stdout/stderr brutos de workers não são publicados. Diferentemente
dos relatórios legados individuais, a evidência desta issue não propaga seus
metadados de arquivo. Sentinelas verificam esse limite nos testes automatizados.

A CI verifica hashes/gabaritos, executa o perfil reduzido e publica somente
`ingestion-validation.json` no artefato `ingestao-sintetica`. Os testes de
persistência e concorrência entram no job PostgreSQL já existente. Nenhuma
planilha real é requerida ou publicada pela CI.

## Evidências e continuidade

O relatório da execução local está em [ingestion-validation-report.md](ingestion-validation-report.md).
Matriz: [traceability-matrix.md](traceability-matrix.md). Os comandos seguem os
mesmos diretórios da CI; o lint oficial parte de `backend/`:

```bash
cd backend
.venv/bin/ruff check . ../scripts
.venv/bin/python -m pytest -q -m 'not integration'
# Em banco isolado preparado, com DATABASE_URL e PG* correspondentes:
.venv/bin/python -m pytest -q -m integration
```

Aumento de limites, catálogo de estados, chaves corporativas, precedências e
liberação assistida continuam sujeitos a decisões próprias e aceite do cliente.
