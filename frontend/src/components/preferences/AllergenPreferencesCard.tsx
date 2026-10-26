import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, LoaderCircle, MilkOff } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  DomainRequestError,
  fetchAllergens,
  fetchProfile,
  updateProfile,
  type Profile,
} from '@/lib/domain';

/** Alérgenos declarados por el usuario, con filtrado fail-closed. */
export function AllergenPreferencesCard() {
  const queryClient = useQueryClient();
  const allergensQuery = useQuery({ queryKey: ['allergens'], queryFn: fetchAllergens });
  const profileQuery = useQuery({ queryKey: ['profile'], queryFn: fetchProfile });
  const mutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (profile: Profile) => {
      queryClient.setQueryData(['profile'], profile);
      void queryClient.invalidateQueries({ queryKey: ['dishes'] });
    },
  });

  const profile = profileQuery.data;
  const declared = new Set(profile?.allergen_codes ?? []);
  const selectable = (allergensQuery.data ?? []).filter((allergen) => allergen.code !== 'unknown');
  const error =
    mutation.error instanceof DomainRequestError
      ? mutation.error.message
      : mutation.error
        ? 'No se pudieron guardar los alérgenos.'
        : null;

  const toggle = (code: string) => {
    if (!profile) {
      return;
    }
    const next = new Set(declared);
    if (next.has(code)) {
      next.delete(code);
    } else {
      next.add(code);
    }
    mutation.mutate({
      people: profile.people,
      days: profile.days,
      budget_cents: profile.budget_cents,
      allergen_codes: [...next],
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MilkOff aria-hidden="true" className="size-5 text-primary" />
          Alérgenos declarados
        </CardTitle>
        <CardDescription>
          Filtrado estricto: un producto con alérgenos sin confirmar no se usa si declaras algún
          alérgeno. Nunca se relajan alérgenos para ajustar el presupuesto.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {allergensQuery.isPending || profileQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Cargando alérgenos…
          </p>
        ) : null}
        {allergensQuery.isError || profileQuery.isError ? (
          <p role="alert" className="text-sm text-destructive">
            No se pudieron cargar los alérgenos o el perfil.
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          {selectable.map((allergen) => (
            <label
              key={allergen.code}
              className="flex items-center gap-2 rounded-md border p-2 text-sm"
            >
              <input
                id={`allergen-${allergen.code}`}
                type="checkbox"
                className="size-4 rounded border-input"
                checked={declared.has(allergen.code)}
                disabled={!profile || mutation.isPending}
                onChange={() => toggle(allergen.code)}
              />
              {allergen.name}
            </label>
          ))}
        </div>

        {declared.size > 0 ? (
          <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900">
            <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <p>
              Declarados {declared.size} alérgenos. Los platos que no tengan productos confirmados
              quedarán fuera del catálogo visible.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No has declarado alérgenos. Se pueden usar productos con información parcial.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
