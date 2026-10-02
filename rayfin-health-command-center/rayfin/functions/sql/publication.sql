-- Run against the discovered AppBackend SQL database as its schema administrator.
-- Apply Rayfin entities first, then this script. Never drop legacy snapshot tables.
-- The only write capability granted to an operator is EXECUTE on the publisher.
-- No EXECUTE AS/owner impersonation: role checks and audit see the caller's OBO session.
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF OBJECT_ID(N'dbo.PublishedSnapshots', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PublishedSnapshots (
        id uniqueidentifier NOT NULL CONSTRAINT PK_PublishedSnapshots PRIMARY KEY,
        version int NOT NULL,
        payloadJson nvarchar(max) NOT NULL,
        capturedAt datetime2 NOT NULL,
        syncRunId uniqueidentifier NOT NULL,
        publisherId nvarchar(200) NOT NULL,
        sources nvarchar(200) NOT NULL
    );
END;
IF OBJECT_ID(N'dbo.SyncRuns', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SyncRuns (
        id uniqueidentifier NOT NULL CONSTRAINT PK_SyncRuns PRIMARY KEY,
        startedAt datetime2 NOT NULL, completedAt datetime2 NULL,
        status nvarchar(9) NOT NULL CONSTRAINT CK_SyncRuns_status CHECK (status IN (N'running', N'succeeded', N'failed')),
        kpiRows int NOT NULL, seriesRows int NOT NULL, worklistRows int NOT NULL,
        sources nvarchar(200) NOT NULL, error nvarchar(500) NULL,
        publisherId nvarchar(200) NULL, expectedVersion int NULL, publishedVersion int NULL
    );
END;
IF COL_LENGTH(N'dbo.SyncRuns', N'publisherId') IS NULL
    ALTER TABLE dbo.SyncRuns ADD publisherId nvarchar(200) NULL;
IF COL_LENGTH(N'dbo.SyncRuns', N'expectedVersion') IS NULL
    ALTER TABLE dbo.SyncRuns ADD expectedVersion int NULL;
IF COL_LENGTH(N'dbo.SyncRuns', N'publishedVersion') IS NULL
    ALTER TABLE dbo.SyncRuns ADD publishedVersion int NULL;
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'dbo.PublishedSnapshots') AND name = N'CK_PublishedSnapshots_Singleton')
    ALTER TABLE dbo.PublishedSnapshots WITH CHECK ADD CONSTRAINT CK_PublishedSnapshots_Singleton
        CHECK (id = '00000000-0000-0000-0000-000000000001' AND version > 0 AND ISJSON(payloadJson) = 1);
IF DATABASE_PRINCIPAL_ID(N'health_snapshot_writer') IS NULL
    CREATE ROLE health_snapshot_writer AUTHORIZATION dbo;
GO

