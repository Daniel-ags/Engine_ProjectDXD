"""
Where the editor keeps resource files until the project is saved.

An import copies its files here, and an editor that changes a file's bytes (a
recolor, a colorkey conversion, generated autotiles) writes the new version here.
The resource points at the staged files, and saving the project copies them in.
Nothing ever overwrites a staged file, so undo can always point a resource back
at an earlier version.

Each version of a resource's files is a folder named by a hash of their names and
contents, holding them under their own names, since some resources name several
files from one base path. Folders sit under `.project_staging/<project name>/<session id>/`
in the editor's main directory, or in the OS temp folder when that is read-only.
A session's folder goes when the editor closes or opens another project. Each
session holds a lock on a file in its folder, so a folder whose lock is free was
left by an editor that crashed, and is removed when the next one starts.
"""
import atexit
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import uuid
from typing import Callable, Dict, List, Optional

if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl

STAGING_FOLDER = '.project_staging'
LOCK_FILE = '.lock'

def _try_lock(fp) -> bool:
    try:
        if sys.platform == 'win32':
            fp.seek(0)  # It locks from the file's position
            msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False

def _unlock(fp):
    if sys.platform == 'win32':
        fp.seek(0)
        msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)

def _version_hash(files: Dict[str, str]) -> str:
    """A hash of each file's name and contents, from file names to their paths"""
    digest = hashlib.sha256()
    for name, path in files.items():
        digest.update(name.encode('utf-8') + b'\0')
        with open(path, 'rb') as fp:
            for chunk in iter(lambda: fp.read(1 << 20), b''):
                digest.update(chunk)
        digest.update(b'\0')
    return digest.hexdigest()[:16]

class Staging:
    def __init__(self, root: str):
        self.root = root
        self.session_id = uuid.uuid4().hex[:12]
        self.project_name: Optional[str] = None
        self.session_dir: Optional[str] = None  # Made at the first file staged
        self.lock = None
        self.cleaned = False
        atexit.register(self.end)

    def start(self, project_path: str):
        """Begins staging for the project just loaded. Files staged for the project
        before go, since no undo reaches back into another project."""
        self.end()
        self.project_name = os.path.splitext(os.path.basename(os.path.normpath(project_path)))[0]
        if not self.cleaned:
            self.cleaned = True
            self.remove_dead_sessions()

    def end(self):
        """Removes this session's staged files"""
        if self.lock:
            _unlock(self.lock)
            self.lock.close()
            self.lock = None
        if self.session_dir:
            shutil.rmtree(self.session_dir, ignore_errors=True)
            project_dir = os.path.dirname(self.session_dir)
            if os.path.isdir(project_dir) and not os.listdir(project_dir):
                os.rmdir(project_dir)
            self.session_dir = None

    def remove_dead_sessions(self):
        for root in (self.root, self.fallback_root()):
            if not os.path.isdir(root):
                continue
            for project_name in os.listdir(root):
                project_dir = os.path.join(root, project_name)
                if not os.path.isdir(project_dir):
                    continue
                for session_id in os.listdir(project_dir):
                    session_dir = os.path.join(project_dir, session_id)
                    if os.path.isdir(session_dir) and self.is_dead(session_dir):
                        logging.info("Removing staged files left by an editor that closed early: %s", session_dir)
                        shutil.rmtree(session_dir, ignore_errors=True)
                if not os.listdir(project_dir):
                    os.rmdir(project_dir)

    def is_dead(self, session_dir: str) -> bool:
        try:
            with open(os.path.join(session_dir, LOCK_FILE), 'a') as fp:
                if not _try_lock(fp):
                    return False
                _unlock(fp)
                return True
        except OSError:
            return False

    def fallback_root(self) -> str:
        return os.path.join(tempfile.gettempdir(), 'lt_maker' + STAGING_FOLDER)

    def get_session_dir(self) -> str:
        assert self.project_name, "Staging starts when a project is loaded"
        if not self.session_dir:
            for root in (self.root, self.fallback_root()):
                session_dir = os.path.join(root, self.project_name, self.session_id)
                try:
                    os.makedirs(session_dir, exist_ok=True)
                    lock = open(os.path.join(session_dir, LOCK_FILE), 'a')
                except OSError:
                    continue
                if not _try_lock(lock):
                    lock.close()
                    continue
                self.session_dir, self.lock = session_dir, lock
                break
            else:
                raise OSError("Could not make a folder to stage resource files in, at %s or %s" %
                              (self.root, self.fallback_root()))
        return self.session_dir

    def is_staged(self, path: str) -> bool:
        return bool(self.session_dir) and \
            os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(self.session_dir) + os.sep)

    def stage_files(self, paths: List[str]) -> str:
        """Copies files into one version folder, under their own names, and returns
        the folder. A file that does not exist is left out."""
        files = {os.path.basename(path): path for path in paths if os.path.exists(path)}
        version_dir = os.path.join(self.get_session_dir(), _version_hash(files))
        if not os.path.isdir(version_dir):
            new_dir = self._new_dir()
            for name, path in files.items():
                shutil.copyfile(path, os.path.join(new_dir, name))
            self._settle(new_dir, version_dir)
        return version_dir

    def stage_file(self, path: str) -> str:
        """Copies a file into its own version folder, and returns the copy's path"""
        return os.path.join(self.stage_files([path]), os.path.basename(path))

    def write_files(self, writers: Dict[str, Callable[[str], bool]]) -> str:
        """Writes a new version of a resource's files and returns its folder. Each
        writer saves the file named by its key at the path it is given, and returns
        whether it did, like QImage.save."""
        new_dir = self._new_dir()
        for name, write in writers.items():
            if not write(os.path.join(new_dir, name)):
                shutil.rmtree(new_dir, ignore_errors=True)
                raise OSError("Could not write %s" % name)
        files = {name: os.path.join(new_dir, name) for name in writers}
        version_dir = os.path.join(self.get_session_dir(), _version_hash(files))
        self._settle(new_dir, version_dir)
        return version_dir

    def write_file(self, name: str, write: Callable[[str], bool]) -> str:
        """Writes a new version of one file, and returns its path"""
        return os.path.join(self.write_files({name: write}), name)

    def _new_dir(self) -> str:
        new_dir = os.path.join(self.get_session_dir(), 'new-' + uuid.uuid4().hex[:12])
        os.mkdir(new_dir)
        return new_dir

    def _settle(self, new_dir: str, version_dir: str):
        """Names a finished version folder by its hash, unless that version is staged already"""
        if os.path.isdir(version_dir):
            shutil.rmtree(new_dir, ignore_errors=True)
        else:
            os.rename(new_dir, version_dir)

STAGING = Staging(os.path.abspath(STAGING_FOLDER))
