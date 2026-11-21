import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { SessionService } from '../../core/session.service';
import { Execution } from './execution.models';
import { ExecutionDetailComponent } from './execution-detail.component';
import { ExecutionService } from './execution.service';

describe('ExecutionDetailComponent',()=>{
 const execution:Execution={execution_id:'exec-1',status:'completed_with_errors',outcome:'partial',lifecycle:'partial',attempt:1,source:'N-FP',reprocessed_from_execution_id:null,started_at:'2026-01-01T00:00:00Z',finished_at:'2026-01-01T00:01:00Z',failure_reason:null,pipeline_version:'1',rule_catalog_version:'1',state_version:2,state_history:[{from_state:'processing',to_state:'completed_with_errors',reason:'partial',state_version:2,occurred_at:'2026-01-01T00:01:00Z'}],counts:{files:1,files_received:1,files_accepted:1,files_rejected:0,rows_read:2,valid_records:1,rejected_records:1,normalized_records:1,workorders:1,lots:0,serials:0,classifications:1,pending_items:1,errors:1,warnings:0}};
 const api={get:jasmine.createSpy().and.returnValue(of(execution)),divergences:jasmine.createSpy().and.returnValue(of({items:[],pagination:{page:1,page_size:20,total:0,pages:0},sort:'oldest'})),classifications:jasmine.createSpy().and.returnValue(NEVER),pending:jasmine.createSpy().and.returnValue(NEVER),evidences:jasmine.createSpy().and.returnValue(NEVER),download:jasmine.createSpy().and.returnValue(NEVER),reprocess:jasmine.createSpy().and.returnValue(of({execution_id:'exec-2'}))};
 let permissions:string[];
 beforeEach(async()=>{permissions=['execution.read','artifact.read','artifact.export','execution.reprocess'];Object.values(api).forEach(spy=>spy.calls.reset());api.get.and.returnValue(of(execution));api.divergences.and.returnValue(of({items:[],pagination:{page:1,page_size:20,total:0,pages:0},sort:'oldest'}));api.reprocess.and.returnValue(of({execution_id:'exec-2'}));await TestBed.configureTestingModule({imports:[ExecutionDetailComponent],providers:[provideRouter([]),{provide:ActivatedRoute,useValue:{paramMap:of(convertToParamMap({executionId:'exec-1'})),queryParamMap:of(convertToParamMap({tab:'history'})),snapshot:{paramMap:convertToParamMap({executionId:'exec-1'}),queryParamMap:convertToParamMap({tab:'history'})}}},{provide:ExecutionService,useValue:api},{provide:SessionService,useValue:{hasPermission:(key:string)=>permissions.includes(key)}}]}).compileComponents();});
 it('keeps the partial lifecycle compact without rendering a warning banner',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();expect(fixture.nativeElement.textContent).toContain('Com erros');expect(fixture.nativeElement.textContent).toContain('completed_with_errors');expect(fixture.nativeElement.textContent).toContain('partial');expect(fixture.nativeElement.querySelector('.partial-notice')).toBeNull();});
 it('preserves the selected tab and filters in the URL',()=>{const router=TestBed.inject(Router);const navigate=spyOn(router,'navigate').and.resolveTo(true);const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const component=fixture.componentInstance;component.severity.set('warning');component.source.set('OWM');component.selectTab('divergences');expect(navigate).toHaveBeenCalledWith([],jasmine.objectContaining({queryParams:{tab:'divergences',page:1,severity:'warning',source:'OWM',reference:null},queryParamsHandling:'merge',replaceUrl:true}));expect(api.divergences).toHaveBeenCalledWith('exec-1',1,'warning','OWM');});
 it('returns to the catalog with its complete filter context',()=>{const route=TestBed.inject(ActivatedRoute);const snapshot=route.snapshot as unknown as {queryParamMap:ReturnType<typeof convertToParamMap>};snapshot.queryParamMap=convertToParamMap({from:'/executions?status=completed&page=3&sort=oldest'});const router=TestBed.inject(Router);const navigate=spyOn(router,'navigateByUrl').and.resolveTo(true);const component=TestBed.createComponent(ExecutionDetailComponent).componentInstance;component.back();expect(navigate).toHaveBeenCalledWith('/executions?status=completed&page=3&sort=oldest');});
 it('returns to the related import detail when opened from an import result',()=>{const route=TestBed.inject(ActivatedRoute);const snapshot=route.snapshot as unknown as {queryParamMap:ReturnType<typeof convertToParamMap>};snapshot.queryParamMap=convertToParamMap({from:'/imports/exec-1'});const router=TestBed.inject(Router);const navigate=spyOn(router,'navigateByUrl').and.resolveTo(true);const component=TestBed.createComponent(ExecutionDetailComponent).componentInstance;component.back();expect(navigate).toHaveBeenCalledWith('/imports/exec-1');});
 it('hides restricted tabs and actions',()=>{permissions=['execution.read'];const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const component=fixture.componentInstance;expect(component.visibleTabs()).not.toContain('evidences');expect(component.visibleTabs()).not.toContain('divergences');expect(component.canReprocess()).toBeFalse();expect(component.canDownload()).toBeFalse();});
 it('represents forbidden access separately',()=>{api.get.and.returnValue(throwError(()=>failure('forbidden',403)));const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const state=fixture.nativeElement.querySelector('syn-state section') as HTMLElement;expect(state.dataset['state']).toBe('forbidden');expect(state.textContent).toContain('Acesso proibido');});
 it('represents a missing execution separately',()=>{api.get.and.returnValue(throwError(()=>failure('not-found',404)));const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const state=fixture.nativeElement.querySelector('syn-state section') as HTMLElement;expect(state.dataset['state']).toBe('empty');expect(state.textContent).toContain('Execução não encontrada');});
 it('represents service unavailability separately',()=>{api.get.and.returnValue(throwError(()=>failure('unavailable',503)));const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const state=fixture.nativeElement.querySelector('syn-state section') as HTMLElement;expect(state.dataset['state']).toBe('unavailable');expect(state.textContent).toContain('Acompanhamento indisponível');});
 it('leaves unauthorized failures to the session flow',()=>{api.get.and.returnValue(throwError(()=>failure('unauthorized',401)));const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();expect(fixture.componentInstance.loadFailureState()).toBeNull();expect(fixture.nativeElement.querySelector('syn-state')).toBeNull();});
 it('shows a reprocessing conflict next to the action on every tab',()=>{api.reprocess.and.returnValue(throwError(()=>failure('conflict',409)));const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();fixture.componentInstance.reprocess();fixture.detectChanges();expect(fixture.componentInstance.tab()).toBe('history');expect(fixture.nativeElement.textContent).toContain('Reprocessamento não iniciado');expect(fixture.nativeElement.textContent).toContain('processamento incompatível');});
 it('translates technical count keys',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();fixture.componentInstance.selectTab('summary');fixture.detectChanges();expect(fixture.nativeElement.textContent).toContain('Arquivos recebidos');expect(fixture.nativeElement.textContent).not.toContain('files_received');});
 it('uses the shared scrolling frame with a visible detail title and prioritized summary',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();fixture.componentInstance.selectTab('summary');fixture.detectChanges();const frame=fixture.nativeElement.querySelector('.execution-frame') as HTMLElement;const scroll=fixture.nativeElement.querySelector('.detail-scroll') as HTMLElement;expect(fixture.nativeElement.querySelector('.page-header')).toBeNull();expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('Detalhes da execução');expect(fixture.nativeElement.querySelector('.execution-overview')).not.toBeNull();expect(fixture.nativeElement.querySelector('.detail-heading .back-link')).not.toBeNull();expect(fixture.nativeElement.querySelectorAll('.summary-highlights article').length).toBe(4);expect(fixture.nativeElement.querySelectorAll('.summary-groups>section').length).toBe(3);expect(getComputedStyle(frame).borderRadius).toBe('28px');expect(getComputedStyle(frame).overflowY).toBe('hidden');expect(getComputedStyle(scroll).overflowY).toBe('auto');});
 it('matches the established detail header hierarchy',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const heading=fixture.nativeElement.querySelector('.detail-heading') as HTMLElement;const back=heading.children[0] as HTMLElement;expect(getComputedStyle(heading).display).toBe('grid');expect(back.classList).toContain('back-link');expect(back.textContent).toContain('Voltar');expect(heading.children[1].tagName).toBe('H1');expect(getComputedStyle(back).borderRadius).toBe('999px');});
 it('keeps the complete tab menu sticky when history is selected',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();const component=fixture.componentInstance;component.selectTab('history');fixture.detectChanges();const tabs=fixture.nativeElement.querySelector('.tabs') as HTMLElement;expect(tabs.querySelectorAll('button').length).toBe(component.visibleTabs().length);expect(tabs.textContent).toContain('Resumo');expect(tabs.textContent).toContain('Divergências');expect(getComputedStyle(tabs).position).toBe('sticky');expect(getComputedStyle(tabs).top).toBe('0px');});
 it('keeps the history heading below the sticky tabs',()=>{const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();fixture.componentInstance.selectTab('history');fixture.detectChanges();const heading=fixture.nativeElement.querySelector('.history>h2') as HTMLElement;expect(getComputedStyle(heading).marginTop).toBe('0px');expect(Number.parseFloat(getComputedStyle(heading).paddingBottom)).toBeGreaterThan(0);});
 it('creates a new execution without replacing the original',()=>{const component=TestBed.createComponent(ExecutionDetailComponent).componentInstance;component.ngOnInit();component.reprocess();expect(api.reprocess).toHaveBeenCalledWith('exec-1','web-execution-monitor');expect(component.reprocessedId()).toBe('exec-2');expect(component.item()?.execution_id).toBe('exec-1');});
 it('follows reference query changes and back navigation on the same execution',()=>{
  const route=TestBed.inject(ActivatedRoute);const changes=new Subject<ReturnType<typeof convertToParamMap>>();
  Object.assign(route,{queryParamMap:changes});
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  const snapshot=route.snapshot as unknown as {queryParamMap:ReturnType<typeof convertToParamMap>};
  snapshot.queryParamMap=convertToParamMap({tab:'divergences',page:'2',severity:'error',source:'OWM',reference:'DIV-example'});
  changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.componentInstance.tab()).toBe('divergences');
  expect(api.divergences).toHaveBeenCalledWith('exec-1',2,'error','OWM','DIV-example');
  expect(fixture.nativeElement.querySelector('.reference-location').textContent).toContain('DIV-example');
  snapshot.queryParamMap=convertToParamMap({tab:'history'});changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.componentInstance.tab()).toBe('history');expect(fixture.componentInstance.reference()).toBe('');
 });
 it('highlights the matched record on paged and history tabs and reports missing references',()=>{
  const divRef='DIV-'+'a'.repeat(32);const hisRef='HIS-'+'b'.repeat(32);
  const execWithRef:Execution={...execution,state_history:[{...execution.state_history[0],ref_id:hisRef}]};
  api.get.and.returnValue(of(execWithRef));
  api.divergences.and.returnValue(of({items:[{id:1,ref_id:divRef,source:'OWM',severity:'error',code:'invalid_value',scope:'record',workorder_number:'WO-1',reason:'bad',occurred_at:'2026-01-01T00:00:00Z'}],pagination:{page:2,page_size:20,total:21,pages:2},sort:'oldest'}));
  const route=TestBed.inject(ActivatedRoute);const changes=new Subject<ReturnType<typeof convertToParamMap>>();
  Object.assign(route,{queryParamMap:changes});
  const router=TestBed.inject(Router);const navigate=spyOn(router,'navigate').and.resolveTo(true);
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  const snapshot=route.snapshot as unknown as {queryParamMap:ReturnType<typeof convertToParamMap>};
  snapshot.queryParamMap=convertToParamMap({tab:'divergences',page:'1',reference:divRef});
  changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.nativeElement.querySelectorAll('article[data-reference-match="true"]').length).toBe(1);
  expect(fixture.nativeElement.querySelector('.reference-location').textContent).toContain('localizada e destacada');
  expect(navigate).toHaveBeenCalledWith([],jasmine.objectContaining({queryParams:{page:2},queryParamsHandling:'merge',replaceUrl:true}));
  snapshot.queryParamMap=convertToParamMap({tab:'history',reference:hisRef});
  changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.nativeElement.querySelectorAll('.history article[data-reference-match="true"]').length).toBe(1);
  expect(fixture.nativeElement.querySelector('.reference-location').textContent).toContain('localizada e destacada');
  const missingRef='HIS-'+'f'.repeat(32);
  snapshot.queryParamMap=convertToParamMap({tab:'history',reference:missingRef});
  changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.nativeElement.querySelectorAll('.history article[data-reference-match="true"]').length).toBe(0);
  expect(fixture.nativeElement.querySelector('.reference-location').textContent).toContain('não encontrada');
 });
 it('keeps manual pagination on the chosen page without re-resolving the reference when route emits',()=>{
  const divRef='DIV-'+'a'.repeat(32);
  api.divergences.and.callFake((_id:string,page:number,_sev:string,_src:string,ref?:string)=>ref
   ? of({items:[{id:21,ref_id:divRef,source:'OWM',severity:'error',code:'invalid_value',scope:'record',workorder_number:'WO-21',reason:'page2',occurred_at:'2026-01-01T00:00:00Z'}],pagination:{page:2,page_size:20,total:21,pages:2},sort:'oldest'})
   : of({items:[{id:1,ref_id:'DIV-'+'1'.repeat(32),source:'OWM',severity:'error',code:'invalid_value',scope:'record',workorder_number:'WO-1',reason:'page1',occurred_at:'2026-01-01T00:00:00Z'}],pagination:{page,page_size:20,total:21,pages:2},sort:'oldest'}));
  const route=TestBed.inject(ActivatedRoute);const changes=new Subject<ReturnType<typeof convertToParamMap>>();
  Object.assign(route,{queryParamMap:changes});
  const snapshot=route.snapshot as unknown as {queryParamMap:ReturnType<typeof convertToParamMap>};
  const router=TestBed.inject(Router);
  spyOn(router,'navigate').and.callFake((_cmds:unknown[],extras?:{queryParams?:Record<string,unknown>})=>{
   const next:Record<string,string>={};
   for(const key of snapshot.queryParamMap.keys){const v=snapshot.queryParamMap.get(key);if(v!==null)next[key]=v;}
   for(const [k,v] of Object.entries(extras?.queryParams??{})){if(v===null||v===undefined)delete next[k];else next[k]=String(v);}
   snapshot.queryParamMap=convertToParamMap(next);
   changes.next(snapshot.queryParamMap);
   return Promise.resolve(true);
  });
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  snapshot.queryParamMap=convertToParamMap({tab:'divergences',page:'1',reference:divRef});
  changes.next(snapshot.queryParamMap);fixture.detectChanges();
  expect(fixture.componentInstance.pageData()?.pagination.page).toBe(2);
  expect(fixture.nativeElement.querySelectorAll('article[data-reference-match="true"]').length).toBe(1);
  api.divergences.calls.reset();
  fixture.componentInstance.loadTab(1);fixture.detectChanges();
  expect(api.divergences).toHaveBeenCalledWith('exec-1',1,'','');
  expect(api.divergences.calls.count()).toBe(1);
  expect(fixture.componentInstance.pageData()?.pagination.page).toBe(1);
  expect(fixture.componentInstance.reference()).toBe(divRef);
  expect(fixture.nativeElement.querySelectorAll('article[data-reference-match="true"]').length).toBe(0);
 });
 it('cancels stale tab requests and prevents them from overwriting the selected tab',()=>{
  const first=new Subject();api.divergences.and.returnValue(first);
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  fixture.componentInstance.selectTab('divergences');expect(first.observed).toBeTrue();
  fixture.componentInstance.selectTab('history');expect(first.observed).toBeFalse();
  first.next({items:['stale']});expect(fixture.componentInstance.pageData()).toBeNull();
 });
 it('reloads reused route components and cancels execution requests on destroy',()=>{
  const params=new Subject<ReturnType<typeof convertToParamMap>>();Object.assign(TestBed.inject(ActivatedRoute),{paramMap:params});
  const first=new Subject();api.get.and.returnValue(first);
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  params.next(convertToParamMap({executionId:'exec-1'}));expect(first.observed).toBeTrue();
  const second=new Subject();api.get.and.returnValue(second);params.next(convertToParamMap({executionId:'exec-2'}));
  expect(first.observed).toBeFalse();fixture.destroy();expect(second.observed).toBeFalse();
 });
 it('cancels old execution actions when a reused route changes execution',()=>{
  const params=new Subject<ReturnType<typeof convertToParamMap>>();Object.assign(TestBed.inject(ActivatedRoute),{paramMap:params});
  const action=new Subject();api.reprocess.and.returnValue(action);
  const fixture=TestBed.createComponent(ExecutionDetailComponent);fixture.detectChanges();
  params.next(convertToParamMap({executionId:'exec-1'}));fixture.componentInstance.reprocess();
  expect(action.observed).toBeTrue();params.next(convertToParamMap({executionId:'exec-2'}));
  expect(action.observed).toBeFalse();expect(fixture.componentInstance.actionBusy()).toBeFalse();
  action.next({execution_id:'stale'});expect(fixture.componentInstance.reprocessedId()).toBe('');
 });
 function failure(kind:'unauthorized'|'forbidden'|'not-found'|'conflict'|'unavailable',status:number){return {kind,status,code:'review_failure',message:'safe',correlationId:null,fields:[]}}
});
