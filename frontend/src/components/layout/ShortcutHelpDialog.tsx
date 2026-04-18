import { SHORTCUTS } from "@/hooks/useKeyboardShortcuts";

type Props = { open: boolean; onClose: () => void };

export default function ShortcutHelpDialog({ open, onClose }: Props) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 bg-black/70 grid place-items-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-slate-950 border border-slate-700 rounded p-4 w-96"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-medium mb-3">Keyboard shortcuts</h2>
        <table className="w-full text-sm">
          <tbody>
            {Object.entries(SHORTCUTS).map(([key, { label }]) => (
              <tr key={key} className="border-t border-slate-800">
                <td className="py-1 font-mono text-emerald-300">g {key}</td>
                <td className="py-1 text-slate-300">{label}</td>
              </tr>
            ))}
            <tr className="border-t border-slate-800">
              <td className="py-1 font-mono text-emerald-300">?</td>
              <td className="py-1 text-slate-300">Show this dialog</td>
            </tr>
          </tbody>
        </table>
        <button
          className="mt-3 px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm"
          onClick={onClose}
        >Close</button>
      </div>
    </div>
  );
}
