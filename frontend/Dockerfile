FROM node:22-slim AS base
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm install

FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS production
WORKDIR /app
RUN useradd -m -u 1000 cyberlab
COPY --from=build /app/.output ./.output
USER cyberlab
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
