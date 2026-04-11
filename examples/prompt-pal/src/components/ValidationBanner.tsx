import { AlertTriangle, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ValidationBannerProps {
  issues: string[];
  onRetry: () => void;
  retryCount: number;
  loading: boolean;
}

export const ValidationBanner = ({ issues, onRetry, retryCount, loading }: ValidationBannerProps) => {
  return (
    <div className="mt-6 rounded-xl border border-warning/30 bg-warning/5 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h3 className="font-mono font-semibold text-warning text-sm">
            Variation Check Failed
          </h3>
          <ul className="mt-2 space-y-1">
            {issues.map((issue, i) => (
              <li key={i} className="text-sm text-muted-foreground">
                • {issue}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              disabled={loading || retryCount >= 3}
              className="gap-2 font-mono border-warning/30 text-warning hover:bg-warning/10 hover:text-warning"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
              Regenerate ({3 - retryCount} left)
            </Button>
            {retryCount >= 3 && (
              <span className="text-xs text-muted-foreground">Max retries reached</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
