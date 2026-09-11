# Relatório de verificação HTTP, cache e conteúdo

- baseline aplicada em respostas de sucesso, erro e preflight;
- CORS validado com origem permitida e bloqueada, métodos e headers explícitos;
- cache compartilhado desabilitado para contratos sensíveis e downloads;
- cookies de refresh mantidos como `HttpOnly` e `SameSite=Strict`, com `Secure`
  obrigatório em produção;
- CSP sem `unsafe-eval` e varredura automática de sinks DOM perigosos;
- envelopes inesperados permanecem genéricos e não serializam exceções internas.

As verificações executáveis estão em `backend/tests/test_http_security.py` e
`scripts/validate_http_security.py` e fazem parte da CI.

As correções da revisão também validam o build Angular publicado com CSP
configurável por ambiente, bloqueio real de framing no navegador e respostas
`500` geradas externamente ao middleware com a baseline completa.
