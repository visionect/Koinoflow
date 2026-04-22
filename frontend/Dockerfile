FROM node:22-alpine

WORKDIR /app

RUN chown node:node /app

COPY --chown=node:node package.json package-lock.json* ./

USER node

EXPOSE 5173
CMD ["sh", "-c", "npm install && exec npm run dev -- --host 0.0.0.0"]
