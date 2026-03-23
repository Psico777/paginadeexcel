/**
 * EMFOX OMS - CropModal
 * Interactive manual crop selector for product images.
 * Uses mouse drag on a canvas overlay to select a crop region.
 */
import React, { useRef, useState, useEffect, useCallback } from 'react';

export default function CropModal({ product, projectId, onClose, onCropApplied }) {
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const [imgNaturalSize, setImgNaturalSize] = useState({ w: 1, h: 1 });
  const [imgRendered, setImgRendered] = useState({ w: 1, h: 1, left: 0, top: 0 });
  const [dragging, setDragging] = useState(false);
  const [startPt, setStartPt] = useState(null);
  const [rect, setRect] = useState(null); // { x, y, w, h } in canvas coords
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const sourceUrl = product.photo_url || product.crop_url;

  // Redraw canvas overlay
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!rect || rect.w === 0 || rect.h === 0) return;

    const { x, y, w, h } = rect;
    const nx = w < 0 ? x + w : x;
    const ny = h < 0 ? y + h : y;
    const nw = Math.abs(w);
    const nh = Math.abs(h);

    // Darken outside
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.clearRect(nx, ny, nw, nh);

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
  }, [rect]);

  useEffect(() => { redraw(); }, [rect, redraw]);

  // Sync canvas size when image loads
  const handleImgLoad = () => {
    const img = imgRef.current;
    if (!img) return;
    setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    // Delay to ensure the modal layout is fully rendered before measuring
    setTimeout(() => syncCanvasSize(), 50);
  };

  const syncCanvasSize = () => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    const renderedRect = img.getBoundingClientRect();
    // Guard: if layout not ready yet, retry
    if (renderedRect.width === 0) {
      setTimeout(() => syncCanvasSize(), 100);
      return;
    }
    canvas.width = renderedRect.width;
    canvas.height = renderedRect.height;
    setImgRendered({ w: renderedRect.width, h: renderedRect.height, left: renderedRect.left, top: renderedRect.top });
  };

  useEffect(() => {
    window.addEventListener('resize', syncCanvasSize);
    return () => window.removeEventListener('resize', syncCanvasSize);
  }, []);

  const getCanvasCoords = (e) => {
    const canvas = canvasRef.current;
    const r = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - r.left, y: clientY - r.top };
  };

  const onMouseDown = (e) => {
    e.preventDefault();
    const pt = getCanvasCoords(e);
    setStartPt(pt);
    setDragging(true);
    setRect({ x: pt.x, y: pt.y, w: 0, h: 0 });
  };

  const onMouseMove = (e) => {
    if (!dragging || !startPt) return;
    const pt = getCanvasCoords(e);
    setRect({ x: startPt.x, y: startPt.y, w: pt.x - startPt.x, h: pt.y - startPt.y });
  };

  const onMouseUp = () => {
    setDragging(false);
  };

  // Convert canvas rect to image natural coords
  const getImageCoords = () => {
    if (!rect) return null;
    const canvas = canvasRef.current;
    const scaleX = imgNaturalSize.w / canvas.width;
    const scaleY = imgNaturalSize.h / canvas.height;

    const nx = rect.w < 0 ? rect.x + rect.w : rect.x;
    const ny = rect.h < 0 ? rect.y + rect.h : rect.y;
    const nw = Math.abs(rect.w);
    const nh = Math.abs(rect.h);

    return {
      x: Math.round(nx * scaleX),
      y: Math.round(ny * scaleY),
      width: Math.round(nw * scaleX),
      height: Math.round(nh * scaleY),
    };
  };

  const coords = getImageCoords();

  const handleApply = async () => {
    if (!coords || coords.width < 10 || coords.height < 10) {
      setError('Selecciona una región más grande.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const { manualCrop } = await import('../services/api.js');
      const result = await manualCrop(projectId, product.id || product.uid, {
        x: coords.x,
        y: coords.y,
        width: coords.width,
        height: coords.height,
        source_url: sourceUrl,
      });
      onCropApplied(result.crop_url);
      onClose();
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
          Arrastra sobre la imagen para seleccionar el área a recortar
        </div>

        <div style={styles.imgWrapper}>
          <img
            ref={imgRef}
            src={sourceUrl}
            alt="original"
            style={styles.img}
            onLoad={handleImgLoad}
            draggable={false}
          />
          <canvas
            ref={canvasRef}
            style={styles.canvas}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          />
        </div>

        <div style={styles.coordsBar}>
          {coords && coords.width > 0
            ? `📐 x:${coords.x} y:${coords.y} — ${coords.width}×${coords.height}px`
            : 'Arrastra para seleccionar región'}
        </div>

        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.footer}>
          <button style={styles.cancelBtn} onClick={onClose} disabled={loading}>
            Cancelar
          </button>
          <button
            style={{ ...styles.applyBtn, opacity: loading ? 0.6 : 1 }}
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
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 9999, padding: '16px',
  },
  modal: {
    background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: '12px',
    display: 'flex', flexDirection: 'column', gap: '12px',
    maxWidth: '90vw', maxHeight: '90vh', overflow: 'hidden',
    padding: '16px', minWidth: '320px',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  },
  title: { color: '#00e5ff', fontWeight: 700, fontSize: '16px' },
  closeBtn: {
    background: 'none', border: 'none', color: '#aaa', fontSize: '18px',
    cursor: 'pointer', padding: '2px 6px',
  },
  instructions: { color: '#ccc', fontSize: '13px' },
  imgWrapper: {
    position: 'relative', display: 'inline-block',
    maxHeight: '60vh', overflow: 'auto',
  },
  img: { display: 'block', maxWidth: '100%', maxHeight: '60vh', userSelect: 'none' },
  canvas: {
    position: 'absolute', inset: 0, cursor: 'crosshair',
    width: '100%', height: '100%',
  },
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
    background: '#00e5ff', color: '#000', cursor: 'pointer', fontSize: '14px',
    fontWeight: 700,
  },
};
