# Frontend de Cesta

Interfaz local en React 19 + Vite + TypeScript. Textos en español; identificadores de
dominio en inglés.

```powershell
cd frontend
npm install
npm run dev
```

- App: `http://localhost:5173`.
- El servidor de Vite proxya `/api` a `http://127.0.0.1:8000` (backend).
- El layout consulta `/api/health` y muestra «API conectada» o «API no disponible».
- `Ajustes` muestra el estado del catálogo, su progreso y permite lanzar una sync.
- Tailwind CSS 4 + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod y Lucide.

Calidad:

```powershell
npm run lint          # ESLint
npm run format:check  # Prettier
npm run typecheck     # TypeScript
npm run test          # Vitest + Testing Library + MSW
npm run build         # tsc -b + vite build
```

Los tests usan MSW y handlers por defecto para `/api/health` y `/api/catalog/status`;
no hay red real.

No hay recetas ni pasos de cocina en ninguna pantalla.
