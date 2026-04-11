import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

const SYSTEM_PROMPT = `You are an expert AI image prompt engineer. Your job is to generate detailed, high-quality image generation prompts.

CRITICAL RULES:
1. When the user requests multiple prompts with variations (e.g. "different hairs", "different outfits", "different poses"), you MUST ensure each prompt has genuinely DISTINCT values for the requested variation.
2. For hair variations: use completely different hair colors AND styles (e.g. "long flowing platinum blonde hair", "short curly jet black hair", "fiery red wavy bob", "pastel pink pixie cut"). Never repeat similar descriptions.
3. For other variations: apply the same principle — make each prompt meaningfully different in the requested aspect.
4. Each prompt should be detailed and suitable for image generation models like Stable Diffusion or Midjourney.
5. Keep each prompt to 1-3 sentences.

You must respond using the provided tool.`;

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { userRequest, retryWithFeedback } = await req.json();

    if (!userRequest || typeof userRequest !== "string") {
      return new Response(
        JSON.stringify({ error: "userRequest is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) throw new Error("LOVABLE_API_KEY not configured");

    const userMessage = retryWithFeedback
      ? `Original request: "${userRequest}"\n\nPREVIOUS ATTEMPT FAILED VALIDATION: ${retryWithFeedback}\n\nPlease regenerate with TRULY DISTINCT variations. Make each one obviously different.`
      : userRequest;

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
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
                          description: "The specific variation value for this prompt (e.g. the hair style/color if hair was the variation)",
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
      if (response.status === 429) {
        return new Response(JSON.stringify({ error: "Rate limited. Please wait and try again." }), {
          status: 429,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      if (response.status === 402) {
        return new Response(JSON.stringify({ error: "Credits exhausted. Please add funds." }), {
          status: 402,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      const text = await response.text();
      console.error("AI error:", response.status, text);
      throw new Error("AI gateway error");
    }

    const data = await response.json();
    const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];
    if (!toolCall) throw new Error("No tool call in response");

    const result = JSON.parse(toolCall.function.arguments);

    // VALIDATION: Check if variations are actually different
    const validationResult = validateVariations(result);

    return new Response(
      JSON.stringify({
        ...result,
        validation: validationResult,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (e) {
    console.error("Error:", e);
    return new Response(
      JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});

function validateVariations(result: {
  prompts: { text: string; variation_key: string }[];
  variation_type: string;
}) {
  if (result.variation_type === "none" || result.prompts.length <= 1) {
    return { valid: true, issues: [] };
  }

  const issues: string[] = [];
  const keys = result.prompts.map((p) => p.variation_key.toLowerCase().trim());

  // Check for duplicate variation keys
  const uniqueKeys = new Set(keys);
  if (uniqueKeys.size < keys.length) {
    issues.push(`Duplicate ${result.variation_type} variations found: some prompts have the same ${result.variation_type}`);
  }

  // Check for high similarity between variation keys using word overlap
  for (let i = 0; i < keys.length; i++) {
    for (let j = i + 1; j < keys.length; j++) {
      const similarity = wordSimilarity(keys[i], keys[j]);
      if (similarity > 0.7) {
        issues.push(
          `Prompts ${i + 1} and ${j + 1} have very similar ${result.variation_type}: "${result.prompts[i].variation_key}" vs "${result.prompts[j].variation_key}"`
        );
      }
    }
  }

  // Check that variation keys actually appear in the prompt text
  for (let i = 0; i < result.prompts.length; i++) {
    const promptLower = result.prompts[i].text.toLowerCase();
    const keyWords = keys[i].split(/\s+/).filter((w) => w.length > 3);
    const matchCount = keyWords.filter((w) => promptLower.includes(w)).length;
    if (keyWords.length > 0 && matchCount / keyWords.length < 0.3) {
      issues.push(
        `Prompt ${i + 1}: variation "${result.prompts[i].variation_key}" doesn't seem to appear in the prompt text`
      );
    }
  }

  return { valid: issues.length === 0, issues };
}

function wordSimilarity(a: string, b: string): number {
  const wordsA = new Set(a.split(/\s+/).filter((w) => w.length > 2));
  const wordsB = new Set(b.split(/\s+/).filter((w) => w.length > 2));
  if (wordsA.size === 0 && wordsB.size === 0) return 1;
  const intersection = [...wordsA].filter((w) => wordsB.has(w)).length;
  const union = new Set([...wordsA, ...wordsB]).size;
  return union === 0 ? 0 : intersection / union;
}
