import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Wand2, Loader2 } from "lucide-react";

interface PromptInputProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export const PromptInput = ({ value, onChange, onSubmit, loading }: PromptInputProps) => {
  return (
    <div className="relative">
      <div className="rounded-xl border border-border bg-card p-1.5 shadow-lg shadow-primary/5">
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder='e.g. "4 prompts of a demoness with different hairs"'
          className="min-h-[120px] border-0 bg-transparent resize-none text-foreground placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0 text-base"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <div className="flex items-center justify-between px-2 pb-1">
          <span className="text-xs text-muted-foreground font-mono">
            ⌘+Enter to generate
          </span>
          <Button
            onClick={onSubmit}
            disabled={loading || !value.trim()}
            className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90 font-mono"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            Generate
          </Button>
        </div>
      </div>
    </div>
  );
};
