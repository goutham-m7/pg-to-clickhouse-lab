FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS web
WORKDIR /work
COPY console/package*.json ./
RUN npm ci --no-audit --no-fund
COPY console/index.html console/tsconfig.json ./
COPY console/src ./src
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca
WORKDIR /lab
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY ledger ./ledger
COPY evidence/run.json ./evidence/run.json
COPY --from=web /work/dist ./console/dist
ENV PATH="/lab/.venv/bin:$PATH" LAB_NETWORK=compose PYTHONDONTWRITEBYTECODE=1
USER nobody
CMD ["python", "-m", "ledger.serve"]
