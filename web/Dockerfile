FROM node:24-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
ENV SYNERGIA_API_ORIGIN=http://localhost:8000
ENV NGINX_ENVSUBST_FILTER=^SYNERGIA_
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY runtime-config.js.template /opt/synergia/runtime-config.js.template
COPY docker-entrypoint.d/40-synergia-config.sh /docker-entrypoint.d/40-synergia-config.sh
COPY --from=build /workspace/dist/synergia-web/browser /usr/share/nginx/html
EXPOSE 8080
