function safeText(value, fallback) {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function normalizeScore(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const rounded = Math.round(num);
  return Math.min(100, Math.max(0, rounded));
}

function parseStructured(obj) {
  if (!obj || typeof obj !== "object") return null;
  if (!Array.isArray(obj.recommendations)) return null;

  const cards = obj.recommendations
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const score = normalizeScore(item.score);
      return {
        name: safeText(item.name, "未命名店铺"),
        score,
        scoreLabel: score === null ? "" : `${score}% 匹配`,
        reason: safeText(item.reason, "暂无推荐理由"),
        recommendDish: safeText(item.recommend_dish, "暂无推荐菜"),
        sceneFit: safeText(item.scene_fit, "暂无场景信息"),
        warning: safeText(item.warning, "暂无明显不足"),
      };
    });

  return {
    mode: "structured",
    summary: safeText(obj.summary, "已按当前偏好排序推荐。"),
    cards,
    batchSize: Math.max(1, Number(obj.batch_size) || 3),
    totalCount: Math.max(cards.length, Number(obj.total_count) || cards.length),
    rawAnswer: "",
  };
}

function parseTextFallback(answer) {
  const text = safeText(answer, "");
  if (!text) {
    return {
      mode: "empty",
      summary: "暂未获得可展示结果。",
      cards: [],
      batchSize: 3,
      totalCount: 0,
      rawAnswer: "",
    };
  }

  return {
    mode: "raw",
    summary: "工作流返回了非结构化文本，当前展示原始回答。",
    cards: [],
    batchSize: 3,
    totalCount: 0,
    rawAnswer: text,
  };
}

function stripFence(answer) {
  const text = safeText(answer, "");
  if (!text.startsWith("```")) return text;
  return text.replace(/^```[a-zA-Z0-9_-]*\s*/, "").replace(/\s*```$/, "").trim();
}

function parseRecommendationAnswer(answer) {
  const stripped = stripFence(answer);
  if (!stripped) return parseTextFallback(answer);

  try {
    const parsed = JSON.parse(stripped);
    const structured = parseStructured(parsed);
    if (structured) return structured;
  } catch (_err) {
    // fallback below
  }

  return parseTextFallback(answer);
}

module.exports = {
  parseRecommendationAnswer,
};
