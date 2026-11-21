# Kyutai moshi-server : WebSocket. La clé (en-tête kyutai-api-key, vérifiée par la passerelle)
# est transmise telle quelle : moshi-server attend la même (KYUTAI_ID = MODELS_API_KEY).
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_buffering off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
