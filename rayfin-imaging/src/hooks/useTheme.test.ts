// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import {
  DEPLOYMENT_ORIGIN_THEMES,
  DEPLOYMENT_WORKSPACE_THEMES,
  resolveThemeVariant,
} from './useTheme';

describe('resolveThemeVariant (med-1109 Daylight theme scoping)', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme-variant');
  });

  it('maps med-1109 Fabric workspace ID to daylight', () => {
    expect(DEPLOYMENT_WORKSPACE_THEMES['8be8f60c-dae7-4c79-9307-683c5794dcf7']).toBe('daylight');
    expect(
      resolveThemeVariant({
        search: '',
        origin: 'http://localhost:5173',
        workspaceId: '8be8f60c-dae7-4c79-9307-683c5794dcf7',
      })
    ).toBe('daylight');
  });

  it('maps med-1109 hosting origin to daylight', () => {
    expect(
      DEPLOYMENT_ORIGIN_THEMES['https://elite-otter-03514eba33-westus2.webapp.fabricapps.net']
    ).toBe('daylight');
    expect(
      resolveThemeVariant({
        search: '',
        origin: 'https://elite-otter-03514eba33-westus2.webapp.fabricapps.net',
        workspaceId: '',
      })
    ).toBe('daylight');
  });

  it('keeps med-1103a and unknown deployments on the default source theme', () => {
    expect(
      resolveThemeVariant({
        search: '',
        origin: 'https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net',
        workspaceId: 'f306e105-78fd-4b16-bfbe-2b556d493cb7',
      })
    ).toBe('source');
    expect(
      resolveThemeVariant({
        search: '',
        origin: 'https://example.webapp.fabricapps.net',
        workspaceId: '00000000-0000-0000-0000-000000000000',
      })
    ).toBe('source');
  });

  it('allows explicit ?theme=daylight and ?theme=source query overrides for preview/QA', () => {
    expect(
      resolveThemeVariant({
        search: '?theme=daylight',
        origin: 'https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net',
        workspaceId: 'f306e105-78fd-4b16-bfbe-2b556d493cb7',
      })
    ).toBe('daylight');
    expect(
      resolveThemeVariant({
        search: '?theme=source',
        origin: 'https://elite-otter-03514eba33-westus2.webapp.fabricapps.net',
        workspaceId: '8be8f60c-dae7-4c79-9307-683c5794dcf7',
      })
    ).toBe('source');
  });
});
