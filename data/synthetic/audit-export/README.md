# Exemplos sintéticos de exportação de auditoria

`example.json` e `example.csv` representam o mesmo evento fictício no formato
1.0.0. UUIDs, datas e identificadores são sintéticos; não correspondem a uma
conta ou exportação real. A geração foi fixada em 2026-09-02T00:00:00Z.

O CSV contém uma linha `manifest` e uma linha `event`; somente a segunda entra
na contagem. `filters` e `metadata` são células com JSON. O JSON possui os mesmos
filtros, instante, versão, fuso, contagem e evento.

O contrato completo e os procedimentos operacionais estão em
[audit-export.md](../../../docs/audit-export.md). Os exemplos não são dados para
seed, não contêm autenticação e não devem ser importados como workbooks.
