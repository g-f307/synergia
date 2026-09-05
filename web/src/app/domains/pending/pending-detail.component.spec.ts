import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { PendingItem } from './pending.models';
import { PendingDetailComponent } from './pending-detail.component';
import { PendingService } from './pending.service';
import { pendingItem } from './pending.fixtures';

describe('PendingDetailComponent',()=>{
  let fixture:ComponentFixture<PendingDetailComponent>;let response:Subject<PendingItem>;let router:jasmine.SpyObj<Router>;
  beforeEach(async()=>{response=new Subject();router=jasmine.createSpyObj<Router>('Router',['navigateByUrl','createUrlTree','serializeUrl'],{events:new Subject(),url:'/pending-items/1'});router.createUrlTree.and.returnValue({} as UrlTree);router.serializeUrl.and.returnValue('/related');await TestBed.configureTestingModule({imports:[PendingDetailComponent],providers:[provideRouter([]),{provide:Router,useValue:router},{provide:ActivatedRoute,useValue:{snapshot:{paramMap:convertToParamMap({pendingId:'1'}),queryParamMap:convertToParamMap({from:'/pending-items?status=open&page=2'})}}},{provide:PendingService,useValue:{detail:()=>response.asObservable()}}]}).compileComponents();fixture=TestBed.createComponent(PendingDetailComponent);fixture.detectChanges()});
  it('explains rule, version, context, and safely renders evidence',()=>{response.next(pendingItem({evidence:{note:'<script>unsafe()</script>'}}));fixture.detectChanges();const text=fixture.nativeElement.textContent as string;expect(text).toContain('pre_release_pending');expect(text).toContain('1.0.0');expect(text).toContain('WO-001');expect(text).toContain('<script>unsafe()</script>');expect(fixture.nativeElement.querySelector('script')).toBeNull();expect(text).not.toContain('Aprovar')});
  it('handles absent evidence and returns to the exact queue URL',()=>{response.next(pendingItem({evidence:{}}));fixture.detectChanges();expect(fixture.nativeElement.textContent).toContain('Nenhuma evidência');fixture.componentInstance.back();expect(router.navigateByUrl).toHaveBeenCalledWith('/pending-items?status=open&page=2')});
});
