interface SynergiaRuntimeConfig {
  apiUrl?: string;
}

const runtime = (
  globalThis as typeof globalThis & { __SYNERGIA_CONFIG__?: SynergiaRuntimeConfig }
).__SYNERGIA_CONFIG__;

export const environment = {
  apiUrl: runtime?.apiUrl ?? 'http://localhost:8000',
};
