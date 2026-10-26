import { useQuery } from '@tanstack/react-query';
import { LoaderCircle, ShoppingBasket, Wallet } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchPricingPreview } from '@/lib/domain';
import { euroFormatter, formatQuantity } from '@/lib/labels';

function formatEuro(cents: number): string {
  return euroFormatter.format(cents / 100);
}

/**
 * Coste de consumo y ticket de compra de un plato para las personas del perfil.
 *
 * Usa el mismo plan de compra canónico que la lista de la compra de F4, así que
 * el ticket mostrado aquí coincide con el de un menú formado por este plato.
 */
export function DishCostCard({ dishId, people }: { dishId: number; people: number }) {
  const previewQuery = useQuery({
    queryKey: ['pricing-preview', dishId, people],
    queryFn: () => fetchPricingPreview({ people, dishes: [{ dish_id: dishId }] }),
  });
  const preview = previewQuery.data;
  const dish = preview?.dishes[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Wallet aria-hidden="true" className="size-5 text-primary" />
          Coste del plato
        </CardTitle>
        <CardDescription>
          Cálculo con los precios actuales para {people} {people === 1 ? 'persona' : 'personas'}. La
          despensa se descuenta antes de calcular los paquetes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {previewQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Calculando coste…
          </p>
        ) : null}
        {previewQuery.isError ? (
          <p role="alert" className="text-destructive">
            No se pudo calcular el coste. Revisa que todos los ingredientes tengan un producto
            disponible en el catálogo.
          </p>
        ) : null}

        {preview && dish ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Coste de consumo</p>
                <p className="text-lg font-semibold">{formatEuro(preview.consumption_cents)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatEuro(dish.per_serving_cents)} por ración
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Ticket de compra</p>
                <p className="text-lg font-semibold">{formatEuro(preview.ticket_cents)}</p>
                <p className="text-xs text-muted-foreground">Paquetes cerrados.</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Despensa y sobras</p>
                <p className="font-medium">
                  {formatEuro(preview.pantry_consumption_cents)} de despensa
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatEuro(preview.leftover_value_cents)} en sobras
                </p>
              </div>
            </div>

            <div>
              <p className="mb-2 flex items-center gap-2 font-medium">
                <ShoppingBasket aria-hidden="true" className="size-4 text-primary" />
                Compra estimada
              </p>
              {preview.ingredients.every((cost) => cost.products.length === 0) ? (
                <p className="text-muted-foreground">La despensa cubre todos los ingredientes.</p>
              ) : (
                <ul className="space-y-1">
                  {preview.ingredients.flatMap((cost) =>
                    cost.products.map((line) => (
                      <li
                        key={`${cost.ingredient.id}-${line.product_id}`}
                        className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border p-2"
                      >
                        <span>
                          {cost.ingredient.name}: {line.packages} × {line.name} (
                          {formatQuantity(line.package_quantity_milli, line.package_unit)})
                        </span>
                        <span className="font-medium">{formatEuro(line.subtotal_cents)}</span>
                      </li>
                    )),
                  )}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
