const KOBOLD_URL = "http://localhost:5001/v1/chat/completions";

const SYSTEM_PROMPT = `You are an expert AI image prompt engineer. Your job is to generate detailed, high-quality image generation prompts.

CRITICAL RULES:
1. When the user requests multiple prompts with variations (e.g. "different hairs", "different outfits", "different poses"), you MUST ensure each prompt has genuinely DISTINCT values for the requested variation.
2. For hair variations: use completely different hair colors AND styles (e.g. "long flowing platinum blonde hair", "short curly jet black hair", "fiery red wavy bob", "pastel pink pixie cut"). Never repeat similar descriptions.
3. For other variations: apply the same principle - make each prompt meaningfully different in the requested aspect.
4. Each prompt should be detailed and suitable for image generation models like Stable Diffusion or Midjourney.
5. Keep each prompt to 1-3 sentences.

You must respond using the provided tool.`;

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

function validateVariations(result: { prompts: Prompt[]; variation_type: string }) {
  if (result.variation_type === "none" || result.prompts.length <= 1) {
    return { valid: true, issues: [] as string[] };
  }

  const issues: string[] = [];
  const keys = result.prompts.map((p) => p.variation_key.toLowerCase().trim());

  const uniqueKeys = new Set(keys);
  if (uniqueKeys.size < keys.length) {
    issues.push(`Duplicate ${result.variation_type} variations found`);
  }

  for (let i = 0; i < keys.length; i++) {
    for (let j = i + 1; j < keys.length; j++) {
      const wordsA = new Set(keys[i].split(/\s+/).filter((w) => w.length > 2));
      const wordsB = new Set(keys[j].split(/\s+/).filter((w) => w.length > 2));
      const union = new Set([...wordsA, ...wordsB]).size;
      const intersection = [...wordsA].filter((w) => wordsB.has(w)).length;
      if (union > 0 && intersection / union > 0.7) {
        issues.push(
          `Prompts ${i + 1} and ${j + 1} have very similar ${result.variation_type}: "${result.prompts[i].variation_key}" vs "${result.prompts[j].variation_key}"`
        );
      }
    }
  }

  return { valid: issues.length === 0, issues };
}

export async function generatePrompts(
  userRequest: string,
  retryFeedback?: string
): Promise<GenerationResult> {
  const userMessage = retryFeedback
    ? `Original request: "${userRequest}"\n\nPREVIOUS ATTEMPT FAILED VALIDATION: ${retryFeedback}\n\nPlease regenerate with TRULY DISTINCT variations.`
    : userRequest;

  const response = await fetch(KOBOLD_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "koboldcpp",
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
      tools: [
        {
          type: "function",
          function: {
            name: "return_prompts",
            description: "Return generated image prompts with metadata about variations",
            parameters: {
              type: "object",
              properties: {
                prompts: {
                  type: "array",
                  items: {
                    type: "object",
                    properties: {
                      text: { type: "string", description: "The full image generation prompt" },
                      variation_key: {
                        type: "string",
                        description: "The specific variation value for this prompt",
                      },
                    },
                    required: ["text", "variation_key"],
                  },
                },
                variation_type: {
                  type: "string",
                  description: "What aspect varies across prompts (e.g. 'hair', 'outfit', 'pose', 'none')",
                },
              },
              required: ["prompts", "variation_type"],
            },
          },
        },
      ],
      tool_choice: { type: "function", function: { name: "return_prompts" } },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`KoboldCPP error ${response.status}: ${text}`);
  }

  const data = await response.json();
  const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];
  if (!toolCall) throw new Error("No tool call in response");

  const result = JSON.parse(toolCall.function.arguments);
  const validation = validateVariations(result);

  return { ...result, validation };
}
