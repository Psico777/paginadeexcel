"""
EMFOX OMS v2 - Aplicación Principal FastAPI
============================================
Sistema de Procesamiento de Pedidos Inteligente con
persistencia, colaboración en tiempo real y Smart Crop.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import router
from app.database import init_db

# ============================================================
# INICIALIZACIÓN DE LA APP
# ============================================================
app = FastAPI(
    title="EMFOX OMS v2 - Order Management System",
    description=(
        "Sistema inteligente de procesamiento de pedidos para "
        "Emfox Yiwu Trade Co., Ltd. Real-time collaboration, "
        "Smart Crop AI, persistent projects."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================
# CORS (permite peticiones del Frontend React + WebSocket)
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ARCHIVOS ESTÁTICOS (imágenes subidas + crops)
# ============================================================
upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(exist_ok=True)
(upload_dir / "crops").mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

# ============================================================
# DATABASE INITIALIZATION
# ============================================================
init_db()

# ============================================================
# REGISTRAR RUTAS (includes WebSocket)
# ============================================================
app.include_router(router)


# ============================================================
# ROOT ENDPOINT
# ============================================================
@app.get("/")
async def root():
    return {
        "system": "EMFOX OMS",
        "company": "EMFOX YIWU TRADE CO., LTD",
        "version": "2.0.0",
        "status": "operational",
        "docs": "/docs",
        "features": [
            "Projects persistence (SQLite)",
            "Real-time collaboration (WebSocket)",
            "Smart Crop (Gemini bounding boxes + PIL)",
            "Dynamic exchange rate recalculation",
            "Excel export with embedded images",
        ],
    }


# ============================================================
# FRONTEND ESTÁTICO (React build)
# ============================================================
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.responses import FileResponse
    
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="frontend-assets")
    
    @app.get("/app", include_in_schema=False)
    @app.get("/app/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
        file_path = frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
    
    print(f"[FRONTEND] React app at http://localhost:8000/app")
else:
    print(f"[FRONTEND] No build found — run 'cd frontend && npm run build'")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
