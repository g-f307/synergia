import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { ConsolidatedWorkorder } from './query.models';
import { QueryService } from './query.service';
import { WorkorderDetailComponent } from './workorder-detail.component';

describe('WorkorderDetailComponent', () => {
  let fixture: ComponentFixture<WorkorderDetailComponent>;
  let response: Subject<ConsolidatedWorkorder>;
  let router: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    response = new Subject<ConsolidatedWorkorder>();
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl','createUrlTree','serializeUrl'], { events: new Subject(), url: '/workorders/WO-001?execution_id=exec-001&from=%2Fdashboard%2Frelated%2Fworkorders%3Fpage%3D2' });
    router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/synthetic-link');
    await TestBed.configureTestingModule({ imports:[WorkorderDetailComponent],providers:[provideRouter([]),{provide:Router,useValue:router},{provide:ActivatedRoute,useValue:{snapshot:{paramMap:convertToParamMap({workorderNumber:'WO-001'}),queryParamMap:convertToParamMap({from:'/dashboard/related/workorders?page=2'})}}},{provide:QueryService,useValue:{workorder:()=>response.asObservable()}}] }).compileComponents();
    fixture=TestBed.createComponent(WorkorderDetailComponent);fixture.detectChanges();
  });

  it('distinguishes missing, real zero, and populated quantities',()=>{
    response.next(result());fixture.detectChanges();
    const metrics=[...fixture.nativeElement.querySelectorAll('.metrics strong')].map((node:Element)=>node.textContent?.trim());
    expect(metrics[0]).toBe('Não informado');
    expect(metrics[1]).toBe('0');
    expect(metrics[2]).toBe('8');
  });

  it('shows related records and sanitized logical provenance',()=>{
    response.next(result());fixture.detectChanges();const text=fixture.nativeElement.textContent as string;
    expect(text).toContain('LOT-001');expect(text).toContain('SER-001');expect(text).toContain('OWM');expect(text).toContain('oqc_pending');
    expect(text).not.toContain('/internal/imports');expect(text).not.toContain('source_file_id');
  });

  it('preserves the current Workorder as the parent of linked lots',()=>{
    response.next(result());fixture.detectChanges();
    const linkCall=router.createUrlTree.calls.allArgs().find(([commands])=>JSON.stringify(commands)===JSON.stringify(['/lots','LOT-001']));
    expect(linkCall?.[1]?.queryParams?.['from']).toBe(router.url);
  });

  it('omits response-quality banners while keeping the operational partial-release state',()=>{
    response.next({ ...result(), workorder: { ...result().workorder, updated_at: '2000-01-01T00:00:00Z' } });fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="partial"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-state="stale"]')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Resposta parcial');
    expect(fixture.nativeElement.textContent).not.toContain('Dados desatualizados');
    expect(fixture.nativeElement.textContent).toContain('Workorder com liberação parcial');
  });

  it('uses one consistent surface with an internally scrolling detail body',()=>{
    response.next(result());fixture.detectChanges();
    const page=fixture.nativeElement.querySelector('.workorder-detail') as HTMLElement;
    const body=fixture.nativeElement.querySelector('.detail-scroll') as HTMLElement;
    expect(getComputedStyle(page).overflow).toBe('hidden');
    expect(getComputedStyle(body).overflowY).toBe('auto');
    expect(fixture.nativeElement.querySelectorAll('.card').length).toBe(0);
    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('Detalhes do Workorder');
    expect(fixture.nativeElement.querySelector('h1')?.classList).not.toContain('sr-only');
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-icon')).toBeNull();
  });

  it('returns to the exact originating Workorders URL',()=>{fixture.componentInstance.back();expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard/related/workorders?page=2')});
});

function result():ConsolidatedWorkorder{return{workorder:{execution_id:'exec-001',workorder_number:'WO-001',organization_code:'ORG-1',processing_status:'consolidated',planned_quantity:null,produced_quantity:0,received_quantity:8,released_quantity:6,pending_quantity:2,retained_quantity:1,partially_released:true,lots:['LOT-001'],serials:['SER-001'],updated_at:'2026-09-04T12:00:00Z'},classifications:[{classification_id:'c-1',rule_id:'partial_release',state:'active',entity_type:'workorder',entity_id:'WO-001',justification:'Synthetic',reason:null,data_quality:'partial'}],pending_items:[{id:7,execution_id:'exec-001',workorder_number:'WO-001',lot_number:'LOT-001',serial_number:'SER-001',category:'oqc_pending',reason:'Synthetic',status:'open',priority:'high',updated_at:'2026-09-04T12:00:00Z'}],provenance:[{field_name:'received_quantity',source:'OWM',observed_value:8,created_at:'2026-09-04T12:00:00Z'}]}}
