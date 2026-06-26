import os
import ssl

from ftplib import FTP_TLS


class FTPS(FTP_TLS):
    """
    FTPS subclass that reuses the control connection's TLS session for data
    connections. Required by some servers (e.g. ARPAE) for LIST/RETR to work.
    """
    def ntransfercmd(self, cmd, rest=None):
        conn, size = super().ntransfercmd(cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session
            )
        return conn, size


def ftp_connect(host, user, password, port=21, timeout=30):
    """
    ftp_connect - open an FTPS connection and login.
    """
    ftps = FTP_TLS(context=ssl.create_default_context(), timeout=timeout)
    ftps.connect(host, port)
    ftps.login(user, password)

    ftps.prot_c()
    ftps.set_pasv(True)
    return ftps


def ftp_ls(ftps, path="."):
    """
    ftp_ls - list names in path without changing the persistent working dir.
    """
    cur = ftps.pwd()
    try:
        ftps.cwd(path)
        return ftps.nlst()
    finally:
        ftps.cwd(cur)


def ftp_chdir(ftps, path):
    """
    ftp_chdir - change directory and return the new working directory.
    """
    ftps.cwd(path)
    return ftps.pwd()


def ftp_exists_path_mlsd(ftps, path):
    """
    ftp_exists_path_mlsd - check whether a path exists using MLSD listing.
    """
    cur = ftps.pwd()
    try:
        parts = [p for p in path.split("/") if p]
        for part in parts[:-1]:
            ftps.cwd(part)
        for name, facts in ftps.mlsd():
            if name == parts[-1]:
                return True
        return False
    finally:
        ftps.cwd(cur)


def ftp_download(ftps, remote_path, local_path=None, local_dir="."):
    """
    ftp_download - download remote_path.
    - if local_path is None -> save into local_dir with the same basename
    - if local_path is a folder -> save inside that folder
    - if local_path is a file -> save exactly there
    """
    remote_name = os.path.basename(remote_path.rstrip("/"))
    if local_path is None:
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, remote_name)
    else:
        if os.path.isdir(local_path) or local_path.endswith(("/", "\\")):
            os.makedirs(local_path, exist_ok=True)
            local_path = os.path.join(local_path, remote_name)
        else:
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

    with open(local_path, "wb") as f:
        ftps.retrbinary(f"RETR {remote_path}", f.write)

    return local_path


def ftp_close(ftps):
    """
    ftp_close - close the FTPS connection gracefully.
    """
    try:
        ftps.quit()
    except Exception:
        ftps.close()
