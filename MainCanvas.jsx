import React, { useRef, useState, useCallback, useEffect } from 'react';
import { Stage, Layer, Rect, Line, Group, Text } from 'react-konva';
import useNestStore from '../../store/nestStore';
import useUiStore from '../../store/uiStore';
import api from '../../api/client';

const SHEET_COLOR = '#1E2A3A';
const GRID_COLOR = '#2A3A4E';
const BG_COLOR = '#0D1520';

const PART_COLORS = [
  '#3B82F6', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#14B8A6', '#F97316', '#6366F1', '#84CC16',
];

function MainCanvas() {
  const containerRef = useRef(null);
  const stageRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [stagePos, setStagePos] = useState({ x: 0, y: 0 });
  const { parts, placements, sheets } = useNestStore();
  const { zoom, setZoom } = useUiStore();
  const [hoveredPart, setHoveredPart] = useState(null);

  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({ width: rect.width, height: rect.height });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  const handleWheel = useCallback((e) => {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    const scaleBy = 1.05;
    const oldScale = zoom;
    const newScale = e.evt.deltaY < 0 ? oldScale * scaleBy : oldScale / scaleBy;
    const clampedScale = Math.max(0.1, Math.min(20, newScale));

    const pointer = stage.getPointerPosition();
    const mousePointTo = {
      x: (pointer.x - stagePos.x) / oldScale,
      y: (pointer.y - stagePos.y) / oldScale,
    };
    const newPos = {
      x: pointer.x - mousePointTo.x * clampedScale,
      y: pointer.y - mousePointTo.y * clampedScale,
    };
    setZoom(clampedScale);
    setStagePos(newPos);
  }, [zoom, stagePos, setZoom]);

  const handleMouseDown = useCallback((e) => {
    if (e.evt.button === 0 || e.evt.button === 1) {
      setIsDragging(true);
      setDragStart({ x: e.evt.clientX, y: e.evt.clientY });
    }
  }, []);

  const handleMouseMove = useCallback((e) => {
    if (isDragging && dragStart) {
      const dx = e.evt.clientX - dragStart.x;
      const dy = e.evt.clientY - dragStart.y;
      setStagePos(prev => ({ x: prev.x + dx, y: prev.y + dy }));
      setDragStart({ x: e.evt.clientX, y: e.evt.clientY });
    }
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    setDragStart(null);
  }, []);

  const fitToScreen = useCallback(() => {
    setZoom(1.0);
    setStagePos({ x: 20, y: 20 });
  }, [setZoom]);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = e.dataTransfer.files;
    if (files.length === 0) return;
    const file = files[0];
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'svg' && ext !== 'dxf') return;
    try {
      const result = await api.importFile(file);
      useNestStore.getState().addParts(result.parts);
    } catch (err) {
      console.error('Import failed:', err.message || err);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  // Default sheet for display
  const sheet = sheets.length > 0 ? sheets[0] : { id: 'default', width: 1000, height: 500 };
  const sheetW = sheet.width * zoom;
  const sheetH = sheet.height * zoom;

  const hasContent = parts.length > 0 || placements.length > 0;

  return (
    <div
      ref={containerRef}
      className="flex-1 flex flex-col overflow-hidden relative"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      {/* Canvas controls */}
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button
          onClick={fitToScreen}
          className="px-2 py-1 text-xs bg-dn-surface border border-dn-border rounded text-dn-muted hover:text-dn-text transition-colors"
        >
          Fit
        </button>
        <button
          onClick={() => { setZoom(Math.min(20, zoom * 1.2)); }}
          className="px-2 py-1 text-xs bg-dn-surface border border-dn-border rounded text-dn-muted hover:text-dn-text"
        >
          +
        </button>
        <button
          onClick={() => { setZoom(Math.max(0.1, zoom / 1.2)); }}
          className="px-2 py-1 text-xs bg-dn-surface border border-dn-border rounded text-dn-muted hover:text-dn-text"
        >
          −
        </button>
        <span className="px-2 py-1 text-xs bg-dn-surface border border-dn-border rounded text-dn-muted">
          {Math.round(zoom * 100)}%
        </span>
      </div>

      {hasContent ? (
        <Stage
          ref={stageRef}
          width={dimensions.width}
          height={dimensions.height}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          scaleX={zoom}
          scaleY={zoom}
          x={stagePos.x}
          y={stagePos.y}
          style={{ background: BG_COLOR, cursor: isDragging ? 'grabbing' : 'default' }}
        >
          <Layer>
            {/* Sheet background */}
            <Rect
              x={0}
              y={0}
              width={sheet.width}
              height={sheet.height}
              fill={SHEET_COLOR}
              stroke="#3A4A5E"
              strokeWidth={0.5 / zoom}
            />
            {/* Sheet label */}
            <Text
              x={5}
              y={5}
              text={`${sheet.width}×${sheet.height} mm`}
              fontSize={12 / zoom}
              fill="#7A8A9E"
            />
            {/* Grid lines */}
            {Array.from({ length: Math.floor(sheet.width / 50) + 1 }, (_, i) => (
              <Line
                key={`vg${i}`}
                points={[i * 50, 0, i * 50, sheet.height]}
                stroke={GRID_COLOR}
                strokeWidth={0.2 / zoom}
              />
            ))}
            {Array.from({ length: Math.floor(sheet.height / 50) + 1 }, (_, i) => (
              <Line
                key={`hg${i}`}
                points={[0, i * 50, sheet.width, i * 50]}
                stroke={GRID_COLOR}
                strokeWidth={0.2 / zoom}
              />
            ))}
            {/* Render placed parts */}
            {placements.map((placement, idx) => {
              const part = parts.find(p => p.id === placement.part_id);
              if (!part) return null;
              // Normalize polygon to origin (subtract bbox min) so it renders at placement position
              const bbox = part.polygon.bbox;
              const normalized = part.polygon.outer.map(p => [p[0] - bbox.x_min, p[1] - bbox.y_min]);
              const flatPoints = normalized.flat();
              const color = PART_COLORS[idx % PART_COLORS.length];
              return (
                <Group
                  key={placement.part_id}
                  x={placement.x}
                  y={placement.y}
                  rotation={placement.rotation}
                  scaleX={placement.flipped ? -1 : 1}
                  onMouseEnter={() => setHoveredPart(part.id)}
                  onMouseLeave={() => setHoveredPart(null)}
                >
                  <Line
                    points={flatPoints}
                    fill={hoveredPart === part.id ? color + 'AA' : color + '66'}
                    stroke={color}
                    strokeWidth={0.3 / zoom}
                    closed
                  />
                  <Text
                    x={part.polygon.bbox.x_min}
                    y={(part.polygon.bbox.y_min + part.polygon.bbox.y_max) / 2}
                    text={part.name}
                    fontSize={8 / zoom}
                    fill="white"
                  />
                </Group>
              );
            })}
            {/* Render imported parts (not yet placed) — show in a row below sheet */}
            {parts.filter(p => !placements.some(pl => pl.part_id === p.id)).map((part, idx) => {
              const outer = part.polygon.outer;
              const bbox = part.polygon.bbox;
              // Normalize to origin so parts appear in grid regardless of original DXF coordinates
              const normalized = outer.map(p => [p[0] - bbox.x_min, p[1] - bbox.y_min]);
              const flatPoints = normalized.flat();
              const color = PART_COLORS[idx % PART_COLORS.length];
              const cellW = 100;
              const cellH = 80;
              const offsetX = 10 + (idx % 6) * cellW;
              const offsetY = sheet.height + 20 + Math.floor(idx / 6) * cellH;
              return (
                <Group key={part.id} x={offsetX} y={offsetY}>
                  <Line
                    points={flatPoints}
                    fill={color + '44'}
                    stroke={color}
                    strokeWidth={0.3 / zoom}
                    closed
                  />
                  <Text
                    x={0}
                    y={bbox.y_max - bbox.y_min + 2}
                    text={part.name.length > 12 ? part.name.slice(0, 12) + '…' : part.name}
                    fontSize={6 / zoom}
                    fill="#7A8A9E"
                  />
                </Group>
              );
            })}
          </Layer>
        </Stage>
      ) : (
        <div className="flex-1 bg-dn-bg flex items-center justify-center">
          <div className="text-center text-dn-muted">
            <svg className="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p className="text-lg font-medium">Drop SVG or DXF files here</p>
            <p className="text-sm mt-1">or use the Import button above</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default MainCanvas;
