from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_release_workflow_builds_and_verifies_all_first_batch_artifacts():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for contract in (
        "build-windows:",
        "build-android:",
        "build-cloud:",
        "WINDOWS_CERTIFICATE_BASE64",
        "certificateThumbprint",
        "signtool.exe",
        "verify /pa /all /v",
        "verify_windows_secure_identity.py",
        "ANDROID_KEYSTORE_BASE64",
        ":app:assembleRelease",
        "apksigner\" verify --verbose --print-certs",
        "docker/build-push-action@v6",
        "steps.build.outputs.digest",
        "NOTEMELD_BUILD_COMMIT=${{ github.sha }}",
        "NOTEMELD_AGENT_SDK_LINUX_WHEEL_URL",
        "NOTEMELD_AGENT_SDK_LINUX_WHEEL_SHA256",
        "NOTEMELD_AGENT_SDK_LINUX_LIBRARY_URL",
        "NOTEMELD_AGENT_SDK_LINUX_LIBRARY_SHA256",
        "Download pinned official plugin release",
        "NOTEMELD_PLUGINS_ARCHIVE_URL",
        "NOTEMELD_PLUGINS_ARCHIVE_SHA256",
        "NOTEMELD_PLUGINS_DIR",
        "NOTEMELD_AGENT_SDK_WHEEL=cloud/.sdk-build/notemeld-agent-sdk.whl",
        "NOTEMELD_AGENT_SDK_LIBRARY=cloud/.sdk-build/libnotemeld_agent.so",
        "generate_first_batch_rc_manifest.py",
        'version="${tag_version%%-*}"',
        "live ledger approval is intentionally false",
        "release/first-batch-rc.json",
        "public artifact hash mismatch",
        "public first-batch artifact hashes verified",
        "NOTEMELD_AGENT_SDK_AAR_SHA256",
        "NOTEMELD_ANDROID_BUILD_COMMIT: ${{ github.sha }}",
        "NOTEMELD_REQUIRE_INTEL_X64: \"1\"",
        "lipo -archs",
        "runs-on: macos-15-intel",
    ):
        assert contract in workflow
    aar_step = workflow.split("- name: Download pinned Agent SDK AAR", 1)[1].split("- name: Build signed Android release APK", 1)[0]
    assert "\n          PY\n" not in aar_step
    assert "needs: [build-macos, build-macos-intel, build-windows, build-android, build-cloud]" in workflow
    assert workflow.count("Download pinned official plugin release") == 3
    assert "unzip -q \"$archive\"" in workflow
    assert "Expand-Archive -Path $archive" in workflow
    intel_job = workflow.split("  build-macos-intel:", 1)[1].split("  build-windows:", 1)[0]
    arm_job = workflow.split("  build-macos:", 1)[1].split("  build-macos-intel:", 1)[0]
    assert "runs-on: macos-15" in arm_job
    assert "runs-on: macos-latest" not in arm_job
    assert "runs-on: macos-15-intel" in intel_job
    assert "runs-on: macos-latest" not in intel_job
    intel_backend_step = intel_job.split("- name: Build backend sidecar (x86_64)", 1)[1].split("- name: Build desktop app", 1)[0]
    assert "NOTEMELD_SKIP_PORTABILITY_CHECK" not in intel_backend_step
    assert workflow.count("VITE_NOTEMELD_BUILD_COMMIT: ${{ github.sha }}") >= 3
    assert "contains(github.ref_name, 'rc')" in workflow
    assert "-(rc|alpha|beta)([.-].*)$" in workflow
    assert workflow.count('version="${tag_version%%-*}"') >= 3


def test_stable_release_promotes_the_exact_candidate_without_rebuilding():
    workflow = (ROOT / ".github" / "workflows" / "promote-first-batch.yml").read_text(encoding="utf-8")
    for contract in (
        "workflow_dispatch:",
        "candidate_tag:",
        "stable_tag:",
        "gh release view",
        'isPrerelease") is not True',
        "stable tag already exists",
        "Checkout exact candidate commit",
        "gh release download",
        "first-batch-live-evidence.zip",
        "stat.S_ISLNK",
        '".." in path.parts',
        "verify_first_batch_ledger.py",
        "--expected-version",
        "--expected-commit",
        "generate_first_batch_rc_manifest.py",
        "--approval-ledger live-evidence/ledger.md",
        "rm release/first-batch-live-evidence.zip",
        "git tag",
        "git push origin",
        "gh release create",
        "gh release delete-asset",
        "--verify-tag",
    ):
        assert contract in workflow
    assert "docker/build-push-action" not in workflow
    assert "tauri build" not in workflow
    assert "assembleRelease" not in workflow


