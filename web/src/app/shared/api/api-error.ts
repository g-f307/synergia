export type ApiErrorKind = 'unauthorized' | 'forbidden' | 'not-found' | 'conflict' | 'validation' | 'unavailable' | 'internal';

export interface ApiFieldError { field: string; message: string; }
export interface ApiFailure {
  kind: ApiErrorKind;
  status: number;
  code: string;
  message: string;
  correlationId: string | null;
  fields: ApiFieldError[];
  details?: Record<string, unknown>;
}
