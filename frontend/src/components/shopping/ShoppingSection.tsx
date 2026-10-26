import { LoaderCircle, PackageCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatEuro, formatQuantity } from '@/lib/labels';
import type { ShoppingItem, ShoppingSection as ShoppingSectionType } from '@/lib/menu';

type ShoppingSectionProps = {
  section: ShoppingSectionType;
  pendingItemId: number | null;
  onToggleChecked: (item: ShoppingItem, checked: boolean) => void;
  onAlreadyHave: (item: ShoppingItem) => void;
};

/** Sección de la lista de la compra con sus líneas y acciones. */
export function ShoppingSection({
  section,
  pendingItemId,
  onToggleChecked,
  onAlreadyHave,
}: ShoppingSectionProps) {
  return (
    <Card className="print:break-inside-avoid">
      <CardHeader>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle>
            <h2 className="text-base font-semibold">{section.section_name}</h2>
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Subtotal:{' '}
            <span className="font-medium text-foreground">
              {formatEuro(section.subtotal_cents)}
            </span>
          </p>
        </div>
      </CardHeader>
      <CardContent>
        {section.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay productos en esta sección.</p>
        ) : (
          <ul className="space-y-2">
            {section.items.map((item) => {
              const isPending = pendingItemId === item.id;
              return (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center gap-3 rounded-md border p-3"
                  aria-busy={isPending}
                >
                  <input
                    id={`shopping-item-${item.id}`}
                    type="checkbox"
                    className="size-4 shrink-0 rounded border-input"
                    checked={item.checked}
                    disabled={isPending}
                    aria-label={`Marcar ${item.product_name} como comprado`}
                    onChange={(event) => onToggleChecked(item, event.target.checked)}
                  />
                  <label htmlFor={`shopping-item-${item.id}`} className="min-w-0 flex-1">
                    <span className="block font-medium">
                      {item.product_name}
                      {item.brand ? (
                        <span className="font-normal text-muted-foreground"> · {item.brand}</span>
                      ) : null}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {item.packages} {item.packages === 1 ? 'paquete' : 'paquetes'} ×{' '}
                      {formatQuantity(item.package_quantity_milli, item.package_unit)} ·{' '}
                      {formatEuro(item.package_price_cents)} por paquete · {item.ingredient_name}
                    </span>
                  </label>
                  <span className="font-semibold">{formatEuro(item.subtotal_cents)}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isPending}
                    aria-label={`Ya lo tengo: ${item.product_name}`}
                    onClick={() => onAlreadyHave(item)}
                    className="print:hidden"
                  >
                    {isPending ? (
                      <LoaderCircle aria-hidden="true" className="animate-spin" />
                    ) : (
                      <PackageCheck aria-hidden="true" />
                    )}
                    Ya lo tengo
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
