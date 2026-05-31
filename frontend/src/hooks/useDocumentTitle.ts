import { useEffect } from "react";

export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    if (!title) return;
    const prev = document.title;
    document.title = `${title} · Ledger`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