CREATE OR ALTER PROCEDURE dbo.ValidateHealthSnapshot
    @payloadJson nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    IF @payloadJson IS NULL OR DATALENGTH(@payloadJson) > 2000000 OR ISJSON(@payloadJson) <> 1
        THROW 51001, 'Invalid snapshot document.', 1;
    IF (SELECT COUNT(*) FROM OPENJSON(@payloadJson)) <> 4
        OR EXISTS (SELECT 1 FROM OPENJSON(@payloadJson) WHERE [key] NOT IN (N'schemaVersion', N'kpis', N'series', N'worklist'))
        OR EXISTS (SELECT [key] FROM OPENJSON(@payloadJson) GROUP BY [key] HAVING COUNT(*) <> 1)
        OR NOT EXISTS (SELECT 1 FROM OPENJSON(@payloadJson) WHERE [key] = N'schemaVersion' AND type = 2 AND TRY_CONVERT(float, value) = 1)
        OR (SELECT COUNT(*) FROM OPENJSON(@payloadJson) WHERE [key] IN (N'kpis', N'series', N'worklist') AND type = 4) <> 3
        THROW 51001, 'Invalid snapshot envelope.', 1;

    DECLARE @rows TABLE (section nvarchar(10) COLLATE Latin1_General_100_BIN2, rowNumber int, document nvarchar(max));
    INSERT @rows SELECT section.[key], CONVERT(int, item.[key]), item.value
        FROM OPENJSON(@payloadJson) section CROSS APPLY OPENJSON(CASE WHEN section.type = 4 THEN section.value ELSE N'[]' END) item
        WHERE section.type = 4 AND item.type = 5;
    IF EXISTS (SELECT 1 FROM OPENJSON(@payloadJson) section CROSS APPLY OPENJSON(CASE WHEN section.type = 4 THEN section.value ELSE N'[]' END) item WHERE section.type = 4 AND item.type <> 5)
        OR EXISTS (SELECT section FROM @rows GROUP BY section HAVING COUNT(*) > 1000)
        OR (SELECT COUNT(*) FROM @rows WHERE section = N'kpis') <> 14
        THROW 51001, 'Invalid snapshot rows.', 1;

    DECLARE @fields TABLE (section nvarchar(10) COLLATE Latin1_General_100_BIN2, name nvarchar(32) COLLATE Latin1_General_100_BIN2, jsonType int, required bit, maxLength int);
    INSERT @fields VALUES
        (N'kpis',N'lens',1,1,16),(N'kpis',N'metricKey',1,1,64),(N'kpis',N'label',1,1,64),
        (N'kpis',N'value',2,1,NULL),(N'kpis',N'unit',1,1,16),(N'kpis',N'caption',1,0,120),
        (N'kpis',N'rank',2,1,NULL),(N'kpis',N'sourceModel',1,1,64),
        (N'series',N'lens',1,1,16),(N'series',N'series',1,1,32),(N'series',N'label',1,1,160),
        (N'series',N'value',2,1,NULL),(N'series',N'unit',1,1,16),(N'series',N'detail',1,0,200),(N'series',N'rank',2,1,NULL),
        (N'worklist',N'lens',1,1,16),(N'worklist',N'kind',1,1,32),(N'worklist',N'subject',1,1,64),
        (N'worklist',N'segment',1,0,64),(N'worklist',N'primaryValue',2,1,NULL),(N'worklist',N'primaryUnit',1,1,16),
        (N'worklist',N'secondaryValue',2,0,NULL),(N'worklist',N'secondaryUnit',1,0,16),
        (N'worklist',N'flagged',3,0,NULL),(N'worklist',N'rank',2,1,NULL);
    IF EXISTS (SELECT 1 FROM @rows r CROSS APPLY OPENJSON(r.document) p
        LEFT JOIN @fields f ON f.section = r.section AND f.name = p.[key] COLLATE Latin1_General_100_BIN2
        WHERE f.name IS NULL OR f.jsonType <> p.type
            OR (p.type = 1 AND (LEN(LTRIM(RTRIM(p.value))) = 0 OR DATALENGTH(p.value) / 2 > f.maxLength))
            OR (p.type = 2 AND (TRY_CONVERT(float, p.value) IS NULL OR TRY_CONVERT(float, p.value) < 0 OR TRY_CONVERT(float, p.value) > 9007199254740991)))
        OR EXISTS (SELECT 1 FROM @rows r JOIN @fields f ON r.section = f.section AND f.required = 1
            WHERE NOT EXISTS (SELECT 1 FROM OPENJSON(r.document) p WHERE p.[key] COLLATE Latin1_General_100_BIN2 = f.name))
        OR EXISTS (SELECT 1 FROM @rows r CROSS APPLY OPENJSON(r.document) p GROUP BY r.section, r.rowNumber, p.[key] HAVING COUNT(*) <> 1)
        THROW 51001, 'Invalid snapshot field.', 1;

    DECLARE @metrics TABLE (metricKey nvarchar(64) COLLATE Latin1_General_100_BIN2, lens nvarchar(16) COLLATE Latin1_General_100_BIN2, unit nvarchar(16) COLLATE Latin1_General_100_BIN2);
    INSERT @metrics VALUES (N'totalPaid',N'payer',N'money'),(N'collectionRate',N'payer',N'percent'),
        (N'pmpm',N'payer',N'money'),(N'revenueAtRisk',N'payer',N'money'),(N'leakage',N'payer',N'money'),
        (N'openGaps',N'provider',N'count'),(N'qualityRate',N'provider',N'percent'),(N'avgReadmit',N'provider',N'percent'),
        (N'avgRaf',N'provider',N'ratio'),(N'stars',N'provider',N'ratio'),(N'studies',N'medtech',N'count'),
        (N'files',N'medtech',N'count'),(N'perPatient',N'medtech',N'ratio'),(N'avgAge',N'medtech',N'ratio');
    IF EXISTS (SELECT 1 FROM @rows r LEFT JOIN @metrics m ON m.metricKey = JSON_VALUE(r.document, '$.metricKey') COLLATE Latin1_General_100_BIN2
        WHERE r.section = N'kpis' AND (m.metricKey IS NULL OR m.lens <> JSON_VALUE(r.document, '$.lens') COLLATE Latin1_General_100_BIN2 OR m.unit <> JSON_VALUE(r.document, '$.unit') COLLATE Latin1_General_100_BIN2
            OR JSON_VALUE(r.document, '$.sourceModel') COLLATE Latin1_General_100_BIN2 <> CASE WHEN m.lens = N'medtech' THEN N'imagingGold' ELSE N'popHealthGold' END))
        OR EXISTS (SELECT JSON_VALUE(document, '$.metricKey') FROM @rows WHERE section = N'kpis' GROUP BY JSON_VALUE(document, '$.metricKey') HAVING COUNT(*) <> 1)
        THROW 51001, 'Invalid or incomplete snapshot metrics.', 1;

    DECLARE @series TABLE (name nvarchar(32) COLLATE Latin1_General_100_BIN2, lens nvarchar(16) COLLATE Latin1_General_100_BIN2, unit nvarchar(16) COLLATE Latin1_General_100_BIN2);
    INSERT @series VALUES (N'payerSegment',N'payer',N'money'),(N'careGap',N'provider',N'count'),(N'riskTier',N'provider',N'count'),
        (N'starMeasure',N'provider',N'ratio'),(N'modality',N'medtech',N'count');
    IF EXISTS (SELECT 1 FROM @rows r LEFT JOIN @series s ON s.name = JSON_VALUE(r.document, '$.series') COLLATE Latin1_General_100_BIN2
        WHERE r.section = N'series' AND (s.name IS NULL OR s.lens <> JSON_VALUE(r.document, '$.lens') COLLATE Latin1_General_100_BIN2 OR s.unit <> JSON_VALUE(r.document, '$.unit') COLLATE Latin1_General_100_BIN2))
        THROW 51001, 'Invalid snapshot series.', 1;

    IF EXISTS (SELECT 1 FROM @rows WHERE section = N'worklist' AND (
        JSON_VALUE(document, '$.kind') COLLATE Latin1_General_100_BIN2 NOT IN (N'highCostMember', N'heavyAcquisition')
        OR JSON_VALUE(document, '$.lens') COLLATE Latin1_General_100_BIN2 <> CASE JSON_VALUE(document, '$.kind') WHEN N'highCostMember' THEN N'payer' ELSE N'medtech' END
        OR JSON_VALUE(document, '$.primaryUnit') COLLATE Latin1_General_100_BIN2 <> CASE JSON_VALUE(document, '$.kind') WHEN N'highCostMember' THEN N'money' ELSE N'count' END
        OR (JSON_VALUE(document, '$.secondaryValue') IS NULL AND JSON_VALUE(document, '$.secondaryUnit') IS NOT NULL)
        OR (JSON_VALUE(document, '$.secondaryValue') IS NOT NULL AND ISNULL(JSON_VALUE(document, '$.secondaryUnit'),N'') COLLATE Latin1_General_100_BIN2 <> N'count')))
        THROW 51001, 'Invalid snapshot worklist.', 1;
    IF EXISTS (SELECT 1 FROM @rows r CROSS APPLY (SELECT JSON_VALUE(r.document, '$.subject') subject) p
        WHERE r.section = N'worklist' AND p.subject <> N'—' AND (
            (JSON_VALUE(r.document, '$.kind') = N'highCostMember' AND (
                CHARINDEX(N'…', p.subject) NOT BETWEEN 1 AND 5 OR LEN(p.subject) - CHARINDEX(N'…', p.subject) > 4
                OR LEN(p.subject) - LEN(REPLACE(p.subject,N'…',N'')) <> 1
                OR REPLACE(p.subject,N'…',N'') COLLATE Latin1_General_100_BIN2 LIKE N'%[^A-Za-z0-9-]%'))
            OR (JSON_VALUE(r.document, '$.kind') = N'heavyAcquisition' AND (
                LEN(p.subject) > 23 OR LEN(p.subject) % 3 <> 2 OR p.subject <> LTRIM(RTRIM(p.subject))
                OR EXISTS (SELECT 1 FROM STRING_SPLIT(p.subject,N' ') part WHERE LEN(part.value) <> 2 OR part.value COLLATE Latin1_General_100_BIN2 NOT LIKE N'[A-Z].')))))
        THROW 51001, 'Snapshot subjects must be masked.', 1;
    IF EXISTS (SELECT 1 FROM @rows r CROSS APPLY OPENJSON(r.document) p WHERE p.type = 2 AND (
        (p.[key] = N'rank' AND (TRY_CONVERT(float,p.value) >= 1000 OR TRY_CONVERT(float,p.value) <> FLOOR(TRY_CONVERT(float,p.value))))
        OR (p.[key] = N'value' AND ((JSON_VALUE(r.document,'$.unit') = N'percent' AND TRY_CONVERT(float,p.value) > 1)
            OR (JSON_VALUE(r.document,'$.unit') = N'count' AND TRY_CONVERT(float,p.value) <> FLOOR(TRY_CONVERT(float,p.value)))))
        OR (p.[key] = N'primaryValue' AND JSON_VALUE(r.document,'$.primaryUnit') = N'count' AND TRY_CONVERT(float,p.value) <> FLOOR(TRY_CONVERT(float,p.value)))
        OR (p.[key] = N'secondaryValue' AND TRY_CONVERT(float,p.value) <> FLOOR(TRY_CONVERT(float,p.value)))))
        OR EXISTS (SELECT section, CASE section WHEN N'kpis' THEN JSON_VALUE(document,'$.lens') WHEN N'series' THEN JSON_VALUE(document,'$.series') ELSE JSON_VALUE(document,'$.kind') END, TRY_CONVERT(float,JSON_VALUE(document,'$.rank'))
            FROM @rows GROUP BY section, CASE section WHEN N'kpis' THEN JSON_VALUE(document,'$.lens') WHEN N'series' THEN JSON_VALUE(document,'$.series') ELSE JSON_VALUE(document,'$.kind') END, TRY_CONVERT(float,JSON_VALUE(document,'$.rank')) HAVING COUNT(*) > 1)
        THROW 51001, 'Invalid numeric value or duplicate rank.', 1;
