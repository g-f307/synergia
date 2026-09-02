import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { NEVER, Subject, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ImportCreateComponent } from './import-create.component';
import { UploadUpdate } from './import.models';
import { ImportService } from './import.service';

describe('ImportCreateComponent', () => {
  const upload = jasmine.createSpy('upload');
  const session = { profile: () => ({ permissions: [{ key: 'import.create', organizations: ['org-1'] }] }) };
  beforeEach(async () => {
    upload.calls.reset();
    upload.and.returnValue(NEVER);
    await TestBed.configureTestingModule({
      imports: [ImportCreateComponent],
      providers: [provideRouter([]), { provide: ImportService, useValue: { upload } }, { provide: SessionService, useValue: session }]
    }).compileComponents();
  });

  it('validates empty, excessive and unsupported files before upload', () => {
    const fixture = TestBed.createComponent(ImportCreateComponent);
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
    component.file.set(new File(['id\n1'], 'safe.csv'));
    component.submit(new Event('submit'));
    component.submit(new Event('submit'));
    expect(upload).toHaveBeenCalledTimes(1);
    stream.next({ kind: 'progress', progress: 50 });
    expect(component.progress()).toBe(50);
    expect(component.state()).toBe('uploading');
  });

  it('redirects to the created import after acceptance', () => {
    const stream = new Subject<UploadUpdate>();
    upload.and.returnValue(stream);
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
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
    component.file.set(new File(['id\n1'], 'safe.csv'));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('duplicate');
    expect(component.targetExecutionId()).toBe('original');
    expect(component.correlationId()).toBe('corr-1');
    expect(upload).toHaveBeenCalledTimes(1);
  });

  it('distinguishes a server rejection from authorization and network failures', () => {
    const component = TestBed.createComponent(ImportCreateComponent).componentInstance;
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
    expect(component.state()).toBe('error');
    expect(component.targetExecutionId()).toBeNull();

    upload.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 0, code: 'unexpected_error', message: 'safe', correlationId: null, fields: [] } as ApiFailure)));
    component.submit(new Event('submit'));
    expect(component.state()).toBe('error');
  });

  it('renders the complete upload journey in English', () => {
    TestBed.inject(I18nService).configure('en-US');
    const fixture = TestBed.createComponent(ImportCreateComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('New import');
    expect(fixture.nativeElement.textContent).toContain('Allowed formats');
  });
});
