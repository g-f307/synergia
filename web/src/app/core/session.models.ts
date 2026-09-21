export interface TokenResponse {
  access_token: string;
  token_type: 'Bearer';
  expires_in: number;
  session_id: string;
}

export interface EffectivePermission {
  key: string;
  organizations: string[] | null;
}

export interface AppearancePreferences {
  density: 'comfortable' | 'compact';
  font_scale: 'small' | 'normal' | 'large';
}

export interface UserProfile {
  id: string;
  status: string;
  display_name: string;
  emails: Array<{ email: string; is_primary: boolean; is_verified: boolean }>;
  locale: 'pt-BR' | 'en-US' | 'es-ES';
  timezone: string;
  notifications: { email: boolean; in_app: boolean };
  appearance: AppearancePreferences;
  avatar: { media_type: string; size_bytes: number; sha256: string; url: string } | null;
  permissions: EffectivePermission[];
  version: number;
}

export type SessionState = 'anonymous' | 'loading' | 'authenticated' | 'expired' | 'unavailable';
