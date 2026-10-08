from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field

Status = Literal["activo", "inactivo"]


class InstitutionIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=20)
    tax_id: Optional[str] = None
    currency: str = Field(default="DOP", min_length=3, max_length=3)
    timezone: str = "America/Santo_Domingo"
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    director_name: Optional[str] = None
    district: Optional[str] = None
    regional: Optional[str] = None
    status: Status = "activo"


class CampusIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = None
    status: Status = "activo"


class AcademicYearIn(BaseModel):
    name: str = Field(min_length=4, max_length=30)
    start_date: date
    end_date: date
    is_current: bool = False
    status: Literal["planificado", "activo", "cerrado"] = "planificado"


class TermIn(BaseModel):
    academic_year_id: str
    name: str = Field(min_length=2, max_length=60)
    start_date: date
    end_date: date
    status: Literal["abierto", "cerrado"] = "abierto"


class GradeIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    level: Literal["inicial", "primaria", "secundaria"]
    order: int = Field(ge=0, le=50)


class SectionIn(BaseModel):
    academic_year_id: str
    campus_id: str
    grade_id: str
    name: str = Field(min_length=1, max_length=20)
    capacity: int = Field(ge=1, le=80)
    shift: Literal["matutino", "vespertino", "extendido"] = "matutino"


class FeeIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    category: Literal["matricula", "mensualidad", "transporte", "cafeteria", "servicio", "recargo", "material"]
    amount: float = Field(gt=0, le=10_000_000)
    recurring: bool = False
    status: Status = "activo"


class GuardianIn(BaseModel):
    first_name: str = Field(min_length=2, max_length=80)
    last_name: str = Field(min_length=2, max_length=80)
    document_id: str = Field(min_length=4, max_length=30)
    relationship: Literal["padre", "madre", "tutor_legal", "abuelo", "otro"]
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None


class SubjectIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    levels: str = Field(min_length=3, max_length=60, description="inicial,primaria,secundaria")
    order: int = Field(default=0, ge=0, le=50)
    status: Status = "activo"


class TeacherIn(BaseModel):
    first_name: str = Field(min_length=2, max_length=80)
    last_name: str = Field(min_length=2, max_length=80)
    document_id: str = Field(min_length=4, max_length=30)
    email: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    levels: Optional[str] = None
    hire_date: Optional[date] = None
    employment_status: Literal["activo", "licencia", "inactivo"] = "activo"
    user_id: Optional[str] = None


class AssignmentIn(BaseModel):
    teacher_id: str
    section_id: str
    subject_id: Optional[str] = None
    role: Literal["titular", "asignatura", "sustituto", "coordinador"]
    start_date: date
    end_date: Optional[date] = None
    days: Optional[str] = Field(default=None, pattern=r"^[1-6](,[1-6])*$")
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    status: Literal["activa", "finalizada"] = "activa"


class StudentIn(BaseModel):
    first_name: str = Field(min_length=2, max_length=80)
    last_name: str = Field(min_length=2, max_length=80)
    document_id: Optional[str] = Field(default=None, max_length=30)
    birth_date: date
    gender: Literal["M", "F"]
    campus_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: Literal["prospecto", "activo", "inactivo", "retirado", "egresado"] = "prospecto"
