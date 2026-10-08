/* Matriculación transaccional con reserva atómica de cupo. */
CREATE OR ALTER PROCEDURE erp.sp_EnrollStudent
    @InstitutionId INT, @StudentId INT, @SectionId INT, @EnrollType NVARCHAR(20), @UserId INT,
    @EnrollmentId INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRAN;
        DECLARE @YearId INT;
        SELECT @YearId = AcademicYearId FROM erp.Sections WITH (UPDLOCK, ROWLOCK)
        WHERE SectionId = @SectionId AND InstitutionId = @InstitutionId;
        IF @YearId IS NULL THROW 50001, N'Sección inválida para la institución', 1;

        IF NOT EXISTS (SELECT 1 FROM erp.Students WHERE StudentId = @StudentId AND InstitutionId = @InstitutionId
                       AND Status NOT IN (N'retirado', N'egresado'))
            THROW 50002, N'Estudiante inválido o no elegible', 1;

        UPDATE erp.Sections SET EnrolledCount = EnrolledCount + 1
        WHERE SectionId = @SectionId AND EnrolledCount < Capacity;
        IF @@ROWCOUNT = 0 THROW 50003, N'La sección no tiene cupos disponibles', 1;

        INSERT erp.Enrollments (InstitutionId, StudentId, SectionId, AcademicYearId, EnrollType, Status, CreatedBy)
        VALUES (@InstitutionId, @StudentId, @SectionId, @YearId, @EnrollType, N'activa', @UserId);   -- UX_Enrollments_Active evita duplicados
        SET @EnrollmentId = SCOPE_IDENTITY();

        UPDATE erp.Students SET Status = N'activo' WHERE StudentId = @StudentId;
        INSERT erp.AuditLogs (InstitutionId, UserId, UserEmail, Action, Entity, EntityId, Details)
        SELECT @InstitutionId, @UserId, Email, N'enroll', N'enrollments', CAST(@EnrollmentId AS NVARCHAR(40)),
               (SELECT @StudentId AS student_id, @SectionId AS section_id FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
        FROM erp.Users WHERE UserId = @UserId;
        COMMIT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        THROW;
    END CATCH
END
GO
