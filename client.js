const API_BASE = '/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

async function uploadFile(endpoint, file) {
  const url = `${API_BASE}${endpoint}`;
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — browser sets it automatically with multipart boundary
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Upload failed: ${response.status}`);
  }

  return response.json();
}

async function downloadFile(endpoint, filename) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }
  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = window.URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(link.href);
}

export const api = {
  health: () => fetch('/health').then((r) => r.json()),

  importFile: (file) => uploadFile('/files/import', file),

  startNest: (config) => request('/nest/start', { method: 'POST', body: JSON.stringify(config) }),
  cancelNest: (jobId) => request(`/nest/cancel/${jobId}`, { method: 'POST' }),

  exportGcode: (jobId, profile = 'cnc_router', kerf = 0) =>
    downloadFile(`/export/gcode/${jobId}?profile=${profile}&kerf=${kerf}`, `nest_${jobId}.nc`),
  exportDxf: (jobId) => downloadFile(`/export/dxf/${jobId}`, `nest_${jobId}.dxf`),
  exportSvg: (jobId) => downloadFile(`/export/svg/${jobId}`, `nest_${jobId}.svg`),
  exportPdf: (jobId) => downloadFile(`/export/pdf/${jobId}`, `nest_${jobId}.pdf`),

  saveProject: (data) => request('/projects/save', { method: 'POST', body: JSON.stringify(data) }),
  loadProject: (id) => request(`/projects/load/${id}`),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  listProjects: () => request('/projects/list'),

  listMaterials: () => request('/materials/list'),
  addMaterial: (data) => request('/materials/add', { method: 'POST', body: JSON.stringify(data) }),
};

export default api;
