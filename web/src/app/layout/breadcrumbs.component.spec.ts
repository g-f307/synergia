import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { NEVER } from 'rxjs';

import { BreadcrumbsComponent } from './breadcrumbs.component';

describe('BreadcrumbsComponent', () => {
  it('does not render a breadcrumb trail on the new import workspace', async () => {
    await TestBed.configureTestingModule({
      imports: [BreadcrumbsComponent],
      providers: [
        { provide: Router, useValue: { url: '/imports/new', events: NEVER, createUrlTree: () => ({}), serializeUrl: () => '/' } },
        { provide: ActivatedRoute, useValue: {} }
      ]
    }).compileComponents();

    const fixture = TestBed.createComponent(BreadcrumbsComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('nav')).toBeNull();
    expect(fixture.componentInstance.crumbs()).toEqual([]);
  });
});
