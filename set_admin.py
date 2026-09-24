"""Set local admin credentials interactively; only a salted hash is persisted."""
import getpass
import hashlib
import json
import os
from pathlib import Path

def set_admin(password):
    path = Path(__file__).resolve().parent / 'data/admin-auth.json'
    salt = os.urandom(16)
    data = dict(username='admin', salt=salt.hex(), hash=hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
    os.chmod(path, 0o600)

if __name__ == '__main__':
    set_admin(getpass.getpass('New admin password: '))
