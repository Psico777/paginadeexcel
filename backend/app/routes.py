"""
EMFOX OMS v2 - API Routes (FastAPI)
=====================================
Complete CRUD for projects and products, WebSocket for real-time
collaboration, image upload + AI processing with smart crop,
dynamic exchange rate recalculation, and Excel export.
"""

import os
import io
import uuid
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import date, datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, Project, Product, init_db
from app.schemas import (
    ProcessingResponse, ExportRequest, ProductRow, RecalculateRequest,
    BulkRecalculateRequest, ProjectCreate, ProjectUpdate, ProjectSummary,
)
from app.modules.gemini_vision import gemini_service
from app.modules.business_logic import processor
from app.modules.excel_export import generate_emfox_excel
from app.modules.smart_crop import crop_product_from_image, create_thumbnail_from_full_image, detect_and_crop_products, manual_crop
from app.modules.pdf_export import excel_to_pdf
from app.ws_manager import ws_manager

router = APIRouter(prefix="/api", tags=["OMS"])

UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "crops").mkdir(exist_ok=True)

# Initialize database tables on import
init_db()


# ============================================================
# PROJECTS CRUD
# ============================================================
@router.get("/projects")
async def list_projects(db: Session = Depends(get_db)):
    """List all active projects, most recent first."""
    projects = db.query(Project).filter(Project.is_active == True).order_by(Project.updated_at.desc()).all()
    return [p.to_dict() for p in projects]


@router.post("/projects")
async def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project (empty Lista de Productos)."""
    now = datetime.now(timezone.utc)
    project = Project(
        name=data.name,
        description=data.description,
        exchange_rate=data.exchange_rate,
        date_str=date.today().strftime("%d/%m/%Y"),
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project.to_dict()


@router.get("/projects/{project_id}")
async def get_project(project_id: int, db: Session = Depends(get_db)):
    """Get a project with all its products."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    result = project.to_dict()
    result["products"] = [p.to_dict() for p in project.products]
    return result


@router.put("/projects/{project_id}")
async def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    """Update project metadata (consignee, exchange rate, etc.)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)

    await ws_manager.broadcast_to_room(project_id, {
        "type": "project_updated",
        "data": project.to_dict(),
    })

    return project.to_dict()


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    """Soft-delete a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    project.is_active = False
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "message": "Proyecto eliminado"}


