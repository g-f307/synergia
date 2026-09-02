# Aplicação web do SYNERGIA

Frontend oficial do SYNERGIA, implementado em Angular 20. Os contratos são
consumidos exclusivamente pela API FastAPI; esta aplicação não acessa o banco
ou os arquivos importados diretamente.

A Etapa 2 acrescenta login, refresh por cookie `HttpOnly`, interceptor, guards,
perfil/preferências, avatar e consulta administrativa inicial. O access token
permanece somente em memória e o backend continua sendo a autoridade de acesso.

## Desenvolvimento

Instale exatamente as versões do lockfile e inicie o servidor:

```bash
nvm use
npm ci
npm start
```

O arquivo `.nvmrc` fixa a versão de Node.js usada também pela CI.

A aplicação fica em <http://localhost:4200>. O endereço da API está em
`src/environments/environment.ts` e, no ambiente local, aponta para
`http://localhost:8000`.

## Validação

```bash
npm run lint
npm test -- --watch=false --browsers=ChromeHeadless --code-coverage
npm run build
```

O build de produção é gerado em `dist/synergia-web/`. A CI usa a versão de
Node.js declarada em `.nvmrc` e executa os três comandos acima em todo PR para
`main`.

## Limites atuais

Não há framework end-to-end configurado nesta etapa. Playwright/RPA está
planejado e sua adoção exige issue e configuração próprias. O protótipo
estático publicado em `prototype-pages` é uma referência separada e não faz
parte deste diretório.

Consulte a [arquitetura](../docs/architecture.md) e a
[reconstrução do ambiente](../docs/local-environment.md) para o contexto
completo.
