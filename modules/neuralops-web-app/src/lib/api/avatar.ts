import { apiJson } from "./client";

export interface AvatarResult {
  /** Server-relative; resolve with absolutizeMedia before rendering. */
  avatar: string | null;
}

// The server decodes and re-encodes whatever is sent, so it decides the stored
// format and name. Sent as FormData: apiJson leaves the Content-Type to the
// browser so the multipart boundary is set correctly.
export const uploadAvatar = (file: File) => {
  const body = new FormData();
  body.append("file", file);
  return apiJson<AvatarResult>(`/api/v1/me/avatar/`, { method: "POST", body });
};

/** Drop a custom photo; the server falls back to an assigned default. */
export const removeAvatar = () =>
  apiJson<AvatarResult>(`/api/v1/me/avatar/`, { method: "DELETE" });

// Mirrors the server's own limit so an obviously-too-big file is refused
// before it is uploaded. The server still enforces it.
export const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
export const AVATAR_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
