# Serveur Kyutai (moshi-server) pour la reconnaissance et la synthèse vocales.
# Adapté de kyutai-labs/unmute (services/moshi-server/public.Dockerfile, licence MIT).
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    ca-certificates \
    libssl-dev \
    git \
    pkg-config \
    cmake \
    wget \
    openssh-client \
    dos2unix \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

WORKDIR /app

# Premier démarrage : compilation de moshi-server et téléchargement des modèles
# (plusieurs minutes). Les volumes gardent le cache pour les démarrages suivants.
HEALTHCHECK --start-period=10m \
    CMD curl --fail http://localhost:8080/api/build_info || exit 1

EXPOSE 8080
ENV RUST_BACKTRACE=1

# Environnement Python du module TTS de moshi-server (versions figées par Kyutai)
RUN wget https://raw.githubusercontent.com/kyutai-labs/moshi/4fae088e130f6b44d489aefc0ef1836745e921de/rust/moshi-server/pyproject.toml
RUN wget https://raw.githubusercontent.com/kyutai-labs/moshi/4fae088e130f6b44d489aefc0ef1836745e921de/rust/moshi-server/uv.lock

COPY . .

RUN dos2unix ./start_moshi_server.sh && chmod +x ./start_moshi_server.sh

ENTRYPOINT ["uv", "run", "--locked", "--project", "./moshi-server", "./start_moshi_server.sh"]
