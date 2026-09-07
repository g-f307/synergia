import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject } from 'rxjs';

import { PendingPage } from './pending.models';
import { PendingListComponent } from './pending-list.component';
import { PendingService } from './pending.service';
import { pendingItem, pendingPage } from './pending.fixtures';

describe('PendingListComponent',()=>{
  let fixture:ComponentFixture<PendingListComponent>;let response:Subject<PendingPage>;let router:jasmine.SpyObj<Router>;let params:BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  beforeEach(async()=>{response=new Subject();params=new BehaviorSubject(convertToParamMap({status:'open',page:'1'}));router=jasmine.createSpyObj<Router>('Router',['navigate','createUrlTree','serializeUrl'],{events:new Subject(),url:'/pending-items?status=open&page=1'});router.navigate.and.resolveTo(true);router.createUrlTree.and.returnValue({} as UrlTree);router.serializeUrl.and.returnValue('/pending-items/1');await TestBed.configureTestingModule({imports:[PendingListComponent],providers:[provideRouter([]),{provide:Router,useValue:router},{provide:ActivatedRoute,useValue:{queryParamMap:params.asObservable()}},{provide:PendingService,useValue:{list:()=>response.asObservable()}}]}).compileComponents();fixture=TestBed.createComponent(PendingListComponent);fixture.detectChanges()});
  it('shows an empty active queue without simulating actions',()=>{response.next(pendingPage([]));fixture.detectChanges();expect(fixture.nativeElement.querySelector('[data-state="empty"]')).not.toBeNull();expect(fixture.nativeElement.textContent).not.toContain('Aprovar')});
  it('renders distinct nature labels and traceable records',()=>{response.next(pendingPage([pendingItem(),pendingItem({id:2,category:'post_release_hold'}),pendingItem({id:3,category:'processing_failure'}),pendingItem({id:4,category:'partial_release'})]));fixture.detectChanges();const text=fixture.nativeElement.textContent as string;expect(text).toContain('Pré-liberação');expect(text).toContain('Hold pós-liberação');expect(text).toContain('Falha técnica');expect(text).toContain('Liberação parcial');expect(text).toContain('WO-001')});
  it('preserves filters and pagination in the URL',()=>{fixture.componentInstance.identifierType.set('serial');fixture.componentInstance.identifier.set('SER-001');fixture.componentInstance.priority.set('critical');fixture.componentInstance.changePage(2);expect(router.navigate).toHaveBeenCalledWith([],{relativeTo:jasmine.anything(),queryParams:jasmine.objectContaining({status:'open',priority:'critical',serial:'SER-001',page:2}),})});
});
