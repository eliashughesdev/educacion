/* =====================================================================
   School ERP Enterprise - Esquema SQL Server (Bloque 1)
   Versión: 001  |  Motor: Microsoft SQL Server 2019+
   Dinero: DECIMAL(18,2) | Fechas: DATETIME2 en UTC | Texto: NVARCHAR
   Ejecutar con: sqlcmd -S <servidor> -d SchoolERP -i 001_core_schema.sql
   ===================================================================== */
SET XACT_ABORT ON;
GO
IF SCHEMA_ID('erp') IS NULL EXEC('CREATE SCHEMA erp');
GO

/* ---------- Identidad ---------- */
CREATE TABLE erp.Institutions (
    InstitutionId   INT IDENTITY(1,1) CONSTRAINT PK_Institutions PRIMARY KEY,
    Code            NVARCHAR(20)  NOT NULL CONSTRAINT UQ_Institutions_Code UNIQUE,
    Name            NVARCHAR(150) NOT NULL,
    TaxId           NVARCHAR(20)  NULL,
    CurrencyCode    CHAR(3)       NOT NULL CONSTRAINT DF_Institutions_Currency DEFAULT ('DOP'),
    TimeZone        NVARCHAR(60)  NOT NULL CONSTRAINT DF_Institutions_TZ DEFAULT ('America/Santo_Domingo'),
    Address         NVARCHAR(250) NULL, Phone NVARCHAR(30) NULL, Email NVARCHAR(160) NULL,
    Status          NVARCHAR(10)  NOT NULL CONSTRAINT CK_Institutions_Status CHECK (Status IN (N'activo', N'inactivo')) DEFAULT (N'activo'),
    CreatedAt       DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME(),
    RowVer          ROWVERSION
);

CREATE TABLE erp.Roles (
    RoleId      INT IDENTITY(1,1) CONSTRAINT PK_Roles PRIMARY KEY,
    RoleKey     NVARCHAR(40)  NOT NULL CONSTRAINT UQ_Roles_Key UNIQUE,
    Label       NVARCHAR(100) NOT NULL,
    IsGlobal    BIT NOT NULL DEFAULT (0),
    IsPersonal  BIT NOT NULL DEFAULT (0)
);
CREATE TABLE erp.Permissions (
    PermissionId INT IDENTITY(1,1) CONSTRAINT PK_Permissions PRIMARY KEY,
    PermKey      NVARCHAR(60) NOT NULL CONSTRAINT UQ_Permissions_Key UNIQUE   -- p.ej. 'payments:reverse'
);
CREATE TABLE erp.RolePermissions (
    RoleId INT NOT NULL CONSTRAINT FK_RP_Role REFERENCES erp.Roles(RoleId),
    PermissionId INT NOT NULL CONSTRAINT FK_RP_Perm REFERENCES erp.Permissions(PermissionId),
    CONSTRAINT PK_RolePermissions PRIMARY KEY (RoleId, PermissionId)
);

