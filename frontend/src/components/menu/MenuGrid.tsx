import { CalendarDays } from 'lucide-react';

import { MenuEntryCard } from '@/components/menu/MenuEntryCard';
import { Card, CardContent } from '@/components/ui/card';
import { mealLabel } from '@/lib/labels';
import type { MenuDetail, MenuEntry, MealSlot } from '@/lib/menu';

const SLOTS: MealSlot[] = ['lunch', 'dinner'];

type MenuGridProps = {
  menu: MenuDetail;
  isBusy: boolean;
  onToggleLock: (entry: MenuEntry) => void;
  onSwap: (entry: MenuEntry) => void;
  onExclude: (entry: MenuEntry) => void;
  onRegenerate: () => void;
  onAddComplement: (entry: MenuEntry) => void;
  onRemoveComplement: (entry: MenuEntry) => void;
};

/** Rejilla de días (0-based en la API) por comida y cena. */
export function MenuGrid({
  menu,
  isBusy,
  onToggleLock,
  onSwap,
  onExclude,
  onRegenerate,
  onAddComplement,
  onRemoveComplement,
}: MenuGridProps) {
  const days = Array.from({ length: menu.days }, (_, dayIndex) => dayIndex);

  return (
    <section aria-labelledby="menu-grid-heading" className="space-y-5">
      <div className="flex items-center gap-2">
        <CalendarDays aria-hidden="true" className="size-5 text-primary" />
        <h2 id="menu-grid-heading" className="text-lg font-semibold">
          Comidas y cenas
        </h2>
      </div>

      {days.map((dayIndex) => {
        const dayEntries = menu.entries.filter((entry) => entry.day_index === dayIndex);
        return (
          <div key={dayIndex} className="space-y-2">
            <h3 className="text-base font-semibold">Día {dayIndex + 1}</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {SLOTS.map((slot) => {
                const main = dayEntries.find(
                  (candidate) => candidate.slot === slot && candidate.course === 'main',
                );
                const complement = dayEntries.find(
                  (candidate) => candidate.slot === slot && candidate.course === 'complement',
                );
                if (!main) {
                  return (
                    <Card key={slot} className="h-full py-4">
                      <CardContent className="text-sm text-muted-foreground">
                        Sin {mealLabel(slot).toLowerCase()} registrada para este día.
                      </CardContent>
                    </Card>
                  );
                }
                return (
                  <div key={slot} className="space-y-2">
                    <MenuEntryCard
                      entry={main}
                      isBusy={isBusy}
                      hasComplement={complement !== undefined}
                      onToggleLock={() => onToggleLock(main)}
                      onSwap={() => onSwap(main)}
                      onExclude={() => onExclude(main)}
                      onRegenerate={onRegenerate}
                      onAddComplement={() => onAddComplement(main)}
                    />
                    {complement ? (
                      <MenuEntryCard
                        entry={complement}
                        isBusy={isBusy}
                        onToggleLock={() => onToggleLock(complement)}
                        onSwap={() => onSwap(complement)}
                        onExclude={() => onExclude(complement)}
                        onRegenerate={onRegenerate}
                        onRemoveComplement={() => onRemoveComplement(main)}
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
