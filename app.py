"""GESCOM + GMAO multi-entités (métier IT) — version monolithe.
Un seul fichier = tout le backend : modèles, sécurité, services, API.
Lancer : uvicorn app:app --reload   (ou : python -m uvicorn app:app)
"""
from datetime import datetime, timedelta
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from sqlalchemy import (Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer,
                        Numeric, String, Text, UniqueConstraint, create_engine, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

# ============================== CONFIG ==============================
class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./gescom.db"
    SECRET_KEY: str = "change-moi-en-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

settings = Settings()
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================== SÉCURITÉ ==============================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def hash_password(p: str) -> str: return pwd_context.hash(p)
def verify_password(p: str, h: str) -> bool: return pwd_context.verify(p, h)
def create_token(user_id: int, role: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, settings.SECRET_KEY, algorithm=ALGORITHM)
def decode_token(t: str) -> dict: return jwt.decode(t, settings.SECRET_KEY, algorithms=[ALGORITHM])

# ============================== MODÈLES ==============================
class Base(DeclarativeBase): pass

class Role(str, Enum):
    EMPLOYE = "employe"; ADMIN_SOCIETE = "admin_societe"; ADMIN_GROUPE = "admin_groupe"
class TypeDocument(str, Enum):
    DEVIS = "devis"; COMMANDE = "commande"; BON_LIVRAISON = "bon_livraison"; FACTURE = "facture"; AVOIR = "avoir"
class StatutDocument(str, Enum):
    BROUILLON = "brouillon"; ENVOYE = "envoye"; ACCEPTE = "accepte"; REFUSE = "refuse"
    FACTURE = "facture"; PAYE = "paye"; ANNULE = "annule"
class TypeMouvement(str, Enum):
    ENTREE = "entree"; SORTIE = "sortie"; TRANSFERT_IN = "transfert_in"; TRANSFERT_OUT = "transfert_out"; INVENTAIRE = "inventaire"
class CategorieArticle(str, Enum):
    MATERIEL = "materiel"; LICENCE = "licence"; PRESTATION = "prestation"; FORFAIT = "forfait"
class PrioriteTicket(str, Enum):
    BASSE = "basse"; NORMALE = "normale"; HAUTE = "haute"; CRITIQUE = "critique"
class StatutTicket(str, Enum):
    OUVERT = "ouvert"; EN_COURS = "en_cours"; RESOLU = "resolu"; FERME = "ferme"

class Entite(Base):
    __tablename__ = "entite"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), unique=True)
    siret: Mapped[str | None] = mapped_column(String(14))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    pdv: Mapped[list["PointDeVente"]] = relationship(back_populates="entite")
    clients: Mapped[list["Client"]] = relationship(back_populates="entite")
    documents: Mapped[list["Document"]] = relationship(back_populates="entite")

class PointDeVente(Base):
    __tablename__ = "point_de_vente"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    nom: Mapped[str] = mapped_column(String(120))
    adresse: Mapped[str | None] = mapped_column(Text)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    entite: Mapped[Entite] = relationship(back_populates="pdv")
    stocks: Mapped[list["Stock"]] = relationship(back_populates="pdv")
    __table_args__ = (UniqueConstraint("entite_id", "nom"),)

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    nom: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(SAEnum(Role), default=Role.EMPLOYE)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    entites: Mapped[list["UserEntite"]] = relationship(back_populates="user")
    pdv: Mapped[list["UserPdv"]] = relationship(back_populates="pdv")

class UserEntite(Base):
    __tablename__ = "user_entite"
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"), primary_key=True)
    user: Mapped[User] = relationship(back_populates="entites")
    entite: Mapped[Entite] = relationship()

class UserPdv(Base):
    __tablename__ = "user_pdv"
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    pdv_id: Mapped[int] = mapped_column(ForeignKey("point_de_vente.id"), primary_key=True)
    user: Mapped[User] = relationship(back_populates="pdv")
    pdv: Mapped[PointDeVente] = relationship()

class Client(Base):
    __tablename__ = "client"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    nom: Mapped[str] = mapped_column(String(200))
    siret: Mapped[str | None] = mapped_column(String(14))
    email: Mapped[str | None] = mapped_column(String(255))
    telephone: Mapped[str | None] = mapped_column(String(30))
    adresse_facturation: Mapped[str | None] = mapped_column(Text)
    entite: Mapped[Entite] = relationship(back_populates="clients")
    contacts: Mapped[list["ContactClient"]] = relationship(back_populates="client")
    adresses: Mapped[list["AdresseClient"]] = relationship(back_populates="client")

