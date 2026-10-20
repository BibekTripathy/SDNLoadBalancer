// Colours and labels for the TCP Lab page. One colour per algorithm, the same
// everywhere (the PNG plots use the light-background steps of the same hues).
// These are the dark-surface steps, validated against the old #0B0F19 page;
// not re-validated for the Catppuccin Latte base #eff1f5 (newreno/linux_reno sit near 3:1).
export const ALGORITHM_COLORS = {
  tahoe: '#3987e5',
  reno: '#d95926',
  newreno: '#199e70',
  linux_reno: '#9085e9',
};

export const ALGORITHM_LABELS = {
  tahoe: 'Tahoe',
  reno: 'Reno',
  newreno: 'New Reno',
  linux_reno: 'Linux reno (SACK off)',
};

export const SIM_ALGORITHMS = ['tahoe', 'reno', 'newreno'];

// Where a number comes from - shown next to every value on the page
export const SOURCE_STYLES = {
  simulator: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  mininet: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
  model: 'bg-slate-700/40 text-slate-300 border-slate-600',
};

export const AXIS = {
  ticks: { color: '#6c6f85', font: { family: 'monospace', size: 10 } },
  grid: { color: '#ccd0da' },
};

// "3.46 (median 3.46, 3.15-3.72, n=3)" - the same format as report.md.
// Only formatting: the statistics themselves come from the backend.
export function formatStats(stats, digits = 2) {
  if (!stats || stats.n === 0 || stats.mean === null) return '-';
  const fix = (value) => Number(value).toFixed(digits);
  if (stats.n === 1) return fix(stats.mean);
  return `${fix(stats.mean)} (median ${fix(stats.median)}, ${fix(stats.min)}-${fix(stats.max)}, n=${stats.n})`;
}
