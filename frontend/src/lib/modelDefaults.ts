/**
 * Single home for the hardcoded provider/model initial picks.
 *
 * The backend catalog (apps/ai/catalog.py, served via /api/schwab/models/) is
 * the source of truth for what actually exists; these literals only seed UI
 * state before the user picks. When a default model id churns, update it here
 * (and the backend's own defaults) instead of grepping component literals.
 */

export type ProviderModelPick = { provider: string; model: string };

export const DEFAULT_MODEL_BY_PROVIDER: Record<"claude" | "openai" | "local", string> = {
  claude: "claude-sonnet-4-6",
  openai: "gpt-5",
  local: "",
};

/** The initial provider/model pair pickers start from. Spread before mutating. */
export const DEFAULT_PICK: ProviderModelPick = {
  provider: "claude",
  model: DEFAULT_MODEL_BY_PROVIDER.claude,
};

/** The cheaper second branch CompareDialog seeds alongside DEFAULT_PICK. */
export const DEFAULT_COMPARE_BRANCH: ProviderModelPick = {
  provider: "openai",
  model: "gpt-5-mini",
};
