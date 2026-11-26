FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# rewrites are baked in at build time; nginx already routes /api to the backend, this is the fallback
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
RUN adduser -D -u 10001 app
COPY --from=build --chown=app /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build --chown=app /app/.next ./.next
COPY --from=build --chown=app /app/next.config.mjs ./
USER app
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
