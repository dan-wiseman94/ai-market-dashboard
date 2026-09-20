import { providerLabel } from "@/api/ai";

export type Feature = "tools" | "thinking" | "memory";

/** The consequence of enabling `feature` on `provider`, or null when fully supported. */
export function capabilityHint(feature: Feature, provider: string, supportsTools: boolean | undefined): string | null {
  if (provider === "claude") return null;
  const name = providerLabel(provider);
  if (feature === "thinking" || feature === "memory") return `Claude only — ignored on ${name}`;
  return supportsTools === false ? `Tool use is off for ${name} in Settings → AI Providers` : null;
}

export default function CapabilityHint(props: { feature: Feature; provider: string; supportsTools?: boolean }) {
  const text = capabilityHint(props.feature, props.provider, props.supportsTools);
  return text ? <span role="note" className="text-[11px] text-copper-300">{text}</span> : null;
}
