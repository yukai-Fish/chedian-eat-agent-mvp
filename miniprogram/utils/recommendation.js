function asText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeScore(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const rounded = Math.round(num);
  return Math.min(100, Math.max(0, rounded));
}

function stripFence(answer) {
  const text = asText(answer);
  if (!text.startsWith("```")) return text;
  return text.replace(/^```[a-zA-Z0-9_-]*\s*/, "").replace(/\s*```$/, "").trim();
}

function parseStructured(obj) {
  if (!obj || typeof obj !== "object" || !Array.isArray(obj.recommendations)) {
    return null;
  }

  const cards = obj.recommendations
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const score = normalizeScore(item.score);
      return {
        name: asText(item.name),
        score,
        scoreLabel: score === null ? "" : `${score}% 匹配`,
        reason: asText(item.reason),
        recommendDish: asText(item.recommend_dish),
        sceneFit: asText(item.scene_fit),
        warning: asText(item.warning),
      };
    })
    .filter((item) => item.name);

  return {
    mode: "structured",
    summary: asText(obj.summary),
    cards,
    batchSize: Math.max(1, Number(obj.batch_size) || 3),
    totalCount: Math.max(cards.length, Number(obj.total_count) || cards.length),
    rawAnswer: "",
  };
}

function parseTextFallback(answer) {
  const text = asText(answer);
  return {
    mode: text ? "raw" : "empty",
    summary: "",
    cards: [],
    batchSize: 3,
    totalCount: 0,
    rawAnswer: text,
  };
}

function parseRecommendationAnswer(answer) {
  const stripped = stripFence(answer);
  if (!stripped) return parseTextFallback(answer);

  try {
    const parsed = JSON.parse(stripped);
    const structured = parseStructured(parsed);
    if (structured) return structured;
  } catch (_err) {
    // non-JSON fallback
  }

  return parseTextFallback(answer);
}

module.exports = {
  parseRecommendationAnswer,
};
