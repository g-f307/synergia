import { Routes } from '@angular/router';

import { adminGuard, authenticatedGuard, permissionGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/login.component').then((value) => value.LoginComponent)
  },
  {
    path: 'dashboard/related/:entity',
    canActivate: [authenticatedGuard, permissionGuard('dashboard.read')],
    loadComponent: () => import('./domains/dashboard/dashboard-related.component').then((value) => value.DashboardRelatedComponent)
  },
  {
    path: 'dashboard',
    canActivate: [authenticatedGuard, permissionGuard('dashboard.read')],
    loadComponent: () => import('./domains/dashboard/dashboard.component').then((value) => value.DashboardComponent)
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
  {
    path: 'executions',
    canActivate: [authenticatedGuard, permissionGuard('execution.read')],
    loadComponent: () => import('./domains/executions/execution-search.component').then((value) => value.ExecutionSearchComponent)
  },
  {
    path: 'executions/:executionId',
    canActivate: [authenticatedGuard, permissionGuard('execution.read')],
    loadComponent: () => import('./domains/executions/execution-detail.component').then((value) => value.ExecutionDetailComponent)
  },
  {
    path: 'search',
    canActivate: [authenticatedGuard, permissionGuard('business.read')],
    loadComponent: () => import('./domains/queries/operational-search.component').then((value) => value.OperationalSearchComponent)
  },
  {
    path: 'workorders/:workorderNumber',
    canActivate: [authenticatedGuard, permissionGuard('business.read')],
    loadComponent: () => import('./domains/queries/workorder-detail.component').then((value) => value.WorkorderDetailComponent)
  },
  {
    path: 'lots/:lotNumber',
    data: { entityType: 'lot' },
    canActivate: [authenticatedGuard, permissionGuard('business.read')],
    loadComponent: () => import('./domains/queries/entity-detail.component').then((value) => value.EntityDetailComponent)
  },
  {
    path: 'serials/:serialNumber',
    data: { entityType: 'serial' },
    canActivate: [authenticatedGuard, permissionGuard('business.read')],
    loadComponent: () => import('./domains/queries/entity-detail.component').then((value) => value.EntityDetailComponent)
  },
  {
    path: 'pending-items/:pendingId',
    canActivate: [authenticatedGuard, permissionGuard('pending.read')],
    loadComponent: () => import('./domains/queries/related-pending-detail.component').then((value) => value.RelatedPendingDetailComponent)
  },
  { path: '', pathMatch: 'full', redirectTo: 'profile' },
  { path: '**', redirectTo: 'profile' }
];
