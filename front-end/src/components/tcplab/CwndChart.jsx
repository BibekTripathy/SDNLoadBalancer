import React from 'react';
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { ALGORITHM_COLORS, ALGORITHM_LABELS, AXIS } from './tcpLabStyle';

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend);

// Point shapes for the sender's reaction to a loss (shape + colour, never colour alone)
const LOSS_MARKERS = {
  FAST_RETRANSMIT: { pointStyle: 'triangle', label: 'fast retransmit' },
  TIMEOUT: { pointStyle: 'crossRot', label: 'timeout' },
};

/**
 * cwnd (solid) and ssthresh (dashed) against time, one colour per algorithm.
 * series:  { algorithm: { cwnd: [{x, y}], ssthresh: [{x, y}] } }   (one flow)
 * losses:  [{ algorithm, time, event, cwnd }]                       (same flow)
 * Both axes are in segments / seconds, so cwnd and ssthresh share ONE y axis.
 */
export default function CwndChart({ series, losses, duration, height = 340 }) {
  const datasets = [];
  for (const algorithm of Object.keys(series)) {
    const color = ALGORITHM_COLORS[algorithm];
    datasets.push({
      label: `${ALGORITHM_LABELS[algorithm]} cwnd`,
      data: series[algorithm].cwnd,
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2,
      pointRadius: 0,
      stepped: 'before',
    });
    if (series[algorithm].ssthresh.length > 0) {
      datasets.push({
        label: `${ALGORITHM_LABELS[algorithm]} ssthresh`,
        data: series[algorithm].ssthresh,
        borderColor: color,
        backgroundColor: color,
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        stepped: 'before',
      });
    }
  }
  for (const event of Object.keys(LOSS_MARKERS)) {
    for (const algorithm of Object.keys(series)) {
      const points = losses
        .filter((loss) => loss.algorithm === algorithm && loss.event === event)
        .map((loss) => ({ x: loss.time, y: loss.cwnd }));
      if (points.length === 0) continue;
      // A cross is drawn with its border only, so it needs the algorithm colour there;
      // a triangle is filled, with a thin dark ring so it stands out from the line.
      const isCross = LOSS_MARKERS[event].pointStyle === 'crossRot';
      datasets.push({
        label: `${ALGORITHM_LABELS[algorithm]} ${LOSS_MARKERS[event].label}`,
        data: points,
        showLine: false,
        borderColor: isCross ? ALGORITHM_COLORS[algorithm] : '#0B0F19',
        borderWidth: isCross ? 3 : 1.5,
        backgroundColor: ALGORITHM_COLORS[algorithm],
        pointStyle: LOSS_MARKERS[event].pointStyle,
        pointRadius: 6,
        pointHoverRadius: 8,
      });
    }
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,          // the data changes many times a second while streaming
    parsing: false,
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: { color: '#94A3B8', font: { family: 'monospace', size: 11 }, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          title: (items) => (items.length ? `t = ${items[0].parsed.x.toFixed(2)} s` : ''),
          label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(1)} segments`,
        },
      },
    },
    scales: {
      x: {
        ...AXIS,
        type: 'linear',
        min: 0,
        max: duration || undefined,
        title: { display: true, text: 'time (s)', color: '#94A3B8' },
      },
      y: {
        ...AXIS,
        beginAtZero: true,
        title: { display: true, text: 'segments', color: '#94A3B8' },
      },
    },
  };

  return (
    <div style={{ height }}>
      <Line data={{ datasets }} options={options} />
    </div>
  );
}
