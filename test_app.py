"""Tests du GESCOM+GMAO monolithe — lancer : python -m pytest test_app.py -q"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as A


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    A.Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)

    def override():
        db = S()
        try:
            yield db
        finally:
            db.close()

    A.app.dependency_overrides[A.get_db] = override
    A.engine = engine
    yield TestClient(A.app)
    A.app.dependency_overrides.clear()


def _mk_admin_and_token(client):
    db = next(A.app.dependency_overrides[A.get_db]())
    u = A.User(email="admin@test.fr", nom="Admin", role=A.Role.ADMIN_GROUPE,
               hashed_password=A.hash_password("password123"))
    db.add(u); db.commit()
    r = client.post("/api/auth/token", data={"username": "admin@test.fr", "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_structure_3_societes(client):
    auth = _mk_admin_and_token(client)
    client.post("/api/seed/structure", headers=auth)
    entites = {e["nom"]: e["id"] for e in client.get("/api/entites").json()}
    assert sorted(entites) == ["ELEMIAH", "ORIGIN INFO SYSTEM", "SKYNET"]
    assert len(client.get(f"/api/entites/{entites['ORIGIN INFO SYSTEM']}/pdv").json()) == 2
    assert len(client.get(f"/api/entites/{entites['SKYNET']}/pdv").json()) == 1
    assert len(client.get(f"/api/entites/{entites['ELEMIAH']}/pdv").json()) == 0


def test_catalogue_stocks_chaine_facture(client):
    auth = _mk_admin_and_token(client)
    client.post("/api/seed/structure", headers=auth)
    origin = [e for e in client.get("/api/entites").json() if e["nom"] == "ORIGIN INFO SYSTEM"][0]["id"]
    pdv1 = client.get(f"/api/entites/{origin}/pdv").json()[0]["id"]

    art = client.post("/api/articles", headers=auth, json={
        "reference": "PC-1", "designation": "PC portable", "categorie": "materiel",
        "prix_vente": 1000, "seuil_alerte": 2}).json()
    assert client.post(f"/api/stocks/pdv/{pdv1}/mouvements", headers=auth, json={
        "article_id": art["id"], "quantite": 5, "type": "entree"}).json()["quantite_apres"] == 5

    cl = client.post(f"/api/entites/{origin}/clients", headers=auth, json={"nom": "Client A"}).json()

    devis = client.post("/api/documents", headers=auth, json={
        "entite_id": origin, "client_id": cl["id"], "type": "devis", "pdv_id": pdv1,
        "lignes": [{"article_id": art["id"], "quantite": 2, "prix_unitaire": 1000}]}).json()
    assert devis["total_ttc"] == 2400  # 2000 HT + 20 % TVA

    cmd = client.post(f"/api/documents/{devis['id']}/transformer?nouvelle_type=commande", headers=auth).json()
    bl = client.post(f"/api/documents/{cmd['id']}/transformer?nouvelle_type=bon_livraison", headers=auth).json()
    assert bl["type"] == "bon_livraison"
    assert client.get(f"/api/stocks/pdv/{pdv1}", headers=auth).json()[0]["quantite"] == 3
    facture = client.post(f"/api/documents/{bl['id']}/transformer?nouvelle_type=facture", headers=auth).json()
    assert facture["type"] == "facture"

    dash = client.get("/api/dashboard/groupe", headers=auth).json()
    assert dash["stock_total_groupe"] == 3


def test_transfert_inter_pdv_et_vue_groupe(client):
    auth = _mk_admin_and_token(client)
    client.post("/api/seed/structure", headers=auth)
    origin = [e for e in client.get("/api/entites").json() if e["nom"] == "ORIGIN INFO SYSTEM"][0]["id"]
    skynet = [e for e in client.get("/api/entites").json() if e["nom"] == "SKYNET"][0]["id"]
    pdv1, pdv2 = [p["id"] for p in client.get(f"/api/entites/{origin}/pdv").json()]
    pdv3 = client.get(f"/api/entites/{skynet}/pdv").json()[0]["id"]
    art = client.post("/api/articles", headers=auth, json={
        "reference": "PC-1", "designation": "PC", "prix_vente": 1000}).json()
    client.post(f"/api/stocks/pdv/{pdv1}/mouvements", headers=auth,
                json={"article_id": art["id"], "quantite": 8, "type": "entree"})
    r = client.post(f"/api/stocks/pdv/{pdv1}/mouvements", headers=auth, json={
        "article_id": art["id"], "quantite": 3, "type": "transfert_out", "pdv_cible_id": pdv2})
    assert r.json()["quantite_apres"] == 5
    client.post(f"/api/stocks/pdv/{pdv3}/mouvements", headers=auth,
                json={"article_id": art["id"], "quantite": 4, "type": "entree"})
    conso = client.get("/api/stocks/consolide", headers=auth).json()
    item = [x for x in conso if x["reference"] == "PC-1"][0]
    assert item["quantite_totale"] == 12  # 5 (pdv1) + 3 (pdv2) + 4 (pdv3)
    assert {p["pdv"] for p in item["par_pdv"]} == {"PDV Principal", "PDV Secondaire", "PDV Skynet"}


def test_gmao_ticket_contrat_sla(client):
    auth = _mk_admin_and_token(client)
    client.post("/api/seed/structure", headers=auth)
    origin = [e for e in client.get("/api/entites").json() if e["nom"] == "ORIGIN INFO SYSTEM"][0]["id"]
    cl = client.post(f"/api/entites/{origin}/clients", headers=auth, json={"nom": "Client A"}).json()
    eq = client.post("/api/gmao/equipements", headers=auth, json={
        "entite_id": origin, "client_id": cl["id"], "designation": "Serveur", "numero_serie": "SN1"}).json()
    t = client.post("/api/gmao/tickets", headers=auth, json={
        "entite_id": origin, "client_id": cl["id"], "sujet": "Panne", "equipement_id": eq["id"],
        "priorite": "haute"}).json()
    assert t["statut"] == "ouvert" and t["priorite"] == "haute"
    c = client.post("/api/gmao/contrats", headers=auth, json={
        "entite_id": origin, "client_id": cl["id"], "libelle": "Maintenance", "montant_ht": 500,
        "delai_intervention_heures": 4}).json()
    assert c["delai_intervention_heures"] == 4


def test_employe_ne_peut_pas_creer_user(client):
    db = next(A.app.dependency_overrides[A.get_db]())
    db.add(A.User(email="emp@test.fr", nom="Emp", role=A.Role.EMPLOYE,
                  hashed_password=A.hash_password("password123")))
    db.commit()
    r = client.post("/api/auth/token", data={"username": "emp@test.fr", "password": "password123"})
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/users", headers=auth,
                    json={"email": "x@x.fr", "password": "password123", "nom": "X"})
    assert r.status_code == 403


def test_shop(client):
    auth = _mk_admin_and_token(client)
    client.post("/api/seed/structure", headers=auth)
    origin = [e for e in client.get("/api/entites").json() if e["nom"] == "ORIGIN INFO SYSTEM"][0]["id"]
    pdv1 = client.get(f"/api/entites/{origin}/pdv").json()[0]["id"]
    art = client.post("/api/articles", headers=auth, json={
        "reference": "PC-1", "designation": "PC", "prix_vente": 1000}).json()
    client.post(f"/api/stocks/pdv/{pdv1}/mouvements", headers=auth,
                json={"article_id": art["id"], "quantite": 3, "type": "entree"})
    cl = client.post(f"/api/entites/{origin}/clients", headers=auth, json={"nom": "Client Web"}).json()
    assert client.get("/api/shop/stock/PC-1").json()["disponible_total"] == 3
    r = client.post("/api/shop/commandes", json={
        "entite_id": origin, "client_id": cl["id"], "pdv_id": pdv1,
        "lignes": [{"reference": "PC-1", "quantite": 1}]})
    assert r.status_code == 201 and r.json()["total_ttc"] == 1200
