type Props = { onStop: () => void };

export default function StopButton({ onStop }: Props) {
  return (
    <button
      onClick={onStop}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ledger font-mono text-[11px] uppercase tracking-wider text-loss-300 border border-loss-500/50 hover:bg-loss-500/10 hover:text-loss-300 transition-colors duration-150"
      aria-label="Stop generation"
    >
      <span aria-hidden className="inline-block h-2 w-2 bg-loss-500 rounded-sm" />
      Stop
    </button>
  );
}
