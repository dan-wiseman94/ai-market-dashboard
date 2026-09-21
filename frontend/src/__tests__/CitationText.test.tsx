import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CitationText, type CitationRef } from "@/components/CitationText";

const WEB: CitationRef = {
  location: "web_search_result_location",
  source: "https://example.com/fed",
  title: "Fed holds rates steady",
  cited_text: "The committee left the target range unchanged.",
};
const NEWS: CitationRef = {
  location: "search_result_location",
  source: "news://bzn-4821",
  title: "Chips lead the tape",
  cited_text: "Semis outperformed by 140bp.",
};
const DOC: CitationRef = {
  location: "page_location",
  source: "",
  title: "AAPL 10-K.pdf",
  cited_text: "Services revenue grew 12%.",
};

describe("CitationText", () => {
  it("renders nothing when the message carried no citations", () => {
    const { container } = render(<CitationText citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("numbers the markers in arrival order", () => {
    render(<CitationText citations={[WEB, NEWS, DOC]} />);
    expect(screen.getByTestId("citation-1")).toBeInTheDocument();
    expect(screen.getByTestId("citation-2")).toBeInTheDocument();
    expect(screen.getByTestId("citation-3")).toBeInTheDocument();
  });

  it("renders title and cited text straight from the event payload", () => {
    render(<CitationText citations={[NEWS]} />);
    expect(screen.getByText("Chips lead the tape")).toBeInTheDocument();
    expect(screen.getByText("Semis outperformed by 140bp.")).toBeInTheDocument();
  });

  // news://<id> is the external feed id — no endpoint resolves it, so there is
  // nothing to link to. Only a real http(s) source becomes an anchor.
  it("links only the http(s) source", () => {
    render(<CitationText citations={[WEB, NEWS, DOC]} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://example.com/fed");
  });

  it("falls back to the source, then a placeholder, when there is no title", () => {
    render(
      <CitationText
        citations={[
          { location: "search_result_location", source: "news://9", title: "", cited_text: "" },
          { location: "char_location", source: "", title: "", cited_text: "" },
        ]}
      />,
    );
    expect(screen.getByText("news://9")).toBeInTheDocument();
    expect(screen.getByText("Untitled source")).toBeInTheDocument();
  });

  it("truncates a very long cited span", () => {
    const long = "x".repeat(400);
    render(<CitationText citations={[{ ...WEB, cited_text: long }]} />);
    const quote = screen.getByText(/x+…$/);
    expect(quote.textContent!.length).toBeLessThanOrEqual(160);
  });

  it("exposes the block under an addressable accessible name", () => {
    render(<CitationText citations={[WEB]} />);
    expect(screen.getByRole("complementary", { name: "Citations" })).toBeInTheDocument();
  });
});
