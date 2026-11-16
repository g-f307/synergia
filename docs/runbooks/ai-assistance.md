# Assistência de IA — suspensão e recuperação

Entrega incremental da #191. Este checkpoint cobre controles de operação;
métricas, alertas, painel e exercício Graylog serão entregues nos próximos blocos.
A ativação operacional continua condicionada à validação final da #192.

## Escolher o controle

| Configuração | Leitura | Novos POSTs | Interface |
| --- | --- | --- | --- |
| `ENABLED=false` | 503, como antes | 503 `ai_assistance_disabled` | card oculto |
| `ENABLED=true`, `GENERATION_ENABLED=false` | autorizada, sem provider | 503 `ai_assistance_generation_disabled` | resultados consultáveis, sem botão |
| `ENABLED=true`, `GENERATION_ENABLED=true` | autorizada | sujeita a todas as validações e limites | geração explícita |

Prefixo das duas variáveis: `SYNERGIA_AI_ASSISTANCE_`. A nova variável
`GENERATION_ENABLED` tem padrão `true`, subordinado à flag geral cujo padrão
continua `false`. Não há ativação implícita em instalações existentes.

Para suspender novas gerações, manter `ENABLED=true` e configurar
`GENERATION_ENABLED=false` no mecanismo privado de configuração do ambiente.
Recriar o serviço pelo procedimento de implantação. No Compose local, com a
configuração já alterada e o checkout/imagem corretos:

```bash
docker compose up -d --no-deps --force-recreate backend
```

Alterar apenas o arquivo não modifica o ambiente de um processo já iniciado.
Instâncias antigas ainda em rotação conservam a configuração anterior: retirar
todas elas antes de declarar a suspensão efetiva. Requisições já admitidas podem
terminar dentro do prazo do provider ou ser interrompidas pelo reinício; o
controle não promete desfazer processamento já enviado ao runtime.

A leitura usa contexto e repositório, sem criar provider nem limitador de
geração. Em modo suspenso é possível omitir endpoint e modelo/digest; se presentes,
continuam validados. Banco, retenção e autenticação/autorização continuam
necessários. Não executar rollback SQL para suspender geração: isso apagaria
dados da assistência e não é o kill switch operacional.

## Sonda informativa

`GET /operations/ai-assistance/health` exige o mesmo Bearer técnico de `/metrics`
(`OBSERVABILITY_METRICS_TOKEN`), em rede controlada. Não é endpoint para usuários
humanos e nunca deve ser consultado pelo Angular ou usado para readiness.

| Status | Significado |
| --- | --- |
| `disabled` | flag geral desligada; nenhum acesso ao runtime |
| `suspended` | geração suspensa; nenhum acesso ao runtime |
| `healthy` | versão e modelo/digest anunciados conferem no instante da consulta |
| `busy` | exclusão local ocupada; não houve nova chamada concorrente |
| `unavailable` | configuração, transporte ou pin não validado; consultar código fechado |

HTTP 200 significa que a sonda informativa executou. Não comprova que uma futura
inferência será bem-sucedida. HTTP 401 indica credencial técnica inválida; 503,
configuração de observabilidade inválida. A resposta contém somente `status`,
`generation_enabled`, `duration_ms` e `code`.

A sonda só faz GET de `/api/version` e `/api/tags`, com o mesmo transporte sem
proxy/redirect e limite de 8 KiB. Usa processo isolado, orçamento curto de três
segundos com margem para encerramento e exclusão compartilhada com a geração.
Não carrega pesos nem chama `/api/chat`. Pin conferido é o anunciado pelo runtime;
comprometimento do próprio host/runtime permanece fora dessa comprovação.

Com Python do backend e token já fornecido pelo mecanismo seguro do ambiente,
a consulta local abaixo não coloca o segredo nos argumentos nem o imprime:

```bash
backend/.venv/bin/python - <<'PY'
import os
import urllib.request

try:
    token = os.environ['OBSERVABILITY_METRICS_TOKEN']
    request = urllib.request.Request(
        'http://127.0.0.1:8000/operations/ai-assistance/health',
        headers={'Authorization': 'Bearer ' + token},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=5
    ) as response:
        print(response.read(2048).decode())
except Exception:
    raise SystemExit('ai_assistance_probe_failed') from None
PY
```

`/health/live` e `/health/ready` não consultam o runtime. Uma sonda IA indisponível
não retira uma API saudável da rotação nem impede consulta de resultados válidos.

## Recuperar reservas expiradas

Procedimento administrativo local, pelo operador autorizado, usando a conexão
privada do banco e uma identidade técnica existente. Não há endpoint público de
recuperação. Uma reserva normal dura dois minutos; não reduzir seu prazo para
forçar recuperação. Antes, confirmar a suspensão e o encerramento dos workers
antigos. Não repetir uma geração enquanto a anterior puder estar ativa.

Na raiz, com `DATABASE_URL` já configurada pelo mecanismo seguro:

```bash
read -r -p 'UUID da identidade técnica existente: ' AI_ASSISTANCE_ACTOR_ID
export AI_ASSISTANCE_ACTOR_ID
PYTHONPATH=backend backend/.venv/bin/python scripts/recover_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100 --dry-run
```

Conferir quantidade e intervalo antes do modo efetivo:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/recover_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100 --apply
```

Sem `--apply`, a execução é sempre prévia. O lote aceita 1–1000 registros,
usa `FOR UPDATE SKIP LOCKED` e remove somente reservas `processing` cujo prazo
venceu. Preserva reservas válidas e resultados, não chama o modelo e não cria
nova geração. Repetir a prévia até zerar o recorte; processamento concorrente
pode fazer a quantidade efetiva diferir da prévia.

Cada remoção emite `ai.assistance.expired` e sua projeção Graylog na mesma
transação; o histórico não é removido. A finalização por um UUID de reserva já
recuperada é recusada. O comando mostra apenas quantidade e intervalo; erros
usam o código `ai_assistance_recovery_failed`, sem DSN ou conteúdo.

## Distinguir falhas e reabilitar

- Contexto/elegibilidade: verificar lifecycle terminal e permissões da execução.
- Provider: comparar código da sonda, pin configurado e disponibilidade local.
- Validação: fallback/rejeição não significa indisponibilidade de banco.
- Persistência: erro de integridade impede entrega; não editar JSON para contornar.
- Frontend: conferir capability; após suspensão, a leitura continua sujeita às
  permissões e ao hash atual do contexto. Um resultado antigo incompatível não
  deve aparecer como atual.

Para reabilitar, confirmar configuração/pin, recursos disponíveis, ausência de
workers anteriores e reservas presas, auditoria funcional e autorização da janela.
Restaurar `GENERATION_ENABLED=true` e recriar as instâncias. Conferir sonda,
readiness e um caso sintético autorizado. Os próximos blocos acrescentam critérios
por métricas/alertas; este checkpoint não declara a #191 ou #192 concluída.
