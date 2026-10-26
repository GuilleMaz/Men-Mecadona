import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CircleCheck, LoaderCircle, UtensilsCrossed } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DomainRequestError,
  fetchProfile,
  updateProfile,
  type Profile,
  type ProfileUpdate,
} from '@/lib/domain';

const menuFormSchema = z.object({
  people: z
    .number({ error: 'Indica cuántas personas sois.' })
    .int({ error: 'Las personas deben ser un número entero.' })
    .min(1, { error: 'Debe haber al menos 1 persona.' })
    .max(10, { error: 'El máximo es 10 personas.' }),
  days: z
    .number({ error: 'Indica cuántos días quieres cubrir.' })
    .int({ error: 'Los días deben ser un número entero.' })
    .min(1, { error: 'El menú debe cubrir al menos 1 día.' })
    .max(14, { error: 'El máximo es 14 días.' }),
  budgetEuros: z
    .number({ error: 'Indica un presupuesto.' })
    .positive({ error: 'El presupuesto debe ser mayor que 0.' })
    .max(10_000, { error: 'El presupuesto máximo es 10.000 €.' }),
});

type MenuFormValues = z.infer<typeof menuFormSchema>;

const euro = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });

const defaultValues: MenuFormValues = {
  people: 2,
  days: 7,
  budgetEuros: 70,
};

function profileToValues(profile: Profile): MenuFormValues {
  return {
    people: profile.people,
    days: profile.days,
    budgetEuros: profile.budget_cents / 100,
  };
}

export function MenuPage() {
  const [summary, setSummary] = useState<string | null>(null);
  const profileQuery = useQuery({ queryKey: ['profile'], queryFn: fetchProfile });
  const mutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (profile) => {
      const values = profileToValues(profile);
      setSummary(
        `${values.people} personas · ${values.days} días · ${euro.format(values.budgetEuros)} de presupuesto`,
      );
    },
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<MenuFormValues>({
    defaultValues,
    resolver: zodResolver(menuFormSchema),
  });

  useEffect(() => {
    if (profileQuery.data && !isDirty) {
      reset(profileToValues(profileQuery.data));
    }
  }, [profileQuery.data, reset, isDirty]);

  const onSubmit = (values: MenuFormValues) => {
    const payload: ProfileUpdate = {
      people: values.people,
      days: values.days,
      budget_cents: Math.round(values.budgetEuros * 100),
    };
    mutation.mutate(payload);
  };

  const mutationError =
    mutation.error instanceof DomainRequestError
      ? mutation.error.message
      : mutation.error
        ? 'No se pudieron guardar los datos del menú.'
        : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Crea tu menú</h2>
        <p className="text-sm text-muted-foreground">
          Indica personas, días y presupuesto total. Cesta propondrá comidas y cenas que no superen
          ese límite.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Datos del menú</CardTitle>
          <CardDescription>
            Se guardan en tu perfil local. La generación del menú llegará en la siguiente fase.
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="people">Personas</Label>
              <Input
                id="people"
                type="number"
                inputMode="numeric"
                min={1}
                max={10}
                step={1}
                aria-invalid={Boolean(errors.people)}
                aria-describedby={errors.people ? 'people-error' : undefined}
                {...register('people', { valueAsNumber: true })}
              />
              {errors.people ? (
                <p id="people-error" className="text-sm text-destructive">
                  {errors.people.message}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">De 1 a 10 personas.</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="days">Días</Label>
              <Input
                id="days"
                type="number"
                inputMode="numeric"
                min={1}
                max={14}
                step={1}
                aria-invalid={Boolean(errors.days)}
                aria-describedby={errors.days ? 'days-error' : undefined}
                {...register('days', { valueAsNumber: true })}
              />
              {errors.days ? (
                <p id="days-error" className="text-sm text-destructive">
                  {errors.days.message}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">De 1 a 14 días.</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="budget">Presupuesto total (€)</Label>
              <Input
                id="budget"
                type="number"
                inputMode="decimal"
                min={0.01}
                step={0.01}
                aria-invalid={Boolean(errors.budgetEuros)}
                aria-describedby={errors.budgetEuros ? 'budget-error' : undefined}
                {...register('budgetEuros', { valueAsNumber: true })}
              />
              {errors.budgetEuros ? (
                <p id="budget-error" className="text-sm text-destructive">
                  {errors.budgetEuros.message}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Límite máximo del ticket.</p>
              )}
            </div>
          </CardContent>

          <CardFooter className="mt-6 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">
              Precios de la tienda online de Mercadona (CP 22002, almacén 4389).
            </p>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <LoaderCircle aria-hidden="true" className="animate-spin" />
              ) : (
                <UtensilsCrossed aria-hidden="true" />
              )}
              Generar menú
            </Button>
          </CardFooter>
        </form>
      </Card>

      {mutationError ? (
        <p role="alert" className="text-sm text-destructive">
          {mutationError}
        </p>
      ) : null}

      {summary ? (
        <div
          role="status"
          aria-label="Resumen del menú"
          className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm"
        >
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <p className="font-medium">Datos guardados</p>
            <p className="text-muted-foreground">
              {summary}. La generación del menú se activará en la siguiente fase.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
