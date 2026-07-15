// "prmpt" wordmark + circled-R mark. viewBox 0 0 355 110, all white fill.
// Rendered as an SVG so it inherits the exclusion blend mode cleanly and scales
// crisply across the three responsive breakpoints.
export default function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 355 110"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="prmpt"
    >
      <text
        x="0"
        y="86"
        fill="#FFFFFF"
        style={{
          fontFamily: "'Inter Tight', sans-serif",
          fontWeight: 500,
          fontSize: '104px',
          letterSpacing: '-0.06em',
        }}
      >
        prmpt
      </text>
      {/* circled R mark, top-right */}
      <circle cx="337" cy="20" r="15.5" stroke="#FFFFFF" strokeWidth="2.5" />
      <text
        x="337"
        y="26"
        textAnchor="middle"
        fill="#FFFFFF"
        style={{
          fontFamily: "'Inter Tight', sans-serif",
          fontWeight: 500,
          fontSize: '17px',
          letterSpacing: '-0.04em',
        }}
      >
        R
      </text>
    </svg>
  )
}
