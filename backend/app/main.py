import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.proxy_routes import proxy_router
from app.api.routes import router

# Auto-load backend/.env for local development.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env', override=False)

app = FastAPI(title='成电吃什么 Agent API', version='0.1.0')


class Utf8ResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset=" not in content_type.lower():
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

# Comma-separated list, e.g.
# CORS_ALLOW_ORIGINS=https://your-site.netlify.app,http://localhost:3000
raw_origins = os.getenv('CORS_ALLOW_ORIGINS', '').strip()
if raw_origins:
    allow_origins = [item.strip() for item in raw_origins.split(',') if item.strip()]
else:
    allow_origins = [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:3001',
        'http://127.0.0.1:3001',
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(Utf8ResponseMiddleware)
app.include_router(router, prefix='/api/v1', tags=['mvp'])
app.include_router(proxy_router, prefix='/api', tags=['workflow-proxy'])


@app.on_event("startup")
async def _print_runtime_provider() -> None:
    provider = os.getenv("RECOMMEND_PROVIDER", "workflow").strip().lower()
    spark_model = os.getenv("XFYUN_SPARKX_MODEL", "").strip()
    spark_x2 = os.getenv("XFYUN_SPARKX2_ENDPOINT", "").strip()
    has_spark_password = bool(os.getenv("XFYUN_SPARKX_API_PASSWORD", "").strip())
    print(
        "[startup] recommend_provider=%s spark_model=%s spark_x2_endpoint=%s spark_password_set=%s"
        % (provider, spark_model or "-", spark_x2 or "-", "yes" if has_spark_password else "no")
    )
