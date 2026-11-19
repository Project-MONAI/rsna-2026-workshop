FROM nginx:1.29-alpine
COPY containers/gateway/default.conf.template /etc/nginx/templates/default.conf.template
COPY containers/gateway/index.html containers/gateway/chat-entry.html containers/gateway/paseo-entry.html /usr/share/nginx/html/
COPY containers/gateway/previews/ /usr/share/nginx/html/previews/
COPY docs/miagent_v3_overview.html /usr/share/nginx/html/previews/miagent_v3_overview.html
