/**
 * EMFOX OMS v2 - API Service Layer
 * Projects CRUD, Products CRUD, WebSocket, Export
 */
import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
});

// ============================================================
// PROJECTS
// ============================================================
export async function listProjects() {
  const response = await api.get('/projects');
  return response.data;
}

export async function createProject(data) {
  const response = await api.post('/projects', data);
  return response.data;
}

export async function getProject(projectId) {
  const response = await api.get(`/projects/${projectId}`);
  return response.data;
}

export async function updateProject(projectId, data) {
  const response = await api.put(`/projects/${projectId}`, data);
  return response.data;
}

export async function deleteProject(projectId) {
  const response = await api.delete(`/projects/${projectId}`);
  return response.data;
}

// ============================================================
// PRODUCTS
// ============================================================
export async function uploadAndProcess(files, projectId = null) {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const url = projectId ? `/projects/${projectId}/upload-and-process` : '/upload-and-process';
  const response = await api.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function updateProduct(projectId, productUid, product) {
  const response = await api.put(`/projects/${projectId}/products/${productUid}`, product);
  return response.data;
}

export async function deleteProduct(projectId, productUid) {
  const response = await api.delete(`/projects/${projectId}/products/${productUid}`);
  return response.data;
}

export async function clearAllProducts(projectId) {
  const response = await api.delete(`/projects/${projectId}/products`);
  return response.data;
}

export async function recalculateAll(projectId, newRate) {
  const response = await api.post(`/projects/${projectId}/recalculate-all`, {
    cny_to_usd_rate: newRate,
  });
  return response.data;
}

export async function recalculateProduct(product, rate = null) {
  const response = await api.post('/recalculate', { product, cny_to_usd_rate: rate });
  return response.data;
}

// ============================================================
// EXPORT
// ============================================================
export async function exportToExcel(exportData) {
  const response = await api.post('/export', exportData, { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
  link.setAttribute('download', `EMFOX_ListaProductos_${today}.xlsx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function exportToPdf(exportData) {
  const response = await api.post('/export-pdf', exportData, { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
  link.setAttribute('download', `EMFOX_ListaProductos_${today}.pdf`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function manualCrop(projectId, productUid, cropData) {
  const response = await api.post(
    `/projects/${projectId}/products/${productUid}/manual-crop`,
    cropData
  );
  return response.data;
}

// ============================================================
// CONFIG
// ============================================================
export async function getConfig() {
  const response = await api.get('/config');
  return response.data;
}

// ============================================================
// WEBSOCKET
// ============================================================
export function connectWebSocket(projectId, userName = 'Anónimo') {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.host}/api/ws/${projectId}?user=${encodeURIComponent(userName)}`;
  return new WebSocket(wsUrl);
}

export default api;
