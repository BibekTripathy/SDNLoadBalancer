import React from 'react';
import { SOURCE_STYLES } from './tcpLabStyle';

// Small label saying where numbers come from: simulator, mininet or model.
export default function SourceBadge({ source }) {
  const style = SOURCE_STYLES[source] || SOURCE_STYLES.model;
  return (
    <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase ${style}`}>
      {source}
    </span>
  );
}
