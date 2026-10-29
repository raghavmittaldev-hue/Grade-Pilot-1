# MarkBook

```bash
pip install -r requirements.txt
python app.py                                   # http://127.0.0.1:5000
python -m unittest discover -s tests -t .       # tests
```

Deploy: push to GitHub, then Render > New > Blueprint (uses render.yaml). Also ships with Procfile and Dockerfile.
Separate frontend host: set CORS_ORIGINS on the API and `window.API_BASE` before app.js.

| Method | Route |
|---|---|
| GET, POST | /api/students |
| GET, PUT, PATCH, DELETE | /api/students/<id> |
| POST | /api/students/<id>/marks |
| PATCH, DELETE | /api/marks/<id> |
| GET | /api/stats |
| GET | /api/health |
