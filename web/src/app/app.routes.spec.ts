import { routes } from './app.routes';

describe('application routes', () => {
  it('protects the TV monitor with authentication and execution access', () => {
    const route = routes.find((candidate) => candidate.path === 'tv');

    expect(route).toBeDefined();
    expect(route?.canActivate?.length).toBe(2);
    expect(route?.loadComponent).toBeDefined();
  });
});
