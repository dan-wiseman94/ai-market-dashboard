import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";
import { DEFAULT_MODEL_BY_PROVIDER } from "@/lib/modelDefaults";

export type Catalog = {
  models: AiModel[];
  /** Backend fallback model per provider (API value, else the seed literal). */
  defaults: Record<string, string>;
  isLoading: boolean;
  modelsFor: (provider: string) => AiModel[];
  defaultFor: (provider: string) => string;
  byId: (id: string) => AiModel | undefined;
};

export function useCatalog(): Catalog {
  const { data, isLoading } = useAiModels();
  const models = data?.models ?? [];
  const defaults: Record<string, string> = { ...DEFAULT_MODEL_BY_PROVIDER, ...(data?.defaults ?? {}) };
  return {
    models,
    defaults,
    isLoading,
    modelsFor: (provider) => models.filter((m) => m.provider === provider),
    defaultFor: (provider) => defaults[provider] ?? "",
    byId: (id) => models.find((m) => m.id === id),
  };
}

/** The model a picker lands on after a provider change: the provider's default when
 * the catalog lists it, else the first catalog model, else "" (local: user-typed). */
export function pickModelFor(provider: string, catalog: Catalog): string {
  const list = catalog.modelsFor(provider);
  const d = catalog.defaultFor(provider);
  if (d && list.some((m) => m.id === d)) return d;
  return list[0]?.id ?? "";
}
