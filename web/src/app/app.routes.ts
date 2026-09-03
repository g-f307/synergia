import { Routes } from '@angular/router';

import { adminGuard, authenticatedGuard, permissionGuard } from './core/auth.guard';

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
  {
    path: 'imports/new',
    canActivate: [authenticatedGuard, permissionGuard('import.create')],
    loadComponent: () => import('./domains/imports/import-create.component').then((value) => value.ImportCreateComponent)
  },
  {
    path: 'imports/:executionId',
    canActivate: [authenticatedGuard, permissionGuard('import.read')],
    loadComponent: () => import('./domains/imports/import-detail.component').then((value) => value.ImportDetailComponent)
  },
  { path: '', pathMatch: 'full', redirectTo: 'profile' },
  { path: '**', redirectTo: 'profile' }
];
