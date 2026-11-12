import { createContext, useContext } from "react";
export const BrandCtx = createContext(null);
export const useBrand = () => useContext(BrandCtx);
