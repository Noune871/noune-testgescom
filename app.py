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
    pdv: Mapped[list["UserPdv"]] = relationship(back_populates="user")

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
    date_ouverture: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    date_resolution: Mapped[datetime | None] = mapped_column(DateTime)
    temps_passe_minutes: Mapped[int] = mapped_column(Integer, default=0)
    equipement: Mapped[Equipement | None] = relationship(back_populates="tickets")

class ContratMaintenance(Base):
    __tablename__ = "contrat_maintenance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entite_id: Mapped[int] = mapped_column(ForeignKey("entite.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    numero: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(200))
    date_debut: Mapped[datetime] = mapped_column(DateTime)
    date_fin: Mapped[datetime | None] = mapped_column(DateTime)
    periodicite_jours: Mapped[int] = mapped_column(Integer, default=365)
    montant_ht: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    delai_intervention_heures: Mapped[int | None] = mapped_column(Integer)  # SLA
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("entite_id", "numero"),)

Base.metadata.create_all(bind=engine)

# ============================== DÉPENDANCES DROITS ==============================
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    user = db.query(User).get(int(payload["sub"]))
    if not user or not user.actif:
        raise HTTPException(status_code=401, detail="Utilisateur invalide")
    return user

def require_role(*roles: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(status_code=403, detail="Droits insuffisants")
        return user
    return dep

# ============================== SCHÉMAS ==============================
class ArticleIn(BaseModel):
    reference: str = Field(..., max_length=80)
    designation: str = Field(..., max_length=300)
    categorie: CategorieArticle = CategorieArticle.MATERIEL
    prix_achat: float = 0; prix_vente: float = 0; tva_taux: float = 20
    seuil_alerte: int = 0
    duree_licence_jours: int | None = None; nb_postes: int | None = None

class ArticleOut(BaseModel):
    id: int; reference: str; designation: str; categorie: str
    prix_vente: float; actif: bool
    class Config: from_attributes = True

class EntiteIn(BaseModel):
    nom: str = Field(..., max_length=120); siret: str | None = Field(default=None, max_length=14)
class EntiteOut(BaseModel):
    id: int; nom: str; actif: bool
    class Config: from_attributes = True

class PdvIn(BaseModel):
    nom: str = Field(..., max_length=120); adresse: str | None = None
class PdvOut(BaseModel):
    id: int; nom: str; entite_id: int; actif: bool
    class Config: from_attributes = True

class ClientIn(BaseModel):
    nom: str = Field(..., max_length=200); siret: str | None = None
    email: str | None = None; telephone: str | None = None; adresse_facturation: str | None = None
class ClientOut(BaseModel):
    id: int; nom: str; email: str | None
    contacts: list[dict] = []; adresses: list[dict] = []
    class Config: from_attributes = True

class MouvementIn(BaseModel):
    article_id: int; quantite: int = Field(..., gt=0)
    type: TypeMouvement = TypeMouvement.ENTREE
    commentaire: str | None = None; pdv_cible_id: int | None = None

class LigneDocIn(BaseModel):
    article_id: int; quantite: int = Field(..., gt=0)
    prix_unitaire: float = Field(..., ge=0); remise: float = Field(default=0, ge=0, le=100)
class LigneDocOut(BaseModel):
    article_id: int; quantite: int; prix_unitaire: float; remise: float
    class Config: from_attributes = True
class DocumentIn(BaseModel):
    entite_id: int; client_id: int; type: TypeDocument
    pdv_id: int | None = None; lignes: list[LigneDocIn]
class DocumentOut(BaseModel):
    id: int; numero: str; type: str; statut: str
    total_ht: float; total_ttc: float; entite_id: int; client_id: int; pdv_id: int | None
    lignes: list[LigneDocOut]
    class Config: from_attributes = True

class UserIn(BaseModel):
    email: str; password: str = Field(..., min_length=8); nom: str
    role: Role = Role.EMPLOYE; entite_ids: list[int] = []; pdv_ids: list[int] = []
class UserOut(BaseModel):
    id: int; email: str; nom: str; role: str; actif: bool
    entites: list[int] = []; pdv: list[int] = []
    class Config: from_attributes = True

class EquipementIn(BaseModel):
    entite_id: int; client_id: int | None = None; pdv_id: int | None = None
    designation: str = Field(..., max_length=300); categorie: str = "materiel"
    marque: str | None = None; modele: str | None = None; numero_serie: str | None = None
class EquipementOut(BaseModel):
    id: int; designation: str; categorie: str; numero_serie: str | None
    class Config: from_attributes = True

class TicketIn(BaseModel):
    entite_id: int; client_id: int; sujet: str = Field(..., max_length=300)
    description: str | None = None; equipement_id: int | None = None
    priorite: PrioriteTicket = PrioriteTicket.NORMALE
class TicketOut(BaseModel):
    id: int; sujet: str; statut: str; priorite: str; client_id: int
    class Config: from_attributes = True

class ContratIn(BaseModel):
    entite_id: int; client_id: int; libelle: str = Field(..., max_length=200)
    montant_ht: float = 0; periodicite_jours: int = 365
    delai_intervention_heures: int | None = None
class ContratOut(BaseModel):
    id: int; numero: str; libelle: str; montant_ht: float; actif: bool
    delai_intervention_heures: int | None
    class Config: from_attributes = True

class LigneShop(BaseModel):
    reference: str; quantite: int = Field(..., gt=0)
class CommandeShop(BaseModel):
    entite_id: int; client_id: int; pdv_id: int | None = None; lignes: list[LigneShop]

# ============================== SERVICES MÉTIER ==============================
class DocumentError(Exception): pass

def _numero(db: Session, entite_id: int, type_: TypeDocument) -> str:
    prefix = {"devis": "DEV", "commande": "CMD", "bon_livraison": "BL", "facture": "FA", "avoir": "AV"}[type_.value]
    n = db.query(Document).filter(Document.entite_id == entite_id, Document.type == type_).count()
    return f"{prefix}-{datetime.now().year}-{n + 1:04d}"

def recalculer(doc: Document, db: Session):
    ht = tva = 0.0
    for l in doc.lignes:
        base = l.quantite * float(l.prix_unitaire) * (1 - float(l.remise) / 100)
        ht += base
        art = db.query(Article).get(l.article_id)
        tva += base * float(art.tva_taux) / 100
    doc.total_ht, doc.total_ttc = ht, ht + tva

def creer_document(db, entite_id, client_id, type_, lignes, pdv_id=None, parent_id=None) -> Document:
    doc = Document(entite_id=entite_id, pdv_id=pdv_id, client_id=client_id, type=type_,
                   numero=_numero(db, entite_id, type_), parent_id=parent_id)
    db.add(doc); db.flush()
    for l in lignes:
        db.add(LigneDocument(document_id=doc.id, article_id=l["article_id"], quantite=l["quantite"],
                             prix_unitaire=l["prix_unitaire"], remise=l.get("remise", 0)))
    db.flush(); recalculer(doc, db); db.commit(); db.refresh(doc)
    return doc

CHAINE = {TypeDocument.DEVIS: TypeDocument.COMMANDE,
          TypeDocument.COMMANDE: TypeDocument.BON_LIVRAISON,
          TypeDocument.BON_LIVRAISON: TypeDocument.FACTURE}

def transformer(doc: Document, db: Session, nouveau: TypeDocument) -> Document:
    if CHAINE.get(doc.type) != nouveau:
        raise DocumentError(f"Transformation {doc.type.value} -> {nouveau.value} interdite")
    lignes = [{"article_id": l.article_id, "quantite": l.quantite,
               "prix_unitaire": float(l.prix_unitaire), "remise": float(l.remise)} for l in doc.lignes]
    return creer_document(db, doc.entite_id, doc.client_id, nouveau, lignes, doc.pdv_id, doc.id)

def appliquer_stock_bl(db: Session, bl: Document):
    if not bl.pdv_id: return
    for ligne in bl.lignes:
        stock = db.query(Stock).get((ligne.article_id, bl.pdv_id))
        qte = stock.quantite if stock else 0
        if qte < ligne.quantite:
            raise DocumentError(f"Stock insuffisant (dispo {qte}, demandé {ligne.quantite})")
        if not stock:
            stock = Stock(article_id=ligne.article_id, pdv_id=bl.pdv_id, quantite=0); db.add(stock)
        stock.quantite -= ligne.quantite
        db.add(MouvementStock(article_id=ligne.article_id, pdv_id=bl.pdv_id, type=TypeMouvement.SORTIE,
                              quantite=ligne.quantite, document_id=bl.id, commentaire=f"BL {bl.numero}"))
# ============================== API ==============================
app = FastAPI(title="GESCOM+GMAO multi-entités (métier IT)", version="1.0.0")

@app.get("/api/health")
def health(): return {"status": "ok"}

@app.post("/api/auth/token")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == form.username).first()
    if not u or not verify_password(form.password, u.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    return {"access_token": create_token(u.id, u.role.value), "token_type": "bearer"}

# --- Utilisateurs (création réservée aux admins) ---
@app.post("/api/users", response_model=UserOut, status_code=201)
def create_user(data: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_role("admin_societe", "admin_groupe"))):
    if data.role == Role.ADMIN_GROUPE and admin.role != Role.ADMIN_GROUPE:
        raise HTTPException(status_code=403, detail="Seul un admin groupe crée un admin groupe")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    u = User(email=data.email, nom=data.nom, role=data.role, hashed_password=hash_password(data.password))
    db.add(u); db.flush()
    for e in data.entite_ids: db.add(UserEntite(user_id=u.id, entite_id=e))
    for p in data.pdv_ids: db.add(UserPdv(user_id=u.id, pdv_id=p))
    db.commit(); db.refresh(u); return u

