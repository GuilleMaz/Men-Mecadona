import { Route, Routes } from 'react-router';

import { AppLayout } from '@/components/layout/AppLayout';
import { DishesPage } from '@/pages/DishesPage';
import { MenuDetailPage } from '@/pages/MenuDetailPage';
import { MenuPage } from '@/pages/MenuPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { ShoppingListPage } from '@/pages/ShoppingListPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<MenuPage />} />
        <Route path="menus/:id" element={<MenuDetailPage />} />
        <Route path="menus/:id/shopping-list" element={<ShoppingListPage />} />
        <Route path="dishes" element={<DishesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
