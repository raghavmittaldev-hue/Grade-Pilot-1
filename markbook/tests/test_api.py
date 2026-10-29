import os
import tempfile
import unittest

from app import create_app


class MarkBookTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.c = create_app(self.path).test_client()

    def tearDown(self):
        os.remove(self.path)

    def student(self, name="Asha", roll="CS01"):
        return self.c.post("/api/students", json={"name": name, "roll_no": roll})

    def mark(self, sid, subject, score):
        return self.c.post(f"/api/students/{sid}/marks", json={"subject": subject, "score": score})

    def test_student_crud(self):
        r = self.student()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.student(roll="cs01").status_code, 409)
        self.assertEqual(self.c.post("/api/students", json={"name": ""}).status_code, 400)
        self.assertEqual(self.c.patch("/api/students/1", json={"name": "Asha K"}).get_json()["name"], "Asha K")
        self.assertEqual(self.c.put("/api/students/1", json={"name": "X"}).status_code, 400)
        self.assertEqual(self.c.delete("/api/students/1").status_code, 204)
        self.assertEqual(self.c.get("/api/students/1").status_code, 404)

    def test_marks_validation_and_duplicates(self):
        self.student()
        self.assertEqual(self.mark(1, "Maths", 88).status_code, 201)
        self.assertEqual(self.mark(1, "maths", 90).status_code, 409)
        self.assertEqual(self.mark(1, "Physics", 101).status_code, 400)
        self.assertEqual(self.mark(1, "Physics", "x").status_code, 400)
        self.assertEqual(self.mark(9, "Physics", 50).status_code, 404)

    def test_average_grade_rank(self):
        self.student("A", "1"); self.student("B", "2")
        self.mark(1, "Maths", 90); self.mark(1, "Physics", 70)
        self.mark(2, "Maths", 30)
        s = {x["name"]: x for x in self.c.get("/api/students").get_json()}
        self.assertEqual(s["A"]["average"], 80.0)
        self.assertEqual(s["A"]["grade"], "A")
        self.assertEqual(s["A"]["rank"], 1)
        self.assertEqual(s["B"]["grade"], "F")
        self.assertEqual(s["B"]["rank"], 2)

    def test_patch_delete_mark_and_cascade(self):
        self.student(); self.mark(1, "Maths", 50)
        mid = self.c.get("/api/students/1").get_json()["marks"][0]["id"]
        self.assertEqual(self.c.patch(f"/api/marks/{mid}", json={"score": 75}).get_json()["average"], 75)
        self.assertEqual(self.c.patch(f"/api/marks/{mid}", json={"score": -1}).status_code, 400)
        self.assertEqual(self.c.delete(f"/api/marks/{mid}").status_code, 204)
        self.mark(1, "Maths", 60)
        self.c.delete("/api/students/1")
        self.assertEqual(self.c.get("/api/stats").get_json()["total_students"], 0)

    def test_stats(self):
        self.assertIsNone(self.c.get("/api/stats").get_json()["class_average"])
        self.student("A", "1"); self.student("B", "2"); self.student("C", "3")
        self.mark(1, "Maths", 90); self.mark(2, "Maths", 60); self.mark(3, "Maths", 30)
        st = self.c.get("/api/stats").get_json()
        self.assertEqual(st["class_average"], 60.0)
        self.assertEqual(st["median"], 60.0)
        self.assertEqual(st["highest"]["name"], "A")
        self.assertEqual(st["lowest"]["name"], "C")
        self.assertEqual(st["pass_rate"], 66.7)
        self.assertEqual(st["grade_distribution"], {"A": 1, "B": 0, "C": 1, "D": 0, "F": 1})
        self.assertEqual(st["subjects"][0]["subject"], "Maths")
        self.assertEqual(st["needs_attention"][0]["name"], "C")

    def test_search_and_errors(self):
        self.student("Asha", "CS01"); self.student("Ravi", "CS02")
        self.assertEqual(len(self.c.get("/api/students?q=rav").get_json()), 1)
        self.assertEqual(self.c.post("/api/stats").status_code, 405)
        self.assertIn("error", self.c.get("/api/nope").get_json())


if __name__ == "__main__":
    unittest.main()
