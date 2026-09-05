// Best-effort context-window sizes by bare model id, so the register dialog
// starts from the right number instead of the server's 8192 for everything.
// Matched on the id alone (case-insensitive) so OpenAI-compatible endpoints
// that proxy a known family get it too; anything unknown falls back to the
// provider's typical size, then the server default. A guess the user can edit.

export const DEFAULT_CONTEXT_WINDOW = 8_192;

const BY_ID: [RegExp, number][] = [
  [/^gpt-4\.1/, 1_047_576],
  [/^gpt-5/, 400_000],
  [/^gpt-4o/, 128_000],
  [/^gpt-4-turbo/, 128_000],
  [/^gpt-4$/, 8_192],
  [/^gpt-3\.5/, 16_385],
  [/^o[134](-|$)/, 200_000],
  [/^claude/, 200_000],
  [/^gemini-1\.5-pro/, 2_097_152],
  [/^gemini/, 1_048_576],
  [/^llama-?3\.[1-3]/, 131_072],
  [/^llama-?3/, 8_192],
  [/^deepseek/, 131_072],
  [/^qwen/, 32_768],
  [/^(mistral|mixtral)/, 32_768],
  [/^gemma/, 8_192],
];

const BY_PROVIDER: Record<string, number> = { anthropic: 200_000, google: 1_048_576 };

export function defaultContextWindow(provider: string, modelId: string): number {
  const id = modelId.trim().toLowerCase();
  if (!id) return DEFAULT_CONTEXT_WINDOW;
  for (const [re, size] of BY_ID) if (re.test(id)) return size;
  return BY_PROVIDER[provider] ?? DEFAULT_CONTEXT_WINDOW;
}
