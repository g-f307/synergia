import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { NEVER, Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ImportCreateComponent } from './import-create.component';
import { UploadUpdate } from './import.models';
import { ImportService } from './import.service';

describe('ImportCreateComponent', () => {
  const upload = jasmine.createSpy('upload');
  const policy = jasmine.createSpy('policy');
  let permissionOrganizations: string[] | null;
  const session = { profile: () => ({ permissions: [{ key: 'import.create', organizations: permissionOrganizations }] }) };
  beforeEach(async () => {
    permissionOrganizations = ['org-1'];
    upload.calls.reset();
    upload.and.returnValue(NEVER);
    policy.calls.reset();
    policy.and.returnValue(of({
      policies: [
        { source: 'N-FP', allowed_extensions: ['csv', 'json', 'xlsx'], max_bytes: 25 * 1024 * 1024 },
        { source: 'OWM', allowed_extensions: ['csv', 'json', 'xlsx'], max_bytes: 25 * 1024 * 1024 },
        { source: 'GMES/OQC', allowed_extensions: ['csv', 'json', 'xlsx'], max_bytes: 25 * 1024 * 1024 },
        { source: 'TMS', allowed_extensions: ['csv', 'json', 'xlsx'], max_bytes: 25 * 1024 * 1024 }
      ],
      organizations: [{ id: 'org-1', organization_code: 'ORG-1', display_name: 'Organization 1' }]
    }));
    await TestBed.configureTestingModule({
      imports: [ImportCreateComponent],
      providers: [provideRouter([]), { provide: ImportService, useValue: { upload, policy } }, { provide: SessionService, useValue: session }]
    }).compileComponents();
  });

  it('validates empty, excessive and unsupported files before upload', () => {
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.file.set(new File([], 'empty.csv'));
    component.selectFile({ target: { files: [new File([], 'empty.csv')] } } as unknown as Event);
    expect(component.fileError()).toContain('vazio');
    component.selectFile({ target: { files: [new File(['x'], 'payload.exe')] } } as unknown as Event);
    expect(component.fileError()).toContain('CSV');
    const large = new File(['x'], 'large.csv');
    Object.defineProperty(large, 'size', { value: 26 * 1024 * 1024 });
    component.selectFile({ target: { files: [large] } } as unknown as Event);
    expect(component.fileError()).toContain('25 MiB');
    expect(upload).not.toHaveBeenCalled();
  });

  it('blocks double submission and displays upload progress', () => {
    const stream = new Subject<UploadUpdate>();
    upload.and.returnValue(stream);
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
    component.ngOnInit();
    component.file.set(new File(['id\n1'], 'safe.csv'));
    component.submit(new Event('submit'));
    component.submit(new Event('submit'));
    expect(upload).toHaveBeenCalledTimes(1);
    stream.next({ kind: 'progress', progress: 50 });
    expect(component.progress()).toBe(50);
    expect(component.state()).toBe('uploading');
  });

  it('infers and sends the only scoped organization without showing a selector', () => {
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const file = new File(['id\n1'], 'safe.csv');
    component.selectFile({ target: { files: [file] } } as unknown as Event);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#import-organization')).toBeNull();
    expect(component.organizationId()).toBe('org-1');
    component.submit(new Event('submit'));
    expect(upload).toHaveBeenCalledWith('N-FP', file, 'org-1');
  });

  it('requires an explicit organization and sends it for a global permission', () => {
    permissionOrganizations = null;
    policy.and.returnValue(of({
      policies: [{ source: 'N-FP', allowed_extensions: ['csv'], max_bytes: 4096 }],
      organizations: [
        { id: 'org-1', organization_code: 'ORG-1', display_name: 'Organization 1' },
        { id: 'org-2', organization_code: 'ORG-2', display_name: 'Organization 2' }
      ]
    }));
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const file = new File(['id\n1'], 'safe.csv');
    component.selectFile({ target: { files: [file] } } as unknown as Event);
    fixture.detectChanges();
    const selector = fixture.nativeElement.querySelector('#import-organization') as HTMLSelectElement;
    expect(selector).not.toBeNull();
    expect(component.canSubmit()).toBeFalse();
    selector.value = 'org-2';
    selector.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(component.canSubmit()).toBeTrue();
    component.submit(new Event('submit'));
    expect(upload).toHaveBeenCalledWith('N-FP', file, 'org-2');
  });

  it('preserves explicit selection for multiple organization scopes', () => {
    permissionOrganizations = ['org-1', 'org-2'];
    policy.and.returnValue(of({
      policies: [{ source: 'N-FP', allowed_extensions: ['csv'], max_bytes: 4096 }],
      organizations: [
        { id: 'org-1', organization_code: 'ORG-1', display_name: 'Organization 1' },
        { id: 'org-2', organization_code: 'ORG-2', display_name: 'Organization 2' }
      ]
    }));
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const file = new File(['id\n1'], 'safe.csv');
    component.selectFile({ target: { files: [file] } } as unknown as Event);
    expect(component.organizationSelectionRequired()).toBeTrue();
    expect(component.canSubmit()).toBeFalse();
    component.organizationId.set('org-1');
    component.submit(new Event('submit'));
    expect(upload).toHaveBeenCalledWith('N-FP', file, 'org-1');
  });

  it('redirects to the created import after acceptance', () => {
    const stream = new Subject<UploadUpdate>();
    upload.and.returnValue(stream);
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
    component.ngOnInit();
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    component.file.set(new File(['workorder\nWO-1'], 'plan-reference.csv'));
    component.submit(new Event('submit'));
    stream.next({ kind: 'complete', result: { execution_id: 'exec-58', status: 'completed', source: 'N-FP', file_name: 'plan-reference.csv', extension: 'csv', size_bytes: 20, started_at: '2026-09-02T12:00:00Z', finished_at: '2026-09-02T12:00:01Z', failure_reason: null, duplicate_of_execution_id: null } });
    expect(component.state()).toBe('accepted');
    expect(router.navigate).toHaveBeenCalledWith(['/imports', 'exec-58']);
  });

  it('keeps duplicate retries explicit and links to the original execution', () => {
    const failure: ApiFailure = { kind: 'conflict', status: 409, code: 'duplicate_file', message: 'safe', correlationId: 'corr-1', fields: [], details: { execution_id: 'new', duplicate_of_execution_id: 'original' } };
    upload.and.returnValue(throwError(() => failure));
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
    component.ngOnInit();
    component.file.set(new File(['id\n1'], 'safe.csv'));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('duplicate');
    expect(component.targetExecutionId()).toBe('original');
    expect(component.correlationId()).toBe('corr-1');
    expect(upload).toHaveBeenCalledTimes(1);
  });

  it('distinguishes a server rejection from authorization and network failures', () => {
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
    component.ngOnInit();
    component.file.set(new File(['not-json'], 'bad.json'));
    upload.and.returnValue(throwError(() => ({ kind: 'validation', status: 422, code: 'corrupted_file', message: 'safe', correlationId: null, fields: [], details: { execution_id: 'rejected' } } as ApiFailure)));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('rejected');
    expect(component.targetExecutionId()).toBe('rejected');
    expect(component.rejectionReason()).toContain('corrompido');

    upload.and.returnValue(throwError(() => ({ kind: 'validation', status: 415, code: 'content_type_mismatch', message: 'safe', correlationId: null, fields: [], details: { execution_id: 'mime-rejected' } } as ApiFailure)));
    component.submit(new Event('submit'));
    expect(component.rejectionReason()).toContain('tipo real');

    upload.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'corr-403', fields: [] } as ApiFailure)));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('forbidden');
    expect(component.stateMessage()).toContain('permissão');
    expect(component.targetExecutionId()).toBeNull();

    upload.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 0, code: 'unexpected_error', message: 'safe', correlationId: null, fields: [] } as ApiFailure)));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('unavailable');
    expect(component.stateTitle()).toContain('indisponível');
  });

  it('renders the complete upload journey in English', () => {
    TestBed.inject(I18nService).configure('en-US');
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('New import');
    expect(fixture.nativeElement.textContent).toContain('Formats allowed');
  });

  it('uses the active source policy for guidance and client validation', () => {
    policy.and.returnValue(of({
      policies: [
        { source: 'N-FP', allowed_extensions: ['csv'], max_bytes: 1024 },
        { source: 'OWM', allowed_extensions: ['json'], max_bytes: 2048 }
      ],
      organizations: [{ id: 'org-1', organization_code: 'ORG-1', display_name: 'Organization 1' }]
    }));
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.acceptedExtensions()).toBe('.csv');
    expect(component.sizeLabel()).toBe('1 KiB');
    component.selectFile({ target: { files: [new File(['x'], 'data.json')] } } as unknown as Event);
    expect(component.fileError()).toContain('CSV');
    component.selectSource('OWM');
    expect(component.acceptedExtensions()).toBe('.json');
    expect(component.fileError()).toBe('');
  });

  it('fails closed when the upload policy is unavailable', () => {
    policy.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 500, code: 'internal_error', message: 'safe', correlationId: 'corr-policy', fields: [] } as ApiFailure)));
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.canSubmit()).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('envio permanece bloqueado');
    expect(fixture.nativeElement.textContent).toContain('corr-policy');
  });

  for (const code of ['storage_error', 'pipeline_error']) {
    it(`treats ${code} with an execution ID as an operational failure`, () => {
      upload.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 500, code, message: 'safe', correlationId: 'corr-500', fields: [], details: { execution_id: 'failed-execution' } } as ApiFailure)));
      const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
      component.ngOnInit();
      component.file.set(new File(['id\n1'], 'safe.csv'));
      component.submit(new Event('submit'));
      expect(component.state()).toBe('unavailable');
      expect(component.rejectionReason()).toBe('');
      expect(component.targetExecutionId()).toBe('failed-execution');
    });
  }
});
