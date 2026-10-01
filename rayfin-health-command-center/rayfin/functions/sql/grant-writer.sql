-- sqlcmd -i grant-writer.sql -v WriterPrincipal="<existing approved Entra SQL principal>"
-- Provision the verified external user/group separately; never infer it from browser input.
SET NOCOUNT ON;
DECLARE @writer sysname = N'$(WriterPrincipal)';
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @writer AND type IN ('E', 'X'))
    THROW 51004, 'WriterPrincipal must identify an existing approved external SQL user or group.', 1;
IF DATABASE_PRINCIPAL_ID(N'health_snapshot_writer') IS NULL
    THROW 51004, 'Apply publication.sql before enrolling an operator.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.database_role_members
    WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'health_snapshot_writer')
        AND member_principal_id = DATABASE_PRINCIPAL_ID(@writer)
)
BEGIN
    DECLARE @statement nvarchar(400) = N'ALTER ROLE health_snapshot_writer ADD MEMBER ' + QUOTENAME(@writer) + N';';
    EXEC sys.sp_executesql @statement;
END;
SELECT rolePrincipal.name AS roleName, memberPrincipal.name AS memberName, memberPrincipal.type_desc
FROM sys.database_role_members membership
JOIN sys.database_principals rolePrincipal ON rolePrincipal.principal_id = membership.role_principal_id
JOIN sys.database_principals memberPrincipal ON memberPrincipal.principal_id = membership.member_principal_id
WHERE rolePrincipal.name = N'health_snapshot_writer';
