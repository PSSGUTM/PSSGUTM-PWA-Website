import { useEffect, useState } from "react";
import { api } from "./api.js";

// Senarai asal (dipaparkan walaupun server belum sedia). Server menentukan kolej mana ada perkhidmatan.
export const FALLBACK_COLLEGES = [
  { code: "KTDI", name: "Kolej Tun Dr. Ismail" },
  { code: "KTF", name: "Kolej Tun Fatimah" },
  { code: "KRP", name: "Kolej Rahman Putra" },
  { code: "KTR", name: "Kolej Tun Razak" },
  { code: "KTHO", name: "Kolej Tun Hussein Onn" },
  { code: "K9", name: "Kolej 9" },
  { code: "K10", name: "Kolej 10" },
  { code: "KP", name: "Kolej Perdana" },
  { code: "KTC", name: "Kolej Tuanku Canselor" },
  { code: "KDSE", name: "Kolej Datin Seri Endon" },
  { code: "KTGB", name: "Kolej Tun Ghafar Baba" },
  { code: "KLG", name: "KLG Residence" },
  { code: "KDOJ", name: "Kolej Dato' Onn Jaafar" },
];

export function useColleges() {
  const [state, setState] = useState({ colleges: FALLBACK_COLLEGES, loaded: false, error: false });
  useEffect(() => {
    api.publicGet("/colleges")
      .then((list) => setState({ colleges: list, loaded: true, error: false }))
      .catch(() => setState((s) => ({ ...s, error: true })));
  }, []);
  return state;
}
