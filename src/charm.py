#!/usr/bin/env python3

"""MinIO Operator Charm.

This charm deploys and manages MinIO on Juju infra machines.
"""

import logging
import os
import shutil
import subprocess
from urllib import request

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main

logger = logging.getLogger(__name__)


class MinioTestCharm(CharmBase):
    """Charm the service."""

    state = StoredState()

    SERVICE_NAME = "minio"
    SYSTEMD_ENV_FILE = "/etc/default/minio"
    MINIO_DATA_DIR = "/var/lib/minio"
    MINIO_SYSTEM_USER = "minio-user"
    MINIO_SYSTEM_GROUP = "minio-user"

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_install(self, event):
        minio_deb_file = "/tmp/minio.deb"
        request.urlretrieve(url=self.model.config["minio-deb-url"],
                            filename=minio_deb_file)
        subprocess.check_call(["dpkg", "-i", minio_deb_file])
        subprocess.check_call(["groupadd", "-r", self.MINIO_SYSTEM_GROUP])
        subprocess.check_call(["useradd", "-M", "-r",
                               "-g", self.MINIO_SYSTEM_GROUP,
                               self.MINIO_SYSTEM_USER])
        os.makedirs(self.MINIO_DATA_DIR, exist_ok=True)
        shutil.chown(self.MINIO_DATA_DIR,
                     user=self.MINIO_SYSTEM_USER,
                     group=self.MINIO_SYSTEM_GROUP)
        subprocess.check_call(["systemctl", "enable", self.SERVICE_NAME])

    def _on_config_changed(self, event):
        self._write_systemd_env_file()
        subprocess.check_call(["systemctl", "restart", self.SERVICE_NAME])

    def _write_systemd_env_file(self):
        minio_opts = "--address {} --console-address {}".format(
            self.model.config["address"],
            self.model.config["console-address"],
        )
        minio_env = {
            "MINIO_ROOT_USER": self.model.config["root-user"],
            "MINIO_ROOT_PASSWORD": self.model.config["root-password"],
            "MINIO_VOLUMES": self.MINIO_DATA_DIR,
            "MINIO_REGION": self.model.config["region"],
            "MINIO_OPTS": minio_opts,
        }
        with open(self.SYSTEMD_ENV_FILE, "w") as f:
            for k, v in minio_env.items():
                f.write("{}={}\n".format(k, v))


if __name__ == "__main__":
    main(MinioTestCharm)
