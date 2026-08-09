FROM node:20-slim

# Non-root runner user
RUN groupadd -r ace && useradd -r -g ace -m ace

# Pre-install vitest + typescript at a fixed project root.
# node_modules are baked into the image — no npm calls at runtime.
WORKDIR /opt/ts-project
COPY ts-harness/package.json .
COPY ts-harness/tsconfig.json .
COPY ts-harness/vitest.config.ts .
COPY ts-harness/eslint.config.js .
RUN npm install --ignore-scripts && npm cache clean --force

# Workspace bind-mounted here by the runner
RUN mkdir -p /workspace && chown ace:ace /workspace

# /tmp is mounted as tmpfs by the runner (vitest writes results there)
USER ace
WORKDIR /workspace
