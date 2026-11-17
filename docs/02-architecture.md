# Architecture — GESCOM + GMAO multi-entités

## Modèle de données
- Entite 1—* PointDeVente 1—* Stock
- Entite 1—* Client / Article / Document / Equipement / Contrat
- Document : Devis → Commande → BonLivraison → Facture (lignes = mouvements de stock sur le PDV)
- User + Role (employe | admin_societe | admin_groupe), rattaché aux entités/PDV

## Règles clés
- 1 document = 1 entité + 1 PDV (si vente physique)
- Transfert inter-PDV = 2 mouvements de stock
- Visibilité : employé = ses PDV ; admin société = sa société ; admin groupe = tout + paramétrages

## Stack
FastAPI + SQLAlchemy (SQLite en dev, PostgreSQL en prod) + JWT/RBAC + pytest.
Frontend React à venir. 7 tests automatisés.
