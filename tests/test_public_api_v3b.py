from w_mwxt_wavetable_tool import (
    MinimalProject,
    MinimalProjectManifest,
    ProjectAudioRecord,
    ProjectSaveResult,
    ProjectSourceCheck,
    SourceStatus,
    SourceValidationPolicy,
    open_project,
    save_project,
)


def test_code_v3b_public_api_is_importable() -> None:
    assert all(
        item is not None
        for item in (
            MinimalProject,
            MinimalProjectManifest,
            ProjectAudioRecord,
            ProjectSaveResult,
            ProjectSourceCheck,
            SourceStatus,
            SourceValidationPolicy,
            open_project,
            save_project,
        )
    )