# ============================================================
# PRODUCTS CRUD (within a project)
# ============================================================
@router.post("/projects/{project_id}/products")
async def add_product(project_id: int, product: ProductRow, db: Session = Depends(get_db)):
    """Add a single product to a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    max_order = db.query(Product).filter(Product.project_id == project_id).count()

    db_product = Product(
        uid=product.id or str(uuid.uuid4()),
        project_id=project_id,
        sort_order=max_order,
        code=product.code,
        articulo=product.articulo,
        description=product.description,
        photo_url=product.photo_url,
        crop_url=product.crop_url,
        quantity_cajas=product.quantity_cajas,
        quantity_und_por_caja=product.quantity_und_por_caja,
        quantity_total=product.quantity_total,
        cbm_unit=product.cbm_unit,
        cbm_total=product.cbm_total,
        precio_unitario_cny=product.precio_unitario_cny,
        precio_unitario_usd=product.precio_unitario_usd,
        total_usd=product.total_usd,
        tasa_cambio=product.tasa_cambio,
        editable=True,
    )
    db.add(db_product)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_product)

    row_dict = db_product.to_dict()
    await ws_manager.broadcast_to_room(project_id, {
        "type": "product_added",
        "data": row_dict,
    })

    return row_dict


@router.put("/projects/{project_id}/products/{product_uid}")
async def update_product(project_id: int, product_uid: str, product: ProductRow, db: Session = Depends(get_db)):
    """Update a product in a project (from cell edit)."""
    db_product = db.query(Product).filter(
        Product.uid == product_uid, Product.project_id == project_id
    ).first()
    if not db_product:
        raise HTTPException(404, "Producto no encontrado")

    db_product.code = product.code
    db_product.articulo = product.articulo
    db_product.description = product.description
    db_product.photo_url = product.photo_url
    db_product.crop_url = product.crop_url
    db_product.quantity_cajas = product.quantity_cajas
    db_product.quantity_und_por_caja = product.quantity_und_por_caja
    db_product.quantity_total = product.quantity_total
    db_product.cbm_unit = product.cbm_unit
    db_product.cbm_total = product.cbm_total
    db_product.precio_unitario_cny = product.precio_unitario_cny
    db_product.precio_unitario_usd = product.precio_unitario_usd
    db_product.total_usd = product.total_usd
    db_product.tasa_cambio = product.tasa_cambio
    db_product.updated_at = datetime.now(timezone.utc)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_product)

    row_dict = db_product.to_dict()
    await ws_manager.broadcast_to_room(project_id, {
        "type": "product_updated",
        "data": row_dict,
    })

    return row_dict


@router.post("/projects/{project_id}/products/{product_uid}/manual-crop")
async def apply_manual_crop(project_id: int, product_uid: str, payload: dict, db: Session = Depends(get_db)):
    """Apply a user-defined manual crop to a product image."""
    x = int(payload.get("x", 0))
    y = int(payload.get("y", 0))
    width = int(payload.get("width", 0))
    height = int(payload.get("height", 0))
    source_url = payload.get("source_url", "")

    if width <= 0 or height <= 0:
        raise HTTPException(400, "Invalid crop dimensions")

    # Resolve source_url to a local path
    # source_url may be /uploads/... or /uploads/crops/...
    local_path = None
    if source_url.startswith("/uploads/"):
        local_path = str(UPLOAD_DIR / source_url[len("/uploads/"):])
    elif source_url.startswith("http"):
        # Download to temp file
        import tempfile, requests as _req
        resp = _req.get(source_url, timeout=30)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(resp.content)
            local_path = tmp.name

    if not local_path or not os.path.exists(local_path):
        raise HTTPException(400, f"Source image not found: {source_url}")

    try:
        crop_url = manual_crop(local_path, x, y, width, height, product_uid)
    except Exception as e:
        raise HTTPException(500, f"Crop failed: {e}")

    # Update DB
    db_product = db.query(Product).filter(
        Product.uid == product_uid, Product.project_id == project_id
    ).first()
    if not db_product:
        raise HTTPException(404, "Producto no encontrado")

    db_product.crop_url = crop_url
    db.commit()
    db.refresh(db_product)

    await ws_manager.broadcast_to_room(project_id, {
        "type": "product_updated",
        "data": db_product.to_dict(),
    })

    return {"success": True, "crop_url": crop_url}


@router.delete("/projects/{project_id}/products/{product_uid}")
async def delete_product(project_id: int, product_uid: str, db: Session = Depends(get_db)):
    """Delete a single product from a project."""
    db_product = db.query(Product).filter(
        Product.uid == product_uid, Product.project_id == project_id
    ).first()
    if not db_product:
        raise HTTPException(404, "Producto no encontrado")

    db.delete(db_product)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.updated_at = datetime.now(timezone.utc)

    db.commit()

    await ws_manager.broadcast_to_room(project_id, {
        "type": "product_deleted",
        "data": {"id": product_uid},
    })

    return {"success": True}


@router.delete("/projects/{project_id}/products")
async def clear_all_products(project_id: int, db: Session = Depends(get_db)):
    """Delete ALL products from a project (Clear All)."""
    db.query(Product).filter(Product.project_id == project_id).delete()

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.updated_at = datetime.now(timezone.utc)

    db.commit()

    await ws_manager.broadcast_to_room(project_id, {
        "type": "products_cleared",
        "data": {"project_id": project_id},
    })

    return {"success": True, "message": "Todos los productos eliminados"}


# ============================================================
# BULK RECALCULATE (exchange rate change)
# ============================================================
@router.post("/projects/{project_id}/recalculate-all")
async def recalculate_all_products(
    project_id: int, data: BulkRecalculateRequest, db: Session = Depends(get_db)
):
    """Recalculate ALL products with a new exchange rate."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    project.exchange_rate = data.cny_to_usd_rate
    project.updated_at = datetime.now(timezone.utc)

    db_products = db.query(Product).filter(Product.project_id == project_id).order_by(Product.sort_order).all()
    updated_rows = []

    for db_p in db_products:
        db_p.tasa_cambio = data.cny_to_usd_rate
        db_p.precio_unitario_usd = round(db_p.precio_unitario_cny / data.cny_to_usd_rate, 2)
        db_p.total_usd = round(db_p.quantity_total * db_p.precio_unitario_usd, 2)
        db_p.updated_at = datetime.now(timezone.utc)
        updated_rows.append(db_p.to_dict())

    db.commit()

    await ws_manager.broadcast_to_room(project_id, {
        "type": "products_recalculated",
        "data": {"exchange_rate": data.cny_to_usd_rate, "products": updated_rows},
    })

    return {"success": True, "products": updated_rows}