def test_stable_tags_do_not_trigger_the_candidate_rebuild_workflow():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert '- "v*-rc*"' in workflow
    assert '- "v*-alpha*"' in workflow
    assert '- "v*-beta*"' in workflow
    assert '\n      - "v*"' not in workflow


def test_cloud_ci_build_consumes_the_same_pinned_linux_sdk_contract():
    workflow = (ROOT / ".github" / "workflows" / "cloud-backend.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "cloud" / "Dockerfile").read_text(encoding="utf-8")
    for contract in (
        "Download pinned Linux Agent SDK artifacts",
        "NOTEMELD_AGENT_SDK_LINUX_WHEEL_URL",
        "NOTEMELD_AGENT_SDK_LINUX_WHEEL_SHA256",
        "NOTEMELD_AGENT_SDK_LINUX_LIBRARY_URL",
        "NOTEMELD_AGENT_SDK_LINUX_LIBRARY_SHA256",
        "--build-arg NOTEMELD_AGENT_SDK_WHEEL=cloud/.sdk-build/notemeld-agent-sdk.whl",
        "--build-arg NOTEMELD_AGENT_SDK_LIBRARY=cloud/.sdk-build/libnotemeld_agent.so",
    ):
        assert contract in workflow
    assert 'RUN test -n "${NOTEMELD_AGENT_SDK_WHEEL}" && test -n "${NOTEMELD_AGENT_SDK_LIBRARY}"' in dockerfile
    assert "COPY desktop/frontend/packages ./packages" in dockerfile
    assert "NOTEMELD_CLOUD_WEB_DIST=/app/cloud-web-dist" in dockerfile


def test_cloud_production_startup_fails_closed_before_uvicorn():
    start = (ROOT / "scripts" / "cloud" / "start.sh").read_text(encoding="utf-8")
    for variable in (
        "NOTEMELD_AGENT_SDK_LIBRARY",
        "NOTEMELD_CLOUD_SMTP_HOST",
        "NOTEMELD_CLOUD_SMTP_SENDER",
        "NOTEMELD_CLOUD_S3_BUCKET",
        "NOTEMELD_CLOUD_S3_ACCESS_KEY_ID",
        "NOTEMELD_CLOUD_S3_SECRET_ACCESS_KEY",
        "NOTEMELD_CLOUD_RELAY_URL",
        "NOTEMELD_CLOUD_BUILD_COMMIT",
        "NOTEMELD_CLOUD_IMAGE_DIGEST",
    ):
        assert '"${' + variable + ':?' + variable + ' is required in production}' in start
    assert '[[ ! -f "${NOTEMELD_AGENT_SDK_LIBRARY}" ]]' in start
    assert 'CLOUD_HOST must be externally reachable in production' in start


def test_desktop_packaging_requires_the_independent_official_plugin_release():
    spec = (ROOT / "scripts" / "desktop" / "packaging" / "backend" / "pyinstaller" / "backend.spec").read_text(encoding="utf-8")
    assert 'external_plugin_dir("official-link-note")' in spec
    assert "official.link-note plugin release is required for desktop packaging" in spec
    assert "NOTEMELD_PLUGINS_DIR" in spec


def test_android_release_signing_is_secret_driven_and_debug_build_stays_available():
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    for variable in (
        "NOTEMELD_ANDROID_KEYSTORE_PATH",
        "NOTEMELD_ANDROID_KEYSTORE_PASSWORD",
        "NOTEMELD_ANDROID_KEY_ALIAS",
        "NOTEMELD_ANDROID_KEY_PASSWORD",
        "NOTEMELD_ANDROID_VERSION_CODE",
        "NOTEMELD_ANDROID_VERSION_NAME",
    ):
        assert variable in gradle
    assert 'create("release")' in gradle
    assert 'buildTypes.getByName("release").signingConfig' in gradle


def test_mobile_adapter_workflow_pins_and_injects_the_android_sdk_aar():
    workflow = (ROOT / ".github" / "workflows" / "mobile-adapters.yml").read_text(encoding="utf-8")
    for contract in (
        "Download pinned Agent SDK AAR",
        "NOTEMELD_AGENT_SDK_AAR_URL",
        "NOTEMELD_AGENT_SDK_AAR_SHA256",
        "sha256sum -c -",
        "NOTEMELD_AGENT_SDK_AAR: ${{ runner.temp }}/notemeld-agent-sdk.aar",
        "gradle --no-daemon :app:assembleDebug",
    ):
        assert contract in workflow
