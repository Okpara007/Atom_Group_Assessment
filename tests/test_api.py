import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
import app.routes.documents as documents
import app.services.persistence as persistence


async def _noop_background_worker():
    return


async def _noop_enqueue(_document_id: str):
    return


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.uploads_dir = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(self.uploads_dir, exist_ok=True)

        self.patches = [
            patch.object(persistence, "DB_PATH", self.db_path),
            patch.object(documents, "UPLOADS_DIR", self.uploads_dir),
            patch.object(main, "background_worker", _noop_background_worker),
            patch.object(documents, "add_document_to_queue", _noop_enqueue),
        ]
        for p in self.patches:
            p.start()

        persistence.create_tables()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp_dir.cleanup()

    def _auth_headers(self):
        response = self.client.post(
            "/auth/login",
            json={"username": "user1", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_auth_and_protected_access(self):
        invalid_login = self.client.post(
            "/auth/login",
            json={"username": "user1", "password": "wrong"},
        )
        self.assertEqual(invalid_login.status_code, 401)

        protected_without_token = self.client.get("/documents")
        self.assertEqual(protected_without_token.status_code, 401)

        protected_with_token = self.client.get("/documents", headers=self._auth_headers())
        self.assertEqual(protected_with_token.status_code, 200)
        self.assertEqual(protected_with_token.json()["documents"], [])

    def test_upload_validation_and_storage_structure(self):
        headers = self._auth_headers()
        files = [
            ("files", ("valid.txt", b"hello world", "text/plain")),
            ("files", ("invalid.csv", b"a,b,c", "text/csv")),
        ]

        response = self.client.post("/upload", headers=headers, files=files)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["uploaded_count"], 1)
        self.assertEqual(body["failed_count"], 1)

        uploaded = body["uploaded_documents"][0]
        self.assertEqual(uploaded["filename"], "valid.txt")
        self.assertEqual(uploaded["status"], "pending")
        self.assertTrue(os.path.exists(uploaded["stored_path"]))

        parent_dir = os.path.basename(os.path.dirname(uploaded["stored_path"]))
        self.assertEqual(parent_dir, uploaded["document_id"])

        self.assertIn("Invalid file type", body["errors"][0]["error"])

    def test_documents_status_filter(self):
        headers = self._auth_headers()
        files = [("files", ("doc.txt", b"test document", "text/plain"))]
        upload_response = self.client.post("/upload", headers=headers, files=files)
        self.assertEqual(upload_response.status_code, 200)

        pending_response = self.client.get("/documents?status=pending", headers=headers)
        self.assertEqual(pending_response.status_code, 200)
        pending_docs = pending_response.json()["documents"]
        self.assertGreaterEqual(len(pending_docs), 1)
        self.assertTrue(all(doc["current_status"] == "pending" for doc in pending_docs))

        invalid_filter = self.client.get("/documents?status=unknown", headers=headers)
        self.assertEqual(invalid_filter.status_code, 400)


if __name__ == "__main__":
    unittest.main()
