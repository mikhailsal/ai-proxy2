interface AppIconProps {
  size?: number;
}

export function AppIcon({ size = 20 }: AppIconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }}
    >
      <rect width="32" height="32" rx="6" fill="#0d1117" />
      <rect width="32" height="32" rx="6" fill="none" stroke="#30363d" strokeWidth="1" />
      <circle cx="6" cy="10" r="2" fill="#58a6ff" opacity="0.7" />
      <circle cx="6" cy="16" r="2" fill="#58a6ff" opacity="0.8" />
      <circle cx="6" cy="22" r="2" fill="#58a6ff" opacity="0.7" />
      <line x1="8" y1="10" x2="13" y2="14.5" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      <line x1="8" y1="16" x2="13" y2="16" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" />
      <line x1="8" y1="22" x2="13" y2="17.5" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      <polygon points="16,10 21,16 16,22 11,16" fill="#1f6feb" stroke="#58a6ff" strokeWidth="1.2" />
      <circle cx="16" cy="16" r="2.5" fill="#58a6ff" />
      <circle cx="16" cy="16" r="1" fill="#e6edf3" />
      <line x1="19" y1="14.5" x2="24" y2="10" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      <line x1="19" y1="16" x2="24" y2="16" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" />
      <line x1="19" y1="17.5" x2="24" y2="22" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
      <polygon points="24,8.5 24,11.5 27,10" fill="#58a6ff" opacity="0.7" />
      <polygon points="24,14.5 24,17.5 27,16" fill="#58a6ff" opacity="0.8" />
      <polygon points="24,20.5 24,23.5 27,22" fill="#58a6ff" opacity="0.7" />
    </svg>
  );
}
