# Cahier des charges — GESCOM + GMAO multi-entités (métier IT)

## Contexte
Remplacer GMCWeb (> 600 €/mois). Logiciel sur mesure pour 3 sociétés liées,
plusieurs points de vente, GESCOM + GMAO intégrés.

## Périmètre
- ORIGIN INFO SYSTEM : 2 PDV | SKYNET : 1 PDV | ELEMIAH : facturation + GMAO sans PDV
- Stocks séparés par PDV + vue consolidée groupe + transferts inter-PDV
- Vente en ligne prévue (API prête, pas active)

## Rôles
- Employé : lecture + saisie sur ses PDV
- Admin société : utilisateurs et tarifs de sa société
- Admin groupe : seul habilité aux paramétrages généraux

## Modules GESCOM
Clients (multi-adresses, contacts), catalogue IT (matériel/licence/prestation/forfait),
stocks (entrées/sorties/transferts/seuils/inventaires), chaîne
devis → commande → BL → facture → règlement (stock auto), relances impayés,
facturation électronique 2026.

## Modules GMAO
Parc IT client (n° série, garantie), licences (expiration, postes), tickets SAV
(priorités, technicien, temps passé), contrats de maintenance (SLA, facturation récurrente).

## Groupe
CA consolidé par entité, ventes inter-sociétés, dashboards.

## Stack
FastAPI + SQLAlchemy (SQLite dev / PostgreSQL prod) + JWT/RBAC + pytest. React à venir.
