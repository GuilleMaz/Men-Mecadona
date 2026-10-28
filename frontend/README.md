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
- `Menú` guarda personas, días y presupuesto en el perfil local, genera el menú y muestra el modal de inviabilidad (mínimo, déficit y sugerencias) o el aviso de timeout.
- `/menus/:id` muestra la rejilla días × comida/cena con principal y acompañamiento opcional, el estado, la barra de presupuesto, CP/almacén/fecha y las acciones bloquear, cambiar, «no me gusta», añadir/quitar acompañamiento, revalidar y regenerar. Al abrir un menú actual se revalida una vez; el banner `stale` muestra el ticket anterior, el revalidado y el delta.
- `/menus/:id/shopping-list` agrupa la compra por secciones, permite marcar comprados y «ya lo tengo», y muestra el total sticky, sobras, coste por comida/día/persona y la identidad contable. Se imprime en A4 con el botón «Imprimir».
- `/history` lista los menús guardados con ticket, presupuesto, estado y enlaces al menú y a la lista.
- `Platos` busca y filtra el catálogo por momento y curso (`Principal`/`Acompañamiento`), muestra la composición, el coste de consumo/ticket del plato y permite «no me gusta» por plato o ingrediente.
- `Ajustes` muestra el estado del catálogo, el origen de precios y la copia local, y gestiona alérgenos, exclusiones y despensa.
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
alérgenos, ingredientes, platos, exclusiones, despensa, preview de coste y todos
los endpoints de menús y lista de la compra; no hay red real. Estado actual: 54
tests en 9 archivos.

Accesibilidad y entrega: enlace «Saltar al contenido», foco visible, diálogos con
trampa de foco y Escape, `aria-live` para estados, etiquetas en formularios,
navegación por teclado y hoja de impresión A4 (`@media print`) que oculta navegación,
acciones y total sticky. En producción local, FastAPI sirve `dist` y las rutas del
cliente caen en `index.html`.

No hay recetas ni pasos de cocina en ninguna pantalla.
