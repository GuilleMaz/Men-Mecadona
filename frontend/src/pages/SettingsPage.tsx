import { MilkOff } from 'lucide-react';

import { CatalogStatusCard } from '@/components/catalog/CatalogStatusCard';
import { AllergenPreferencesCard } from '@/components/preferences/AllergenPreferencesCard';
import { ExclusionsCard } from '@/components/preferences/ExclusionsCard';
import { PantryCard } from '@/components/preferences/PantryCard';
import { Card, CardContent } from '@/components/ui/card';

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Ajustes</h2>
        <p className="text-sm text-muted-foreground">
          Estado del catálogo, exclusiones, alérgenos y despensa del perfil local.
        </p>
      </div>

      <CatalogStatusCard />

      <AllergenPreferencesCard />

      <ExclusionsCard />

      <PantryCard />

      <Card>
        <CardContent className="flex items-start gap-3 text-sm text-muted-foreground">
          <MilkOff aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
          <p>
            Los alérgenos se filtran de forma estricta. La app no sustituye al etiquetado oficial
            del producto: confirma siempre los alérgenos en el envase.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
