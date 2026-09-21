import { Citation } from "@/components/Citation";

/**
 * One citation the model attached to the text it streamed.
 *
 * Mirrors the `citation` frame on the `thread.<id>` channel (apps/ai/types.py
 * CitationEvent, broadcast by apps/threads/_stream.py). The Anthropic location
 * variants are NOT uniform, so every field can be empty:
 *
 * - `search_result_location` → `source` is the block's source. For news that is
 *   the article url when we had one, else `news://<feed-id>`. **That id is the
 *   external feed's id, not a `NewsItem` pk, and no endpoint resolves it** — so
 *   a `news://` citation is rendered from this payload alone, never looked up.
 * - `web_search_result_location` → `source` is a real http(s) url.
 * - `char_location` / `page_location` / `content_block_location` (a Files-API
 *   document) → `source` is "" and only `title` (the document title) is set.
 */
export type CitationRef = {
  location: string;
  source: string;
  title: string;
  cited_text: string;
};

const MAX_QUOTE = 160;

function quote(text: string): string {
  return text.length > MAX_QUOTE ? `${text.slice(0, MAX_QUOTE - 1)}…` : text;
}

/** A citation with neither a title nor a source still needs a readable name. */
function displayTitle(c: CitationRef): string {
  return c.title || c.source || "Untitled source";
}

/**
 * The sources block under an assistant message: one numbered `[n]` marker per
 * distinct citation, with the title and the text the model actually cited.
 *
 * Markers are listed rather than spliced into the message body: the body is
 * markdown, and cutting it at byte offsets to interleave markers would break
 * lists, tables and code fences (and the alternative — injecting raw HTML — is
 * banned by the FE lint).
 */
export function CitationText({ citations }: { citations: CitationRef[] }) {
  if (citations.length === 0) return null;
  return (
    <aside
      aria-label="Citations"
      data-testid="citations"
      className="mt-4 pt-3 border-t border-rule-soft"
    >
      <span className="ledger-eyebrow">Sources</span>
      <ol className="mt-2 flex flex-col gap-1.5">
        {citations.map((c, i) => (
          <li
            key={`${c.source}|${c.title}`}
            data-testid={`citation-row-${i + 1}`}
            className="flex gap-2 items-baseline font-mono text-[11.5px] leading-[1.5]"
          >
            <Citation
              index={i + 1}
              source={c.source}
              title={displayTitle(c)}
              snippet={c.cited_text}
            />
            <span className="min-w-0">
              <span className="text-ink-200">{displayTitle(c)}</span>
              {c.cited_text && (
                <q className="ml-1.5 text-ink-500">{quote(c.cited_text)}</q>
              )}
            </span>
          </li>
        ))}
      </ol>
    </aside>
  );
}

export default CitationText;
