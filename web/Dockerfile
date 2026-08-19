# The React client, built once and served as static files.
#
# There was no production story for this at all: in development Vite serves it
# on the host, so the frontend had never been deployable. The API is addressed
# relatively (`/api/v1`), so serving it on the same origin as Django needs no
# build-time configuration and raises no CORS.

FROM node:22-alpine AS build
WORKDIR /app

# Dependencies first, so a source change does not reinstall them.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# `npm run build` is `tsc -b && vite build` — the typecheck is the gate, so a
# type error fails the image rather than shipping.
RUN npm run build

FROM nginx:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
