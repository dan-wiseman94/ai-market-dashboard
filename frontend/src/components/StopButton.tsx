type Props = { onStop: () => void };

export default function StopButton({ onStop }: Props) {
  return (
    <button
      onClick={onStop}
      className="text-xs px-2 py-0.5 rounded bg-rose-900/40 text-rose-200 hover:bg-rose-900/60"
    >
      Stop
    </button>
  );
}
