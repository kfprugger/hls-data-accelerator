-- sqlcmd -i grant-writer.sql -v WriterEmail="<approved writer's Fabric sign-in email>"
-- Run as a database administrator. Enrolls one person in the publication allowlist that the
-- publishSnapshot function and dbo.PublishHealthSnapshot match against the caller's token email.
-- Confirm the person separately; never take the address from browser input.
SET NOCOUNT ON;
DECLARE @email nvarchar(400) = LTRIM(RTRIM(N'$(WriterEmail)'));
IF LEN(@email) > 200 OR @email NOT LIKE N'_%@_%._%' OR @email LIKE N'% %'
    THROW 51004, 'WriterEmail must be the approved writer''s sign-in email address.', 1;
IF OBJECT_ID(N'dbo.SnapshotWriters', N'U') IS NULL OR OBJECT_ID(N'dbo.PublishHealthSnapshot', N'P') IS NULL
    THROW 51004, 'Apply the Rayfin entities and publication.sql before enrolling a writer.', 1;
IF NOT EXISTS (SELECT 1 FROM dbo.SnapshotWriters WHERE email = @email)
    INSERT dbo.SnapshotWriters (id, email) VALUES (NEWID(), @email);
SELECT email AS enrolledWriter FROM dbo.SnapshotWriters ORDER BY email;
