import React, { useCallback, useState, useRef, useEffect } from 'react';
import useNestStore from '../../store/nestStore';
import api from '../../api/client';

function Toolbar() {
  const { parts, isNesting, jobId, nestResult, nestConfig } = useNestStore();
  const [showExport, setShowExport] = useState(false);
  const exportRef = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (exportRef.current && !exportRef.current.contains(e.target)) {
        setShowExport(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleImport = useCallback(async () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.svg,.dxf';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const result = await api.importFile(file);
        useNestStore.getState().addParts(result.parts);
      } catch (err) {
        console.error('Import failed:', err.message || err);
      }
    };
    input.click();
  }, []);

  const handleNest = useCallback(async () => {
    if (parts.length === 0) return;
    const store = useNestStore.getState();
    try {
      store.setIsNesting(true);
      const result = await api.startNest(store.nestConfig);
      store.setJobId(result.job_id);
      store.setPlacements(result.placements || []);
      store.setNestResult(result);
      store.setIsNesting(false);
    } catch (err) {
      console.error('Nest failed:', err);
      store.setIsNesting(false);
    }
  }, [parts]);

  const handleCancel = useCallback(async () => {
    if (!jobId) return;
    try {
      await api.cancelNest(jobId);
    } catch (err) {
      console.error('Cancel failed:', err);
    }
    useNestStore.getState().setIsNesting(false);
    useNestStore.getState().setJobId(null);
  }, [jobId]);

  const handleExport = useCallback((format) => {
    if (!jobId) return;
    const store = useNestStore.getState();
    const kerf = store.nestConfig.kerf;
    switch (format) {
      case 'gcode': api.exportGcode(jobId, 'cnc_router', kerf); break;
      case 'gcode_laser': api.exportGcode(jobId, 'laser', kerf); break;
      case 'gcode_plasma': api.exportGcode(jobId, 'plasma', kerf); break;
      case 'dxf': api.exportDxf(jobId); break;
      case 'svg': api.exportSvg(jobId); break;
      case 'pdf': api.exportPdf(jobId); break;
    }
    setShowExport(false);
  }, [jobId]);

  return (
    <div className="flex items-center h-12 px-4 bg-dn-surface border-b border-dn-border">
      <div className="flex items-center gap-2 mr-6">
        <span className="text-dn-accent font-bold text-lg">DropNest</span>
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={handleImport}
          className="px-3 py-1.5 text-sm bg-dn-accent text-white rounded hover:bg-blue-600 transition-colors"
        >
          Import
        </button>
        <button
          onClick={handleNest}
          disabled={parts.length === 0 || isNesting}
          className="px-3 py-1.5 text-sm bg-dn-success text-white rounded hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isNesting ? 'Nesting...' : 'Nest ▶'}
        </button>
        <button
          onClick={handleCancel}
          disabled={!isNesting}
          className="px-3 py-1.5 text-sm bg-dn-border text-dn-text rounded hover:bg-dn-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Stop
        </button>
        <div className="relative" ref={exportRef}>
          <button
            onClick={() => setShowExport(!showExport)}
            disabled={!nestResult}
            className="px-3 py-1.5 text-sm bg-dn-border text-dn-text rounded hover:bg-dn-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Export ▼
          </button>
          {showExport && (
            <div className="absolute top-full left-0 mt-1 w-48 bg-dn-surface border border-dn-border rounded shadow-lg z-50">
              <button onClick={() => handleExport('gcode')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">G-code (CNC Router)</button>
              <button onClick={() => handleExport('gcode_laser')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">G-code (Laser)</button>
              <button onClick={() => handleExport('gcode_plasma')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">G-code (Plasma)</button>
              <div className="border-t border-dn-border" />
              <button onClick={() => handleExport('dxf')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">DXF</button>
              <button onClick={() => handleExport('svg')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">SVG</button>
              <button onClick={() => handleExport('pdf')} className="w-full text-left px-3 py-2 text-sm text-dn-text hover:bg-dn-border">PDF</button>
            </div>
          )}
        </div>
      </div>
      <div className="ml-auto flex items-center gap-3 text-dn-muted text-sm">
        {parts.length > 0 && <span>{parts.length} parts</span>}
        {nestResult && (
          <>
            <span>|</span>
            <span className="text-dn-success">{(nestResult.efficiency || 0).toFixed(1)}% eff</span>
            <span>{(nestResult.waste_pct || 0).toFixed(1)}% waste</span>
          </>
        )}
      </div>
    </div>
  );
}

export default Toolbar;
