FROM mcr.microsoft.com/playwright:v1.63.0-noble
RUN apt-get update && apt-get install -y --no-install-recommends libnss3-tools \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /acceptance
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --ignore-scripts
COPY tests/deployment/browser_auth.mjs ./browser_auth.mjs
COPY tests/deployment/browser_pilot.mjs ./browser_pilot.mjs
ENTRYPOINT ["node", "browser_auth.mjs"]
