import { AlertTriangle, MilkOff, RefreshCw, Settings2, ShoppingBasket } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const sections = [
  {
    icon: Settings2,
    title: 'Exclusiones',
    description: 'Ingredientes, platos y etiquetas que no quieres ver en tus menús.',
  },
  {
    icon: AlertTriangle,
    title: 'Alérgenos',
    description: 'Alérgenos declarados con filtrado estricto y sin relajaciones.',
  },
  {
    icon: ShoppingBasket,
    title: 'Despensa',
    description: 'Cantidades que ya tienes en casa para descontarlas antes de comprar.',
  },
  {
    icon: RefreshCw,
    title: 'Sincronización',
    description: 'Estado del catálogo de Mercadona, última actualización y errores.',
  },
];

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Ajustes</h2>
        <p className="text-sm text-muted-foreground">
          Preferencias del perfil local: exclusiones, alérgenos y despensa.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {sections.map(({ icon: Icon, title, description }) => (
          <Card key={title}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Icon aria-hidden="true" className="size-5 text-primary" />
                {title}
              </CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Card>
        <CardContent className="flex items-start gap-3 text-sm text-muted-foreground">
          <MilkOff aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
          <p>
            Los alérgenos se filtran de forma estricta. La app no sustituye al etiquetado oficial
            del producto: confirma siempre los alérgenos en el envase.
          </p>
        </CardContent>
      </Card>

      <p className="text-sm text-muted-foreground">
        Estas opciones se activarán en la fase 2. El estado de sincronización llegará con el
        catálogo, en la fase 1.
      </p>
    </div>
  );
}
