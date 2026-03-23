/**
 * EMFOX OMS v2 - EditableTable Component
 * TanStack Table with editable cells, auto-recalculation,
 * delete per row, crop_url thumbnails, EMFOX column layout.
 */
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table';
import { Pencil, Trash2 } from './Icons.jsx';

// ============================================================
// CELDA EDITABLE - Texto
// ============================================================
function EditableCell({ getValue, row, column, table }) {
  const initialValue = getValue();
  const [value, setValue] = useState(initialValue);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => { setValue(initialValue); }, [initialValue]);

  const onBlur = () => {
    setIsEditing(false);
    if (value !== initialValue) {
      table.options.meta?.updateData(row.index, column.id, value);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') onBlur();
    if (e.key === 'Escape') { setValue(initialValue); setIsEditing(false); }
  };

  if (isEditing) {
    return (
      <input
        className="cell-input"
        value={value ?? ''}
        onChange={(e) => setValue(e.target.value)}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
        autoFocus
      />
    );
  }

  return (
    <div className="cell-display" onClick={() => setIsEditing(true)} title="Click para editar">
      {value ?? '—'}
      <Pencil size={10} className="cell-edit-icon" />
    </div>
  );
}

// ============================================================
// CELDA NUMÉRICA EDITABLE
// ============================================================
function EditableNumberCell({ getValue, row, column, table }) {
  const initialValue = getValue();
  const [value, setValue] = useState(initialValue);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => { setValue(initialValue); }, [initialValue]);

  const onBlur = () => {
    setIsEditing(false);
    const numVal = parseFloat(value);
    if (!isNaN(numVal) && numVal !== initialValue) {
      table.options.meta?.updateData(row.index, column.id, numVal);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') onBlur();
    if (e.key === 'Escape') { setValue(initialValue); setIsEditing(false); }
  };

  if (isEditing) {
    return (
      <input
        className="cell-input cell-input-number"
        type="number"
        step="any"
        value={value ?? ''}
        onChange={(e) => setValue(e.target.value)}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
        autoFocus
      />
    );
  }

  return (
    <div className="cell-display cell-number" onClick={() => setIsEditing(true)} title="Click para editar">
      {value ?? '—'}
      <Pencil size={10} className="cell-edit-icon" />
    </div>
  );
}

