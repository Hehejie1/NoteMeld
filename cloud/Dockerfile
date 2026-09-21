FROM node:22-bookworm-slim AS cloud-web-build

WORKDIR /frontend
COPY desktop/frontend/package.json desktop/frontend/pnpm-lock.yaml desktop/frontend/pnpm-workspace.yaml ./
COPY desktop/frontend/packages ./packages
RUN corepack enable && pnpm install --frozen-lockfile
COPY desktop/frontend/apps ./apps
COPY desktop/frontend/src ./src
COPY desktop/frontend/vite.config.ts ./vite.config.ts
RUN pnpm build:cloud-web

FROM python:3.11-slim

ARG NOTEMELD_BUILD_COMMIT=""
ARG NOTEMELD_AGENT_SDK_WHEEL=""
ARG NOTEMELD_AGENT_SDK_LIBRARY=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOTEMELD_CLOUD_DATA_DIR=/var/lib/notemeld-cloud \
    NOTEMELD_CLOUD_BUILD_COMMIT=${NOTEMELD_BUILD_COMMIT}

WORKDIR /app
COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt \
    && useradd --create-home --uid 10001 notemeld \
    && mkdir -p /var/lib/notemeld-cloud \
    && chown -R notemeld:notemeld /var/lib/notemeld-cloud

# Production Cloud must consume an immutable SDK binding and matching native
# library.  The release pipeline supplies both paths from the SDK artifact
# manifest; an omitted artifact fails the image build rather than enabling a
# Python-owned or deterministic runtime.
RUN test -n "${NOTEMELD_AGENT_SDK_WHEEL}" && test -n "${NOTEMELD_AGENT_SDK_LIBRARY}"
COPY ${NOTEMELD_AGENT_SDK_WHEEL} /tmp/
COPY ${NOTEMELD_AGENT_SDK_LIBRARY} /opt/notemeld-agent-sdk/libnotemeld_agent.so
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

COPY cloud /app/cloud
COPY --from=cloud-web-build /frontend/dist-cloud-web /app/cloud-web-dist
ENV NOTEMELD_AGENT_SDK_LIBRARY=/opt/notemeld-agent-sdk/libnotemeld_agent.so \
    NOTEMELD_CLOUD_WEB_DIST=/app/cloud-web-dist
USER notemeld

EXPOSE 8583
CMD ["sh", "-c", "exec uvicorn cloud.main:app --host 0.0.0.0 --port 8583 --workers ${WEB_CONCURRENCY:-1}"]
