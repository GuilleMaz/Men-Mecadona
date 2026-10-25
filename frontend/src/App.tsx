import { Route, Routes } from 'react-router';

import { AppLayout } from '@/components/layout/AppLayout';
import { DishesPage } from '@/pages/DishesPage';
import { MenuPage } from '@/pages/MenuPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { SettingsPage } from '@/pages/SettingsPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<MenuPage />} />
        <Route path="dishes" element={<DishesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
