# Frontend Dockerfile
# Multi-stage: build the React app, serve with nginx

FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --silent

COPY . .
RUN npm run build


# ── Runtime: serve with nginx ──────────────────────────────────
FROM nginx:alpine AS runtime

# copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config — handle React Router (all routes → index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]