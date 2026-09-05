export const APP_NAME = "NeuralOps Nexus";
export const APP_VERSION = "0.13.10";
export const APP_STAGE = "Alpha";

// Highest server version this app is known-compatible with. While MAJOR is 0,
// MINOR drift is treated as breaking; PATCH drift only warns.
export const COMPATIBLE_SERVER_VERSION = "0.1.2";

export type ServerVersionDrift = "match" | "minor" | "breaking" | "unknown";

export function compareServerVersion(serverVersion: string | null | undefined): ServerVersionDrift {
  if (!serverVersion || serverVersion === "dev" || serverVersion === "unknown") return "unknown";
  const parse = (v: string) => v.split(".").map(Number);
  const server = parse(serverVersion);
  const app = parse(COMPATIBLE_SERVER_VERSION);
  if (server.length < 3 || server.some(Number.isNaN)) return "unknown";
  if (server[0] !== app[0]) return "breaking";
  if (server[1] !== app[1]) return app[0] === 0 ? "breaking" : "minor";
  if (server[2] !== app[2]) return "minor";
  return "match";
}
