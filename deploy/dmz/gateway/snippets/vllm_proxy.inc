# vLLM : réponses en flux (SSE) transmises sans tampon ; l'en-tête Authorization est relayé
# (vLLM vérifie aussi la clé, VLLM_API_KEY).
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header Connection "";
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto https;
proxy_buffering off;
proxy_request_buffering off;
proxy_cache off;
# Évaluation d'une station complète ou génération de l'assistant : jusqu'à quelques minutes
proxy_read_timeout 600s;
proxy_send_timeout 600s;