# ============================================================
# UPLOAD + AI PROCESS (with smart crop)
# ============================================================
@router.post("/projects/{project_id}/upload-and-process", response_model=ProcessingResponse)
async def upload_and_process(
    project_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload images, process with Gemini AI, smart-crop, and save to project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    saved_paths = []
    saved_urls = []

    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            continue
        ext = Path(file.filename).suffix or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / unique_name
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_paths.append(str(file_path))
        saved_urls.append(f"/uploads/{unique_name}")

    if not saved_paths:
        raise HTTPException(400, "No se subieron imágenes válidas")

    try:
        ai_products = await gemini_service.analyze_images(saved_paths)

        if not ai_products:
            return ProcessingResponse(
                success=True, message="No se detectaron productos en las imágenes",
                products=[], date=date.today().strftime("%d/%m/%Y"),
            )

        existing_count = db.query(Product).filter(Product.project_id == project_id).count()
        next_code = settings.next_product_code + existing_count

        rate = project.exchange_rate or settings.cny_to_usd_rate
        product_rows = []

        # Group products by source image for batch smart crop
        products_by_image = {}
        for i, ai_p in enumerate(ai_products):
            img_idx = ai_p.image_index if ai_p.image_index < len(saved_paths) else 0
            products_by_image.setdefault(img_idx, []).append((i, ai_p))

        # Smart crop: detect and crop products per source image
        crop_urls_map = {}  # i -> crop_url
        for img_idx, items in products_by_image.items():
            source_path = saved_paths[img_idx]
            uids_for_image = []
            indices_for_image = []
            bboxes_for_image = []
            for i, ai_p in items:
                product_uid = str(uuid.uuid4())
                uids_for_image.append(product_uid)
                indices_for_image.append(i)
                crop_urls_map[i] = {"uid": product_uid, "crop_url": None}
                # Collect Gemini bboxes for this image
                bbox_dict = None
                if ai_p.bbox:
                    bbox_dict = {
                        "x_pct": ai_p.bbox.x_pct,
                        "y_pct": ai_p.bbox.y_pct,
                        "w_pct": ai_p.bbox.w_pct,
                        "h_pct": ai_p.bbox.h_pct,
                    }
                bboxes_for_image.append(bbox_dict)

            # Use improved detection with AI bboxes as primary strategy
            crop_results = detect_and_crop_products(
                source_path, uids_for_image,
                expected_count=len(items),
                bboxes_from_ai=bboxes_for_image,
            )
            for j, (idx, _) in enumerate(items):
                if j < len(crop_results) and crop_results[j]:
                    crop_urls_map[idx]["crop_url"] = crop_results[j]

        for i, ai_p in enumerate(ai_products):
            info = crop_urls_map.get(i, {})
            product_uid = info.get("uid", str(uuid.uuid4()))
            crop_url = info.get("crop_url")
            code = next_code + i

            img_idx = ai_p.image_index if ai_p.image_index < len(saved_paths) else 0
            source_path = saved_paths[img_idx]
            source_url = saved_urls[img_idx]

            if not crop_url:
                crop_url = create_thumbnail_from_full_image(source_path, product_uid)

            precio_usd = round(ai_p.precio_unitario_cny / rate, 2)
            total_usd = round(ai_p.cantidad_sugerida * precio_usd, 2)

            desc_parts = []
            if ai_p.tamano_cm:
                desc_parts.append(f"{ai_p.tamano_cm} cm")
            if ai_p.notas:
                desc_parts.append(ai_p.notas)
            if not desc_parts:
                desc_parts.append(ai_p.descripcion_general[:50])
            description = " - ".join(desc_parts)

            bbox_data = {}
            if ai_p.bbox:
                bbox_data = {
                    "x_pct": ai_p.bbox.x_pct,
                    "y_pct": ai_p.bbox.y_pct,
                    "w_pct": ai_p.bbox.w_pct,
                    "h_pct": ai_p.bbox.h_pct,
                }

            db_product = Product(
                uid=product_uid,
                project_id=project_id,
                sort_order=existing_count + i,
                code=code,
                articulo=f"Producto {existing_count + i + 1}",
                description=description,
                photo_url=source_url,
                crop_url=crop_url,
                quantity_cajas=1,
                quantity_und_por_caja=ai_p.cantidad_sugerida,
                quantity_total=ai_p.cantidad_sugerida,
                cbm_unit=ai_p.volumen_total_m3,
                cbm_total=ai_p.volumen_total_m3,
                precio_unitario_cny=ai_p.precio_unitario_cny,
                precio_unitario_usd=precio_usd,
                total_usd=total_usd,
                tasa_cambio=rate,
                source_image=source_path,
                bbox_x=int(bbox_data.get("x_pct", 0) * 10) if bbox_data else None,
                bbox_y=int(bbox_data.get("y_pct", 0) * 10) if bbox_data else None,
                bbox_w=int(bbox_data.get("w_pct", 100) * 10) if bbox_data else None,
                bbox_h=int(bbox_data.get("h_pct", 100) * 10) if bbox_data else None,
            )
            db.add(db_product)
            product_rows.append(db_product)

        project.updated_at = datetime.now(timezone.utc)
        db.commit()

        row_dicts = []
        for p in product_rows:
            db.refresh(p)
            row_dicts.append(p.to_dict())

        total_usd_all = sum(d["total_usd"] for d in row_dicts)
        total_cbm_all = sum(d["cbm_total"] for d in row_dicts)

        await ws_manager.broadcast_to_room(project_id, {
            "type": "products_added_batch",
            "data": {"products": row_dicts},
        })

        return ProcessingResponse(
            success=True,
            message=f"{len(row_dicts)} producto(s) detectados y procesados",
            products=[ProductRow(**d) for d in row_dicts],
            date=date.today().strftime("%d/%m/%Y"),
            total_general_usd=round(total_usd_all, 2),
            total_cbm=round(total_cbm_all, 4),
        )

    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)}")


