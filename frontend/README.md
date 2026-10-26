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
- `Menú` guarda personas, días y presupuesto en el perfil local.
- `Platos` busca y filtra el catálogo, muestra la composición y permite «no me gusta» por plato o ingrediente.
- `Ajustes` muestra el estado del catálogo y gestiona alérgenos, exclusiones y despensa.
- Tailwind CSS 4 + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod y Lucide.

Calidad:

```powershell
npm run lint          # ESLint
npm run format:check  # Prettier
npm run typecheck     # TypeScript
npm run test          # Vitest + Testing Library + MSW
npm run build         # tsc -b + vite build
```

Los tests usan MSW y handlers por defecto para `/api/health`, catálogo, perfil,
alérgenos, ingredientes, platos, exclusiones y despensa; no hay red real.

No hay recetas ni pasos de cocina en ninguna pantalla.
