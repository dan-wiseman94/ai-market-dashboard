/**
 * Seed values for provider/model pickers before `/api/schwab/models/`
 * (`useCatalog().defaults`) has loaded. The backend catalog is the source of
 * truth; when a default id churns there, update it here too.
 */

export type ProviderModelPick = { provider: string; model: string };

export const DEFAULT_MODEL_BY_PROVIDER: Record<"claude" | "openai" | "local", string> = {
  claude: "claude-opus-5",
  openai: "gpt-5.6-sol",
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
