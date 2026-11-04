import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { NgForm } from '@angular/forms';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { ApiFailure } from '../../shared/api/api-error';
import { FeedbackCreateComponent } from './feedback-create.component';
import { FeedbackDetailComponent } from './feedback-detail.component';
import { FeedbackItem, FeedbackService } from './feedback.service';

const item: FeedbackItem = { id: '77777777-7777-4777-8777-777777777777', protocol: 'FB-77777777777747778777777777777777', organization_id: 'org-a', author_user_id: 'author', kind: 'bug', title: '<img src=x onerror=alert(1)>', description: '<script>alert(1)</script>', expected_result: null, observed_result: null, source_route: '/profile', state: 'received', version: 1, created_at: '2026-11-03T12:00:00Z', updated_at: '2026-11-03T12:00:00Z', history: [], allowed_transitions: ['under_review', 'discarded'] };
const policy = { can_create: true, organization: {id:'org-a',display_name:'Synthetic organization'}, organization_issue: null, sources: [{id:'profile',route:'/profile'}] };
const form = () => ({ invalid: false, control: { markAllAsTouched: jasmine.createSpy() }, resetForm: jasmine.createSpy() } as unknown as NgForm);
function failure(status: number, code = ''): ApiFailure { return { status, code, kind: 'error', message: 'safe error', fields: {}, details: {} } as unknown as ApiFailure; }

describe('Feedback journey', () => {
  let api: FeedbackService;
  let policyCall: jasmine.Spy;
  let create: jasmine.Spy;
  let detail: jasmine.Spy;
  let transition: jasmine.Spy;
  beforeEach(async () => {
    policyCall = jasmine.createSpy().and.returnValue(of(policy));
    create = jasmine.createSpy().and.returnValue(of(item));
    detail = jasmine.createSpy().and.returnValue(of(item));
    transition = jasmine.createSpy().and.returnValue(of({ ...item, state:'under_review', version:2 }));
    await TestBed.configureTestingModule({
      imports: [FeedbackCreateComponent, FeedbackDetailComponent],
      providers: [provideHttpClient(), provideRouter([]), {provide: ActivatedRoute, useValue: { snapshot: { data: {triage:true}, queryParamMap:convertToParamMap({source:'https://evil.example/?secret=private'}) }, paramMap:of(convertToParamMap({feedbackId:item.id})) }}]
    }).compileComponents();
    api = TestBed.inject(FeedbackService);
    spyOn(api, 'policy').and.callFake(policyCall);
    spyOn(api, 'create').and.callFake(create);
    spyOn(api, 'detail').and.callFake(detail);
    spyOn(api, 'transition').and.callFake(transition);
  });
  it('falls back to a permitted source instead of forwarding an arbitrary URL', () => {
    const fixture = TestBed.createComponent(FeedbackCreateComponent); fixture.detectChanges();
    expect(fixture.componentInstance.source).toBe('profile');
  });
  it('blocks an ambiguous organization with actionable guidance', () => {
    policyCall.and.returnValue(of({...policy,can_create:false,organization:null,organization_issue:'ambiguous'}));
    const fixture = TestBed.createComponent(FeedbackCreateComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('administrador');
    fixture.componentInstance.submit(form());
    expect(create).not.toHaveBeenCalled();
  });
  it('shows loading and unavailable states and retains user input after failure', () => {
    const pending = new Subject<typeof policy>(); policyCall.and.returnValue(pending);
    const fixture = TestBed.createComponent(FeedbackCreateComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state=loading]')).not.toBeNull();
    pending.next(policy); fixture.detectChanges();
    const component = fixture.componentInstance; component.title='Synthetic title'; component.description='Synthetic description';
    create.and.returnValue(throwError(() => failure(503)));
    component.submit(form()); fixture.detectChanges();
    expect(component.title).toBe('Synthetic title');
    expect(component.description).toBe('Synthetic description');
    expect(fixture.nativeElement.querySelector('[data-state=error]')).not.toBeNull();
  });
  it('omits bug-only fields for suggestions and confirms the immutable protocol', () => {
    const fixture = TestBed.createComponent(FeedbackCreateComponent); const component=fixture.componentInstance;
    component.kind='suggestion'; component.expected='stale bug result'; component.title='Suggestion title'; component.description='Synthetic suggestion';
    component.submit(form()); fixture.detectChanges();
    expect(create.calls.mostRecent().args[0].expected_result).toBeUndefined();
    expect(create.calls.mostRecent().args[0].organization_id).toBeUndefined();
    expect(fixture.nativeElement.querySelector('[data-state=success]').textContent).toContain(item.protocol);
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });
  it('renders user text without creating executable elements', () => {
    const fixture=TestBed.createComponent(FeedbackDetailComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.detail script')).toBeNull();
    expect(fixture.nativeElement.querySelector('.detail img')).toBeNull();
    expect(fixture.nativeElement.querySelector('.plain').textContent).toBe(item.description);
  });
  it('blocks a stale decision until the updated record is explicitly reloaded', () => {
    transition.and.returnValue(throwError(() => failure(409,'feedback_conflict')));
    const fixture=TestBed.createComponent(FeedbackDetailComponent); const component=fixture.componentInstance;
    component.reason='My unsaved decision'; component.submit(form()); component.submit(form()); fixture.detectChanges();
    expect(transition).toHaveBeenCalledTimes(1);
    expect(component.reason).toBe('My unsaved decision');
    expect(fixture.nativeElement.textContent).toContain('Recarregue');
    detail.and.returnValue(of({...item,version:2,state:'under_review'}));
    component.retry(); fixture.detectChanges();
    expect(component.item()?.version).toBe(2);
    expect(component.failure()).toBeNull();
  });
  it('does not send a second request while submission is in progress', () => {
    create.and.returnValue(new Subject<FeedbackItem>());
    const fixture=TestBed.createComponent(FeedbackCreateComponent); const component=fixture.componentInstance;
    component.submit(form()); component.submit(form());
    expect(create).toHaveBeenCalledTimes(1);
  });
});
