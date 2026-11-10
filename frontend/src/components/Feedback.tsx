import type { SnapshotError } from "../types/market-snapshot";

export function CardSkeleton() {
  return (
    <div className="panel space-y-3 p-4" aria-hidden="true">
      <div className="skeleton h-2.5 w-20" />
      <div className="skeleton h-7 w-28" />
      <div className="skeleton h-3 w-24" />
      <div className="skeleton h-8 w-full" />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading the market snapshot">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, index) => (
          <CardSkeleton key={index} />
        ))}
      </div>
      <div className="panel p-5">
        <div className="skeleton h-40 w-full" />
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <div key={index} className="panel space-y-2 p-4" aria-hidden="true">
            <div className="skeleton h-2.5 w-24" />
            {Array.from({ length: 6 }, (_, row) => (
              <div key={row} className="skeleton h-4 w-full" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

interface ErrorCardProps {
  message: string;
  onRetry: () => void;
}

export function ErrorCard({ message, onRetry }: ErrorCardProps) {
  return (
    <div className="panel mx-auto max-w-lg space-y-3 p-6 text-center" role="alert">
      <h2 className="text-sm font-semibold text-down">Couldn't load market data</h2>
      <p className="text-xs text-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-edge px-3 py-1.5 text-xs font-semibold text-ink hover:bg-edge/60"
      >
        Retry
      </button>
    </div>
  );
}

export function ErrorBanner({ errors }: { errors: SnapshotError[] }) {
  if (errors.length === 0) return null;
  return (
    <div
      className="rounded-xl border border-caution/30 bg-caution/10 px-4 py-2.5 text-xs text-caution"
      role="status"
    >
      <p className="font-semibold">Some sections couldn't load</p>
      <ul className="mt-1 space-y-0.5 text-caution/90">
        {errors.slice(0, 4).map((error, index) => (
          <li key={`${error.section}-${index}`}>
            {error.section}
            {error.provider ? ` (${error.provider})` : ""}: {error.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
