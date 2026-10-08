/* School ERP Enterprise - 002: Docentes, calificaciones MINERD y boletines (objetivo SQL Server; no ejecutado en la vista previa) */
SET XACT_ABORT ON;
GO
ALTER TABLE erp.Institutions ADD DirectorName NVARCHAR(120) NULL, District NVARCHAR(60) NULL, Regional NVARCHAR(60) NULL;
GO
CREATE TABLE erp.Subjects (
    SubjectId INT IDENTITY(1,1) CONSTRAINT PK_Subjects PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    Code NVARCHAR(20) NOT NULL, Name NVARCHAR(120) NOT NULL, Levels NVARCHAR(60) NOT NULL, SortOrder INT NOT NULL DEFAULT (0),
    Status NVARCHAR(10) NOT NULL DEFAULT (N'activo'), CONSTRAINT UQ_Subjects UNIQUE (InstitutionId, Code)
);
CREATE TABLE erp.Teachers (
    TeacherId INT IDENTITY(1,1) CONSTRAINT PK_Teachers PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    UserId INT NULL REFERENCES erp.Users(UserId),
    FirstName NVARCHAR(80) NOT NULL, LastName NVARCHAR(80) NOT NULL, DocumentId NVARCHAR(30) NOT NULL,
    Specialty NVARCHAR(120) NULL, Levels NVARCHAR(60) NULL, HireDate DATE NULL,
    EmploymentStatus NVARCHAR(10) NOT NULL DEFAULT (N'activo') CHECK (EmploymentStatus IN (N'activo', N'licencia', N'inactivo')),
    CONSTRAINT UQ_Teachers_Doc UNIQUE (InstitutionId, DocumentId)
);
CREATE UNIQUE INDEX UX_Teachers_User ON erp.Teachers(UserId) WHERE UserId IS NOT NULL;
CREATE TABLE erp.TeacherAssignments (
    AssignmentId INT IDENTITY(1,1) CONSTRAINT PK_TeacherAssignments PRIMARY KEY,
    InstitutionId INT NOT NULL REFERENCES erp.Institutions(InstitutionId),
    TeacherId INT NOT NULL REFERENCES erp.Teachers(TeacherId), SectionId INT NOT NULL REFERENCES erp.Sections(SectionId),
    SubjectId INT NULL REFERENCES erp.Subjects(SubjectId),
    Role NVARCHAR(12) NOT NULL CHECK (Role IN (N'titular', N'asignatura', N'sustituto', N'coordinador')),
    StartDate DATE NOT NULL, EndDate DATE NULL, Days NVARCHAR(12) NULL, StartTime TIME(0) NULL, EndTime TIME(0) NULL,
    Status NVARCHAR(10) NOT NULL CHECK (Status IN (N'activa', N'finalizada')),
    CONSTRAINT CK_TA_Subject CHECK (Role IN (N'titular', N'coordinador') OR SubjectId IS NOT NULL),
    CONSTRAINT CK_TA_Time CHECK (StartTime IS NULL OR EndTime > StartTime)
);
CREATE UNIQUE INDEX UX_TA_Homeroom ON erp.TeacherAssignments(SectionId) WHERE Role = N'titular' AND Status = N'activa';
CREATE UNIQUE INDEX UX_TA_Subject ON erp.TeacherAssignments(SectionId, SubjectId) WHERE Role = N'asignatura' AND Status = N'activa';
CREATE INDEX IX_TA_Teacher ON erp.TeacherAssignments(TeacherId, Status) INCLUDE (SectionId, SubjectId, Role);
CREATE TABLE erp.ReportCardTemplates (
    TemplateId INT IDENTITY(1,1) CONSTRAINT PK_RCT PRIMARY KEY,
    TemplateKey NVARCHAR(40) NOT NULL, Version NVARCHAR(20) NOT NULL, Level NVARCHAR(12) NOT NULL,
    Definition NVARCHAR(MAX) NOT NULL CHECK (ISJSON(Definition) = 1),   -- competencias, períodos, escala, nota mínima
    OfficialValidation NVARCHAR(200) NOT NULL, CONSTRAINT UQ_RCT UNIQUE (TemplateKey, Version)
);
CREATE TABLE erp.GradePeriods (
    SectionId INT NOT NULL REFERENCES erp.Sections(SectionId), SubjectId INT NOT NULL REFERENCES erp.Subjects(SubjectId),
    Period CHAR(2) NOT NULL CHECK (Period IN ('P1', 'P2', 'P3', 'P4')),
    Status NVARCHAR(10) NOT NULL CHECK (Status IN (N'borrador', N'publicado')), PublishedBy INT NULL, PublishedAt DATETIME2(3) NULL,
    CONSTRAINT PK_GradePeriods PRIMARY KEY (SectionId, SubjectId, Period)
);
CREATE TABLE erp.CompetencyGrades (
    CompetencyGradeId BIGINT IDENTITY(1,1) CONSTRAINT PK_CompetencyGrades PRIMARY KEY,
    InstitutionId INT NOT NULL, AcademicYearId INT NOT NULL REFERENCES erp.AcademicYears(AcademicYearId),
    StudentId INT NOT NULL REFERENCES erp.Students(StudentId), SectionId INT NOT NULL REFERENCES erp.Sections(SectionId),
    SubjectId INT NOT NULL REFERENCES erp.Subjects(SubjectId), Period CHAR(2) NOT NULL,
    CompetencyKey NVARCHAR(10) NOT NULL, NumericValue DECIMAL(5,2) NULL CHECK (NumericValue BETWEEN 0 AND 100), QualitativeValue NVARCHAR(4) NULL,
    UpdatedBy INT NOT NULL, UpdatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), RowVer ROWVERSION,
    CONSTRAINT UQ_CG UNIQUE (StudentId, SectionId, SubjectId, Period, CompetencyKey)
);
CREATE INDEX IX_CG_Student_Year ON erp.CompetencyGrades(StudentId, AcademicYearId) INCLUDE (SubjectId, Period, CompetencyKey, NumericValue);
CREATE TABLE erp.PeriodNotes (
    StudentId INT NOT NULL REFERENCES erp.Students(StudentId), SectionId INT NOT NULL REFERENCES erp.Sections(SectionId), Period CHAR(2) NOT NULL,
    PresentDays INT NULL CHECK (PresentDays >= 0), AbsentDays INT NULL CHECK (AbsentDays >= 0),
    Observation NVARCHAR(1200) NULL, Support NVARCHAR(1200) NULL, UpdatedBy INT NOT NULL, UpdatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_PeriodNotes PRIMARY KEY (StudentId, SectionId, Period)
);
CREATE TABLE erp.GradeRevisionRequests (
    RevisionId INT IDENTITY(1,1) CONSTRAINT PK_GRR PRIMARY KEY,
    StudentId INT NOT NULL, SectionId INT NOT NULL, SubjectId INT NOT NULL, Period CHAR(2) NOT NULL,
    OldValues NVARCHAR(MAX) NOT NULL CHECK (ISJSON(OldValues) = 1), NewValues NVARCHAR(MAX) NOT NULL CHECK (ISJSON(NewValues) = 1),
    Reason NVARCHAR(400) NOT NULL, Status NVARCHAR(10) NOT NULL CHECK (Status IN (N'pendiente', N'aprobada', N'rechazada')),
    RequestedBy INT NOT NULL, ResolvedBy INT NULL, CreatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), ResolvedAt DATETIME2(3) NULL,
    CONSTRAINT CK_GRR_SoD CHECK (ResolvedBy IS NULL OR ResolvedBy <> RequestedBy)
);
CREATE TABLE erp.ReportCardApprovals (
    ApprovalId INT IDENTITY(1,1) CONSTRAINT PK_RCA PRIMARY KEY,
    StudentId INT NOT NULL, AcademicYearId INT NOT NULL, ContentHash CHAR(12) NOT NULL,
    Stage NVARCHAR(10) NOT NULL CHECK (Stage IN (N'docente', N'direccion')), ApprovedBy INT NOT NULL REFERENCES erp.Users(UserId),
    ApprovedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), CONSTRAINT UQ_RCA UNIQUE (StudentId, AcademicYearId, ContentHash, Stage)
);
GO
