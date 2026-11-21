# Image de l'API ECOS (FastAPI). Production : docker-compose.prod.yml ; développement :
# docker-compose.yml (code monté, rechargement automatique).
FROM python:3.11-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt


FROM python:3.11-slim

ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# L'application tourne sous un utilisateur sans privilèges (docker-entrypoint.sh) ; le code
# lui reste en lecture seule, seul /app/storage (pièces jointes) lui appartient.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin ecos
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY . .
RUN mkdir -p /app/storage && chown ecos:ecos /app/storage && chmod 755 docker-entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=6s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