# ============================================================
# LEGACY ENDPOINTS (backwards compatible)
# ============================================================
@router.post("/upload-and-process", response_model=ProcessingResponse)
async def upload_and_process_legacy(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Legacy endpoint - uses latest active project."""
    project = db.query(Project).filter(Project.is_active == True).order_by(Project.updated_at.desc()).first()
    if not project:
        project = Project(
            name=f"Lista_{date.today().strftime('%Y%m%d')}",
            exchange_rate=settings.cny_to_usd_rate,
            date_str=date.today().strftime("%d/%m/%Y"),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
    return await upload_and_process(project.id, files, db)


@router.post("/recalculate", response_model=ProductRow)
async def recalculate_product(request: RecalculateRequest):
    """Recalculate a single product after edit."""
    updated = processor.recalculate_product(request.product, request.cny_to_usd_rate)
    return updated


@router.post("/export")
async def export_excel(data: ExportRequest):
    """Generate and download Excel with EMFOX format and embedded images."""
    if not data.products:
        raise HTTPException(400, "No hay productos para exportar")
    if not data.date:
        data.date = date.today().strftime("%d/%m/%Y")
    try:
        buffer = generate_emfox_excel(data)
        filename = f"EMFOX_ListaProductos_{date.today().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(500, f"Error generando Excel: {str(e)}")


@router.post("/export-pdf")
async def export_pdf(data: ExportRequest):
    """Generate Excel, convert to PDF via iLovePDF, and download."""
    if not data.products:
        raise HTTPException(400, "No hay productos para exportar")
    if not data.date:
        data.date = date.today().strftime("%d/%m/%Y")
    try:
        # First generate the Excel
        excel_buffer = generate_emfox_excel(data)

        # Convert to PDF via iLovePDF API
        pdf_bytes = await excel_to_pdf(excel_buffer)

        filename = f"EMFOX_ListaProductos_{date.today().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generando PDF: {str(e)}")


@router.get("/config")
async def get_config():
    return {
        "cny_to_usd_rate": settings.cny_to_usd_rate,
        "next_product_code": settings.next_product_code,
        "gemini_model": settings.gemini_model,
        "company": "EMFOX YIWU TRADE CO., LTD",
    }


# ============================================================
# WEBSOCKET ENDPOINT
# ============================================================
@router.websocket("/ws/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: int,
    user: str = Query(default="Anónimo"),
):
    """WebSocket for real-time collaboration on a project."""
    await ws_manager.connect(websocket, project_id, user)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "cursor_move":
                await ws_manager.broadcast_to_room(project_id, {
                    "type": "cursor_move", "user": user,
                    "data": data.get("data", {}),
                }, exclude=websocket)

            elif msg_type == "typing":
                await ws_manager.broadcast_to_room(project_id, {
                    "type": "typing", "user": user,
                    "data": data.get("data", {}),
                }, exclude=websocket)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, project_id)
    except Exception as e:
        print(f"[WS] Error: {e}")
        await ws_manager.disconnect(websocket, project_id)
