-- sqlcmd -i grant-app-identity.sql -v AppIdentityPrincipal="<SQL principal of the AppBackend item owner>"
-- Functions use application auth, so every publication reaches SQL as the app identity: the owner of
-- the Fabric app item. Enroll that principal once; people are authorized separately by grant-writer.sql.
SET NOCOUNT ON;
DECLARE @principal sysname = N'$(AppIdentityPrincipal)';
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @principal AND type IN ('E', 'X'))
    THROW 51004, 'AppIdentityPrincipal must identify the existing external SQL user of the AppBackend owner.', 1;
IF DATABASE_PRINCIPAL_ID(N'health_snapshot_writer') IS NULL
    THROW 51004, 'Apply publication.sql before enrolling the app identity.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.database_role_members
    WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'health_snapshot_writer')
        AND member_principal_id = DATABASE_PRINCIPAL_ID(@principal)
)
BEGIN
    DECLARE @statement nvarchar(400) = N'ALTER ROLE health_snapshot_writer ADD MEMBER ' + QUOTENAME(@principal) + N';';
    EXEC sys.sp_executesql @statement;
END;
SELECT rolePrincipal.name AS roleName, memberPrincipal.name AS memberName, memberPrincipal.type_desc
FROM sys.database_role_members membership
JOIN sys.database_principals rolePrincipal ON rolePrincipal.principal_id = membership.role_principal_id
JOIN sys.database_principals memberPrincipal ON memberPrincipal.principal_id = membership.member_principal_id
WHERE rolePrincipal.name = N'health_snapshot_writer';
