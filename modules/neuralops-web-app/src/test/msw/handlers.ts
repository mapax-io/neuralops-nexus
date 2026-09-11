import { http, HttpResponse, type RequestHandler } from "msw";

// Shared API mocks; per-test overrides go through server.use().
export const handlers: RequestHandler[] = [
  // No released server has this endpoint yet, so 404 is the honest default:
  // every component test that doesn't override it exercises the same legacy
  // fallback that runs in production today.
  http.get("*/api/v1/me/permissions/", () => new HttpResponse(null, { status: 404 })),
];
