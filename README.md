# noune-testgescom

Logiciel GESCOM + GMAO multi-entités pour le métier IT (matériel, licences, SAV, contrats).

## Structure
- 3 sociétés : ORIGIN INFO SYSTEM (2 PDV), SKYNET (1 PDV), ELEMIAH (facturation + GMAO)
- `docs/` : cahier des charges + architecture
- `app.py` : backend complet (API FastAPI monolithe)
- `test_app.py` : 7 tests automatisés

## Lancer en local
```bash
pip install -r requirements.txt
python -m pytest test_app.py -q      # 7 tests doivent passer
uvicorn app:app --reload             # http://localhost:8000/docs
