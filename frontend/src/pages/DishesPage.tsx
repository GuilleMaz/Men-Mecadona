import { UtensilsCrossed } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function DishesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Catálogo de platos</h2>
        <p className="text-sm text-muted-foreground">
          Platos con sus ingredientes, etiquetas y coste. Nunca instrucciones de elaboración.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UtensilsCrossed aria-hidden="true" className="size-5 text-primary" />
            Platos disponibles
          </CardTitle>
          <CardDescription>
            El catálogo se cargará desde el seed de platos y se validará contra el catálogo
            sincronizado de Mercadona.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Esta pantalla estará operativa en la fase 2, junto con las preferencias y las
            exclusiones.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
