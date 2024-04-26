import os


def createDir(dir_path: str):
    os.makedirs(dir_path, exist_ok=True)
    owner_uid = 1000
    owner_gid = 1000
    os.chown(dir_path, owner_uid, owner_gid)
    os.chmod(dir_path, 0o777)
