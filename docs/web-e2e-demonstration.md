# Demonstração reproduzível do fluxo web

## Preparação

Com PostgreSQL 16 ativo e todas as migrations aplicadas em um banco vazio:

```bash
export DATABASE_URL=postgresql://synergia:senha@localhost:5432/synergia_e2e
python scripts/bootstrap_web_e2e.py
cd web
npm ci
npx playwright install chromium
npm run e2e
```

O bootstrap cria exclusivamente dados marcados como sintéticos. A senha pode
ser substituída por `E2E_PASSWORD`; o valor padrão existe apenas para o banco
descartável do teste. O script não imprime senha, hash ou token.

## Jornada demonstrada

1. autenticar o operador sintético;
2. enviar as fontes N-FP e GMES/OQC da fixture versionada;
3. localizar a execução persistida;
4. consultar `SYN-WO-000001`;
5. abrir a fila e o detalhe de uma pendência gerada pelas regras;
6. repetir controles negativos de sessão, papel, organização, rejeição e rede;
7. validar inglês, viewport móvel, teclado e acessibilidade automatizada.

O relatório navegável fica em `web/reports/e2e-html/index.html`. Vídeos,
capturas e traces ficam em `web/reports/e2e-results/` e são publicados pela CI
como o artefato `fluxo-web-e2e`.

