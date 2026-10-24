# Corpus de ingestão v1

Dados inteiramente inventados. Nenhum valor, nome de usuário ou identificador
foi extraído dos workbooks do cliente. Somente a estrutura publicada dos
adapters é reproduzida. Seed nominal: 141; gerador e schema: 1.0.0.

`manifest.json` congela inventário, configuração e SHA-256 dos XLSX e gabaritos.
Os JSON por caso congelam contagens, códigos e digest semântico dos registros
normalizados sintéticos (incluindo proveniência). Duplicatas seguem a política
existente: são sinalizadas, não subtraídas automaticamente das linhas aceitas.
Rejeitadas são persistidas como registros importados rejeitados, sem registro
normalizado. Abas ausentes são explícitas nos casos mínimos por aba.

Casos: WO Status composto e bordas; NFP, OWM SN, CTNR STATUS e LOT PENDING_OQC
isoladas; deriva no WO Status; Total Decision limpo, bordas, duplicata, vazio,
datas mistas/serial Excel e #REF!, deriva, coluna e aba adicionais. A linha de
totais do Total Decision contém sentinela e nunca alimenta o domínio. A aba
LOT PENDING_OQC continua bloqueada pelo contrato vigente.

```bash
backend/.venv/bin/python scripts/build_ingestion_corpus.py
# Apenas ao revisar uma alteração intencional das fixtures/gabaritos:
backend/.venv/bin/python scripts/build_ingestion_corpus.py --write
```

Verificação nunca regenera gabaritos. Alterar um gabarito exige revisar seu diff
e suas expectativas; atualizar hashes não constitui aceite de negócio. O teste
de regeneração identifica mudanças de bytes, inclusive em dependências XLSX.
Massas maiores são geradas temporariamente, fora deste diretório.
