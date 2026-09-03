import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { UserProfile } from '../core/session.models';
import { SessionService } from '../core/session.service';
import { ProfileComponent } from './profile.component';

describe('ProfileComponent', () => {
  const profile: UserProfile = {
    id: 'user-1',
    status: 'active',
    display_name: 'Usuário sintético',
    emails: [{ email: 'profile@example.invalid', is_primary: true, is_verified: true }],
    locale: 'pt-BR',
    timezone: 'America/Manaus',
    notifications: { email: true, in_app: true },
    avatar: { media_type: 'image/png', size_bytes: 3, sha256: 'sha-initial', url: '/me/avatar' },
    permissions: [],
    version: 1
  };
  const profileState = signal<UserProfile | null>(profile);
  const session = {
    profile: profileState,
    loadAvatar: jasmine.createSpy('loadAvatar').and.returnValue(of(new Blob(['png']))),
    uploadAvatar: jasmine.createSpy('uploadAvatar'),
    removeAvatar: jasmine.createSpy('removeAvatar'),
    updateProfile: jasmine.createSpy('updateProfile')
  };

  beforeEach(async () => {
    profileState.set(profile);
    session.loadAvatar.calls.reset();
    session.loadAvatar.and.returnValue(of(new Blob(['png'])));
    session.uploadAvatar.calls.reset();
    session.removeAvatar.calls.reset();
    spyOn(URL, 'createObjectURL').and.returnValue('blob:avatar');
    spyOn(URL, 'revokeObjectURL');
    await TestBed.configureTestingModule({
      imports: [ProfileComponent],
      providers: [{ provide: SessionService, useValue: session }]
    }).compileComponents();
  });

  it('loads and displays the authenticated avatar, then removes it from the view', () => {
    session.removeAvatar.and.returnValue(of({ ...profile, avatar: null, version: 2 }));
    const fixture = TestBed.createComponent(ProfileComponent);
    fixture.detectChanges();

    const image = fixture.nativeElement.querySelector('img.avatar-preview') as HTMLImageElement;
    expect(session.loadAvatar).toHaveBeenCalled();
    expect(image.src).toContain('blob:avatar');

    fixture.componentInstance.removeAvatar();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img.avatar-preview')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:avatar');
  });

  it('reloads and displays the avatar after upload', () => {
    const updated = {
      ...profile,
      avatar: { ...profile.avatar!, sha256: 'sha-updated' },
      version: 2
    };
    session.uploadAvatar.and.returnValue(of(updated));
    const fixture = TestBed.createComponent(ProfileComponent);
    fixture.detectChanges();
    session.loadAvatar.calls.reset();

    const file = new File(['png'], 'avatar.png', { type: 'image/png' });
    fixture.componentInstance.selectAvatar({
      target: { files: [file] }
    } as unknown as Event);
    fixture.detectChanges();

    expect(session.loadAvatar).toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector('img.avatar-preview')).not.toBeNull();
  });

  it('renders the remodeled profile as separate settings and avatar surfaces', () => {
    const fixture = TestBed.createComponent(ProfileComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.page-header')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.profile-settings')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.avatar-panel')).not.toBeNull();
  });
});
