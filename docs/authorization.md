# Autorização das APIs

Todas as operações OpenAPI, exceto `GET /health`, `POST /auth/login` e
`POST /auth/refresh`, exigem access token Bearer. O backend valida assinatura,
emissor, audiência, algoritmo e datas do JWT e confirma no PostgreSQL que o
usuário e a sessão continuam ativos.

## Decisão de acesso

As permissões são carregadas do banco em cada requisição por concessão direta,
papel ou grupo. Papéis recebidos do cliente ou gravados no JWT não autorizam
operações. Por isso, revogação de sessão, desativação do usuário e mudança de
papel produzem efeito imediato.

- autenticação ausente, inválida, expirada ou revogada retorna `401`;
- usuário autenticado sem a ação exigida retorna `403`;
- recurso inexistente ou pertencente a outra organização retorna o mesmo `404`;
- uma concessão global é representada por escopo nulo; caso contrário, somente
  os UUIDs de organização concedidos são aceitos.

Novos uploads recebem `organization_id`. Quando o ator possui exatamente um
escopo para `import.create`, ele pode ser inferido; concessões globais ou
múltiplas exigem seleção explícita. A execução persiste esse UUID, e o
reprocessamento herda o mesmo escopo. Dados históricos sem classificação IAM
não são expostos por verificações organizacionais.

## Auditoria e correlação

A API aceita `X-Correlation-ID` no formato UUID ou gera um novo valor e sempre
o devolve na resposta. Negações relevantes registram ação, método, rota
normalizada, UUID interno do ator, sessão, organização e correlation ID. Tokens,
e-mails, IPs em texto puro e conteúdo dos recursos não são registrados.

## Validação

```bash
cd backend
pytest -q -m "not integration"
ruff check app tests ../scripts
cd ..
python scripts/validate_access_matrix.py
```

Os testes marcados como `integration` exigem PostgreSQL 16 com todas as
migrations aplicadas.
