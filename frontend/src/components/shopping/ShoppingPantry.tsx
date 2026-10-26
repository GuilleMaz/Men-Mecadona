import { PackageOpen } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatQuantity } from '@/lib/labels';
import type { ShoppingPantryItem } from '@/lib/menu';

/** Despensa congelada en el menú, sin tocar la despensa global del perfil. */
export function ShoppingPantry({ items }: { items: ShoppingPantryItem[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <PackageOpen aria-hidden="true" className="size-5 text-primary" />
          <h2 className="text-base font-semibold">Despensa de este menú</h2>
        </CardTitle>
        <CardDescription>
          Ingredientes que ya tenías al generar el menú. «Ya lo tengo» añade aquí, no a tu despensa
          global.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Este menú no usa despensa.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {items.map((item) => (
              <li
                key={item.ingredient_id}
                className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border p-2"
              >
                <span>{item.ingredient_name}</span>
                <span className="text-muted-foreground">
                  {formatQuantity(item.quantity_milli, item.base_unit)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
