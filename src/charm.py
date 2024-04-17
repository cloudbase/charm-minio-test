#!/usr/bin/env python3

# Copyright 2023 Cloudbase Solutions Srl

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MinIO Operator Charm.

This charm deploys and manages MinIO on Juju infra machines.
"""

import grp
import logging
import os
import pwd
import shutil
import subprocess
from urllib import request

import ops.charm as ops_charm
import ops.framework as ops_framework
import ops.main as ops_main
import ops.model as ops_model
from charms.data_platform_libs.v0 import s3

logger = logging.getLogger(__name__)


class MinioTestCharm(ops_charm.CharmBase):
    """Charm the service."""

    state = ops_framework.StoredState()

    SERVICE_NAME = "minio"
    SYSTEMD_ENV_FILE = "/etc/default/minio"
    MINIO_DATA_DIR = "/var/lib/minio"
    MINIO_SYSTEM_USER = "minio-user"
    MINIO_SYSTEM_GROUP = "minio-user"
    UNIT_ACTIVE_STATUS = ops_model.ActiveStatus("Unit is ready")

    def __init__(self, *args):
        super().__init__(*args)

        self.s3_provider = s3.S3Provider(self, "s3-credentials")

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.s3_provider.on.credentials_requested,
            self._on_credential_requested,
        )

    def _on_install(self, event):
        logging.info("Installing MinIO")
        minio_deb_file = "/tmp/minio.deb"
        request.urlretrieve(
            url=self.config["deb-url"], filename=minio_deb_file
        )
        subprocess.check_call(["dpkg", "-i", minio_deb_file])
        self._add_system_group()
        self._add_system_user()
        os.makedirs(self.MINIO_DATA_DIR, exist_ok=True)
        shutil.chown(
            self.MINIO_DATA_DIR,
            user=self.MINIO_SYSTEM_USER,
            group=self.MINIO_SYSTEM_GROUP,
        )
        subprocess.check_call(["systemctl", "enable", self.SERVICE_NAME])

    def _on_config_changed(self, event):
        self._write_systemd_env_file()
        self._restart_service()
        self.unit.status = self.UNIT_ACTIVE_STATUS

    def _on_credential_requested(self, event: s3.CredentialRequestedEvent):
        if not self.unit.is_leader():
            return

        binding = self.model.get_binding(event.relation)
        endpoint = "http://{}:{}".format(
            str(binding.network.bind_address),
            self.config["port"],
        )
        conn_data = {
            "bucket": self.config["bucket"] or event.bucket,
            "access-key": self.config["root-user"],
            "secret-key": self.config["root-password"],
            "endpoint": endpoint,
            "region": self.config["region"],
        }
        if self.config["s3-uri-style"]:
            conn_data["s3-uri-style"] = self.config["s3-uri-style"]

        self.s3_provider.update_connection_info(event.relation.id, conn_data)

    def _add_system_group(self):
        existing_groups = [g.gr_name for g in grp.getgrall()]
        if self.MINIO_SYSTEM_GROUP in existing_groups:
            logger.info(
                "Group {} already exists".format(self.MINIO_SYSTEM_GROUP)
            )
            return
        subprocess.check_call(["groupadd", "-r", self.MINIO_SYSTEM_GROUP])

    def _add_system_user(self):
        existing_users = [u.pw_name for u in pwd.getpwall()]
        if self.MINIO_SYSTEM_USER in existing_users:
            logger.info(
                "User {} already exists".format(self.MINIO_SYSTEM_USER)
            )
            return
        subprocess.check_call(
            [
                "useradd",
                "-M",
                "-r",
                "-g",
                self.MINIO_SYSTEM_GROUP,
                self.MINIO_SYSTEM_USER,
            ]
        )

    def _write_systemd_env_file(self):
        logger.info("Writing systemd environment file")
        minio_opts = "--address :{} --console-address :{}".format(
            self.config["port"],
            self.config["console-port"],
        )
        minio_env = {
            "MINIO_ROOT_USER": self.config["root-user"],
            "MINIO_ROOT_PASSWORD": self.config["root-password"],
            "MINIO_VOLUMES": self.MINIO_DATA_DIR,
            "MINIO_REGION": self.config["region"],
            "MINIO_OPTS": minio_opts,
        }
        with open(self.SYSTEMD_ENV_FILE, "w") as f:
            for k, v in minio_env.items():
                f.write("{}={}\n".format(k, v))

    def _restart_service(self):
        logging.info("Restarting MinIO systemd service")
        subprocess.check_call(["systemctl", "restart", self.SERVICE_NAME])


if __name__ == "__main__":
    ops_main.main(MinioTestCharm)
