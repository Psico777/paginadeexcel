/**
 * EMFOX OMS - CropModal v2
 * Fixed: canvas coordinates now always match displayed image pixels.
 * Approach: draw image directly on canvas (no separate img tag), 
 * so canvas pixels = image pixels after scaling. No timing issues.
 */
import React, { useRef, useState, useEffect, useCallback } from 'react';

export default function CropModal({ product, projectId, onClose, onCropApplied }) {
  const canvasRef = useRef(null);
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [scale, setScale] = useState(1);          // canvas px / image px
  const [dragging, setDragging] = useState(false);
  const [startPt, setStartPt] = useState(null);
  const [rect, setRect] = useState(null);          // in canvas coords
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [imgLoaded, setImgLoaded] = useState(false);
  const imgObjRef = useRef(null);

  const sourceUrl = product.photo_url || product.crop_url;

  // ── Load image and draw on canvas ──────────────────────────
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      imgObjRef.current = img;
      setImgNatural({ w: img.naturalWidth, h: img.naturalHeight });

      const canvas = canvasRef.current;
      if (!canvas) return;

      // Fit image inside 80vw × 70vh while keeping aspect ratio
      const maxW = Math.min(window.innerWidth * 0.82, 900);
      const maxH = window.innerHeight * 0.68;
      const scaleW = maxW / img.naturalWidth;
      const scaleH = maxH / img.naturalHeight;
      const s = Math.min(scaleW, scaleH, 1); // never upscale

      canvas.width  = Math.round(img.naturalWidth  * s);
      canvas.height = Math.round(img.naturalHeight * s);
      setScale(s);

      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      setImgLoaded(true);
      setRect(null);
    };
    img.onerror = () => setError('No se pudo cargar la imagen.');
    img.src = sourceUrl;
  }, [sourceUrl]);

  // ── Redraw canvas (image + selection) ─────────────────────
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgObjRef.current;
    if (!canvas || !img || !imgLoaded) return;
    const ctx = canvas.getContext('2d');

    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    if (!rect || Math.abs(rect.w) < 2 || Math.abs(rect.h) < 2) return;

    const nx = rect.w < 0 ? rect.x + rect.w : rect.x;
    const ny = rect.h < 0 ? rect.y + rect.h : rect.y;
    const nw = Math.abs(rect.w);
    const nh = Math.abs(rect.h);

    // Darken outside selection
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, nx / scale, ny / scale,
      nw / scale, nh / scale, nx, ny, nw, nh);

    // Border
    ctx.strokeStyle = '#00e5ff';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(nx, ny, nw, nh);

    // Corner handles
    ctx.setLineDash([]);
    ctx.fillStyle = '#00e5ff';
    const sz = 7;
    [[nx, ny], [nx + nw, ny], [nx, ny + nh], [nx + nw, ny + nh]].forEach(([cx, cy]) => {
      ctx.fillRect(cx - sz / 2, cy - sz / 2, sz, sz);
    });
  }, [rect, imgLoaded, scale]);

  useEffect(() => { redraw(); }, [rect, redraw]);

  // ── Mouse events ───────────────────────────────────────────
  const getCanvasCoords = (e) => {
    const canvas = canvasRef.current;
    const r = canvas.getBoundingClientRect();
    // Correct for CSS scaling (canvas may be displayed smaller than its pixel size)
    const cssToPixel = canvas.width / r.width;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return {
      x: (clientX - r.left) * cssToPixel,
      y: (clientY - r.top)  * cssToPixel,
    };
  };

  const onMouseDown = (e) => {
    if (!imgLoaded) return;
    e.preventDefault();
    const pt = getCanvasCoords(e);
    setStartPt(pt);
    setRect({ x: pt.x, y: pt.y, w: 0, h: 0 });
    setDragging(true);
  };

  const onMouseMove = (e) => {
    if (!dragging || !startPt) return;
    e.preventDefault();
    const pt = getCanvasCoords(e);
    setRect({ x: startPt.x, y: startPt.y, w: pt.x - startPt.x, h: pt.y - startPt.y });
  };

  const onMouseUp = (e) => {
    if (!dragging) return;
    e.preventDefault();
    setDragging(false);
  };

  // ── Compute image-space coordinates ───────────────────────
  const getImageCoords = () => {
    if (!rect || Math.abs(rect.w) < 5 || Math.abs(rect.h) < 5) return null;
    const nx = rect.w < 0 ? rect.x + rect.w : rect.x;
    const ny = rect.h < 0 ? rect.y + rect.h : rect.y;
    const nw = Math.abs(rect.w);
    const nh = Math.abs(rect.h);
    return {
      x:      Math.round(nx / scale),
      y:      Math.round(ny / scale),
      width:  Math.round(nw / scale),
      height: Math.round(nh / scale),
    };
  };

  const coords = getImageCoords();

  const handleApply = async () => {
    if (!coords || coords.width < 10 || coords.height < 10) {
      setError('Selecciona una región más grande.');
      return;
    }
    // Use product's project_id as fallback if projectId prop is null
    const pid = projectId || product.project_id;
    if (!pid) {
      setError('No hay proyecto activo. Selecciona un proyecto primero.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const { manualCrop } = await import('../services/api.js');
      const result = await manualCrop(pid, product.id || product.uid, {
        x: coords.x,
        y: coords.y,
        width: coords.width,
        height: coords.height,
        source_url: sourceUrl,
      });
      onClose();
      onCropApplied(result.crop_url);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error al aplicar recorte.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>✂️ Recorte Manual</span>
          <button style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div style={styles.instructions}>
          {imgLoaded ? 'Arrastra para seleccionar el área del producto' : '⏳ Cargando imagen...'}
        </div>

        <div style={styles.canvasWrapper}>
          <canvas
            ref={canvasRef}
            style={{ ...styles.canvas, cursor: imgLoaded ? 'crosshair' : 'wait' }}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
            onTouchStart={onMouseDown}
            onTouchMove={onMouseMove}
            onTouchEnd={onMouseUp}
          />
        </div>

        <div style={styles.coordsBar}>
          {coords && coords.width > 0
            ? `📐 x:${coords.x} y:${coords.y} — ${coords.width}×${coords.height}px (imagen: ${imgNatural.w}×${imgNatural.h})`
            : imgLoaded ? 'Arrastra para seleccionar región' : '...'}
        </div>

        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.footer}>
          <button style={styles.cancelBtn} onClick={onClose} disabled={loading}>
            Cancelar
          </button>
          <button
            style={{ ...styles.applyBtn, opacity: (loading || !coords || coords.width < 10) ? 0.5 : 1 }}
            onClick={handleApply}
            disabled={loading || !coords || coords.width < 10}
          >
            {loading ? '⏳ Procesando...' : '✂️ Aplicar recorte'}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 9999, padding: '16px',
  },
  modal: {
    background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: '12px',
    display: 'flex', flexDirection: 'column', gap: '12px',
    maxWidth: '92vw', maxHeight: '95vh', overflow: 'hidden',
    padding: '16px',
  },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: '#00e5ff', fontWeight: 700, fontSize: '16px' },
  closeBtn: { background: 'none', border: 'none', color: '#aaa', fontSize: '20px', cursor: 'pointer' },
  instructions: { color: '#ccc', fontSize: '13px' },
  canvasWrapper: { overflow: 'auto', maxHeight: '68vh', borderRadius: '6px', background: '#000' },
  canvas: { display: 'block', maxWidth: '100%' },
  coordsBar: {
    color: '#7ec8e3', fontSize: '12px', fontFamily: 'monospace',
    background: '#0d0d1a', padding: '6px 10px', borderRadius: '6px',
  },
  error: { color: '#ff6b6b', fontSize: '13px' },
  footer: { display: 'flex', gap: '10px', justifyContent: 'flex-end' },
  cancelBtn: {
    padding: '8px 18px', borderRadius: '8px', border: '1px solid #444',
    background: '#2a2a3e', color: '#ccc', cursor: 'pointer', fontSize: '14px',
  },
  applyBtn: {
    padding: '8px 18px', borderRadius: '8px', border: 'none',
    background: '#00e5ff', color: '#000', cursor: 'pointer', fontSize: '14px', fontWeight: 700,
  },
};
