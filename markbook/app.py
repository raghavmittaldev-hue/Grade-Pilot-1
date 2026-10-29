"""MarkBook API: collect student marks, view per-student performance and class statistics."""
import os
import sqlite3
import statistics

from flask import Flask, g, jsonify, request, send_from_directory

PASS_MARK = 40


def grade_for(pct):
    if pct is None:
        return None
    for cutoff, letter in ((80, "A"), (65, "B"), (50, "C"), (PASS_MARK, "D")):
        if pct >= cutoff:
            return letter
    return "F"


def create_app(db_path=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DATABASE"] = db_path or os.environ.get("DATABASE_PATH", "markbook.db")
    allowed_origin = os.environ.get("CORS_ORIGINS", "*")

    @app.after_request
    def cors(resp):
        if request.path.startswith("/api/"):
            resp.headers["Access-Control-Allow-Origin"] = allowed_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_e):
        d = g.pop("db", None)
        if d is not None:
            d.close()

    with app.app_context():
        c = db()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                roll_no TEXT NOT NULL UNIQUE COLLATE NOCASE
            );
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL COLLATE NOCASE,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
                UNIQUE (student_id, subject)
            );
            """
        )
        c.commit()

    def err(msg, code):
        return jsonify({"error": msg}), code

    # ---------- data assembly ----------
    def all_students(q=None):
        rows = db().execute("SELECT * FROM students ORDER BY name COLLATE NOCASE").fetchall()
        marks = db().execute("SELECT * FROM marks ORDER BY subject COLLATE NOCASE").fetchall()
        by_student = {}
        for m in marks:
            by_student.setdefault(m["student_id"], []).append(
                {"id": m["id"], "subject": m["subject"], "score": m["score"]}
            )
        out = []
        for r in rows:
            ms = by_student.get(r["id"], [])
            avg = round(sum(m["score"] for m in ms) / len(ms), 2) if ms else None
            out.append({"id": r["id"], "name": r["name"], "roll_no": r["roll_no"],
                        "marks": ms, "average": avg, "grade": grade_for(avg), "rank": None})
        ranked = sorted((s for s in out if s["average"] is not None), key=lambda s: -s["average"])
        last_avg, last_rank = None, 0
        for i, s in enumerate(ranked, 1):  # ties share a rank
            if s["average"] != last_avg:
                last_rank, last_avg = i, s["average"]
            s["rank"] = last_rank
        if q:
            ql = q.lower()
            out = [s for s in out if ql in s["name"].lower() or ql in s["roll_no"].lower()]
        return out

    def one_student(sid):
        return next((s for s in all_students() if s["id"] == sid), None)

    # ---------- validation ----------
    def parse_json():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None

    def clean_student(data, partial):
        out = {}
        for field, limit in (("name", 80), ("roll_no", 30)):
            if field in data or not partial:
                v = data.get(field)
                if not isinstance(v, str) or not v.strip():
                    return None, f"'{field}' is required and must be a non-empty string."
                if len(v.strip()) > limit:
                    return None, f"'{field}' must be {limit} characters or fewer."
                out[field] = v.strip()
        return out, None

    def clean_score(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
            return None
        return float(v)

    # ---------- frontend ----------
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ---------- students ----------
    @app.get("/api/students")
    def list_students():
        return jsonify(all_students(request.args.get("q", "").strip()))

    @app.get("/api/students/<int:sid>")
    def get_student(sid):
        s = one_student(sid)
        return jsonify(s) if s else err(f"Student {sid} not found.", 404)

    @app.post("/api/students")
    def create_student():
        data = parse_json()
        if data is None:
            return err("Request body must be a JSON object.", 400)
        clean, e = clean_student(data, partial=False)
        if e:
            return err(e, 400)
        try:
            cur = db().execute("INSERT INTO students (name, roll_no) VALUES (?, ?)",
                               (clean["name"], clean["roll_no"]))
            db().commit()
        except sqlite3.IntegrityError:
            return err(f"Roll number '{clean['roll_no']}' already exists.", 409)
        resp = jsonify(one_student(cur.lastrowid))
        resp.status_code = 201
        resp.headers["Location"] = f"/api/students/{cur.lastrowid}"
        return resp

    def update_student(sid, partial):
        if one_student(sid) is None:
            return err(f"Student {sid} not found.", 404)
        data = parse_json()
        if data is None:
            return err("Request body must be a JSON object.", 400)
        clean, e = clean_student(data, partial)
        if e:
            return err(e, 400)
        if not clean:
            return err("No updatable fields supplied.", 400)
        sets = ", ".join(f"{k} = ?" for k in clean)
        try:
            db().execute(f"UPDATE students SET {sets} WHERE id = ?", (*clean.values(), sid))
            db().commit()
        except sqlite3.IntegrityError:
            return err("That roll number already exists.", 409)
        return jsonify(one_student(sid))

    @app.put("/api/students/<int:sid>")
    def put_student(sid):
        return update_student(sid, partial=False)

    @app.patch("/api/students/<int:sid>")
    def patch_student(sid):
        return update_student(sid, partial=True)

    @app.delete("/api/students/<int:sid>")
    def delete_student(sid):
        if one_student(sid) is None:
            return err(f"Student {sid} not found.", 404)
        db().execute("DELETE FROM students WHERE id = ?", (sid,))
        db().commit()
        return "", 204

    # ---------- marks ----------
    @app.post("/api/students/<int:sid>/marks")
    def add_mark(sid):
        if one_student(sid) is None:
            return err(f"Student {sid} not found.", 404)
        data = parse_json()
        if data is None:
            return err("Request body must be a JSON object.", 400)
        subject = data.get("subject")
        if not isinstance(subject, str) or not subject.strip() or len(subject.strip()) > 50:
            return err("'subject' is required (1-50 characters).", 400)
        score = clean_score(data.get("score"))
        if score is None:
            return err("'score' must be a number between 0 and 100.", 400)
        try:
            db().execute("INSERT INTO marks (student_id, subject, score) VALUES (?, ?, ?)",
                         (sid, subject.strip(), score))
            db().commit()
        except sqlite3.IntegrityError:
            return err(f"Marks for '{subject.strip()}' already exist. Edit the existing entry.", 409)
        resp = jsonify(one_student(sid))
        resp.status_code = 201
        return resp

    @app.patch("/api/marks/<int:mid>")
    def patch_mark(mid):
        row = db().execute("SELECT student_id FROM marks WHERE id = ?", (mid,)).fetchone()
        if row is None:
            return err(f"Mark {mid} not found.", 404)
        data = parse_json()
        score = clean_score(data.get("score")) if data else None
        if score is None:
            return err("'score' must be a number between 0 and 100.", 400)
        db().execute("UPDATE marks SET score = ? WHERE id = ?", (score, mid))
        db().commit()
        return jsonify(one_student(row["student_id"]))

    @app.delete("/api/marks/<int:mid>")
    def delete_mark(mid):
        if db().execute("SELECT 1 FROM marks WHERE id = ?", (mid,)).fetchone() is None:
            return err(f"Mark {mid} not found.", 404)
        db().execute("DELETE FROM marks WHERE id = ?", (mid,))
        db().commit()
        return "", 204

    # ---------- class statistics ----------
    @app.get("/api/stats")
    def stats():
        students = all_students()
        scored = [s for s in students if s["average"] is not None]
        avgs = [s["average"] for s in scored]
        subjects = {}
        for s in students:
            for m in s["marks"]:
                subjects.setdefault(m["subject"].title(), []).append(m["score"])
        subject_stats = [
            {"subject": name, "count": len(v), "average": round(sum(v) / len(v), 2),
             "highest": max(v), "lowest": min(v),
             "pass_rate": round(100 * sum(x >= PASS_MARK for x in v) / len(v), 1)}
            for name, v in sorted(subjects.items())
        ]
        dist = {k: 0 for k in "ABCDF"}
        for s in scored:
            dist[s["grade"]] += 1
        ranked = sorted(scored, key=lambda s: -s["average"])
        brief = lambda s: {"id": s["id"], "name": s["name"], "roll_no": s["roll_no"], "average": s["average"]}
        return jsonify({
            "total_students": len(students),
            "students_with_marks": len(scored),
            "class_average": round(statistics.mean(avgs), 2) if avgs else None,
            "median": round(statistics.median(avgs), 2) if avgs else None,
            "std_dev": round(statistics.pstdev(avgs), 2) if len(avgs) > 1 else 0 if avgs else None,
            "pass_rate": round(100 * sum(a >= PASS_MARK for a in avgs) / len(avgs), 1) if avgs else None,
            "highest": brief(ranked[0]) if ranked else None,
            "lowest": brief(ranked[-1]) if ranked else None,
            "top_performers": [brief(s) for s in ranked[:3]],
            "needs_attention": [brief(s) for s in ranked[::-1] if s["average"] < PASS_MARK][:5],
            "grade_distribution": dist,
            "subjects": subject_stats,
        })

    @app.errorhandler(404)
    def nf(_e):
        return err("Resource not found.", 404)

    @app.errorhandler(405)
    def mna(_e):
        return err("Method not allowed for this route.", 405)

    @app.errorhandler(500)
    def ise(_e):
        return err("Internal server error.", 500)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
