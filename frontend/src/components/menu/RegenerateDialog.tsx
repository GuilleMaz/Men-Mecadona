import { AlertTriangle, LoaderCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { DomainRequestError } from '@/lib/domain';

type RegenerateDialogProps = {
  open: boolean;
  isPending: boolean;
  error: DomainRequestError | null;
  onClose: () => void;
  onConfirm: () => void;
};

/** Confirmación de regeneración del menú completo. */
export function RegenerateDialog({
  open,
  isPending,
  error,
  onClose,
  onConfirm,
}: RegenerateDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Regenerar el menú"
      description="Cesta buscará otra combinación de comidas y cenas dentro del mismo presupuesto y con tus preferencias actuales. Los platos bloqueados se mantienen."
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="button" onClick={onConfirm} disabled={isPending}>
            {isPending ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : null}
            {isPending ? 'Regenerando…' : 'Confirmar regeneración'}
          </Button>
        </>
      }
    >
      <p className="text-muted-foreground">
        El menú actual se sustituirá solo si la generación termina con una propuesta válida. Si no
        cabe en el presupuesto o se agota el tiempo, se conservará el menú que ya tienes.
      </p>

      {isPending ? (
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          Recalculando el menú…
        </p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p>{error.message}</p>
            {error.code === 'BUDGET_EXCEEDED' ? (
              <p className="text-xs">Se conserva el menú anterior.</p>
            ) : null}
            {error.code === 'SOLVER_TIMEOUT' ? (
              <p className="text-xs">
                No se ha guardado nada. Puedes reintentar con más tiempo o ajustar el presupuesto.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
