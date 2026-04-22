import React from 'react';
import useNestStore from '../../store/nestStore';

function StatusBar() {
  const { isNesting, nestResult, parts, placements } = useNestStore();

  const status = isNesting ? 'Nesting...' : (nestResult ? 'Complete' : 'Ready');
  const statusColor = isNesting ? 'text-dn-accent' : (nestResult ? 'text-dn-success' : 'text-dn-muted');

  return (
    <div className="flex items-center h-7 px-4 bg-dn-surface border-t border-dn-border text-xs text-dn-muted">
      <span className={statusColor}>{status}</span>
      <span className="mx-3">|</span>
      <span>{parts.length} parts</span>
      {nestResult && (
        <>
          <span className="mx-3">|</span>
          <span>{placements.length} placed</span>
          <span className="mx-3">|</span>
          <span className="text-dn-success">{(nestResult.efficiency || 0).toFixed(1)}% efficiency</span>
          <span className="mx-2">·</span>
          <span>{(nestResult.waste_pct || 0).toFixed(1)}% waste</span>
        </>
      )}
      <span className="ml-auto">DropNest v1.0</span>
    </div>
  );
}

export default StatusBar;
