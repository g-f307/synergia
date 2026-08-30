# Acompanhamento de execuções

Esta API expõe o estado persistido do pipeline sem depender dos arquivos importados.
Todos os contratos usam o PostgreSQL como fonte de verdade e erros seguem o envelope
`{"error":{"code":"...","message":"...","details":{}}}`.

## Contratos

- `GET /executions/{id}`: estado atual, ciclo (`active`, `completed`, `partial` ou
  `failed`), versões, datas, relação de reprocessamento, histórico e contagens.
- `GET /executions/{id}/divergences`: erros e avisos paginados. Aceita `source`,
  `severity`, `code`, `workorder`, `date_from`, `date_to`, `page`, `page_size` e
  `sort=oldest|newest`.
- `GET /executions/{id}/classifications`: classificações paginadas e respectivas
  regras, prioridades, justificativas e evidências estruturadas.
- `GET /executions/{id}/pending-items`: pendências paginadas da execução.
- `GET /executions/{id}/evidences`: catálogo paginado dos arquivos aprovados.
- `GET /executions/{id}/evidences/{evidence_id}/download`: download controlado.

A ordenação de todas as listas é estável por data ou identificador e sempre possui
desempate pelo identificador público. As evidências são
identificadas por número e nome gerado; nomes originais, `storage_key`, caminhos de
quarentena e caminhos absolutos nunca fazem parte das respostas. Arquivos rejeitados
retornam `403 evidence_not_allowed`.

As contagens de arquivos distinguem `files_received`, `files_accepted` e
`files_rejected`. O campo legado `files` representa todos os recebimentos inspecionados,
inclusive os rejeitados. Em evidências, `available` somente é verdadeiro quando existe
uma chave de armazenamento segura e o arquivo está fisicamente disponível.

## Cenários de estado

| Ciclo público | Estados persistidos |
|---|---|
| `active` | `pending`, `validating`, `normalizing`, `consolidating`, `applying_rules`, `reprocessing` |
| `completed` | `completed`, `duplicate` |
| `partial` | `completed_with_errors` |
| `failed` | `validation_failed`, `failed`, `cancelled` |

O Swagger em `/docs` e o OpenAPI em `/openapi.json` são a referência executável dos
parâmetros e modelos.

## Demonstração sintética

Com a API e o PostgreSQL iniciados, o script gera as massas, importa as quatro fontes,
captura o identificador criado e consulta todo o acompanhamento:

```bash
API_URL=http://localhost:8000 scripts/demo_execution_monitoring.sh
```

O roteiro remove a massa temporária ao terminar e não exige rede corporativa ou RPA.
A coleção reproduzível para clientes HTTP está em
[`docs/http/execution-monitoring.http`](http/execution-monitoring.http).
