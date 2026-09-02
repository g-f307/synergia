import { Routes } from '@angular/router';

import { adminGuard, authenticatedGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/login.component').then((value) => value.LoginComponent)
  },
  {
    path: 'profile',
    canActivate: [authenticatedGuard],
    loadComponent: () => import('./features/profile.component').then((value) => value.ProfileComponent)
  },
  {
    path: 'admin',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./features/admin.component').then((value) => value.AdminComponent)
  },
  { path: '', pathMatch: 'full', redirectTo: 'profile' },
  { path: '**', redirectTo: 'profile' }
];
