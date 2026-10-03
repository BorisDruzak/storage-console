FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
COPY packages/i18n packages/i18n
RUN npm run build

FROM nginx:stable-alpine AS development
ARG APP_RELEASE=0.1.0
LABEL org.opencontainers.image.revision=$APP_RELEASE
COPY deploy/nginx/development.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1

FROM development AS production
COPY deploy/nginx/storage-console.conf /etc/nginx/templates/default.conf.template
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s CMD wget -q -O /dev/null http://127.0.0.1:8081/ready || exit 1
