/**
 * EMFOX OMS - ExportPanel Component
 * Panel de datos de consignatario y botón de exportación a Excel.
 */
import React, { useState } from 'react';
import { FileSpreadsheet, Download, Loader2, FilePdf } from './Icons.jsx';
import { exportToExcel, exportToPdf } from '../services/api.js';

export default function ExportPanel({ products, exportConfig, setExportConfig }) {
  const [isExporting, setIsExporting] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  const getExportData = () => ({
    products,
    consignee: exportConfig.consignee,
    ruc: exportConfig.ruc,
    direccion: exportConfig.direccion,
    origin: exportConfig.origin,
    destination: exportConfig.destination,
    payment_term: exportConfig.payment_term,
    date: exportConfig.date,
  });

  const handleExport = async () => {
    if (!products || products.length === 0) {
      alert('No hay productos para exportar');
      return;
    }
    setIsExporting(true);
    try {
      await exportToExcel(getExportData());
    } catch (error) {
      console.error('Error exportando:', error);
      alert('Error al exportar: ' + error.message);
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportPdf = async () => {
    if (!products || products.length === 0) {
      alert('No hay productos para exportar');
      return;
    }
    setIsExportingPdf(true);
    try {
      await exportToPdf(getExportData());
    } catch (error) {
      console.error('Error exportando PDF:', error);
      const msg = error.response?.data?.detail || error.message;
      alert('Error al exportar PDF: ' + msg);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const updateField = (field, value) => {
    setExportConfig((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="export-panel">
      <h2 className="section-title">
        <FileSpreadsheet size={20} />
        Datos de Exportación
      </h2>

      <div className="export-form">
        <div className="form-row">
          <div className="form-group">
            <label>CONSIGNEE</label>
            <input
              type="text"
              value={exportConfig.consignee}
              onChange={(e) => updateField('consignee', e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>DATE</label>
            <input
              type="text"
              value={exportConfig.date}
              onChange={(e) => updateField('date', e.target.value)}
              placeholder="DD/MM/YYYY"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>RUC</label>
            <input
              type="text"
              value={exportConfig.ruc}
              onChange={(e) => updateField('ruc', e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>DIRECCIÓN</label>
            <input
              type="text"
              value={exportConfig.direccion}
              onChange={(e) => updateField('direccion', e.target.value)}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>ORIGIN</label>
            <input
              type="text"
              value={exportConfig.origin}
              onChange={(e) => updateField('origin', e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>DESTINATION</label>
            <input
              type="text"
              value={exportConfig.destination}
              onChange={(e) => updateField('destination', e.target.value)}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group full-width">
            <label>PAYMENT TERM</label>
            <input
              type="text"
              value={exportConfig.payment_term}
              onChange={(e) => updateField('payment_term', e.target.value)}
            />
          </div>
        </div>
      </div>

      <button
        className="btn-export"
        onClick={handleExport}
        disabled={isExporting || !products || products.length === 0}
      >
        {isExporting ? (
          <>
            <Loader2 size={18} className="spinner" />
            Generando Excel...
          </>
        ) : (
          <>
            <Download size={18} />
            Exportar a Excel (.xlsx)
          </>
        )}
      </button>

      <button
        className="btn-export btn-export-pdf"
        onClick={handleExportPdf}
        disabled={isExportingPdf || !products || products.length === 0}
      >
        {isExportingPdf ? (
          <>
            <Loader2 size={18} className="spinner" />
            Generando PDF...
          </>
        ) : (
          <>
            <FilePdf size={18} />
            Exportar a PDF
          </>
        )}
      </button>
    </div>
  );
}
