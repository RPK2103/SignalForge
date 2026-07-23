import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AsyncStateProps = {
  title: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
};

export function LoadingState({
  title,
  message = "Loading…",
  className,
}: Pick<AsyncStateProps, "title" | "message" | "className">) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        "rounded-lg border border-border/70 bg-muted/20 px-4 py-6 text-center",
        className
      )}
    >
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  className,
}: Pick<AsyncStateProps, "title" | "message" | "className">) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "rounded-lg border border-dashed border-border/70 px-4 py-6 text-center",
        className
      )}
    >
      <p className="text-sm font-medium">{title}</p>
      {message ? (
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      ) : null}
    </div>
  );
}

export function ErrorState({
  title,
  message,
  onRetry,
  retryLabel = "Retry",
  className,
}: AsyncStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border border-rose-200 bg-rose-50/60 px-4 py-4",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-rose-700" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-sm font-medium text-rose-900">{title}</p>
          {message ? (
            <p className="text-sm text-rose-800/90">{message}</p>
          ) : null}
          {onRetry ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="border-rose-200 bg-white"
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {retryLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
