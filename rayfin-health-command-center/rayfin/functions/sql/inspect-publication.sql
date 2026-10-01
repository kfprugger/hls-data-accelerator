-- Run with the real caller's SQL-audience OBO token, not an impersonation context.
SET NOCOUNT ON;
SELECT ORIGINAL_LOGIN() AS authenticatedLogin, USER_NAME() AS databasePrincipal,
    IS_ROLEMEMBER(N'health_snapshot_writer') AS writerRole,
    HAS_PERMS_BY_NAME(N'dbo.PublishHealthSnapshot',N'OBJECT',N'EXECUTE') AS mayPublish,
    HAS_PERMS_BY_NAME(N'dbo.PublishedSnapshots',N'OBJECT',N'INSERT') AS directInsert,
    HAS_PERMS_BY_NAME(N'dbo.PublishedSnapshots',N'OBJECT',N'UPDATE') AS directUpdate,
    HAS_PERMS_BY_NAME(N'dbo.PublishedSnapshots',N'OBJECT',N'DELETE') AS directDelete;
EXEC dbo.GetHealthSyncAccess;
SELECT o.name, o.type_desc, USER_NAME(COALESCE(o.principal_id,s.principal_id)) AS effectiveOwner
FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id
WHERE o.object_id IN (OBJECT_ID(N'dbo.PublishedSnapshots'),OBJECT_ID(N'dbo.SyncRuns'),
    OBJECT_ID(N'dbo.GetHealthSyncAccess'),OBJECT_ID(N'dbo.PublishHealthSnapshot'),OBJECT_ID(N'dbo.ValidateHealthSnapshot'));
-- Exactly one row after initialization; counts/version/actor/timestamp must agree with winning audit.
SELECT p.id,p.version,p.capturedAt,p.publisherId,p.syncRunId,r.status,r.expectedVersion,r.publishedVersion,
    r.kpiRows,r.seriesRows,r.worklistRows,r.publisherId AS auditedPublisher,r.completedAt,
    CONVERT(varchar(64),HASHBYTES('SHA2_256',p.payloadJson),2) AS payloadHash
FROM dbo.PublishedSnapshots p JOIN dbo.SyncRuns r ON r.id=p.syncRunId;
-- Expected result: no rows.
SELECT p.id AS brokenPublication
FROM dbo.PublishedSnapshots p LEFT JOIN dbo.SyncRuns r ON r.id=p.syncRunId
WHERE p.id <> '00000000-0000-0000-0000-000000000001' OR p.version < 1 OR r.id IS NULL
    OR r.status <> N'succeeded' OR r.publishedVersion <> p.version OR r.expectedVersion <> p.version-1
    OR r.publisherId <> p.publisherId OR r.completedAt <> p.capturedAt
    OR r.kpiRows <> (SELECT COUNT(*) FROM OPENJSON(p.payloadJson,'$.kpis'))
    OR r.seriesRows <> (SELECT COUNT(*) FROM OPENJSON(p.payloadJson,'$.series'))
    OR r.worklistRows <> (SELECT COUNT(*) FROM OPENJSON(p.payloadJson,'$.worklist'));
