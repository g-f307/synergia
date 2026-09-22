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
    path: 'admin/users/new',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-user-editor.component').then((value) => value.AdminUserEditorComponent)
  },
  {
    path: 'admin/users/:userId',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-user-editor.component').then((value) => value.AdminUserEditorComponent)
  },
  {
    path: 'admin/users',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-users.component').then((value) => value.AdminUsersComponent)
  },
  {
    path: 'admin/groups/new',
    data: { kind: 'groups' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-editor.component').then((value) => value.AdminAccessEditorComponent)
  },
  {
    path: 'admin/groups/:groupId',
    data: { kind: 'groups' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-editor.component').then((value) => value.AdminAccessEditorComponent)
  },
  {
    path: 'admin/groups',
    data: { kind: 'groups' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-list.component').then((value) => value.AdminAccessListComponent)
  },
  {
    path: 'admin/roles/new',
    data: { kind: 'roles' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-editor.component').then((value) => value.AdminAccessEditorComponent)
  },
  {
    path: 'admin/roles/:roleId',
    data: { kind: 'roles' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-editor.component').then((value) => value.AdminAccessEditorComponent)
  },
  {
    path: 'admin/roles',
    data: { kind: 'roles' },
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/admin/admin-access-list.component').then((value) => value.AdminAccessListComponent)
  },
  {
    path: 'admin/notification-templates/new',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/notification-admin/notification-template-editor.component').then((value) => value.NotificationTemplateEditorComponent)
  },
  {
    path: 'admin/notification-templates/:templateId',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/notification-admin/notification-template-editor.component').then((value) => value.NotificationTemplateEditorComponent)
  },
  {
    path: 'admin/notification-templates',
    canActivate: [authenticatedGuard, adminGuard],
    loadComponent: () => import('./domains/notification-admin/notification-template-list.component').then((value) => value.NotificationTemplateListComponent)
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
    path: 'pending-items',
    canActivate: [authenticatedGuard, permissionGuard('pending.read')],
    loadComponent: () => import('./domains/pending/pending-list.component').then((value) => value.PendingListComponent)
  },
  {
    path: 'pending-items/:pendingId',
    canActivate: [authenticatedGuard, permissionGuard('pending.read')],
    loadComponent: () => import('./domains/pending/pending-detail.component').then((value) => value.PendingDetailComponent)
  },
  {
    path: 'reports',
    canActivate: [authenticatedGuard, permissionGuard('report.read')],
    loadComponent: () => import('./domains/reports/report-catalog.component').then((value) => value.ReportCatalogComponent)
  },
  {
    path: 'reports/:reportId',
    canActivate: [authenticatedGuard, permissionGuard('report.read')],
    loadComponent: () => import('./domains/reports/report-detail.component').then((value) => value.ReportDetailComponent)
  },
  {
    path: 'notifications',
    canActivate: [authenticatedGuard, permissionGuard('notification.read')],
    loadComponent: () => import('./domains/notifications/notification-center.component').then((value) => value.NotificationCenterComponent)
  },
  { path: '', pathMatch: 'full', redirectTo: 'profile' },
  { path: '**', redirectTo: 'profile' }
];
