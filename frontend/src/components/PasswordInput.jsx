import { useState } from "react";

// Medan kata laluan dengan butang mata (tunjuk / sembunyi).
export default function PasswordInput({ value, onChange, placeholder, autoComplete = "current-password", minLength, required, onBlur }) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw">
      <input type={show ? "text" : "password"} value={value} onChange={onChange} onBlur={onBlur} placeholder={placeholder}
             autoComplete={autoComplete} minLength={minLength} required={required} />
      <button type="button" className="eye" aria-label={show ? "Sembunyikan kata laluan" : "Tunjuk kata laluan"} onClick={() => setShow(!show)}>
        {show ? (
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3l18 18M10.6 6.2A9.8 9.8 0 0 1 12 6c5 0 9 6 9 6a15.5 15.5 0 0 1-3.2 3.7M6.5 7.6C4.2 9.2 3 12 3 12s4 6 9 6a9 9 0 0 0 3.5-.7M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12s4-6 9-6 9 6 9 6-4 6-9 6-9-6-9-6z" /><circle cx="12" cy="12" r="3" /></svg>
        )}
      </button>
    </div>
  );
}
