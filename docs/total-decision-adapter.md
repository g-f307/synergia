# Adapter Total Decision para GMES/OQC

## Contrato e limites

A issue #140 entrega o adapter `total_decision@1.0.0`, configurado em
`backend/app/model/total_decision_adapter.json`, sincronizado por teste com o
contrato `1.2.0-draft`. Ele recebe `source=Total Decision` em `POST /imports`,
apenas XLSX, e entrega registros GMES/OQC ao pipeline existente.

A aba autorizada é `Sheet1`. As linhas 1 e 2 contêm o cabeçalho; a linha 3 é
sempre excluída como total; os registros começam na linha física 4. Seletores
combinam a letra da coluna com o caminho do cabeçalho. Grupos mesclados são
resolvidos apenas nos intervalos declarados de `Total Decision` e `ERP Upload`.
Deriva em qualquer coluna autorizada bloqueia a aba antes de importar registros.
Colunas adicionais e outras abas são ignoradas com ocorrência explícita, sem
copiar seu conteúdo ou nomes de abas desconhecidas ao relatório.

Os orçamentos globais de [ingestão XLSX](xlsx-ingestion-budget.md) se aplicam e
aceitam sufixo `_TOTAL_DECISION`. Somente as colunas mapeadas são retidas.
`INGESTION_ALLOWED_SHEETS_TOTAL_DECISION` pode restringir a seleção, nunca
ampliá-la para abas fora do contrato. A inspeção de segurança cobre o pacote
inteiro, inclusive conteúdo fora da allowlist. Não foram ampliados limites de
upload. O pipeline completo continua limitado por orçamento e não tem memória
constante; os registros necessários à consolidação são retidos.

## Mapeamento e políticas conservadoras

| Origem | Campo | Política |
| --- | --- | --- |
| A, B | `production_date`, `inspection_date` | data local sem fuso inventado; texto não interpretável preservado com `unparsed_date` |
| C, BE | `oqc_id`, `oqc_lot_id` | identificadores distintos, textuais, sem equivalência automática com lote operacional |
| J, BF | `workorder_number`, `workorder_id` | sem fallback do ID numérico para número de Workorder; só ID gera aviso de relação pendente |
| D, F, G | linha, modelo e sufixo | texto |
| AK, AL | resultado e instante de decisão | campos próprios da origem; estado desconhecido preservado com aviso; sem criar aprovação humana |
| AP, AQ | resultado e instante de upload ERP | campos próprios; sem executar upload ou interpretar alçada |
| AX, AY, AZ, BA | hold, uploaded, rework e remaining quantity | quantidades separadas, decimais não negativas; ausência continua `null` |
| BM | `source_organization_code` | não mapeado para `organization_code` nem para concessão IAM |
| AM, AN, AR | indicadores `*_present` | somente presença, minimizada antes do pipeline |

A identidade mínima exige `oqc_lot_id` e pelo menos um dos identificadores de
Workorder. Números em campos de identificador viram texto com aviso de zeros
irrecuperáveis; booleanos e números não finitos são inválidos. Linhas com
fórmula, erro de Excel, quantidade negativa ou identidade insuficiente são
rejeitadas individualmente. Linhas vazias são ignoradas. Duplicidade de linha
segue o aviso do pipeline; identidade de negócio não é deduplicada por regra
inventada enquanto a precedência estiver pendente.

Valores originais não restritos são preservados separadamente das conversões.
Números não finitos são rejeitados nos campos não restritos e representados como texto
no registro rejeitado, pois JSON estrito e PostgreSQL JSONB não aceitam esses
números. A representação exata permanece no arquivo original controlado.
Campo, coluna, caminho do cabeçalho e versão do adapter aparecem nas
transformações; arquivo/hash, aba, linha e execução completam a proveniência.
Textos de usuário e observações não aparecem em `original_values`,
`transformations`, ocorrências ou arquivos normalizados: são substituídos por
booleanos de presença. O original aceito permanece no armazenamento controlado,
conforme a política de uploads existente. Preservação estruturada integral
desses textos exige novo contrato de acesso e retenção.

Os seletores e essas políticas técnicas não aprovam a semântica corporativa.
Chaves OQC, relação entre identificadores de Workorder, catálogo de resultados,
fuso, equivalência de organização e precedência continuam aguardando cliente.
Nenhuma decisão desta issue altera as regras OQC ou as alçadas humanas.

## Validação sem persistência e reconciliação

```bash
python scripts/generate_total_decision_fixture.py /tmp/total-sintetico.xlsx --edge
python scripts/validate_total_decision.py /tmp/total-sintetico.xlsx --strict
DATABASE_URL=... python scripts/validate_total_decision.py /tmp/total-sintetico.xlsx \
  --execution-id <id> --strict
```

O comando inspeciona o pacote e executa o pipeline sem repositório persistente.
Retorna somente contagens e códigos, sem nome de arquivo, conteúdo de célula,
identificadores ou textos livres. `--output` grava o mesmo relatório sanitizado.
As equações são `read = ignored_total + imported` e
`imported = normalized + rejected`. Duplicatas são contadas separadamente e
podem ser também rejeitadas por outro erro, sem dupla subtração.

