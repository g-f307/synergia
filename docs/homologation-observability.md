# Observabilidade da homologação assistida

Esta entrega fecha a parte executável da issue #145 sem escolher, em nome do
cliente, a plataforma corporativa de logs e métricas nem transformar limiares
exploratórios em SLO. O contrato legível por máquina está em
[`homologation-observability-contract.json`](homologation-observability-contract.json).

## Estado e destinos

Durante a homologação assistida, a API emite logs JSON em `stdout`, o
Prometheus local coleta métricas e o Grafana local apresenta o painel técnico.
Os dois serviços escutam apenas em loopback; `/metrics` exige token técnico. A
retenção local de métricas é de 15 dias. O destino, a retenção e o controle de
acesso corporativos continuam como decisão externa obrigatória antes da
produção.

Nenhum SLO foi aprovado. Os limiares de alerta são guardrails preliminares para
observar a homologação; os valores medidos devem fundamentar a decisão futura.

## Leitura operacional

O painel separa três sinais que não devem ser confundidos:

- **rejeição válida de negócio:** painel `Import volume`, com linhas rejeitadas
  ou ignoradas e alerta de taxa de rejeição;
- **falha sistêmica:** painel `Journey outcomes (1h)`, readiness e alertas de
  falha de execução, HTTP, coleta ou dependência;
- **orçamento de recurso:** painel `Ingestion estimated memory budget`, que
  compara a estimativa da última ingestão ao limite aplicado pelo mesmo modelo.

Uma importação é rastreável sem consulta direta ao banco por
`X-Correlation-ID`/`correlation_id` e `execution_id`. Os logs registram somente
evento, códigos, contagens, duração e tipo de exceção. Conteúdo de célula,
payload, nome original, caminho interno, credencial e token são proibidos.

## Responsabilidade e severidade

- `critical`: plataforma coordena, suspende novas mutações quando necessário e
  aciona banco, backend ou segurança conforme o runbook;
- `warning`: operações faz a triagem, diferencia rejeição válida de defeito e
  escala quando a fila deixa de avançar ou a condição persiste;
- suspeita de vazamento, adulteração, corrupção ou acesso indevido é incidente
  de segurança, independentemente da severidade original.

Cada regra Prometheus aponta para um runbook versionado. Os responsáveis e as
severidades também estão congelados no contrato JSON para evitar divergência
entre documentação e configuração.

## Exercícios controlados

O exercício mínimo tem três observações ordenadas: baseline pronta, falha com
readiness `503` e recuperação com readiness `200`. O teste
`test_storage_probe_controlled_failure_and_recovery` executa esse ciclo contra
o endpoint real `/health/ready`, com um diretório temporário e sem dados de
cliente. Nesta entrega, somente o cenário de storage é exercitado de ponta a
ponta. Banco e worker/e-mail permanecem cenários documentados para a execução
assistida no ambiente autorizado, com procedimentos próprios em
[`runbooks/`](runbooks/homologation-observability.md).

Em ambiente de homologação, cada exercício deve registrar apenas data, cenário,
correlation ID, estados, tempos e responsável. Nunca anexar DSN, segredo,
endereço de destinatário, nome/caminho de arquivo ou conteúdo processado.

## Validação reproduzível

```bash
python scripts/validate_homologation_observability.py
cd backend
pytest -q tests/test_homologation_observability.py tests/test_health.py tests/test_observability.py
```

As regras Prometheus permanecem validadas com `promtool`, conforme
[`observability.md`](observability.md). O validador impede que alertas, runbooks,
painéis, decisões externas e a allowlist segura divirjam do contrato.
