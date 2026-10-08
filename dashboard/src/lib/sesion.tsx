import { createContext, useContext } from 'react';
import { ROLES, type Rol, type SesionAbierta } from './api';

/** Lo que el panel sabe de quién está adentro, y lo que puede hacer con eso. */
export interface SesionDelPanel extends SesionAbierta {
  puede: (minimo: Rol) => boolean;
  salir: () => void;
}

export const ContextoDeSesion = createContext<SesionDelPanel | null>(null);

export function useSesion(): SesionDelPanel {
  const sesion = useContext(ContextoDeSesion);
  if (!sesion) throw new Error('useSesion va adentro del panel con una sesión abierta');
  return sesion;
}

// Los roles van en escalera, igual que en la API: cada uno puede lo del anterior. El panel solo
// oculta lo que el rol no puede hacer; quien decide es la API, que lo rechaza igual.
export const alcanza = (rol: Rol, minimo: Rol) => ROLES.indexOf(rol) >= ROLES.indexOf(minimo);
