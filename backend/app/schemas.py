"""
EMFOX OMS v2 - Esquemas de Datos (Pydantic Models)
=====================================================
Defines all data structures for AI response, products, projects,
WebSocket messages, and API requests/responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date


# ============================================================
# BOUNDING BOX (from Gemini)
# ============================================================
class BBox(BaseModel):
    """Bounding box as percentage of image dimensions (0-100)."""
    x_pct: float = 0
    y_pct: float = 0
    w_pct: float = 100
    h_pct: float = 100


# ============================================================
# ESQUEMA: Producto (núcleo del sistema)
# ============================================================
class ProductAIResponse(BaseModel):
    """Respuesta cruda de Gemini para UN producto detectado en la imagen."""
    descripcion_general: str = Field(..., description="Descripción del producto detectado")
    precio_unitario_cny: float = Field(..., description="Precio unitario en Yuanes (CNY)")
    cantidad_sugerida: int = Field(..., description="Cantidad total de unidades")
    volumen_total_m3: float = Field(..., description="Volumen total en metros cúbicos")
    tamano_cm: Optional[str] = Field(None, description="Tamaño si visible (ej: 25cm)")
    notas: Optional[str] = Field(None, description="Observaciones adicionales")
    image_index: int = Field(0, description="Índice de la imagen de origen (0-based)")
    bbox: Optional[BBox] = Field(None, description="Bounding box del producto en la imagen")


class ProductRow(BaseModel):
    """Producto completo para la tabla editable del Frontend (post-procesado)."""
    id: str = Field(..., description="ID único (UUID)")
    code: int = Field(..., description="Código secuencial (10001, 10002...)")
    articulo: str = Field(..., description="Nombre del artículo")
    description: str = Field(..., description="Descripción del producto")
    photo_url: Optional[str] = Field(None, description="URL de la miniatura")
    photo_url_original: Optional[str] = Field(None, description="URL de la imagen original")
    crop_url: Optional[str] = Field(None, description="URL del recorte inteligente")

    # Quantity
    quantity_cajas: Optional[int] = Field(None, description="Número de cajas")
    quantity_und_por_caja: Optional[int] = Field(None, description="Unidades por caja")
    quantity_total: int = Field(..., description="Cantidad total de unidades")

    # CBM (Volume)
    cbm_unit: float = Field(..., description="Volumen unitario por caja (m³)")
    cbm_total: float = Field(..., description="Volumen total (m³)")

    # Pricing
    precio_unitario_cny: float = Field(..., description="Precio unitario CNY")
    precio_unitario_usd: float = Field(..., description="Precio unitario USD")
    total_usd: float = Field(..., description="Total USD")

    # Meta
    tasa_cambio: float = Field(..., description="Tasa de cambio CNY→USD")
    editable: bool = Field(default=True)
    sort_order: int = Field(default=0)
    bbox: Optional[BBox] = None


# ============================================================
# PROJECT schemas
# ============================================================
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    exchange_rate: float = 7.2

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    consignee: Optional[str] = None
    ruc: Optional[str] = None
    direccion: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    payment_term: Optional[str] = None
    exchange_rate: Optional[float] = None
    date_str: Optional[str] = None

class ProjectSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    product_count: int = 0
    exchange_rate: float = 7.2
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True


# ============================================================
# PROCESSING
# ============================================================
class ProcessingResponse(BaseModel):
    success: bool
    message: str
    products: List[ProductRow] = []
    consignee: str = "Sres.Cristina y Victor"
    origin: str = "NINGBO, CHINA"
    destination: str = "CALLAO, PERÚ"
    date: str = ""
    total_general_usd: float = 0.0
    total_cbm: float = 0.0


class ExportRequest(BaseModel):
    products: List[ProductRow]
    consignee: str = "Sres.Cristina y Victor"
    ruc: str = ""
    direccion: str = ""
    origin: str = "NINGBO, CHINA"
    destination: str = "CALLAO, PERÚ"
    payment_term: str = ""
    date: Optional[str] = None
    project_id: Optional[int] = None


class RecalculateRequest(BaseModel):
    product: ProductRow
    cny_to_usd_rate: Optional[float] = None


class BulkRecalculateRequest(BaseModel):
    cny_to_usd_rate: float


# ============================================================
# WebSocket message schemas
# ============================================================
class WSMessage(BaseModel):
    type: str
    data: Optional[Dict[str, Any]] = None
    project_id: Optional[int] = None
    user: Optional[str] = None
