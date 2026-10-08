"""SQLAlchemy 2.x models mirroring database/schema/001_core_schema.sql (SQL Server target).

Status: entregado para despliegue on-premise; NO conectado en la vista previa (que usa MongoDB).
Conexión: SQLSERVER_URL="mssql+pyodbc://user:pass@HOST/SchoolERP?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, String, Numeric, Date, DateTime, Boolean, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(18, 2)


class Base(DeclarativeBase):
    __table_args__ = {"schema": "erp"}


class Institution(Base):
    __tablename__ = "Institutions"
    InstitutionId: Mapped[int] = mapped_column(primary_key=True)
    Code: Mapped[str] = mapped_column(String(20), unique=True)
    Name: Mapped[str] = mapped_column(String(150))
    TaxId: Mapped[Optional[str]] = mapped_column(String(20))
    CurrencyCode: Mapped[str] = mapped_column(String(3), default="DOP")
    Status: Mapped[str] = mapped_column(String(10), default="activo")


class User(Base):
    __tablename__ = "Users"
    UserId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[Optional[int]] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    Email: Mapped[str] = mapped_column(String(160), unique=True)
    Name: Mapped[str] = mapped_column(String(120))
    PasswordHash: Mapped[str] = mapped_column(String(200))
    RoleId: Mapped[int] = mapped_column(Integer)
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True)


class Campus(Base):
    __tablename__ = "Campuses"
    CampusId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    Code: Mapped[str] = mapped_column(String(20))
    Name: Mapped[str] = mapped_column(String(120))


class AcademicYear(Base):
    __tablename__ = "AcademicYears"
    AcademicYearId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    Name: Mapped[str] = mapped_column(String(30))
    StartDate: Mapped[date] = mapped_column(Date)
    EndDate: Mapped[date] = mapped_column(Date)
    IsCurrent: Mapped[bool] = mapped_column(Boolean, default=False)


class Section(Base):
    __tablename__ = "Sections"
    SectionId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    AcademicYearId: Mapped[int] = mapped_column(ForeignKey("erp.AcademicYears.AcademicYearId"))
    CampusId: Mapped[int] = mapped_column(ForeignKey("erp.Campuses.CampusId"))
    GradeId: Mapped[int] = mapped_column(Integer)
    Name: Mapped[str] = mapped_column(String(20))
    Capacity: Mapped[int] = mapped_column(Integer)
    EnrolledCount: Mapped[int] = mapped_column(Integer, default=0)


class Student(Base):
    __tablename__ = "Students"
    StudentId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    CampusId: Mapped[int] = mapped_column(ForeignKey("erp.Campuses.CampusId"))
    Code: Mapped[str] = mapped_column(String(20))
    FirstName: Mapped[str] = mapped_column(String(80))
    LastName: Mapped[str] = mapped_column(String(80))
    BirthDate: Mapped[date] = mapped_column(Date)
    Status: Mapped[str] = mapped_column(String(12), default="prospecto")


class Invoice(Base):
    __tablename__ = "Invoices"
    InvoiceId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    Number: Mapped[str] = mapped_column(String(30))
    StudentId: Mapped[int] = mapped_column(ForeignKey("erp.Students.StudentId"))
    IssueDate: Mapped[date] = mapped_column(Date)
    DueDate: Mapped[date] = mapped_column(Date)
    Total: Mapped[Decimal] = mapped_column(Money)
    Paid: Mapped[Decimal] = mapped_column(Money, default=0)
    Balance: Mapped[Decimal] = mapped_column(Money)
    Status: Mapped[str] = mapped_column(String(10))


class Payment(Base):
    __tablename__ = "Payments"
    PaymentId: Mapped[int] = mapped_column(primary_key=True)
    InstitutionId: Mapped[int] = mapped_column(ForeignKey("erp.Institutions.InstitutionId"))
    InvoiceId: Mapped[int] = mapped_column(ForeignKey("erp.Invoices.InvoiceId"))
    Amount: Mapped[Decimal] = mapped_column(Money)
    Method: Mapped[str] = mapped_column(String(14))
    IdempotencyKey: Mapped[str] = mapped_column(String(80), unique=True)
    Status: Mapped[str] = mapped_column(String(10))
    PaidAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysutcdatetime())
