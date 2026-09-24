import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
import server

class PortalTests(unittest.TestCase):
    def test_directory_and_quality(self):
        original = server.DB
        original_auth = server.AUTH_FILE
        with tempfile.TemporaryDirectory() as tmp:
            server.DB = Path(tmp) / 'test.sqlite3'
            server.AUTH_FILE = Path(tmp) / 'auth.json'
            import hashlib, json
            salt = b'test-salt'
            server.AUTH_FILE.write_text(json.dumps(dict(username='admin', salt=salt.hex(), hash=hashlib.scrypt(b'test-password',salt=salt,n=16384,r=8,p=1).hex())))
            try:
                with TestClient(server.app) as client:
                    # Public paths should return 200 without auth
                    self.assertEqual(client.get('/').status_code, 200)
                    self.assertEqual(client.get('/docs').status_code, 200)
                    self.assertEqual(client.get('/api/v1/health').status_code, 200)
                    self.assertEqual(client.get('/api/v1/auth/me').json()['authenticated'], False)

                    # Protected endpoints require authentication
                    for path in ['/api/v1/persons', '/api/v1/persons/1/photo']:
                        self.assertEqual(client.get(path).status_code, 401)

                    # Login failure
                    login_fail = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'wrong-password'})
                    self.assertEqual(login_fail.status_code, 401)

                    # Login success as normal user
                    server.update_user_password('testuser', 'user-pass')
                    login_user = client.post('/api/v1/auth/login', json={'username': 'testuser', 'password': 'user-pass'})
                    self.assertEqual(login_user.status_code, 200)
                    self.assertEqual(login_user.json()['user']['role'], 'user')
                    
                    # Normal user can check image quality
                    blank = io.BytesIO()
                    Image.new('RGB',(320,240),'white').save(blank,format='PNG')
                    user_scan = client.post('/api/v1/image-quality', files={'file':('blank.png',blank.getvalue())})
                    self.assertEqual(user_scan.status_code, 200)

                    # Normal user CANNOT view or modify directory (403 Forbidden)
                    self.assertEqual(client.get('/api/v1/persons').status_code, 403)
                    self.assertEqual(client.post('/api/v1/persons', json={'name': 'Forbidden', 'employee_id': '403'}).status_code, 403)

                    # Logout normal user
                    client.post('/api/v1/auth/logout')

                    # Login success as admin
                    login_res = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'test-password'})
                    self.assertEqual(login_res.status_code, 200)
                    self.assertEqual(login_res.json()['status'], 'ok')
                    self.assertEqual(login_res.json()['user']['role'], 'admin')
                    self.assertEqual(client.get('/api/v1/auth/me').json()['authenticated'], True)

                    # Admin can query persons with active session cookie
                    self.assertEqual(client.get('/api/v1/health').json()['persons'], 4592)
                    self.assertGreater(client.get('/api/v1/persons?q=vo%20thanh%20lam').json()['total'], 0)
                    payload = dict(name='Test Nhân sự', employee_id='TEST-ONLY', title='Tester')
                    r = client.post('/api/v1/persons', json=payload)
                    self.assertEqual(r.status_code, 201)
                    pid = r.json()['id']
                    self.assertEqual(client.post('/api/v1/persons', json=payload).status_code, 409)
                    payload['title'] = 'Updated'
                    self.assertEqual(client.put('/api/v1/persons/'+pid, json=payload).json()['title'], 'Updated')
                    self.assertEqual(client.get('/api/v1/persons/'+pid).json()['name'], payload['name'])
                    self.assertEqual(client.get('/api/v1/persons?offset=-1').status_code, 422)
                    self.assertEqual(client.post('/api/v1/image-quality', files={'file':('bad.jpg',b'bad')}).status_code, 422)
                    
                    first_id = user_scan.json()['case_id']
                    self.assertEqual(client.get('/api/v1/cases/'+first_id+'/image?original=true').content,blank.getvalue())
                    self.assertEqual(client.patch('/api/v1/cases/'+first_id,json={'status':'needs_fix','note':'Test review'}).status_code,200)
                    self.assertEqual(client.get('/api/v1/cases').json()['items'][0]['note'],'Test review')
                    
                    # Cross the retention boundary through the actual upload endpoint.
                    for _ in range(100):
                        r=client.post('/api/v1/image-quality',files={'file':('blank.png',blank.getvalue())})
                        self.assertEqual(r.status_code,200)
                    entries=client.get('/api/v1/cases').json()['items']
                    self.assertEqual(len(entries),100)
                    self.assertNotIn(first_id,[c['id'] for c in entries])
                    self.assertEqual(client.get('/api/v1/cases/'+first_id+'/image').status_code,404)
                    last_id=entries[0]['id']
                    self.assertEqual(client.delete('/api/v1/cases/'+last_id).status_code,200)
                    self.assertEqual(client.get('/api/v1/cases/'+last_id+'/image').status_code,404)

                    # Test actual face photo detection & recognition endpoint
                    test_photo_path = Path(__file__).resolve().parent / 'gallery/NOVA/technology-center-org-chart/photos/Vo-Thanh-Lam-37291.jpg'
                    if test_photo_path.is_file():
                        photo_bytes = test_photo_path.read_bytes()
                        rec_res = client.post('/api/v1/recognize', files={'file': ('lam.jpg', photo_bytes)})
                        self.assertEqual(rec_res.status_code, 200)
                        data = rec_res.json()
                        self.assertEqual(data['total_faces'], 1)
                        self.assertEqual(data['engine']['detector'], 'OpenCV YuNet')
                        self.assertGreater(data['faces'][0]['metrics']['detection_score'], 0.8)

                    # Test change password
                    pwd_res = client.post('/api/v1/auth/change-password', json={'old_password': 'test-password', 'new_password': 'new-password-123'})
                    self.assertEqual(pwd_res.status_code, 200)

                    # Test logout
                    logout_res = client.post('/api/v1/auth/logout')
                    self.assertEqual(logout_res.status_code, 200)
                    self.assertEqual(client.get('/api/v1/auth/me').json()['authenticated'], False)
            finally:
                server.DB = original
                server.AUTH_FILE = original_auth

if __name__ == '__main__':
    unittest.main()
