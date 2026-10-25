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
- Tailwind CSS 4 + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod y Lucide.

Calidad:

```powershell
npm run lint          # ESLint
npm run format:check  # Prettier
npm run test          # Vitest + Testing Library + MSW
npm run build         # tsc -b + vite build
```

No hay recetas ni pasos de cocina en ninguna pantalla.
