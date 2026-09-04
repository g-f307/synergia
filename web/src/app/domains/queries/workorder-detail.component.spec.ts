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
    router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl','createUrlTree','serializeUrl'], { events: new Subject(), url: '/workorders/WO-001' });
    router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/synthetic-link');
    await TestBed.configureTestingModule({ imports:[WorkorderDetailComponent],providers:[provideRouter([]),{provide:Router,useValue:router},{provide:ActivatedRoute,useValue:{snapshot:{paramMap:convertToParamMap({workorderNumber:'WO-001'}),queryParamMap:convertToParamMap({from:'/search?query=WO-001'})}}},{provide:QueryService,useValue:{workorder:()=>response.asObservable()}}] }).compileComponents();
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

  it('distinguishes response quality warnings from partial release',()=>{
    response.next({ ...result(), workorder: { ...result().workorder, updated_at: '2000-01-01T00:00:00Z' } });fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="partial"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Workorder com liberação parcial');
  });

  it('returns to the exact originating search URL',()=>{fixture.componentInstance.back();expect(router.navigateByUrl).toHaveBeenCalledWith('/search?query=WO-001')});
});

function result():ConsolidatedWorkorder{return{workorder:{execution_id:'exec-001',workorder_number:'WO-001',organization_code:'ORG-1',processing_status:'consolidated',planned_quantity:null,produced_quantity:0,received_quantity:8,released_quantity:6,pending_quantity:2,retained_quantity:1,partially_released:true,lots:['LOT-001'],serials:['SER-001'],updated_at:'2026-09-04T12:00:00Z'},classifications:[{classification_id:'c-1',rule_id:'partial_release',state:'active',entity_type:'workorder',entity_id:'WO-001',justification:'Synthetic',reason:null,data_quality:'partial'}],pending_items:[{id:7,execution_id:'exec-001',workorder_number:'WO-001',lot_number:'LOT-001',serial_number:'SER-001',category:'oqc_pending',reason:'Synthetic',status:'open',priority:'high',updated_at:'2026-09-04T12:00:00Z'}],provenance:[{field_name:'received_quantity',source:'OWM',observed_value:8,created_at:'2026-09-04T12:00:00Z'}]}}
