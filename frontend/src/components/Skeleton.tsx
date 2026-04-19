export function Skeleton({
  className = "",
  where = "generic",
}: {
  className?: string;
  where?: string;
}) {
  return (
    <div
      className={`animate-pulse bg-slate-700/50 rounded ${className}`}
      data-testid={`skeleton-${where}`}
    />
  );
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          data-testid="skeleton-row"
          className="animate-pulse bg-slate-700/50 rounded h-8 w-full"
        />
      ))}
    </div>
  );
}
