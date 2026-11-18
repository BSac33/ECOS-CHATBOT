# Kyutai moshi-server : WebSocket. La clé externe (contrôlée par la passerelle) est remplacée
# par l'identifiant interne attendu par moshi-server (authorized_ids des configs .toml).
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_set_header kyutai-api-key public_token;
proxy_buffering off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
