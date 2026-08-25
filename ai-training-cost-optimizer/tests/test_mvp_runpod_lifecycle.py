from training_cost_optimizer.mvp.config import GPU_EXECUTION_PROFILES
from training_cost_optimizer.providers.runpod_lifecycle import (
    PodStatus,
    RunpodRestLifecycleProvider,
)


def test_runpod_lifecycle_provider_builds_fixed_callback_payload_and_maps_status():
    calls = []

    def transport(method, url, body, headers, timeout):
        calls.append((method, url, body, headers, timeout))
        if method == "POST":
            return 201, {"id": "pod-123"}
        if method == "GET":
            return 200, {"desiredStatus": "RUNNING", "runtime": {"uptimeInSeconds": 12}}
        assert method == "DELETE"
        return 204, {}

    provider = RunpodRestLifecycleProvider(
        api_key="test-key",
        callback_base_url="https://api.example.test/",
        transport=transport,
    )
    profile = GPU_EXECUTION_PROFILES[0]

    assert provider.create_pod(profile, "job-123") == "pod-123"
    assert provider.get_pod_status("pod-123") is PodStatus.RUNNING
    provider.delete_pod("pod-123")

    method, url, payload, headers, _ = calls[0]
    assert (method, url) == ("POST", "https://rest.runpod.io/v1/pods")
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["gpuTypeIds"] == [profile.runpod_gpu_type_id]
    assert payload["imageName"] == profile.image_name
    assert payload["dockerStartCmd"] == ["/bin/sh", "-lc", profile.start_command]
    assert payload["env"] == {
        "UNWORK_COMPLETION_URL": "https://api.example.test/api/v1/internal/jobs/job-123/completion"
    }
    assert calls[1][0:2] == ("GET", "https://rest.runpod.io/v1/pods/pod-123")
    assert calls[2][0:2] == ("DELETE", "https://rest.runpod.io/v1/pods/pod-123")



def test_a_pod_still_pulling_its_image_is_not_reported_as_running():
    """Runpod은 Pod를 만드는 순간 desiredStatus를 RUNNING으로 둔다.

    컨테이너가 실제로 뜨기 전까지 runtime은 비어 있다. 이 구간을 실행 중으로
    보고하면 화면은 이미지를 받는 몇 분 동안 학습이 도는 것처럼 보인다.
    """

    def transport(method, url, body, headers, timeout):
        return 200, {"desiredStatus": "RUNNING", "runtime": None}

    provider = RunpodRestLifecycleProvider(
        api_key="test-key", callback_base_url="https://api.example.test", transport=transport
    )

    assert provider.get_pod_status("pod-123") is PodStatus.PROVISIONING


def test_exited_and_terminated_pods_are_terminated():
    for desired in ("EXITED", "TERMINATED"):
        provider = RunpodRestLifecycleProvider(
            api_key="test-key",
            callback_base_url="https://api.example.test",
            transport=lambda m, u, b, h, t, d=desired: (200, {"desiredStatus": d}),
        )
        assert provider.get_pod_status("pod-123") is PodStatus.TERMINATED