Com `--execution-id`, uma conexão somente leitura primeiro verifica a fonte e
o SHA-256 do arquivo na execução; depois compara os totais daquele arquivo.
Execução ou arquivo incompatível é recusado. O modo `--strict` retorna falha
para deriva estrutural, orçamento excedido, desequilíbrio ou divergência de
persistência. Rejeições individuais equilibradas não são falha estrutural.

Idempotência usa o SHA-256 e o ciclo de execução existentes: o mesmo arquivo
reenviado retorna `duplicate_file`; reprocessamento autorizado cria nova
tentativa e não sobrescreve o histórico; confirmar o mesmo resultado duas
vezes é recusado. O adapter não redefine essas políticas.

## Persistência e compatibilidade

Aplicar a migration aditiva `0032_allow_total_decision_source.sql`. Ela amplia
as restrições de fonte em execuções, arquivos e inspeções. A adoção de um banco
legado exige que as três restrições estejam presentes; não basta ampliar uma.
O rollback explícito recusa execução quando já houver dados dessa família.
Migrations anteriores permanecem imutáveis.

A API passa a `0.8.0`. CSV/JSON e XLSX genéricos de GMES/OQC e WO Status mantêm
seus importadores. Este incremento não acrescenta opção ao formulário Angular.

## Validação representativa

A execução local autorizada de 23/10/2026, sem persistência, percorreu 551 linhas:
550 normalizadas, uma rejeitada por quantidade negativa e nenhuma duplicada.
A linha de totais foi excluída. Foram sinalizadas 1.102 datas não interpretáveis,
1.090 estados desconhecidos e 1.228 ocorrências de minimização. As 53 colunas
fora da allowlist foram sinalizadas. Todas as contagens reconciliaram.

Esses agregados descrevem a amostra; não aprovam seus estados nem constituem
teste de capacidade. Fixtures e testes automatizados são inteiramente
sintéticos; os arquivos reais permanecem ignorados em `docs/files/`.
O corpus amplo, concorrência e volume integrado seguem na #141.

## Verificação da implementação

Na máquina de desenvolvimento Ubuntu 24.04, Python 3.12 e PostgreSQL 16:

- suíte não integrada após a revisão: 721 testes aprovados;
- integração completa após a revisão em banco novo, com as 32 migrations: 609 aprovados;
- jornadas Playwright existentes na validação anterior: 14 aprovadas;
- Ruff, compilação Python, 93 massas sintéticas e validadores de acesso, jornadas, ameaças, decisão de release e HTTP aprovados;
- imagem backend construída, migrations locais e smoke de saúde aprovados;
- upload autenticado da fixture sintética e leitura do artefato minimizado validados no container.

Uma rodada anterior no banco de testes reutilizado falhou em dois testes preexistentes por estado persistido de políticas e fila de e-mail. A repetição em banco novo, conforme a CI, aprovou toda a suíte. O teste específico de persistência também passou após adequar sua limpeza à desativação lógica obrigatória de organizações IAM.

O gerador fixa metadados e timestamps do ZIP; um teste compara a saída à fixture versionada, além de comparar gerações na mesma sessão. A verificação específica de reprocessamento confirma replay do pedido, família Total Decision e preservação dos resultados originais.

### Revisão de continuidade da #140

A revisão adicionou regressões para três casos: cabeçalho ausente ou truncado
agora produz `contract_drift` antes da importação; números não finitos rejeitam
somente sua linha, sem inviabilizar JSONB e a persistência das linhas válidas;
colunas adicionais sem título também geram `column_ignored`, sem copiar valores.

| Critério | Evidência local |
| --- | --- |
| Cabeçalhos em dois níveis e exclusão de totais | contrato versionado; testes de grupos, deriva e linhas físicas 4 em diante |
| IDs textuais, datas, ausência e estados | testes sintéticos de zeros, nulos, datas e resultados desconhecidos |
| Dados restritos e campos adicionais | sentinelas ausentes dos artefatos; auditoria de colunas e abas ignoradas |
| Proveniência e persistência GMES/OQC | testes de arquivo, hash, aba, linha, versão, originais minimizados e reconciliação PostgreSQL |
| Validação sem persistência | relatório de contagens equilibradas; comparação vinculada ao arquivo e à execução |
| Repetibilidade e reprocessamento | fixture determinística; duplicidade de upload; replay e preservação do histórico |
| Contrato, API e matriz | testes de sincronização da especificação, OpenAPI e documentação atualizada |

A amostra real foi novamente validada sem persistência e manteve os mesmos
agregados. O formulário Angular continua fora deste incremento; a fonte está
disponível pela API. Semântica corporativa pendente e homologação da #141 não
são concluídas por esta revisão.

Na revisão, uma execução iniciada antes das migrations no banco novo foi
interrompida e descartada. A suíte não integrada também foi repetida sem o
`.env` de desenvolvimento: sua configuração de cookie local conflita com um
teste preexistente de configuração produtiva. Os totais acima correspondem às
execuções corretas, com o esquema aplicado e o isolamento de ambiente da CI.

Comandos principais, usando um banco novo e isolado para integração:

```bash
python -m pytest -q -m "not integration" backend/tests
DATABASE_URL=... PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=... \
  python -m pytest -q -m integration backend/tests
ruff check backend scripts
```

Os resultados locais não substituem a CI remota, a revisão do PR ou os aceites corporativos. Nenhuma release ou liberação produtiva é autorizada por essa validação.
