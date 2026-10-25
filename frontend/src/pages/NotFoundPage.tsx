import { Link } from 'react-router';

import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-semibold">Página no encontrada</h2>
      <p className="text-sm text-muted-foreground">La dirección que has abierto no existe.</p>
      <Button asChild>
        <Link to="/">Volver al menú</Link>
      </Button>
    </div>
  );
}
