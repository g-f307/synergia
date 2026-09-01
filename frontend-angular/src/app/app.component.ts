import { Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { SessionService } from './core/session.service';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  readonly title = 'SYNERGIA';
  readonly session = inject(SessionService);

  logout(): void {
    this.session.logout().subscribe();
  }
}
