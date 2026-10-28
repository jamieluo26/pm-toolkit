"""HTTP boundary tests; core DOCX lifecycle is covered by runtime tests."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import sys
sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
sys.path.insert(0, str(Path(__file__).absolute().parent))
from pm_workbench import Workbench, Server, APIError, MAX_BODY, write_new
from test_workbench_runtime import draft


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pm_workbench_http_", dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.tmp.cleanup)
        self.wb = Workbench(Path(self.tmp.name) / "workspace")
        self.server = Server(("127.0.0.1", 0), self.wb)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def request(self, method, path, value=None, headers=None, raw=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        base = {"Host": self.server.expected_host}
        if method == "POST":
            base.update({"Origin": self.server.expected_origin, "X-Workbench-Token": self.wb.token, "Content-Type": "application/json"})
        base.update(headers or {})
        body = raw if raw is not None else json.dumps(value).encode() if value is not None else None
        conn.request(method, path, body=body, headers=base)
        response = conn.getresponse(); data = response.read(); status = response.status; hdr = dict(response.getheaders()); conn.close()
        return status, hdr, data

    def test_host_origin_token_and_json_boundaries(self):
        code, headers, raw = self.request("GET", "/api/session")
        self.assertEqual(code, 200); self.assertEqual(json.loads(raw)["csrf_token"], self.wb.token)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        navigation = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        self.assertEqual(self.request("GET", "/", headers=navigation)[0], 200)
        self.assertEqual(self.request("GET", "/workbench.html", headers=navigation)[0], 200)
        self.assertEqual(self.request("GET", "/api/session", headers=navigation)[0], 403)
        self.assertEqual(self.request("GET", "/api/projects", headers=navigation)[0], 403)
        self.assertEqual(self.request("GET", "/", headers={**navigation, "Host": "evil.test"})[0], 403)
        for host in ("localhost:" + str(self.server.server_port), "evil.test", "127.0.0.1"):
            self.assertEqual(self.request("GET", "/api/session", headers={"Host": host})[0], 403)
        self.assertEqual(self.request("GET", "/api/session", headers={"Origin": "http://evil.test"})[0], 403)
        self.assertEqual(self.request("GET", "/api/session", headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("POST", "/api/projects", {"draft": draft()}, headers={"X-Workbench-Token": "invalid"})[0], 403)
        self.assertEqual(self.request("POST", "/api/projects", {"draft": draft()}, headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("POST", "/api/projects", {"draft": draft()}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/projects", raw=b'{"draft":1,"draft":2}')[0], 400)
        self.assertEqual(self.request("POST", "/api/projects", raw=b'{"draft":NaN}')[0], 400)
        self.assertEqual(self.request("POST", "/api/projects", raw=b"[1]")[0], 400)
        self.assertEqual(self.request("POST", "/api/projects", raw=b"{}", headers={"Content-Length": str(MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.request("POST", "/api/projects", {"draft": draft(), "command": "whoami"})[0], 400)

    def test_project_cas_forbidden_paths_and_symlink(self):
        code, _, raw = self.request("POST", "/api/projects", {"draft": draft()})
        self.assertEqual(code, 200); p = json.loads(raw)["project"]
        for path in ("/api/projects/../secret", "/api/projects/%2e%2e/secret", "/api/projects/%252e%252e/secret", "/api/projects/a%2fb", "/UPSTREAM.json", "/pm_task.py"):
            self.assertIn(self.request("GET", path)[0], (400, 404))
        self.assertEqual(self.request("POST", f"/api/projects/{p['id']}/save", {"draft": p["draft"], "expected_revision": 0})[0], 409)
        self.assertEqual(self.request("POST", f"/api/projects/{p['id']}/save", {"draft": p["draft"], "expected_revision": 1, "path": "/tmp/steal"})[0], 400)
        self.assertEqual(self.request("GET", f"/api/projects/{p['id']}")[0], 200)
        self.assertEqual(self.request("OPTIONS", "/api/projects")[0], 404)
        q = self.wb.projects_dir / "p_link"; q.symlink_to(self.tmp.name)
        code, _, raw = self.request("GET", "/api/projects/p_link")
        self.assertEqual(code, 400); self.assertNotIn(self.tmp.name.encode(), raw)

    def test_download_whitelist_and_html_sandbox(self):
        p = self.wb.create(draft())["project"]
        state = self.wb.state(p["id"])
        directory, meta = self.wb.new_run(state, "review", "1")
        output = directory / "output"; output.mkdir()
        write_new(output / "prototype.html", b"<script>document.body.textContent='synthetic'</script>", raw=True)
        meta.update(status="HOLD", exit_code=3)
        self.wb.finish_run(state, directory, meta, output)
        path = f"/api/projects/{p['id']}/runs/{meta['id']}/files/prototype.html"
        self.assertEqual(self.request("GET", path, headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})[0], 403)
        self.assertEqual(self.request("GET", path + "?preview=1", headers={"Origin": "http://evil.test"})[0], 403)
        code, headers, body = self.request("GET", path)
        self.assertEqual(code, 200); self.assertTrue(headers["Content-Disposition"].startswith("attachment"))
        self.assertIn("sandbox allow-scripts", headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", headers["Content-Security-Policy"])
        self.assertNotIn(self.wb.token.encode(), body)
        code, headers, body = self.request("GET", path + "?preview=1")
        self.assertEqual(code, 200); self.assertTrue(headers["Content-Disposition"].startswith("inline"))
        self.assertEqual(self.request("GET", path.replace("prototype.html", "run.json"))[0], 404)
        # A locally swapped symlink is rejected even when previously whitelisted.
        (output / "prototype.html").unlink(); (output / "prototype.html").symlink_to(Path(self.tmp.name) / "secret")
        self.assertEqual(self.request("GET", path)[0], 400)
        with self.assertRaises(APIError): Server(("0.0.0.0", 0), self.wb)


if __name__ == "__main__": unittest.main(verbosity=2)
