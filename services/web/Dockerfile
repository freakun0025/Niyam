# Build context: services/web.
FROM nginxinc/nginx-unprivileged:1.28.0-alpine
ENV NGINX_ENTRYPOINT_QUIET_LOGS=1

USER root
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public/ /usr/share/nginx/html/

ARG APP_VERSION=dev
RUN echo "${APP_VERSION}" | grep -Eq '^[A-Za-z0-9._-]+$' \
    && sed -i "s/__APP_VERSION__/${APP_VERSION}/g" \
        /usr/share/nginx/html/index.html /etc/nginx/conf.d/default.conf \
    && sed -i 's/^error_log .*/error_log \/dev\/stderr warn;/' /etc/nginx/nginx.conf

# Validate as the runtime user so the check leaves no root-owned files in /tmp.
USER 101
RUN nginx -t && rm -f /tmp/nginx.pid
EXPOSE 8080
