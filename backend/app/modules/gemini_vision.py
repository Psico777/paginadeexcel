"""
EMFOX OMS v2 - Módulo de Inteligencia Artificial (Gemini Vision)
================================================================
Wrapper para la API de Google Gemini con prompt especializado para
detectar productos en fotos de bodega, leer texto manuscrito, y
devolver bounding boxes para recorte inteligente (Smart Crop).
"""

import json
import re
from pathlib import Path
from typing import List
from google import genai
from google.genai import types

from app.config import settings
from app.schemas import ProductAIResponse

# ============================================================
# SYSTEM PROMPT v2 (with bounding box detection)
# ============================================================
SYSTEM_PROMPT = """
Eres un experto en logística de importación China→Perú que trabaja para EMFOX YIWU TRADE CO., LTD.
Tu trabajo es analizar fotografías de productos en bodegas/showrooms de Yiwu, China,
y extraer datos comerciales para crear órdenes de compra.

## TU MISIÓN
Analiza cada imagen y detecta los PRODUCTOS DISTINTOS visibles.

### ¡¡ REGLA CRÍTICA PARA CONTAR PRODUCTOS !!
Lo que define un "producto distinto" es el **PRECIO** y los **DATOS** escritos en la foto, NO los colores.
- Si ves 8 peluches pero solo hay 4 precios/datos diferentes escritos → son **4 productos**
- Si un mismo modelo viene en 3 colores (rojo, azul, verde) con el MISMO precio → es **1 solo producto** (no 3)
- Solo cuenta como producto separado si tiene su PROPIO precio o datos manuscritos distintos
- Variantes de color del mismo artículo al mismo precio van JUNTAS en una sola entrada
- En la descripción menciona "Varios colores" o lista los colores si aplica

Para cada producto distinto:
1. **IDENTIFICA** el tipo de producto y descríbelo (si hay variantes de color, menciónalo)
2. **LEE EL TEXTO MANUSCRITO** que aparece cerca:
   - Precio en Yuanes ("XX元", "XX YUAN", "XX¥", "XXRMB")  
   - Cantidad ("XXX UND", "XXX台", "XXX unidades")
   - Volumen ("X.XXm³", "X.XX立方米", "X.XX CBM")
   - Tamaño ("XXcm", "XX公分")
3. **ASOCIA** cada dato manuscrito al producto correcto por proximidad visual
4. **UBICA** cada producto con un bounding box aproximado en la imagen

## BOUNDING BOX:
Para cada producto, estima su ubicación en la imagen como porcentajes (0-100):
- x_pct: posición horizontal del borde izquierdo (0=izquierda, 100=derecha)
- y_pct: posición vertical del borde superior (0=arriba, 100=abajo)
- w_pct: ancho del producto como porcentaje del ancho total de la imagen
- h_pct: alto del producto como porcentaje del alto total de la imagen

Ejemplo: un producto que ocupa el cuadrante inferior-derecho:
  "bbox": {"x_pct": 50, "y_pct": 50, "w_pct": 45, "h_pct": 45}

## CAMPO image_index:
Indica en cuál imagen (empezando del 0) se encontró el producto.
Si se enviaron 3 imágenes y este producto está en la segunda, image_index = 1.

## REGLAS:
- Si ves "CBMT" o "CBM TOTAL", es el volumen total (cajas × CBM unitario)
- CUENTA PRODUCTOS POR PRECIOS/DATOS DISTINTOS, NO por colores ni unidades individuales
- Variantes de color al mismo precio = 1 solo producto (mencionar colores en descripción)
- Dato no legible → usa null, NUNCA inventes números
- Precios SIEMPRE en CNY (Yuanes chinos)
- Cantidad puede ser total de piezas o (cajas × piezas/caja)
- Ignora tarjetas de visita (son del proveedor)

## FORMATO DE RESPUESTA OBLIGATORIO:
Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown:
{
  "productos": [
    {
      "descripcion_general": "Oso de peluche blanco con corazón rojo, texto 'Te Amo'. Varios colores disponibles",
      "precio_unitario_cny": 11.0,
      "cantidad_sugerida": 320,
      "volumen_total_m3": 0.55,
      "tamano_cm": "25",
      "notas": "Sin relleno, empaque en bolsa. Colores: rojo, azul, blanco",
      "image_index": 0,
      "bbox": {"x_pct": 10, "y_pct": 5, "w_pct": 40, "h_pct": 60}
    }
  ],
  "observaciones_generales": "Notas generales sobre las fotos"
}

Si no hay productos: {"productos": [], "observaciones_generales": "No se detectaron productos"}
"""


