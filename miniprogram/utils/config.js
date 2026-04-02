const DEV_BASE_URL = "http://127.0.0.1:8000";
const PROD_BASE_URL = "https://chedian-eat-agent-mvp.onrender.com";

function resolveApiBaseUrl() {
  if (typeof __wxConfig !== "undefined" && __wxConfig.envVersion === "develop") {
    return DEV_BASE_URL;
  }
  return PROD_BASE_URL;
}

module.exports = {
  API_BASE_URL: resolveApiBaseUrl(),
};