@app.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_role("admin_societe", "admin_groupe"))):
    return db.query(User).filter(User.actif == True).all()

# --- Entités + PDV (paramétrages généraux = admin groupe) ---
@app.post("/api/entites", response_model=EntiteOut, status_code=201)
def create_entite(data: EntiteIn, db: Session = Depends(get_db), admin: User = Depends(require_role("admin_groupe"))):
    if db.query(Entite).filter(Entite.nom == data.nom).first():
        raise HTTPException(status_code=409, detail="Nom déjà utilisé")
    e = Entite(**data.model_dump()); db.add(e); db.commit(); db.refresh(e); return e

@app.get("/api/entites", response_model=list[EntiteOut])
def list_entites(db: Session = Depends(get_db)):
    return db.query(Entite).filter(Entite.actif == True).all()

@app.post("/api/entites/{entite_id}/pdv", response_model=PdvOut, status_code=201)
def create_pdv(entite_id: int, data: PdvIn, db: Session = Depends(get_db), admin: User = Depends(require_role("admin_groupe"))):
    if not db.query(Entite).get(entite_id): raise HTTPException(status_code=404, detail="Entité introuvable")
    if db.query(PointDeVente).filter(PointDeVente.entite_id == entite_id, PointDeVente.nom == data.nom).first():
        raise HTTPException(status_code=409, detail="PDV déjà existant pour cette entité")
    p = PointDeVente(entite_id=entite_id, **data.model_dump()); db.add(p); db.commit(); db.refresh(p); return p

