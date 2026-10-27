import type { CSSProperties } from 'react';

export type IconName = 'chat' | 'flask' | 'chart' | 'plus' | 'history' | 'chevron' | 'arrow' | 'send' | 'stop' | 'paperclip' | 'shield' | 'check' | 'close' | 'search' | 'file' | 'bell' | 'download' | 'lock' | 'external' | 'info' | 'menu' | 'refresh' | 'settings' | 'clock' | 'source';
const paths: Record<IconName, string[]> = {
  chat: ['M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5 8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z'],
  flask: ['M9 3h6M10 3v7l-5.7 9.1A1.3 1.3 0 0 0 5.4 21h13.2a1.3 1.3 0 0 0 1.1-1.9L14 10V3', 'M8 14h8'],
  chart: ['M4 3v17h17', 'M8 15v-4M13 15V7M18 15V4'],
  plus: ['M12 5v14M5 12h14'], history: ['M3 11a9 9 0 1 1 2 6', 'M3 4v7h7M12 7v5l3 2'],
  chevron: ['m9 5 7 7-7 7'], arrow: ['M5 19 19 5M5 5h14v14'],
  send: ['M12 19V5m-6 6 6-6 6 6'], stop: ['M6 6h12v12H6z'],
  paperclip: ['m8 12 6.5-6.5a3.5 3.5 0 0 1 5 5L10 20a5 5 0 0 1-7-7l10-10a2.5 2.5 0 0 1 3.5 3.5L7 16'],
  shield: ['m12 3 8 3v6c0 4.5-8 9-8 9S4 16.5 4 12V6l8-3Z', 'm9 12 2 2 4-4'],
  check: ['m5 12 4 4L19 6'], close: ['m6 6 12 12M18 6 6 18'],
  search: ['M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15ZM16 16l5 5'],
  file: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z', 'M14 2v6h6M8 13h8M8 17h5'],
  bell: ['M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4'],
  download: ['M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4'],
  lock: ['M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4M12 14v3'],
  external: ['M14 3h7v7M10 14 21 3M10 3H4v17h17v-6'],
  info: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 11v6M12 7h.01'],
  menu: ['M4 6h16M4 12h16M4 18h16'], refresh: ['M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13.6 2M18 18A8 8 0 0 1 4.4 16'],
  settings: ['M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M9 15v6'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 6v6l4 2'],
  source: ['M4 3h5v5H4zM15 16h5v5h-5zM4 16h5v5H4zM6.5 8v8M9 5.5h8.5V16'],
};

export function Icon({ name, size = 20, style, className = '' }: { name: IconName; size?: number; style?: CSSProperties; className?: string }) {
  return <svg aria-hidden="true" className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" style={style}>{paths[name].map((d, index) => <path key={index} d={d} />)}</svg>;
}
