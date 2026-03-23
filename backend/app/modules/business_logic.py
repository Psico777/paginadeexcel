"""
EMFOX OMS - Lógica de Negocio y Procesamiento
===============================================
Convierte datos crudos de la IA en productos procesados listos para la tabla.
Incluye: conversión de moneda, cálculo de totales, asignación de códigos.
"""

import uuid
from typing import List, Optional
from app.config import settings
from app.schemas import ProductAIResponse, ProductRow


class BusinessProcessor:
    """Motor de lógica de negocio para procesamiento de productos."""

    def __init__(self):
        self._next_code = settings.next_product_code
        self._cny_usd_rate = settings.cny_to_usd_rate

    @property
    def exchange_rate(self) -> float:
        return self._cny_usd_rate

    @exchange_rate.setter
    def exchange_rate(self, rate: float):
        if rate <= 0:
            raise ValueError("La tasa de cambio debe ser mayor a 0")
        self._cny_usd_rate = rate

    # ============================================================
    # CONVERSIÓN DE MONEDA
    # ============================================================
    def convert_cny_to_usd(self, amount_cny: float, rate: Optional[float] = None) -> float:
        """
        Convierte un monto de CNY (Yuanes) a USD.
        
        Fórmula: USD = CNY / Tasa
        Ejemplo: 11 CNY / 7.2 = 1.528 USD
        
        Args:
            amount_cny: Monto en Yuanes chinos
            rate: Tasa de cambio opcional (usa la configurada por defecto)
        
        Returns:
            Monto equivalente en USD, redondeado a 2 decimales
        """
        exchange_rate = rate or self._cny_usd_rate
        return round(amount_cny / exchange_rate, 2)

    # ============================================================
    # CÁLCULO DE TOTALES
    # ============================================================
    def calculate_total_usd(self, quantity: int, unit_price_usd: float) -> float:
        """
        Calcula el total USD = Cantidad × Precio Unitario USD.
        
        Args:
            quantity: Cantidad total de unidades
            unit_price_usd: Precio por unidad en USD
            
        Returns:
            Total en USD redondeado a 2 decimales
        """
        return round(quantity * unit_price_usd, 2)

    def calculate_unit_volume(self, total_volume: float, num_boxes: Optional[int] = None) -> float:
        """
        Calcula el volumen unitario por caja.
        Si no hay cajas definidas, el volumen unitario = volumen total (1 lote).
        
        NOTA sobre CBM (de la image_1):
        - CBM UNIT = volumen de 1 caja
        - CBM TOTAL = CAJAS × CBM UNIT
        - Ejemplo: 7 cajas × 3 CBM/caja = 21 CBMT
        """
        if num_boxes and num_boxes > 0:
            return round(total_volume / num_boxes, 4)
        return total_volume

    # ============================================================
    # ASIGNACIÓN DE CÓDIGO SECUENCIAL
    # ============================================================
    def get_next_code(self) -> int:
        """Genera el siguiente código de producto (10001, 10002, ...)."""
        code = self._next_code
        self._next_code += 1
        return code

    def reset_code_sequence(self, start: int = 10001):
        """Reinicia la secuencia de códigos."""
        self._next_code = start

    # ============================================================
    # PROCESAMIENTO COMPLETO: IA → Tabla
    # ============================================================
    def process_ai_products(
        self,
        ai_products: List[ProductAIResponse],
        image_urls: Optional[List[str]] = None,
    ) -> List[ProductRow]:
        """
        Transforma la lista de productos detectados por la IA en filas
        de la tabla editable del frontend.
        
        Flujo:
        1. Recibe ProductAIResponse (datos crudos de Gemini)
        2. Convierte precio CNY → USD
        3. Calcula totales
        4. Asigna código secuencial
        5. Retorna ProductRow listo para el frontend
        """
        rows = []

        for i, ai_product in enumerate(ai_products):
            code = self.get_next_code()
            
            # --- Conversión de moneda ---
            precio_usd = self.convert_cny_to_usd(ai_product.precio_unitario_cny)
            
            # --- Cálculos ---
            total_usd = self.calculate_total_usd(
                ai_product.cantidad_sugerida, precio_usd
            )
            
            # Generar nombre de artículo
            articulo = f"Peluche {i + 1}"
            
            # Descripción basada en datos de la IA
            description_parts = []
            if ai_product.tamano_cm:
                description_parts.append(f"{ai_product.tamano_cm} cm")
            if ai_product.notas:
                description_parts.append(ai_product.notas)
            if not description_parts:
                description_parts.append(ai_product.descripcion_general[:50])
            description = " - ".join(description_parts)

            # Foto (si hay imágenes, asignar la primera disponible)
            photo_url = None
            if image_urls and i < len(image_urls):
                photo_url = image_urls[i]
            elif image_urls:
                photo_url = image_urls[0]

            row = ProductRow(
                id=str(uuid.uuid4()),
                code=code,
                articulo=articulo,
                description=description,
                photo_url=photo_url,
                quantity_cajas=None,  # La IA no siempre proporciona cajas
                quantity_total=ai_product.cantidad_sugerida,
                cbm_unit=ai_product.volumen_total_m3,  # Se ajusta si hay cajas
                cbm_total=ai_product.volumen_total_m3,
                precio_unitario_cny=ai_product.precio_unitario_cny,
                precio_unitario_usd=precio_usd,
                total_usd=total_usd,
                tasa_cambio=self._cny_usd_rate,
                editable=True,
            )
            rows.append(row)

        return rows

    # ============================================================
    # RECÁLCULO (cuando el usuario edita una celda)
    # ============================================================
    def recalculate_product(
        self, product: ProductRow, rate: Optional[float] = None
    ) -> ProductRow:
        """
        Recalcula un producto después de que el usuario editó celdas.
        Se llama cuando cambia quantity, precio, o cajas.
        """
        exchange_rate = rate or self._cny_usd_rate

        # Recalcular precio USD desde CNY
        product.precio_unitario_usd = self.convert_cny_to_usd(
            product.precio_unitario_cny, exchange_rate
        )

        # Recalcular total USD
        product.total_usd = self.calculate_total_usd(
            product.quantity_total, product.precio_unitario_usd
        )

        # Recalcular CBM
        if product.quantity_cajas and product.quantity_cajas > 0:
            product.cbm_total = round(
                product.cbm_unit * product.quantity_cajas, 4
            )

        product.tasa_cambio = exchange_rate
        return product


# Singleton del procesador
processor = BusinessProcessor()
