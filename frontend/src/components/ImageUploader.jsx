/**
 * EMFOX OMS - ImageUploader Component
 * Zona drag-and-drop para subir fotos de productos.
 * Soporta múltiples imágenes, preview, y envío al backend.
 */
import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, ImageIcon as Image, X, Loader2 } from './Icons.jsx';

export default function ImageUploader({ onProcessed, isLoading, setIsLoading, projectId }) {
  const [previews, setPreviews] = useState([]);
  const [files, setFiles] = useState([]);

  const onDrop = useCallback((acceptedFiles) => {
    const newFiles = [...files, ...acceptedFiles];
    setFiles(newFiles);

    // Generar previews
    const newPreviews = acceptedFiles.map((file) => ({
      file,
      url: URL.createObjectURL(file),
      name: file.name,
    }));
    setPreviews((prev) => [...prev, ...newPreviews]);
  }, [files]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png', '.webp'],
    },
    multiple: true,
    disabled: isLoading,
  });

  const removeFile = (index) => {
    const newFiles = files.filter((_, i) => i !== index);
    const newPreviews = previews.filter((_, i) => i !== index);
    URL.revokeObjectURL(previews[index].url);
    setFiles(newFiles);
    setPreviews(newPreviews);
  };

  const handleProcess = async () => {
    if (files.length === 0) return;
    setIsLoading(true);
    try {
      const { uploadAndProcess } = await import('../services/api.js');
      const result = await uploadAndProcess(files, projectId);
      onProcessed(result);
    } catch (error) {
      console.error('Error procesando:', error);
      alert('Error al procesar imágenes: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  const clearAll = () => {
    previews.forEach((p) => URL.revokeObjectURL(p.url));
    setFiles([]);
    setPreviews([]);
  };

  return (
    <div className="upload-section">
      <h2 className="section-title">
        <Image size={20} />
        Subir Fotos de Productos
      </h2>

      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? 'dropzone-active' : ''} ${isLoading ? 'dropzone-disabled' : ''}`}
      >
        <input {...getInputProps()} />
        <Upload size={48} className="dropzone-icon" />
        {isDragActive ? (
          <p>Suelta las imágenes aquí...</p>
        ) : (
          <>
            <p className="dropzone-main">
              Arrastra fotos de productos aquí o haz clic para seleccionar
            </p>
            <p className="dropzone-sub">
              JPG, PNG, WebP • Múltiples imágenes permitidas
            </p>
          </>
        )}
      </div>

      {/* Previews */}
      {previews.length > 0 && (
        <div className="previews-container">
          <div className="previews-header">
            <span>{previews.length} imagen(es) seleccionada(s)</span>
            <button onClick={clearAll} className="btn-link" disabled={isLoading}>
              Limpiar todo
            </button>
          </div>
          <div className="previews-grid">
            {previews.map((preview, index) => (
              <div key={index} className="preview-card">
                <img src={preview.url} alt={preview.name} />
                <button
                  className="preview-remove"
                  onClick={() => removeFile(index)}
                  disabled={isLoading}
                >
                  <X size={14} />
                </button>
                <span className="preview-name">{preview.name}</span>
              </div>
            ))}
          </div>

          {/* Botón procesar */}
          <button
            className="btn-primary btn-process"
            onClick={handleProcess}
            disabled={isLoading || files.length === 0}
          >
            {isLoading ? (
              <>
                <Loader2 size={18} className="spinner" />
                Procesando con Gemini AI...
              </>
            ) : (
              <>
                <Upload size={18} />
                Procesar {files.length} imagen(es) con IA
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