@app.get("/api/entites/{entite_id}/pdv", response_model=list[PdvOut])
def list_pdv(entite_id: int, db: Session = Depends(get_db)):
    return db.query(PointDeVente).filter(PointDeVente.entite_id == entite_id, PointDeVente.actif == True).all()

STRUCTURE = [("ORIGIN INFO SYSTEM", ["PDV Principal", "PDV Secondaire"]),
             ("SKYNET", ["PDV Skynet"]), ("ELEMIAH", [])]

@app.post("/api/seed/structure")
def seed(db: Session = Depends(get_db), admin: User = Depends(require_role("admin_groupe"))):
    out = []
    for nom, pdvs in STRUCTURE:
        e = db.query(Entite).filter(Entite.nom == nom).first() or Entite(nom=nom)
        if not e.id: db.add(e); db.flush()
        for pn in pdvs:
            if not db.query(PointDeVente).filter(PointDeVente.entite_id == e.id, PointDeVente.nom == pn).first():
                db.add(PointDeVente(entite_id=e.id, nom=pn))
        out.append({"entite": e.nom, "pdv": pdvs})
    db.commit(); return {"message": "Structure OK (idempotent)", "entites": out}

# --- Catalogue IT ---
@app.post("/api/articles", response_model=ArticleOut, status_code=201)
def create_article(data: ArticleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(Article).filter(Article.reference == data.reference).first():
        raise HTTPException(status_code=409, detail="Référence déjà existante")
    a = Article(**data.model_dump()); db.add(a); db.commit(); db.refresh(a); return a

@app.get("/api/articles", response_model=list[ArticleOut])
def list_articles(categorie: CategorieArticle | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Article).filter(Article.actif == True)
    if categorie: q = q.filter(Article.categorie == categorie)
    return q.order_by(Article.designation).all()

@app.patch("/api/articles/{aid}", response_model=ArticleOut)
def update_article(aid: int, prix_vente: float | None = None, actif: bool | None = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.query(Article).get(aid)
    if not a: raise HTTPException(status_code=404, detail="Article introuvable")
    if prix_vente is not None: a.prix_vente = prix_vente
    if actif is not None: a.actif = actif
    db.commit(); db.refresh(a); return a

# --- Stocks par PDV ---
def _get_stock(db, article_id, pdv_id) -> Stock:
    s = db.query(Stock).get((article_id, pdv_id))
    if not s:
        s = Stock(article_id=article_id, pdv_id=pdv_id, quantite=0); db.add(s)
    return s

@app.get("/api/stocks/pdv/{pdv_id}")
def stock_pdv(pdv_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(Stock, Article).join(Article, Stock.article_id == Article.id)
            .filter(Stock.pdv_id == pdv_id, Article.actif == True).all())
    return [{"reference": a.reference, "designation": a.designation, "quantite": s.quantite,
             "seuil_alerte": a.seuil_alerte, "alerte": s.quantite <= a.seuil_alerte} for s, a in rows]

@app.get("/api/stocks/consolide")
def stock_consolide(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(Article, Stock, PointDeVente).join(Stock, Stock.article_id == Article.id)
            .join(PointDeVente, Stock.pdv_id == PointDeVente.id).filter(Article.actif == True).all())
    agg = {}
    for a, s, p in rows:
        agg.setdefault(a.id, {"article": a, "total": 0, "par_pdv": []})
        agg[a.id]["total"] += s.quantite
        agg[a.id]["par_pdv"].append({"pdv": p.nom, "entite": p.entite.nom, "quantite": s.quantite})
    return [{"reference": v["article"].reference, "designation": v["article"].designation,
             "quantite_totale": v["total"], "par_pdv": v["par_pdv"]} for v in agg.values()]

@app.post("/api/stocks/pdv/{pdv_id}/mouvements", status_code=201)
def mouvement(pdv_id: int, data: MouvementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Article).get(data.article_id): raise HTTPException(status_code=404, detail="Article introuvable")
    if not db.query(PointDeVente).get(pdv_id): raise HTTPException(status_code=404, detail="PDV introuvable")
    s = _get_stock(db, data.article_id, pdv_id)
    if data.type == TypeMouvement.TRANSFERT_OUT:
        if not data.pdv_cible_id or data.pdv_cible_id == pdv_id:
            raise HTTPException(status_code=400, detail="pdv_cible_id requis et différent")
        if s.quantite < data.quantite: raise HTTPException(status_code=409, detail="Stock insuffisant")
        s.quantite -= data.quantite
        db.add(MouvementStock(article_id=data.article_id, pdv_id=pdv_id, type=data.type,
                              quantite=data.quantite, pdv_cible_id=data.pdv_cible_id, commentaire=data.commentaire))
        _get_stock(db, data.article_id, data.pdv_cible_id).quantite += data.quantite
        db.add(MouvementStock(article_id=data.article_id, pdv_id=data.pdv_cible_id, type=TypeMouvement.TRANSFERT_IN,
                              quantite=data.quantite, pdv_cible_id=pdv_id, commentaire=data.commentaire))
    elif data.type == TypeMouvement.SORTIE:
        if s.quantite < data.quantite: raise HTTPException(status_code=409, detail="Stock insuffisant (négatif interdit)")
        s.quantite -= data.quantite
        db.add(MouvementStock(article_id=data.article_id, pdv_id=pdv_id, type=data.type,
                              quantite=data.quantite, commentaire=data.commentaire))
    else:
        s.quantite += data.quantite
        db.add(MouvementStock(article_id=data.article_id, pdv_id=pdv_id, type=data.type,
                              quantite=data.quantite, commentaire=data.commentaire))
    db.commit()
    return {"article_id": data.article_id, "pdv_id": pdv_id, "quantite_apres": s.quantite}
# --- Clients ---
@app.post("/api/entites/{entite_id}/clients", response_model=ClientOut, status_code=201)
def create_client(entite_id: int, data: ClientIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Entite).get(entite_id): raise HTTPException(status_code=404, detail="Entité introuvable")
    c = Client(entite_id=entite_id, **data.model_dump()); db.add(c); db.commit(); db.refresh(c); return c

@app.get("/api/entites/{entite_id}/clients", response_model=list[ClientOut])
def list_clients(entite_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Client).filter(Client.entite_id == entite_id).all()

@app.post("/api/clients/{client_id}/contacts", status_code=201)
def add_contact(client_id: int, nom: str, email: str | None = None, telephone: str | None = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Client).get(client_id): raise HTTPException(status_code=404, detail="Client introuvable")
    c = ContactClient(client_id=client_id, nom=nom, email=email, telephone=telephone)
    db.add(c); db.commit(); return {"id": c.id, "nom": nom}

# --- Chaîne documentaire : devis -> commande -> BL -> facture ---
@app.post("/api/documents", response_model=DocumentOut, status_code=201)
def create_document(data: DocumentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for l in data.lignes:
        if not db.query(Article).get(l.article_id): raise HTTPException(status_code=404, detail="Article introuvable")
    return creer_document(db, data.entite_id, data.client_id, data.type,
                          [l.model_dump() for l in data.lignes], data.pdv_id)

@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(entite_id: int | None = None, type: TypeDocument | None = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Document)
    if entite_id: q = q.filter(Document.entite_id == entite_id)
    if type: q = q.filter(Document.type == type)
    return q.order_by(Document.date.desc()).all()

@app.post("/api/documents/{doc_id}/transformer", response_model=DocumentOut)
def transform(doc_id: int, nouvelle_type: TypeDocument, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).get(doc_id)
    if not doc: raise HTTPException(status_code=404, detail="Document introuvable")
    try:
        nouveau = transformer(doc, db, nouvelle_type)
        if nouvelle_type == TypeDocument.BON_LIVRAISON:
            appliquer_stock_bl(db, nouveau)  # sortie de stock à la validation du BL
            db.commit(); db.refresh(nouveau)
    except DocumentError as e:
        db.rollback(); raise HTTPException(status_code=409, detail=str(e))
    return nouveau

# --- GMAO : parc IT, tickets SAV, contrats ---
@app.post("/api/gmao/equipements", response_model=EquipementOut, status_code=201)
def create_equipement(data: EquipementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    e = Equipement(**data.model_dump()); db.add(e); db.commit(); db.refresh(e); return e

@app.get("/api/gmao/equipements", response_model=list[EquipementOut])
def list_equipements(client_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Equipement)
    if client_id: q = q.filter(Equipement.client_id == client_id)
    return q.all()

@app.post("/api/gmao/tickets", response_model=TicketOut, status_code=201)
def create_ticket(data: TicketIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = TicketSAV(**data.model_dump()); db.add(t); db.commit(); db.refresh(t); return t

@app.get("/api/gmao/tickets", response_model=list[TicketOut])
def list_tickets(statut: StatutTicket | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(TicketSAV)
    if statut: q = q.filter(TicketSAV.statut == statut)
    return q.order_by(TicketSAV.date_ouverture.desc()).all()

@app.patch("/api/gmao/tickets/{tid}", response_model=TicketOut)
def update_ticket(tid: int, statut: StatutTicket | None = None, technicien_id: int | None = None,
                  temps_passe_minutes: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.query(TicketSAV).get(tid)
    if not t: raise HTTPException(status_code=404, detail="Ticket introuvable")
    if statut: t.statut = statut
    if technicien_id is not None: t.technicien_id = technicien_id
    if temps_passe_minutes is not None: t.temps_passe_minutes = temps_passe_minutes
    db.commit(); db.refresh(t); return t

@app.post("/api/gmao/contrats", response_model=ContratOut, status_code=201)
def create_contrat(data: ContratIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(ContratMaintenance).filter(ContratMaintenance.entite_id == data.entite_id).count()
    c = ContratMaintenance(entite_id=data.entite_id, client_id=data.client_id, libelle=data.libelle,
                           numero=f"CTR-{datetime.now().year}-{n + 1:04d}", date_debut=datetime.utcnow(),
                           montant_ht=data.montant_ht, periodicite_jours=data.periodicite_jours,
                           delai_intervention_heures=data.delai_intervention_heures)
    db.add(c); db.commit(); db.refresh(c); return c

@app.get("/api/gmao/contrats", response_model=list[ContratOut])
def list_contrats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ContratMaintenance).filter(ContratMaintenance.actif == True).all()

# --- Dashboard groupe (les 3 sociétés consolidées) ---
@app.get("/api/dashboard/groupe")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ca = (db.query(Entite.nom, func.sum(Document.total_ttc)).join(Document, Document.entite_id == Entite.id)
          .filter(Document.type == TypeDocument.FACTURE).group_by(Entite.nom).all())
    return {
        "ca_ttc_par_entite": {n: float(t) for n, t in ca},
        "stock_total_groupe": db.query(func.coalesce(func.sum(Stock.quantite), 0)).scalar(),
        "tickets_ouverts": db.query(func.count(TicketSAV.id)).filter(
            TicketSAV.statut.in_([StatutTicket.OUVERT, StatutTicket.EN_COURS])).scalar(),
        "factures_impayees": db.query(func.count(Document.id)).filter(
            Document.type == TypeDocument.FACTURE, Document.statut != StatutDocument.PAYE).scalar(),
    }

# --- E-commerce (vente en ligne prévue) ---
@app.get("/api/shop/catalogue")
def shop_catalogue(db: Session = Depends(get_db)):
    return [{"reference": a.reference, "designation": a.designation, "categorie": a.categorie.value,
             "prix_vente": float(a.prix_vente), "tva_taux": float(a.tva_taux)}
            for a in db.query(Article).filter(Article.actif == True).all()]

@app.get("/api/shop/stock/{reference}")
def shop_stock(reference: str, db: Session = Depends(get_db)):
    a = db.query(Article).filter(Article.reference == reference).first()
    if not a: raise HTTPException(status_code=404, detail="Article introuvable")
    rows = (db.query(Stock, PointDeVente).join(PointDeVente, Stock.pdv_id == PointDeVente.id)
            .filter(Stock.article_id == a.id).all())
    return {"reference": reference, "disponible_total": sum(s.quantite for s, _ in rows),
            "par_pdv": [{"pdv": p.nom, "quantite": s.quantite} for s, p in rows]}

@app.post("/api/shop/commandes", status_code=201)
def shop_commande(data: CommandeShop, db: Session = Depends(get_db)):
    lignes = []
    for l in data.lignes:
        a = db.query(Article).filter(Article.reference == l.reference).first()
        if not a: raise HTTPException(status_code=404, detail=f"Référence inconnue: {l.reference}")
        lignes.append({"article_id": a.id, "quantite": l.quantite, "prix_unitaire": float(a.prix_vente)})
    doc = creer_document(db, data.entite_id, data.client_id, TypeDocument.COMMANDE, lignes, data.pdv_id)
    return {"numero": doc.numero, "total_ttc": float(doc.total_ttc), "statut": doc.statut.value}
