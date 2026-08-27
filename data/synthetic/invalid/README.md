# Arquivos sintéticos inválidos

`n-fp_invalid_rows.csv` reúne erros intencionais para exercitar o relatório:

- quantidade e data inválidas;
- Workorder ausente e chave sem correspondência;
- serial duplicado e serial com formato inválido;
- organização desconhecida;
- erros de fórmula preservados (`#VALUE!` e `#REF!`);
- linha vazia.

O arquivo deve resultar em uma execução com estado `blocked`. Ele é evidência de
teste e não deve ser corrigido nem usado como entrada válida.
