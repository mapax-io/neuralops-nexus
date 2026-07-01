FROM oven/bun:1
WORKDIR /app
EXPOSE 3000
CMD ["sh", "-c", "bun install && bun run dev --host 0.0.0.0 --port 3000"]