END;
GO

CREATE OR ALTER PROCEDURE dbo.GetHealthSyncAccess
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CAST(CASE WHEN IS_ROLEMEMBER(N'health_snapshot_writer') = 1
        AND HAS_PERMS_BY_NAME(N'dbo.PublishHealthSnapshot', N'OBJECT', N'EXECUTE') = 1 THEN 1 ELSE 0 END AS bit) AS canSync,
        COALESCE(p.version, 0) AS version,
        CONVERT(nvarchar(200), ORIGINAL_LOGIN()) AS publisherId,
        COALESCE(CONVERT(nvarchar(33), p.capturedAt, 127) + N'Z', N'') AS capturedAt,
        (SELECT COUNT(*) FROM OPENJSON(p.payloadJson, '$.kpis')) AS kpiRows,
        (SELECT COUNT(*) FROM OPENJSON(p.payloadJson, '$.series')) AS seriesRows,
        (SELECT COUNT(*) FROM OPENJSON(p.payloadJson, '$.worklist')) AS worklistRows
    FROM (VALUES (1)) v(n) LEFT JOIN dbo.PublishedSnapshots p ON p.id = '00000000-0000-0000-0000-000000000001';
END;
GO

CREATE OR ALTER PROCEDURE dbo.PublishHealthSnapshot
    @payloadJson nvarchar(max),
    @expectedVersion int
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    -- Check even if someone accidentally grants EXECUTE to a broader principal later.
    IF ISNULL(IS_ROLEMEMBER(N'health_snapshot_writer'), 0) <> 1
        THROW 51003, 'Snapshot publication permission denied.', 1;
    DECLARE @actor nvarchar(200) = CONVERT(nvarchar(200), ORIGINAL_LOGIN());
    DECLARE @runId uniqueidentifier = NEWID(), @startedAt datetime2 = SYSUTCDATETIME();
    DECLARE @version int = 0, @capturedAt datetime2, @publishedBy nvarchar(200), @currentPayload nvarchar(max);
    DECLARE @kpiRows int, @seriesRows int, @worklistRows int;
    BEGIN TRY
        IF @expectedVersion IS NULL OR @expectedVersion < 0 OR @expectedVersion >= 2147483647
            THROW 51001, 'Invalid expected publication version.', 1;
        EXEC dbo.ValidateHealthSnapshot @payloadJson;
        SELECT @kpiRows = COUNT(*) FROM OPENJSON(@payloadJson, '$.kpis');
        SELECT @seriesRows = COUNT(*) FROM OPENJSON(@payloadJson, '$.series');
        SELECT @worklistRows = COUNT(*) FROM OPENJSON(@payloadJson, '$.worklist');
        BEGIN TRANSACTION;
        -- HOLDLOCK protects the missing singleton key too: concurrent initial seeds have one winner.
        SELECT @version = version, @capturedAt = capturedAt, @publishedBy = publisherId, @currentPayload = payloadJson
            FROM dbo.PublishedSnapshots WITH (UPDLOCK, HOLDLOCK)
            WHERE id = '00000000-0000-0000-0000-000000000001';
        IF @version <> @expectedVersion
        BEGIN
            INSERT dbo.SyncRuns (id, startedAt, completedAt, status, kpiRows, seriesRows, worklistRows, sources, error, publisherId, expectedVersion, publishedVersion)
                VALUES (@runId, @startedAt, SYSUTCDATETIME(), N'failed', 0, 0, 0, N'popHealthGold,imagingGold', N'Conflict: a newer snapshot was published.', @actor, @expectedVersion, @version);
            COMMIT TRANSACTION;
            SELECT N'conflict' AS status, @version AS version, COALESCE(CONVERT(nvarchar(33), @capturedAt, 127) + N'Z',N'') AS capturedAt,
                (SELECT COUNT(*) FROM OPENJSON(@currentPayload,'$.kpis')) AS kpiRows,
                (SELECT COUNT(*) FROM OPENJSON(@currentPayload,'$.series')) AS seriesRows,
                (SELECT COUNT(*) FROM OPENJSON(@currentPayload,'$.worklist')) AS worklistRows, COALESCE(@publishedBy,N'') AS publisherId;
            RETURN;
        END;
        SET @capturedAt = SYSUTCDATETIME();
        SET @version += 1;
        IF @version = 1
            INSERT dbo.PublishedSnapshots (id, version, payloadJson, capturedAt, syncRunId, publisherId, sources)
                VALUES ('00000000-0000-0000-0000-000000000001', @version, @payloadJson, @capturedAt, @runId, @actor, N'popHealthGold,imagingGold');
        ELSE
            UPDATE dbo.PublishedSnapshots SET version = @version, payloadJson = @payloadJson, capturedAt = @capturedAt,
                syncRunId = @runId, publisherId = @actor, sources = N'popHealthGold,imagingGold'
                WHERE id = '00000000-0000-0000-0000-000000000001' AND version = @expectedVersion;
        INSERT dbo.SyncRuns (id, startedAt, completedAt, status, kpiRows, seriesRows, worklistRows, sources, publisherId, expectedVersion, publishedVersion)
            VALUES (@runId, @startedAt, @capturedAt, N'succeeded', @kpiRows, @seriesRows, @worklistRows, N'popHealthGold,imagingGold', @actor, @expectedVersion, @version);
        COMMIT TRANSACTION;
        SELECT N'published' AS status, @version AS version, CONVERT(nvarchar(33), @capturedAt, 127) + N'Z' AS capturedAt,
            @kpiRows AS kpiRows, @seriesRows AS seriesRows, @worklistRows AS worklistRows, @actor AS publisherId;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        -- Do not echo source values, tokens or SQL internals into the viewer-readable audit.
        INSERT dbo.SyncRuns (id, startedAt, completedAt, status, kpiRows, seriesRows, worklistRows, sources, error, publisherId, expectedVersion)
            VALUES (@runId, @startedAt, SYSUTCDATETIME(), N'failed', 0, 0, 0, N'popHealthGold,imagingGold', N'Publication failed; the previous snapshot was retained.', @actor, @expectedVersion);
        THROW;
    END CATCH;
END;
GO
-- dbo ownership chaining allows only the stored procedures' static SQL to write.
-- Direct CRUD (including a generic Rayfin mutation route) remains denied.
IF EXISTS (
    SELECT 1 FROM sys.objects o JOIN sys.schemas s ON s.schema_id = o.schema_id
    WHERE o.object_id IN (OBJECT_ID(N'dbo.PublishedSnapshots'), OBJECT_ID(N'dbo.SyncRuns'),
        OBJECT_ID(N'dbo.GetHealthSyncAccess'), OBJECT_ID(N'dbo.PublishHealthSnapshot'), OBJECT_ID(N'dbo.ValidateHealthSnapshot'))
        AND COALESCE(o.principal_id, s.principal_id) <> DATABASE_PRINCIPAL_ID(N'dbo')
)
    THROW 51004, 'Publication objects must share dbo ownership for the restricted static SQL ownership chain.', 1;
DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.PublishedSnapshots TO public;
DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.SyncRuns TO public;
GRANT EXECUTE ON OBJECT::dbo.GetHealthSyncAccess TO public;
GRANT EXECUTE ON OBJECT::dbo.PublishHealthSnapshot TO health_snapshot_writer;
GO
