FROM node:22-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
RUN mkdir -p src public
USER 1000:1000
EXPOSE 5173
CMD ["npm", "run", "dev"]
