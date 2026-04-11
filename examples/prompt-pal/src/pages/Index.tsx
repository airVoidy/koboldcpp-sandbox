import { useState } from "react";
import { PromptInput } from "@/components/PromptInput";
import { PromptResults } from "@/components/PromptResults";
import { ValidationBanner } from "@/components/ValidationBanner";
import { generatePrompts } from "@/lib/generate";
import { toast } from "@/hooks/use-toast";
import { Sparkles } from "lucide-react";

interface Prompt {
  text: string;
  variation_key: string;
}

interface GenerationResult {
  prompts: Prompt[];
  variation_type: string;
  validation: {
    valid: boolean;
    issues: string[];
  };
}

const Index = () => {
  const [userRequest, setUserRequest] = useState("");
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  const generate = async (retryFeedback?: string) => {
    if (!userRequest.trim()) return;
    setLoading(true);

    try {
      const data = await generatePrompts(userRequest.trim(), retryFeedback);

      setResult(data);
      if (!data.validation.valid) {
        setRetryCount((c) => c + 1);
      } else {
        setRetryCount(0);
      }
    } catch (e: any) {
      toast({
        title: "Error",
        description: e.message || "Failed to generate prompts",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = () => {
    if (!result) return;
    const feedback = result.validation.issues.join(". ");
    generate(feedback);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/5 text-primary text-sm font-mono mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            AI Prompt Builder
          </div>
          <h1 className="text-4xl md:text-5xl font-mono font-bold text-foreground tracking-tight">
            Craft Perfect Prompts
          </h1>
          <p className="mt-3 text-muted-foreground text-lg max-w-xl mx-auto">
            Generate validated image prompts with guaranteed variety. Requests with variations are checked for genuine differences.
          </p>
        </div>

        {/* Input */}
        <PromptInput
          value={userRequest}
          onChange={setUserRequest}
          onSubmit={() => generate()}
          loading={loading}
        />

        {/* Validation Banner */}
        {result && !result.validation.valid && (
          <ValidationBanner
            issues={result.validation.issues}
            onRetry={handleRetry}
            retryCount={retryCount}
            loading={loading}
          />
        )}

        {/* Results */}
        {result && (
          <PromptResults
            prompts={result.prompts}
            variationType={result.variation_type}
            isValid={result.validation.valid}
          />
        )}
      </div>
    </div>
  );
};

export default Index;
