// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { parseServer } from './sql';

describe('parseServer', () => {
    it('splits the Fabric serverFqdn port suffix that tedious cannot resolve', () => {
        expect(parseServer('abc.database.fabric.microsoft.com,1433')).toEqual({ host: 'abc.database.fabric.microsoft.com', port: 1433 });
    });

    it('accepts tcp: prefixes, non-default ports, and bare hosts', () => {
        expect(parseServer(' tcp:abc.database.windows.net,14330 ')).toEqual({ host: 'abc.database.windows.net', port: 14330 });
        expect(parseServer('abc.database.windows.net')).toEqual({ host: 'abc.database.windows.net', port: 1433 });
    });
});
