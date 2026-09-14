import { http, HttpResponse, type RequestHandler } from "msw";

// Shared API mocks; per-test overrides go through server.use().
export const handlers: RequestHandler[] = [
  // No released server has this endpoint yet, so 404 is the honest default:
  // every component test that doesn't override it exercises the same legacy
  // fallback that runs in production today.
  http.get("*/api/v1/me/permissions/", () => new HttpResponse(null, { status: 404 })),
  // The model id suggestions come from a third-party catalog; empty by default
  // so a suite that does not care sees the plain field.
  http.get("https://openrouter.ai/api/v1/models", () => HttpResponse.json({ data: [] })),
  // Usage and budgets per model: an older server has no such route, and the
  // cards must render exactly as before against one.
  http.get("*/api/v1/model-configs/usage/", () => new HttpResponse(null, { status: 404 })),
];
