FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ── Dev stage: Vite dev server with HMR ──────────────────────────────
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npx", "vite"]

# ── Build stage: production bundle ───────────────────────────────────
FROM deps AS build
COPY . .
RUN npm run build

# ── Production stage: nginx serving static files ─────────────────────
FROM nginx:alpine AS production

ARG HOST_UID=9999
ARG HOST_GID=9999

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
