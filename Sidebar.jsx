import React, { useCallback } from 'react';
import useNestStore from '../../store/nestStore';
import api from '../../api/client';

const PART_COLORS = [
  '#3B82F6', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#14B8A6', '#F97316', '#6366F1', '#84CC16',
];

function Sidebar() {
  const { parts, sheets, nestConfig, removePart, updatePartQuantity, addSheet, setNestConfig } = useNestStore();

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

  const handleAddSheet = useCallback(() => {
    addSheet({
      id: `sheet_${Date.now()}`,
      width: 1000,
      height: 500,
      material: 'MDF',
      cost: 10.0,
      defect_zones: [],
    });
  }, [addSheet]);

  return (
    <div className="w-[280px] flex-shrink-0 bg-dn-surface border-r border-dn-border overflow-y-auto">
      {/* Parts section */}
      <div className="p-3 border-b border-dn-border">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-dn-muted uppercase tracking-wider">Parts</h3>
          <button
            onClick={handleImport}
            className="px-2 py-0.5 text-xs bg-dn-accent text-white rounded hover:bg-blue-600 transition-colors"
          >
            + Import
          </button>
        </div>
        {parts.length === 0 ? (
          <p className="text-sm text-dn-muted">No parts imported yet</p>
        ) : (
          <div className="space-y-1 max-h-[300px] overflow-y-auto">
            {parts.map((part, idx) => (
              <div key={part.id} className="flex items-center gap-2 p-1.5 rounded hover:bg-dn-border/30 group">
                <div
                  className="w-3 h-3 rounded-sm flex-shrink-0"
                  style={{ backgroundColor: PART_COLORS[idx % PART_COLORS.length] }}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-dn-text truncate">{part.name}</p>
                  <p className="text-[10px] text-dn-muted">{part.polygon.area.toFixed(1)} mm²</p>
                </div>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min="1"
                    max="999"
                    value={part.quantity}
                    onChange={(e) => updatePartQuantity(part.id, parseInt(e.target.value) || 1)}
                    className="w-10 text-xs text-center bg-dn-bg border border-dn-border rounded px-1 py-0.5 text-dn-text"
                  />
                  <button
                    onClick={() => removePart(part.id)}
                    className="text-dn-muted hover:text-dn-danger text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {parts.length > 0 && (
          <p className="text-[10px] text-dn-muted mt-2">
            {parts.length} part{parts.length !== 1 ? 's' : ''} · {parts.reduce((s, p) => s + p.quantity, 0)} total copies
          </p>
        )}
      </div>

      {/* Sheets section */}
      <div className="p-3 border-b border-dn-border">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-dn-muted uppercase tracking-wider">Sheets</h3>
          <button
            onClick={handleAddSheet}
            className="px-2 py-0.5 text-xs bg-dn-border text-dn-text rounded hover:bg-dn-muted/30 transition-colors"
          >
            + Add
          </button>
        </div>
        {sheets.length === 0 ? (
          <div className="text-sm text-dn-muted">
            <p>Default: 1000×500 mm</p>
          </div>
        ) : (
          <div className="space-y-1">
            {sheets.map((sheet) => (
              <div key={sheet.id} className="p-1.5 rounded hover:bg-dn-border/30">
                <p className="text-xs text-dn-text">{sheet.width}×{sheet.height} mm</p>
                <p className="text-[10px] text-dn-muted">{sheet.material || 'No material'} · ${sheet.cost}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Settings section */}
      <div className="p-3">
        <h3 className="text-xs font-semibold text-dn-muted uppercase tracking-wider mb-2">Settings</h3>
        <div className="space-y-2">
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Mode</label>
            <select
              value={nestConfig.mode}
              onChange={(e) => setNestConfig({ mode: e.target.value })}
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            >
              <option value="quality">Quality</option>
              <option value="balanced">Balanced</option>
              <option value="speed">Speed</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Rotation step</label>
            <select
              value={nestConfig.rotation_step}
              onChange={(e) => setNestConfig({ rotation_step: parseFloat(e.target.value) })}
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            >
              <option value="90">90°</option>
              <option value="45">45°</option>
              <option value="30">30°</option>
              <option value="15">15°</option>
              <option value="1">Free (1°)</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Sheet width (mm)</label>
            <input
              type="number"
              min="100"
              step="10"
              value={nestConfig.sheet_width}
              onChange={(e) => setNestConfig({ sheet_width: Math.max(100, Math.min(5000, parseFloat(e.target.value) || 1000)) })}
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            />
          </div>
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Sheet height (mm)</label>
            <input
              type="number"
              min="100"
              step="10"
              value={nestConfig.sheet_height}
              onChange={(e) => setNestConfig({ sheet_height: Math.max(100, Math.min(5000, parseFloat(e.target.value) || 500)) })
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            />
          </div>
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Spacing (mm)</label>
            <input
              type="number"
              min="0"
              step="0.5"
              value={nestConfig.spacing}
              onChange={(e) => setNestConfig({ spacing: parseFloat(e.target.value) || 0 })}
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            />
          </div>
          <div>
            <label className="text-[10px] text-dn-muted block mb-0.5">Kerf (mm)</label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={nestConfig.kerf}
              onChange={(e) => setNestConfig({ kerf: parseFloat(e.target.value) || 0 })}
              className="w-full text-xs bg-dn-bg border border-dn-border rounded px-2 py-1 text-dn-text"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;