class GeminiVisionService:
    """Servicio de visión artificial usando Google Gemini."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        print(f"[GEMINI] Inicializado con modelo: {self.model}")

    def _load_image_as_part(self, image_path: str) -> types.Part:
        """Carga una imagen local y la convierte en Part para Gemini."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = mime_map.get(path.suffix.lower(), "image/jpeg")

        with open(path, "rb") as f:
            image_data = f.read()

        return types.Part.from_bytes(data=image_data, mime_type=mime_type)

    async def analyze_images(self, image_paths: List[str]) -> List[ProductAIResponse]:
        """
        Analiza imágenes y extrae datos + bounding boxes por producto.
        Returns list of ProductAIResponse with optional bbox data.
        """
        parts = []

        for i, img_path in enumerate(image_paths):
            try:
                image_part = self._load_image_as_part(img_path)
                parts.append(image_part)
                parts.append(types.Part.from_text(
                    text=f"[Imagen {i} de {len(image_paths)}] Analiza esta foto de producto."
                ))
            except FileNotFoundError as e:
                print(f"[GEMINI] Advertencia: {e}")
                continue

        if not parts:
            raise ValueError("No se pudo cargar ninguna imagen")

        parts.append(types.Part.from_text(
            text="Ahora analiza TODAS las imágenes anteriores y extrae la información de "
                 "cada producto individual. Incluye bounding box y image_index. "
                 "Responde con el JSON estructurado."
        ))

        print(f"[GEMINI] Enviando {len(image_paths)} imagen(es) para análisis...")

        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )

        raw_text = response.text.strip()
        print(f"[GEMINI] Respuesta recibida ({len(raw_text)} chars)")

        # Clean markdown wrapping
        json_text = raw_text
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"[GEMINI] Error parseando JSON: {e}")
            print(f"[GEMINI] Texto crudo: {raw_text[:500]}")
            match = re.search(r'\{[\s\S]*\}', raw_text)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Gemini no retornó JSON válido: {raw_text[:200]}")

        products = []
        for item in data.get("productos", []):
            try:
                bbox_raw = item.get("bbox")
                bbox = None
                if bbox_raw and isinstance(bbox_raw, dict):
                    bbox = {
                        "x_pct": float(bbox_raw.get("x_pct", 0)),
                        "y_pct": float(bbox_raw.get("y_pct", 0)),
                        "w_pct": float(bbox_raw.get("w_pct", 100)),
                        "h_pct": float(bbox_raw.get("h_pct", 100)),
                    }

                product = ProductAIResponse(
                    descripcion_general=item.get("descripcion_general", "Producto no identificado"),
                    precio_unitario_cny=float(item.get("precio_unitario_cny", 0)),
                    cantidad_sugerida=int(item.get("cantidad_sugerida", 0)),
                    volumen_total_m3=float(item.get("volumen_total_m3", 0)),
                    tamano_cm=item.get("tamano_cm"),
                    notas=item.get("notas"),
                    image_index=int(item.get("image_index", 0)),
                    bbox=bbox,
                )
                products.append(product)
            except (ValueError, TypeError) as e:
                print(f"[GEMINI] Error en producto: {e}, datos: {item}")
                continue

        print(f"[GEMINI] {len(products)} producto(s) detectados exitosamente")
        return products


# Singleton
gemini_service = GeminiVisionService()
