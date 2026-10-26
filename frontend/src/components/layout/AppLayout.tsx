import { CalendarDays, History, Settings, UtensilsCrossed } from 'lucide-react';
import { NavLink, Outlet } from 'react-router';

import { BackendStatus } from '@/components/layout/BackendStatus';
import { cn } from '@/lib/utils';

const navigation = [
  { to: '/', label: 'Menú', icon: CalendarDays, end: true },
  { to: '/history', label: 'Historial', icon: History, end: false },
  { to: '/dishes', label: 'Platos', icon: UtensilsCrossed, end: false },
  { to: '/settings', label: 'Ajustes', icon: Settings, end: false },
];

export function AppLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <a
        href="#contenido"
        className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
      >
        Saltar al contenido
      </a>
      <header className="border-b bg-card print:hidden">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">Cesta</p>
            <p className="text-lg font-semibold">Menús de comida y cena</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <BackendStatus />
            <nav aria-label="Navegación principal">
              <ul className="flex flex-wrap gap-1">
                {navigation.map(({ to, label, icon: Icon, end }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={end}
                      className={({ isActive }) =>
                        cn(
                          'inline-flex min-h-10 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                        )
                      }
                    >
                      <Icon aria-hidden="true" className="size-4" />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </div>
      </header>

      <main id="contenido" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t px-4 py-4 text-center text-xs text-muted-foreground print:hidden">
        <p>
          Solo comida y cena, sin recetas ni pasos de cocina. Precios de la tienda online de
          Mercadona (CP 22002). Cesta no está afiliada a Mercadona. Confirma siempre el etiquetado y
          los alérgenos en el envase.
        </p>
      </footer>
    </div>
  );
}
