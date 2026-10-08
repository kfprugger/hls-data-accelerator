// Apply the shipped publication boundary to this app's discovered SQL database.
// Tokens are process-scoped; no credentials or source-estate identifiers are saved.
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
const require = createRequire(new URL('../rayfin/functions/package.json', import.meta.url));
const { Connection, Request } = require('tedious');
for (const key of ['SQL_SERVER', 'SQL_DATABASE', 'SQL_ACCESS_TOKEN', 'SQL_DEPLOYER_UPN']) {
  if (!process.env[key]) throw new Error(`${key} is required`);
}
const connection = new Connection({
  server: process.env.SQL_SERVER.replace(/^tcp:/, '').split(',')[0],
  authentication: { type: 'azure-active-directory-access-token', options: { token: process.env.SQL_ACCESS_TOKEN } },
  options: { database: process.env.SQL_DATABASE, encrypt: true, trustServerCertificate: false, requestTimeout: 120000 },
});
await new Promise((resolve, reject) => { connection.once('connect', error => error ? reject(error) : resolve()); connection.connect(); });
const execute = sql => new Promise((resolve, reject) => connection.execSqlBatch(new Request(sql, error => error ? reject(error) : resolve())));
const principal = process.env.SQL_DEPLOYER_UPN;
const literal = principal.replaceAll("'", "''");
try {
  await execute(`IF DATABASE_PRINCIPAL_ID(N'${literal}') IS NULL CREATE USER [${principal.replaceAll(']', ']]')}] FROM EXTERNAL PROVIDER;`);
  for (const name of ['publication.sql', 'grant-app-identity.sql', 'grant-writer.sql']) {
    const sql = (await readFile(new URL(`../rayfin/functions/sql/${name}`, import.meta.url), 'utf8'))
      .replaceAll('$(AppIdentityPrincipal)', literal).replaceAll('$(WriterEmail)', literal);
    for (const batch of sql.split(/^\s*GO\s*$/im)) if (batch.trim()) await execute(batch);
  }
  console.log('Publication procedures installed; the deploying app owner is enrolled as a snapshot writer.');
} finally {
  connection.close();
}