class ContactClient(Base):
    __tablename__ = "contact_client"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    nom: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    telephone: Mapped[str | None] = mapped_column(String(30))
    client: Mapped[Client] = relationship(back_populates="contacts")

class AdresseClient(Base):
    __tablename__ = "adresse_client"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    libelle: Mapped[str] = mapped_column(String(120))
    adresse: Mapped[str] = mapped_column(Text)
    livraison: Mapped[bool] = mapped_column(Boolean, default=False)
    client: Mapped[Client] = relationship(back_populates="adresses")

class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(80), unique=True)
    designation: Mapped[str] = mapped_column(String(300))
    categorie: Mapped[CategorieArticle] = mapped_column(SAEnum(CategorieArticle), default=CategorieArticle.MATERIEL)
    prix_achat: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    prix_vente: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tva_taux: Mapped[float] = mapped_column(Numeric(5, 2), default=20)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    seuil_alerte: Mapped[int] = mapped_column(Integer, default=0)
    duree_licence_jours: Mapped[int | None] = mapped_column(Integer)
    nb_postes: Mapped[int | None] = mapped_column(Integer)
    stocks: Mapped[list["Stock"]] = relationship(back_populates="article")

class Stock(Base):
    __tablename__ = "stock"
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), primary_key=True)
    pdv_id: Mapped[int] = mapped_column(ForeignKey("point_de_vente.id"), primary_key=True)
    quantite: Mapped[int] = mapped_column(Integer, default=0)
    article: Mapped[Article] = relationship(back_populates="stocks")
    pdv: Mapped[PointDeVente] = relationship(back_populates="stocks")

class MouvementStock(Base):
    __tablename__ = "mouvement_stock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    pdv_id: Mapped[int] = mapped_column(ForeignKey("point_de_vente.id"))
    type: Mapped[TypeMouvement] = mapped_column(SAEnum(TypeMouvement))
    quantite: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"))
    pdv_cible_id: Mapped[int | None] = mapped_column(ForeignKey("point_de_vente.id"))
    commentaire: Mapped[str | None] = mapped_column(Text)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    pdv_id: Mapped[int | None] = mapped_column(ForeignKey("point_de_vente.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    type: Mapped[TypeDocument] = mapped_column(SAEnum(TypeDocument))
    numero: Mapped[str] = mapped_column(String(40))
    statut: Mapped[StatutDocument] = mapped_column(SAEnum(StatutDocument), default=StatutDocument.BROUILLON)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"), default=None)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_ht: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_ttc: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    entite: Mapped[Entite] = relationship(back_populates="documents")
    lignes: Mapped[list["LigneDocument"]] = relationship(back_populates="document")
    __table_args__ = (UniqueConstraint("entite_id", "type", "numero"),)

class LigneDocument(Base):
    __tablename__ = "ligne_document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    quantite: Mapped[int] = mapped_column(Integer)
    prix_unitaire: Mapped[float] = mapped_column(Numeric(12, 2))
    remise: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    document: Mapped[Document] = relationship(back_populates="lignes")

class Equipement(Base):
    __tablename__ = "equipement"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    client_id: Mapped[int | None] = mapped_column(ForeignKey("client.id"))
    pdv_id: Mapped[int | None] = mapped_column(ForeignKey("point_de_vente.id"))
    designation: Mapped[str] = mapped_column(String(300))
    categorie: Mapped[str] = mapped_column(String(60), default="materiel")
    marque: Mapped[str | None] = mapped_column(String(80))
    modele: Mapped[str | None] = mapped_column(String(120))
    numero_serie: Mapped[str | None] = mapped_column(String(120))
    date_achat: Mapped[datetime | None] = mapped_column(DateTime)
    fin_garantie: Mapped[datetime | None] = mapped_column(DateTime)
    tickets: Mapped[list["TicketSAV"]] = relationship(back_populates="equipement")

class TicketSAV(Base):
    __tablename__ = "ticket_sav"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    equipement_id: Mapped[int | None] = mapped_column(ForeignKey("equipement.id"))
    contrat_id: Mapped[int | None] = mapped_column(ForeignKey("contrat_maintenance.id"))
    technicien_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    sujet: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    priorite: Mapped[PrioriteTicket] = mapped_column(SAEnum(PrioriteTicket), default=PrioriteTicket.NORMALE)
    statut: Mapped[StatutTicket] = mapped_column(SAEnum(StatutTicket), default=StatutTicket.OUVERT)
