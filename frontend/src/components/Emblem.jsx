// Logo lalai = gambar pesilat PSSGUTM (public/icon-512.png), dipakai bila admin belum upload logo
// atau bila logo upload tak dapat dimuat. Logo yang admin upload sentiasa diutamakan.
export default function Emblem({ size = 160 }) {
  return (
    <img src="/icon-512.png" alt="PSSGUTM" width={size} height={size}
      style={{ width: size, height: size, objectFit: "cover", borderRadius: "50%" }} />
  );
}

// Logo sentiasa dipaparkan bulat (dipotong kemas di tengah), bukan petak.
export function BrandMark({ brand, size = 120 }) {
  const box = { width: size, height: size };
  return (
    <span className="mark-round" style={box}>
      {brand?.has_logo
        ? <img src={brand.logo_url} alt="" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = "/icon-512.png"; }} />
        : <img src="/icon-512.png" alt="PSSGUTM" />}
    </span>
  );
}

// Ukiran di sekeliling logo: gelang sisik naga + awan larat + tumpal batik (corak asal, bukan lambang mana-mana pihak).
function Ring({ n, r0, r1, children }) {
  return Array.from({ length: n }, (_, i) => (
    <g key={i} transform={`rotate(${(360 / n) * i} 150 150)`}>{children}</g>
  ));
}

export function OrnateMark({ brand, size = 170 }) {
  const full = size + 96;
  return (
    <div className="orn" style={{ width: full, height: full }}>
      <svg className="orn-svg" viewBox="0 0 300 300" aria-hidden="true">
        <g className="orn-outer">
          <circle cx="150" cy="150" r="146" className="o-line" />
          <Ring n={32}>
            <path d="M150 4 L143 22 Q150 28 157 22 Z" className="o-fill" />
          </Ring>
          <circle cx="150" cy="150" r="124" className="o-line thin" />
        </g>
        <g className="orn-inner">
          <Ring n={16}>
            <path d="M150 34 q14 -10 24 2 q-8 14 -22 8 q6 -4 4 -8 q-4 -3 -6 -2 z" className="o-fill soft" />
          </Ring>
          <Ring n={48}>
            <circle cx="150" cy="30" r="1.8" className="o-fill" />
          </Ring>
        </g>
        <circle cx="150" cy="150" r="104" className="o-line" />
      </svg>
      <span className="orn-logo" style={{ width: size, height: size }}>
        {brand?.has_logo
          ? <img src={brand.logo_url} alt="" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = "/icon-512.png"; }} />
          : <img src="/icon-512.png" alt="PSSGUTM" />}
      </span>
    </div>
  );
}
