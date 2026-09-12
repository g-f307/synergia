FROM node:24-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
USER root
RUN apk upgrade --no-cache
ENV SYNERGIA_API_ORIGIN=http://localhost:8000
ENV NGINX_ENVSUBST_FILTER=^SYNERGIA_
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chown=nginx:nginx runtime-config.js.template /opt/synergia/runtime-config.js.template
COPY --chmod=755 docker-entrypoint.d/40-synergia-config.sh /docker-entrypoint.d/40-synergia-config.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-synergia-config.sh
COPY --chown=nginx:nginx --from=build /workspace/dist/synergia-web/browser /usr/share/nginx/html
USER nginx
EXPOSE 8080
