"""Thin RunPod POD API client used for provisioning and lifecycle actions."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Iterable, Optional

import requests


class RunPodError(Exception):
    """Raised when RunPod actions fail."""


class RunPodCapacityError(RunPodError):
    """Raised when RunPod cannot provision a pod due to lack of capacity."""

    def __init__(self, message: str, *, gpu_type: str | None = None, cloud_type: str | None = None):
        super().__init__(message)
        self.gpu_type = gpu_type
        self.cloud_type = cloud_type


class RunPodClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        api_url: str | None = None,
        default_gpu: str | None = None,
        gpu_preferences: Iterable[str] | None = None,
        pod_template_id: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise RunPodError("RUNPOD_API_KEY must be configured")

        self.api_url = api_url or os.getenv("RUNPOD_API_URL", "https://api.runpod.io/graphql")
        self.default_gpu = default_gpu or os.getenv("RUNPOD_DEFAULT_GPU", "NVIDIA_L4")
        env_gpu_preferences = os.getenv("RUNPOD_GPU_PREFERENCES")
        if gpu_preferences is not None:
            base_gpu_preferences = list(gpu_preferences)
        elif env_gpu_preferences:
            base_gpu_preferences = [
                gpu.strip() for gpu in env_gpu_preferences.split(",") if gpu.strip()
            ]
        else:
            base_gpu_preferences = [self.default_gpu, "NVIDIA_A10G", "NVIDIA_A100"]

        self.gpu_preferences: list[str] = []
        for gpu in base_gpu_preferences:
            if gpu and gpu not in self.gpu_preferences:
                self.gpu_preferences.append(gpu)
        self.pod_template_id = pod_template_id or os.getenv("RUNPOD_POD_TEMPLATE_ID")

    # --------------------------- GraphQL utilities ---------------------------
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        payload = {"query": query, "variables": variables or {}}
        resp = requests.post(self.api_url, json=payload, headers=self._headers(), timeout=60)
        if not resp.ok:
            raise RunPodError(f"RunPod API request failed: {resp.status_code} {resp.text}")
        data = resp.json()
        if "errors" in data:
            for error in data["errors"]:
                message = error.get("message", "")
                if "no longer any instances available" in message.lower():
                    raise RunPodCapacityError(message)
            raise RunPodError(str(data["errors"]))
        return data.get("data") or {}

    # ------------------------------- Pod control -----------------------------
    def _deploy_pod(self, *, gpu: str, name: str | None = None) -> str:
        mutation = """
        mutation Deploy($input: PodFindAndDeployOnDemandInput!) {
          podFindAndDeployOnDemand(input: $input) {
            id
          }
        }
        """
        variables = {
            "input": {
                "cloudType": "SECURE",
                "gpuTypeId": gpu,
                "templateId": self.pod_template_id,
                "name": name or "sdxl-lora-job",
                "volumeInGb": 0,
            }
        }
        try:
            data = self._graphql(mutation, variables)
        except RunPodCapacityError as err:
            raise RunPodCapacityError(
                err.args[0], gpu_type=gpu, cloud_type="SECURE"
            ) from err
        pod = data.get("podFindAndDeployOnDemand")
        if not pod or "id" not in pod:
            raise RunPodError("Failed to parse pod creation response")
        return pod["id"]

    def create_pod(self, *, gpu_type: str | None = None, name: str | None = None) -> str:
        if not self.pod_template_id:
            raise RunPodError("RUNPOD_POD_TEMPLATE_ID is required to provision pods")

        gpu_candidates: list[str] = []
        if gpu_type:
            gpu_candidates.append(gpu_type)
        for gpu in self.gpu_preferences:
            if gpu not in gpu_candidates:
                gpu_candidates.append(gpu)
        if not gpu_candidates:
            raise RunPodError("No GPU types configured for pod creation")

        last_capacity_error: RunPodCapacityError | None = None
        for gpu in gpu_candidates:
            try:
                return self._deploy_pod(gpu=gpu, name=name)
            except RunPodCapacityError as err:
                last_capacity_error = err

        if last_capacity_error:
            raise RunPodCapacityError(
                "RunPod does not currently have capacity for configured GPU types: "
                + ", ".join(gpu_candidates),
                gpu_type=last_capacity_error.gpu_type or gpu_candidates[-1],
                cloud_type=last_capacity_error.cloud_type,
            ) from last_capacity_error

        raise RunPodError("Failed to create pod for unknown reasons")

    def terminate_pod(self, pod_id: str) -> None:
        mutation = """
        mutation PodTerminate($podId: ID!) {
          podTerminate(podId: $podId)
        }
        """
        self._graphql(mutation, {"podId": pod_id})

    def wait_for_pod_ready(self, pod_id: str, *, timeout: int = 900, interval: int = 15) -> None:
        query = """
        query PodStatus($podId: ID!) {
          pod(podId: $podId) {
            id
            runtime {
              state
            }
          }
        }
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._graphql(query, {"podId": pod_id})
            runtime = (data.get("pod") or {}).get("runtime") or {}
            state = runtime.get("state")

            if state == "RUNNING":
                return
            if state in {"FAILED", "CANCELLED", "TERMINATED"}:
                raise RunPodError(f"Pod {pod_id} failed to start (state={state})")

            time.sleep(interval)

        raise RunPodError(f"Pod {pod_id} did not become ready within {timeout} seconds")

    # ------------------------------- File IO --------------------------------
    def upload_files(self, pod_id: str, files: Iterable[Path], *, remote_dir: str) -> None:
        """Upload a collection of files to a remote directory."""
        for file_path in files:
            with open(file_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            mutation = """
            mutation PodUpload($input: PodUploadInput!) {
              podUploadFiles(input: $input)
            }
            """
            variables = {
                "input": {
                    "podId": pod_id,
                    "files": [
                        {
                            "path": f"{remote_dir}/{file_path.name}",
                            "content": encoded,
                        }
                    ],
                }
            }
            self._graphql(mutation, variables)

    def download_file(self, pod_id: str, remote_path: str, local_path: Path) -> None:
        query = """
        query PodDownload($podId: ID!, $path: String!) {
          podDownloadFile(podId: $podId, path: $path)
        }
        """
        data = self._graphql(query, {"podId": pod_id, "path": remote_path})
        encoded = data.get("podDownloadFile")
        if not encoded:
            raise RunPodError(f"No data returned for {remote_path}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(base64.b64decode(encoded))

    # ------------------------------ Command exec ----------------------------
    def execute_command(self, pod_id: str, command: str, *, workdir: str | None = None) -> str:
        """Execute a shell command inside the pod and return stdout/stderr."""
        mutation = """
        mutation PodCommand($input: PodExecInput!) {
          podExec(input: $input) {
            output
            exitCode
          }
        }
        """
        variables = {
            "input": {
                "podId": pod_id,
                "command": command if workdir is None else f"cd {workdir} && {command}",
            }
        }
        data = self._graphql(mutation, variables)
        exec_result = data.get("podExec") or {}
        exit_code = exec_result.get("exitCode")
        if exit_code not in (None, 0):
            raise RunPodError(
                f"Command failed (exit={exit_code}): {command}\n{exec_result.get('output')}"
            )
        return exec_result.get("output") or ""
