import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Info, LoaderCircle, UtensilsCrossed } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { Link, useNavigate } from 'react-router';
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
import { Dialog } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DomainRequestError,
  fetchProfile,
  updateProfile,
  type Profile,
  type ProfileUpdate,
} from '@/lib/domain';
import { formatEuro } from '@/lib/labels';
import { generateMenu, type MenuGenerateResponse } from '@/lib/menu';

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

function budgetEquivalences(values: MenuFormValues) {
  const budgetCents = Math.round((values.budgetEuros || 0) * 100);
  const meals = Math.max(1, (values.days || 1) * 2);
  const people = Math.max(1, values.people || 1);
  return {
    perDay: Math.round(budgetCents / Math.max(1, values.days || 1)),
    perPersonDay: Math.round(budgetCents / (Math.max(1, values.days || 1) * people)),
    perMeal: Math.round(budgetCents / meals),
  };
}

type Notice = { kind: 'timeout'; message: string } | null;

export function MenuPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [infeasible, setInfeasible] = useState<MenuGenerateResponse | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const profileQuery = useQuery({ queryKey: ['profile'], queryFn: fetchProfile });

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    control,
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

  const people = useWatch({ control, name: 'people' });
  const days = useWatch({ control, name: 'days' });
  const budgetEuros = useWatch({ control, name: 'budgetEuros' });
  const equivalences = budgetEquivalences({ people, days, budgetEuros });

  const mutation = useMutation({
    mutationFn: async (values: MenuFormValues) => {
      const payload: ProfileUpdate = {
        people: values.people,
        days: values.days,
        budget_cents: Math.round(values.budgetEuros * 100),
      };
      await updateProfile(payload);
      return generateMenu({
        people: values.people,
        days: values.days,
        budget_cents: payload.budget_cents,
      });
    },
    onSuccess: async (generation) => {
      await queryClient.invalidateQueries({ queryKey: ['profile'] });
      if (generation.status === 'infeasible') {
        setInfeasible(generation);
        return;
      }
      if (generation.menu_id !== null) {
        navigate(`/menus/${generation.menu_id}`);
        return;
      }
      setNotice({
        kind: 'timeout',
        message:
          'El cálculo agotó el tiempo disponible y no se pudo guardar ningún menú. Puedes reintentarlo o ajustar el presupuesto.',
      });
    },
  });

  const onSubmit = (values: MenuFormValues) => {
    setInfeasible(null);
    setNotice(null);
    mutation.mutate(values);
  };

  const retry = () => {
    setInfeasible(null);
    setNotice(null);
    void handleSubmit(onSubmit)();
  };

  const generationError =
    mutation.error instanceof DomainRequestError
      ? mutation.error
      : mutation.error
        ? new DomainRequestError('No se pudo generar el menú. Inténtalo de nuevo.')
        : null;

  const isGenerating = mutation.isPending;

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
            Se guardan en tu perfil local. Después generamos el menú con tus alérgenos, exclusiones
            y despensa.
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit(onSubmit)} noValidate aria-busy={isGenerating}>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
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
            </div>

            <p className="rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              Equivale a {formatEuro(equivalences.perDay)} al día,{' '}
              {formatEuro(equivalences.perPersonDay)} por persona y día y{' '}
              {formatEuro(equivalences.perMeal)} por comida o cena.
            </p>
          </CardContent>

          <CardFooter className="mt-6 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">
              Precios de la tienda online de Mercadona (CP 22002, almacén 4389).
            </p>
            <Button type="submit" disabled={isGenerating}>
              {isGenerating ? (
                <LoaderCircle aria-hidden="true" className="animate-spin" />
              ) : (
                <UtensilsCrossed aria-hidden="true" />
              )}
              {isGenerating ? 'Generando menú…' : 'Generar menú'}
            </Button>
          </CardFooter>
        </form>
      </Card>

      <div aria-live="polite">
        {isGenerating ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Generando comidas y cenas dentro de tu presupuesto…
          </p>
        ) : null}
      </div>

      {generationError ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <div className="space-y-2">
            <p>{generationError.message}</p>
            {generationError.code === 'NO_ELIGIBLE_DISHES' ? (
              <p>
                Revisa tus alérgenos, exclusiones y la despensa en{' '}
                <Link to="/settings" className="underline underline-offset-4">
                  Ajustes
                </Link>
                .
              </p>
            ) : null}
            <Button type="button" variant="outline" size="sm" onClick={retry}>
              Reintentar
            </Button>
          </div>
        </div>
      ) : null}

      {notice ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-900"
        >
          <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <div className="space-y-2">
            <p className="font-medium">No se generó ningún menú</p>
            <p>{notice.message}</p>
            <Button type="button" variant="outline" size="sm" onClick={retry}>
              Reintentar
            </Button>
          </div>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Solo comidas y cenas, sin recetas ni pasos de cocina. Nunca se relajan alérgenos ni
        exclusiones para cuadrar el presupuesto.
      </p>

      <Dialog
        open={infeasible !== null}
        onClose={() => setInfeasible(null)}
        title="El menú no cabe en el presupuesto"
        description="No se ha guardado ningún menú ni se ha generado una lista de la compra oficial."
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setInfeasible(null)}>
              Cerrar
            </Button>
            {infeasible?.minimum_ticket_cents != null ? (
              <Button
                type="button"
                onClick={() => {
                  setValue('budgetEuros', (infeasible.minimum_ticket_cents ?? 0) / 100, {
                    shouldDirty: true,
                  });
                  setInfeasible(null);
                }}
              >
                Ajustar presupuesto al mínimo
              </Button>
            ) : null}
          </>
        }
      >
        {infeasible ? (
          <>
            <dl className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border p-3">
                <dt className="text-xs text-muted-foreground">
                  {infeasible.minimum_is_estimate ? 'Mínimo estimado' : 'Mínimo necesario'}
                </dt>
                <dd className="text-lg font-semibold">
                  {infeasible.minimum_ticket_cents != null
                    ? formatEuro(infeasible.minimum_ticket_cents)
                    : 'No disponible'}
                </dd>
              </div>
              <div className="rounded-md border p-3">
                <dt className="text-xs text-muted-foreground">Tu presupuesto</dt>
                <dd className="text-lg font-semibold">{formatEuro(infeasible.budget_cents)}</dd>
              </div>
              <div className="rounded-md border p-3">
                <dt className="text-xs text-muted-foreground">Déficit</dt>
                <dd className="text-lg font-semibold text-destructive">
                  {formatEuro(infeasible.shortfall_cents)}
                </dd>
              </div>
            </dl>

            {infeasible.minimum_is_estimate ? (
              <p className="text-muted-foreground">
                El mínimo es una estimación: los paquetes cerrados y la despensa pueden variar el
                importe final.
              </p>
            ) : null}

            <div className="space-y-2">
              <h3 className="font-medium">Sugerencias</h3>
              {infeasible.suggestions.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {infeasible.suggestions.map((suggestion) => (
                    <li key={suggestion}>{suggestion}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">
                  Aumenta el presupuesto o reduce los días o las personas.
                </p>
              )}
            </div>
          </>
        ) : null}
      </Dialog>
    </div>
  );
}