// ============================================================
// COMPONENTE PRINCIPAL
// ============================================================
export default function EditableTable({ products, setProducts, exchangeRate, onDeleteProduct }) {

  const recalculate = useCallback((rowIndex, columnId, value) => {
    setProducts((old) => {
      const newData = [...old];
      const row = { ...newData[rowIndex] };
      row[columnId] = value;

      const rate = exchangeRate || row.tasa_cambio || 7.2;

      if (columnId === 'precio_unitario_cny') {
        row.precio_unitario_usd = Math.round((parseFloat(value) / rate) * 100) / 100;
      }
      if (columnId === 'precio_unitario_usd') {
        row.precio_unitario_usd = parseFloat(value);
      }

      // Recalculate quantity_total when cajas or und_por_caja changes
      if (columnId === 'quantity_cajas' || columnId === 'quantity_und_por_caja') {
        const cajas = columnId === 'quantity_cajas' ? (parseFloat(value) || 0) : (row.quantity_cajas || 0);
        const undPorCaja = columnId === 'quantity_und_por_caja' ? (parseFloat(value) || 0) : (row.quantity_und_por_caja || 0);
        row.quantity_total = Math.round(cajas * undPorCaja);
      }

      row.total_usd = Math.round(
        (row.quantity_total || 0) * (row.precio_unitario_usd || 0) * 100
      ) / 100;

      if ((columnId === 'quantity_cajas' || columnId === 'cbm_unit') && row.cbm_unit) {
        row.cbm_total = Math.round(
          (row.quantity_cajas || 0) * row.cbm_unit * 10000
        ) / 10000;
      }

      newData[rowIndex] = row;
      return newData;
    });
  }, [setProducts, exchangeRate]);

  const columns = useMemo(() => [
    // DELETE
    {
      id: 'actions',
      header: '',
      size: 40,
      cell: ({ row }) => (
        <button
          className="btn-delete-row"
          onClick={() => onDeleteProduct && onDeleteProduct(row.original.id)}
          title="Eliminar producto"
        >
          <Trash2 size={14} />
        </button>
      ),
    },
    // PHOTO (crop_url preferred over photo_url)
    {
      id: 'photo',
      header: 'PHOTO',
      accessorKey: 'photo_url',
      size: 80,
      cell: ({ row }) => {
        const crop = row.original.crop_url;
        const photo = row.original.photo_url;
        const url = crop || photo;
        return url ? (
          <img src={url} alt="producto" className="table-thumb" />
        ) : (
          <div className="table-thumb-placeholder">📦</div>
        );
      },
    },
    // CODE
    {
      id: 'code',
      header: 'CODE',
      accessorKey: 'code',
      size: 80,
      cell: ({ getValue }) => <span className="cell-code">{getValue()}</span>,
    },
    // ARTICULO
    {
      id: 'articulo',
      header: 'ARTICULO',
      accessorKey: 'articulo',
      size: 120,
      cell: EditableCell,
    },
    // DESCRIPTION
    {
      id: 'description',
      header: 'DESCRIPTION',
      accessorKey: 'description',
      size: 180,
      cell: EditableCell,
    },
    // QUANTITY - CAJAS
    {
      id: 'quantity_cajas',
      header: 'CAJAS',
      accessorKey: 'quantity_cajas',
      size: 70,
      cell: EditableNumberCell,
      meta: { group: 'QUANTITY' },
    },
    // QUANTITY - UND POR CAJA
    {
      id: 'quantity_und_por_caja',
      header: 'UND/CAJA',
      accessorKey: 'quantity_und_por_caja',
      size: 90,
      cell: EditableNumberCell,
      meta: { group: 'QUANTITY' },
    },
    // QUANTITY - TOTAL
    {
      id: 'quantity_total',
      header: 'TOTAL',
      accessorKey: 'quantity_total',
      size: 80,
      cell: EditableNumberCell,
      meta: { group: 'QUANTITY' },
    },
    // CBM - UNIT
    {
      id: 'cbm_unit',
      header: 'UNIT',
      accessorKey: 'cbm_unit',
      size: 70,
      cell: EditableNumberCell,
      meta: { group: 'CBM' },
    },
    // CBM - TOTAL
    {
      id: 'cbm_total',
      header: 'TOTAL',
      accessorKey: 'cbm_total',
      size: 70,
      cell: ({ getValue }) => (
        <span className="cell-number">{getValue()?.toFixed(2) ?? '—'}</span>
      ),
      meta: { group: 'CBM' },
    },
    // USD PRICE - UNIT
    {
      id: 'precio_unitario_usd',
      header: 'UNIT',
      accessorKey: 'precio_unitario_usd',
      size: 90,
      cell: ({ getValue, row, column, table }) => (
        <EditableNumberCell getValue={() => getValue()} row={row} column={column} table={table} />
      ),
      meta: { group: 'USD PRICE', format: 'currency' },
    },
    // USD PRICE - TOTAL
    {
      id: 'total_usd',
      header: 'TOTAL',
      accessorKey: 'total_usd',
      size: 110,
      cell: ({ getValue }) => (
        <span className="cell-currency cell-total">
          $ {(getValue() ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      ),
      meta: { group: 'USD PRICE' },
    },
  ], [onDeleteProduct]);

  const table = useReactTable({
    data: products,
    columns,
    getCoreRowModel: getCoreRowModel(),
    meta: {
      updateData: recalculate,
    },
  });

  const totalUSD = products.reduce((sum, p) => sum + (p.total_usd || 0), 0);
  const totalCBM = products.reduce((sum, p) => sum + (p.cbm_total || 0), 0);
  const totalQty = products.reduce((sum, p) => sum + (p.quantity_total || 0), 0);
  const totalCajas = products.reduce((sum, p) => sum + (p.quantity_cajas || 0), 0);

  const columnGroups = [
    { label: '', colSpan: 1 },    // actions
    { label: '', colSpan: 1 },    // PHOTO
    { label: '', colSpan: 1 },    // CODE
    { label: '', colSpan: 1 },    // ARTICULO
    { label: '', colSpan: 1 },    // DESCRIPTION
    { label: 'QUANTITY', colSpan: 3 },
    { label: 'CBM', colSpan: 2 },
    { label: 'USD PRICE', colSpan: 2 },
  ];

  return (
    <div className="table-container">
      <div className="table-scroll">
        <table className="emfox-table">
          <thead>
            <tr className="header-group-row">
              {columnGroups.map((group, i) => (
                <th
                  key={i}
                  colSpan={group.colSpan}
                  className={group.label ? 'header-group' : 'header-group-empty'}
                >
                  {group.label}
                </th>
              ))}
            </tr>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="header-columns-row">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} style={{ width: header.getSize() }} className="header-cell">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, rowIndex) => (
              <tr key={row.id} className={`data-row ${rowIndex % 2 === 0 ? 'row-even' : 'row-odd'}`}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="data-cell">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="totals-row">
              <td></td>
              <td colSpan={4} className="totals-label">TOTALES</td>
              <td className="totals-value">{totalCajas.toLocaleString()}</td>
              <td></td>
              <td className="totals-value">{totalQty.toLocaleString()}</td>
              <td></td>
              <td className="totals-value">{totalCBM.toFixed(2)} m³</td>
              <td></td>
              <td className="totals-value totals-currency">
                $ {totalUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="table-info-bar">
        <span>{products.length} producto(s)</span>
        <span>Tasa: 1 USD = {exchangeRate} CNY</span>
        <span>Total: $ {totalUSD.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
      </div>
    </div>
  );
}
