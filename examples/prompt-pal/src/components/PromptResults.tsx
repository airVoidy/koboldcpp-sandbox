import { useState } from "react";
import { CheckCircle2, Copy, Check, Tag } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Prompt {
  text: string;
  variation_key: string;
}

interface PromptResultsProps {
  prompts: Prompt[];
  variationType: string;
  isValid: boolean;
}

export const PromptResults = ({ prompts, variationType, isValid }: PromptResultsProps) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const copyPrompt = async (text: string, index: number) => {
    await navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div className="mt-8 space-y-4">
      <div className="flex items-center gap-3">
        {isValid && (
          <div className="flex items-center gap-1.5 text-success text-sm font-mono">
            <CheckCircle2 className="w-4 h-4" />
            Variations verified
          </div>
        )}
        {variationType !== "none" && (
          <Badge variant="secondary" className="font-mono text-xs gap-1">
            <Tag className="w-3 h-3" />
            Varying: {variationType}
          </Badge>
        )}
      </div>

      <div className="grid gap-3">
        {prompts.map((prompt, i) => (
          <Card
            key={i}
            className="group border-border bg-card hover:border-primary/30 transition-colors cursor-pointer"
            onClick={() => copyPrompt(prompt.text, i)}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-mono text-xs text-muted-foreground">
                      #{i + 1}
                    </span>
                    {variationType !== "none" && (
                      <Badge
                        variant="outline"
                        className="text-xs font-mono border-primary/20 text-primary"
                      >
                        {prompt.variation_key}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-foreground leading-relaxed">
                    {prompt.text}
                  </p>
                </div>
                <button className="shrink-0 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
                  {copiedIndex === i ? (
                    <Check className="w-4 h-4 text-success" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};