CREATE TABLE erp.Users (
    UserId        INT IDENTITY(1,1) CONSTRAINT PK_Users PRIMARY KEY,
    InstitutionId INT NULL CONSTRAINT FK_Users_Inst REFERENCES erp.Institutions(InstitutionId),
    Email         NVARCHAR(160) NOT NULL CONSTRAINT UQ_Users_Email UNIQUE,
    Name          NVARCHAR(120) NOT NULL,
    PasswordHash  NVARCHAR(200) NOT NULL,
    RoleId        INT NOT NULL CONSTRAINT FK_Users_Role REFERENCES erp.Roles(RoleId),
    GuardianId    INT NULL, StudentId INT NULL,
    IsActive      BIT NOT NULL DEFAULT (1),
    LastLoginAt   DATETIME2(3) NULL,
    CreatedAt     DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE erp.RefreshTokens (
    Jti        CHAR(32) NOT NULL CONSTRAINT PK_RefreshTokens PRIMARY KEY,
    UserId     INT NOT NULL CONSTRAINT FK_RT_User REFERENCES erp.Users(UserId),
    Revoked    BIT NOT NULL DEFAULT (0),
    ExpiresAt  DATETIME2(3) NOT NULL
);
CREATE INDEX IX_RefreshTokens_User ON erp.RefreshTokens(UserId) WHERE Revoked = 0;
CREATE TABLE erp.LoginAttempts (
    Identifier  NVARCHAR(220) NOT NULL CONSTRAINT PK_LoginAttempts PRIMARY KEY,  -- ip:email
    FailCount   INT NOT NULL DEFAULT (0),
    LockedUntil DATETIME2(3) NULL,
    LastAt      DATETIME2(3) NULL
);
CREATE TABLE erp.AuditLogs (
    AuditId       BIGINT IDENTITY(1,1) CONSTRAINT PK_AuditLogs PRIMARY KEY,
    InstitutionId INT NULL, UserId INT NULL, UserEmail NVARCHAR(160) NOT NULL,
    Action        NVARCHAR(40) NOT NULL, Entity NVARCHAR(60) NOT NULL, EntityId NVARCHAR(40) NULL,
    Details       NVARCHAR(MAX) NULL CONSTRAINT CK_Audit_Json CHECK (Details IS NULL OR ISJSON(Details) = 1),
    Ip            NVARCHAR(45) NULL,
    At            DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_AuditLogs_Inst_At ON erp.AuditLogs(InstitutionId, At DESC) INCLUDE (Action, Entity, UserEmail);

/* ---------- Institucional / académico ---------- */
CREATE TABLE erp.Campuses (
    CampusId INT IDENTITY(1,1) CONSTRAINT PK_Campuses PRIMARY KEY,
    InstitutionId INT NOT NULL CONSTRAINT FK_Campuses_Inst REFERENCES erp.Institutions(InstitutionId),
    Code NVARCHAR(20) NOT NULL, Name NVARCHAR(120) NOT NULL, Address NVARCHAR(250) NULL, Phone NVARCHAR(30) NULL,
    Status NVARCHAR(10) NOT NULL DEFAULT (N'activo') CHECK (Status IN (N'activo', N'inactivo')),
    CONSTRAINT UQ_Campuses_Code UNIQUE (InstitutionId, Code)
);
CREATE TABLE erp.AcademicYears (
    AcademicYearId INT IDENTITY(1,1) CONSTRAINT PK_AcademicYears PRIMARY KEY,
    InstitutionId INT NOT NULL CONSTRAINT FK_AY_Inst REFERENCES erp.Institutions(InstitutionId),
    Name NVARCHAR(30) NOT NULL, StartDate DATE NOT NULL, EndDate DATE NOT NULL,
    IsCurrent BIT NOT NULL DEFAULT (0),
    Status NVARCHAR(12) NOT NULL DEFAULT (N'planificado') CHECK (Status IN (N'planificado', N'activo', N'cerrado')),
    CONSTRAINT UQ_AY_Name UNIQUE (InstitutionId, Name),
    CONSTRAINT CK_AY_Dates CHECK (EndDate > StartDate)
);
CREATE UNIQUE INDEX UX_AY_Current ON erp.AcademicYears(InstitutionId) WHERE IsCurrent = 1;
CREATE TABLE erp.AcademicTerms (
    TermId INT IDENTITY(1,1) CONSTRAINT PK_Terms PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    AcademicYearId INT NOT NULL CONSTRAINT FK_Terms_AY REFERENCES erp.AcademicYears(AcademicYearId),
    Name NVARCHAR(60) NOT NULL, StartDate DATE NOT NULL, EndDate DATE NOT NULL,
    Status NVARCHAR(10) NOT NULL DEFAULT (N'abierto') CHECK (Status IN (N'abierto', N'cerrado'))
);
CREATE TABLE erp.Grades (
    GradeId INT IDENTITY(1,1) CONSTRAINT PK_Grades PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    Name NVARCHAR(60) NOT NULL, Level NVARCHAR(12) NOT NULL CHECK (Level IN (N'inicial', N'primaria', N'secundaria')),
    SortOrder INT NOT NULL CHECK (SortOrder BETWEEN 0 AND 50),
    CONSTRAINT UQ_Grades_Name UNIQUE (InstitutionId, Name)
);
CREATE TABLE erp.Sections (
    SectionId INT IDENTITY(1,1) CONSTRAINT PK_Sections PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    AcademicYearId INT NOT NULL REFERENCES erp.AcademicYears(AcademicYearId),
    CampusId INT NOT NULL REFERENCES erp.Campuses(CampusId),
    GradeId INT NOT NULL REFERENCES erp.Grades(GradeId),
    Name NVARCHAR(20) NOT NULL,
    Capacity INT NOT NULL CHECK (Capacity BETWEEN 1 AND 80),
    EnrolledCount INT NOT NULL DEFAULT (0),
    Shift NVARCHAR(12) NOT NULL DEFAULT (N'matutino') CHECK (Shift IN (N'matutino', N'vespertino', N'extendido')),
    RowVer ROWVERSION,
    CONSTRAINT UQ_Sections UNIQUE (AcademicYearId, CampusId, GradeId, Name),
    CONSTRAINT CK_Sections_Cupo CHECK (EnrolledCount BETWEEN 0 AND Capacity)
);

/* ---------- Estudiantes y tutores ---------- */
CREATE TABLE erp.Students (
    StudentId INT IDENTITY(1,1) CONSTRAINT PK_Students PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    CampusId INT NOT NULL REFERENCES erp.Campuses(CampusId),
    Code NVARCHAR(20) NOT NULL, FirstName NVARCHAR(80) NOT NULL, LastName NVARCHAR(80) NOT NULL,
    FullName AS (FirstName + N' ' + LastName) PERSISTED,
    DocumentId NVARCHAR(30) NULL, BirthDate DATE NOT NULL, Gender CHAR(1) NOT NULL CHECK (Gender IN ('M', 'F')),
    Email NVARCHAR(160) NULL, Phone NVARCHAR(30) NULL, Address NVARCHAR(250) NULL,
    Status NVARCHAR(12) NOT NULL DEFAULT (N'prospecto') CHECK (Status IN (N'prospecto', N'activo', N'inactivo', N'retirado', N'egresado')),
    CreatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Students_Code UNIQUE (InstitutionId, Code)
);
CREATE UNIQUE INDEX UX_Students_Doc ON erp.Students(InstitutionId, DocumentId) WHERE DocumentId IS NOT NULL;
CREATE INDEX IX_Students_Status ON erp.Students(InstitutionId, Status, LastName) INCLUDE (Code, FirstName, CampusId);
CREATE TABLE erp.Guardians (
    GuardianId INT IDENTITY(1,1) CONSTRAINT PK_Guardians PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    FirstName NVARCHAR(80) NOT NULL, LastName NVARCHAR(80) NOT NULL, DocumentId NVARCHAR(30) NOT NULL,
    Relationship NVARCHAR(12) NOT NULL CHECK (Relationship IN (N'padre', N'madre', N'tutor_legal', N'abuelo', N'otro')),
    Phone NVARCHAR(30) NULL, Email NVARCHAR(160) NULL, Address NVARCHAR(250) NULL, Occupation NVARCHAR(100) NULL,
    CONSTRAINT UQ_Guardians_Doc UNIQUE (InstitutionId, DocumentId)
);
CREATE TABLE erp.StudentGuardians (
    StudentId INT NOT NULL REFERENCES erp.Students(StudentId),
    GuardianId INT NOT NULL REFERENCES erp.Guardians(GuardianId),
    IsLegalGuardian BIT NOT NULL DEFAULT (1),
    CONSTRAINT PK_StudentGuardians PRIMARY KEY (StudentId, GuardianId)
);
CREATE TABLE erp.Enrollments (
    EnrollmentId INT IDENTITY(1,1) CONSTRAINT PK_Enrollments PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    StudentId INT NOT NULL REFERENCES erp.Students(StudentId),
    SectionId INT NOT NULL REFERENCES erp.Sections(SectionId),
    AcademicYearId INT NOT NULL REFERENCES erp.AcademicYears(AcademicYearId),
    EnrollType NVARCHAR(20) NOT NULL CHECK (EnrollType IN (N'nueva', N'reinscripcion', N'traslado_externo', N'cambio_seccion')),
    Status NVARCHAR(12) NOT NULL CHECK (Status IN (N'activa', N'retirada', N'trasladada', N'finalizada')),
    PreviousEnrollmentId INT NULL REFERENCES erp.Enrollments(EnrollmentId),
    Reason NVARCHAR(300) NULL,
    EnrolledAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), CreatedBy INT NOT NULL REFERENCES erp.Users(UserId)
);
CREATE UNIQUE INDEX UX_Enrollments_Active ON erp.Enrollments(StudentId, AcademicYearId) WHERE Status = N'activa';

/* ---------- Finanzas ---------- */
CREATE TABLE erp.FeeCatalog (
    FeeId INT IDENTITY(1,1) CONSTRAINT PK_FeeCatalog PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    Code NVARCHAR(20) NOT NULL, Name NVARCHAR(120) NOT NULL,
    Category NVARCHAR(12) NOT NULL CHECK (Category IN (N'matricula', N'mensualidad', N'transporte', N'cafeteria', N'servicio', N'recargo', N'material')),
    Amount DECIMAL(18,2) NOT NULL CHECK (Amount > 0), IsRecurring BIT NOT NULL DEFAULT (0),
    Status NVARCHAR(10) NOT NULL DEFAULT (N'activo'),
    CONSTRAINT UQ_Fee_Code UNIQUE (InstitutionId, Code)
);
CREATE TABLE erp.Invoices (
    InvoiceId INT IDENTITY(1,1) CONSTRAINT PK_Invoices PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    Number NVARCHAR(30) NOT NULL, StudentId INT NOT NULL REFERENCES erp.Students(StudentId),
    IssueDate DATE NOT NULL, DueDate DATE NOT NULL,
    Subtotal DECIMAL(18,2) NOT NULL, DiscountTotal DECIMAL(18,2) NOT NULL DEFAULT (0),
    Total DECIMAL(18,2) NOT NULL, Paid DECIMAL(18,2) NOT NULL DEFAULT (0), Balance DECIMAL(18,2) NOT NULL,
    Status NVARCHAR(10) NOT NULL CHECK (Status IN (N'pendiente', N'parcial', N'pagada', N'anulada')),
    BatchKey NVARCHAR(60) NULL, Notes NVARCHAR(300) NULL, VoidReason NVARCHAR(300) NULL,
    CreatedBy INT NOT NULL REFERENCES erp.Users(UserId), CreatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    RowVer ROWVERSION,
    CONSTRAINT UQ_Invoices_Number UNIQUE (InstitutionId, Number),
    CONSTRAINT CK_Invoices_Math CHECK (Total = Subtotal - DiscountTotal AND Paid >= 0 AND Balance >= 0 AND (Status = N'anulada' OR Balance = Total - Paid))
);
CREATE INDEX IX_Invoices_AR ON erp.Invoices(InstitutionId, DueDate) INCLUDE (StudentId, Balance) WHERE Balance > 0 AND Status <> N'anulada';
CREATE INDEX IX_Invoices_Student ON erp.Invoices(StudentId, IssueDate DESC);
CREATE UNIQUE INDEX UX_Invoices_Batch ON erp.Invoices(StudentId, BatchKey) WHERE BatchKey IS NOT NULL AND Status <> N'anulada';
CREATE TABLE erp.InvoiceLines (
    InvoiceLineId INT IDENTITY(1,1) CONSTRAINT PK_InvoiceLines PRIMARY KEY,
    InvoiceId INT NOT NULL REFERENCES erp.Invoices(InvoiceId) ON DELETE CASCADE,
    FeeId INT NULL REFERENCES erp.FeeCatalog(FeeId),
    Description NVARCHAR(200) NOT NULL, Quantity INT NOT NULL CHECK (Quantity >= 1),
    UnitPrice DECIMAL(18,2) NOT NULL, Discount DECIMAL(18,2) NOT NULL DEFAULT (0),
    LineTotal AS (CAST(Quantity * UnitPrice - Discount AS DECIMAL(18,2))) PERSISTED,
    CONSTRAINT CK_Lines_Discount CHECK (Discount >= 0 AND Discount <= Quantity * UnitPrice)
);
CREATE TABLE erp.CashSessions (
    CashSessionId INT IDENTITY(1,1) CONSTRAINT PK_CashSessions PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    CashierId INT NOT NULL REFERENCES erp.Users(UserId), RegisterName NVARCHAR(60) NOT NULL,
    OpeningAmount DECIMAL(18,2) NOT NULL CHECK (OpeningAmount >= 0), OpenedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    ClosedAt DATETIME2(3) NULL, ExpectedAmount DECIMAL(18,2) NULL, CountedAmount DECIMAL(18,2) NULL,
    Difference AS (CountedAmount - ExpectedAmount) PERSISTED,
    Status NVARCHAR(8) NOT NULL CHECK (Status IN (N'abierta', N'cerrada'))
);
CREATE UNIQUE INDEX UX_Cash_OpenPerCashier ON erp.CashSessions(CashierId) WHERE Status = N'abierta';
CREATE TABLE erp.Payments (
    PaymentId INT IDENTITY(1,1) CONSTRAINT PK_Payments PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    ReceiptNumber NVARCHAR(30) NULL, InvoiceId INT NOT NULL REFERENCES erp.Invoices(InvoiceId),
    StudentId INT NOT NULL REFERENCES erp.Students(StudentId), CashSessionId INT NOT NULL REFERENCES erp.CashSessions(CashSessionId),
    Amount DECIMAL(18,2) NOT NULL CHECK (Amount > 0),
    Method NVARCHAR(14) NOT NULL CHECK (Method IN (N'efectivo', N'tarjeta', N'transferencia', N'cheque', N'deposito')),
    Reference NVARCHAR(80) NULL, IdempotencyKey NVARCHAR(80) NOT NULL CONSTRAINT UQ_Payments_Idem UNIQUE,
    Status NVARCHAR(10) NOT NULL CHECK (Status IN (N'aplicado', N'revertido')),
    CashierId INT NOT NULL REFERENCES erp.Users(UserId), PaidAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    ReversedBy INT NULL REFERENCES erp.Users(UserId), ReversedAt DATETIME2(3) NULL, ReverseReason NVARCHAR(300) NULL,
    CONSTRAINT CK_Payments_SoD CHECK (ReversedBy IS NULL OR ReversedBy <> CashierId)
);
CREATE UNIQUE INDEX UX_Payments_Receipt ON erp.Payments(InstitutionId, ReceiptNumber) WHERE ReceiptNumber IS NOT NULL;
CREATE INDEX IX_Payments_Inst_Date ON erp.Payments(InstitutionId, PaidAt DESC) INCLUDE (Amount, Method, Status);
CREATE TABLE erp.Sequences (
    SeqKey NVARCHAR(60) NOT NULL CONSTRAINT PK_Sequences PRIMARY KEY,
    LastValue INT NOT NULL DEFAULT (0)
);
GO

/* ---------- Vista de antigüedad de saldos ---------- */
CREATE OR ALTER VIEW erp.vw_ReceivablesAging AS
SELECT i.InstitutionId, i.InvoiceId, i.Number, i.StudentId, s.Code AS StudentCode, s.FullName AS StudentName,
       i.DueDate, i.Total, i.Paid, i.Balance,
       DaysOverdue = CASE WHEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) > 0 THEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) ELSE 0 END,
       Bucket = CASE WHEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) <= 0 THEN N'corriente'
                     WHEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) <= 30 THEN N'1-30'
                     WHEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) <= 60 THEN N'31-60'
                     WHEN DATEDIFF(DAY, i.DueDate, CAST(SYSUTCDATETIME() AS DATE)) <= 90 THEN N'61-90' ELSE N'90+' END
FROM erp.Invoices i JOIN erp.Students s ON s.StudentId = i.StudentId
WHERE i.Balance > 0 AND i.Status <> N'anulada';
GO
