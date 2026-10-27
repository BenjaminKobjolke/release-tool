"""Tests for the release tag conflict policy."""

from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from release_tool.exceptions import ReleaseCreateError
from release_tool.tag_guard import TagConflict, conflict_mode, ensure_free_label


@pytest.mark.parametrize(
    ("dry_run", "self_contained", "auto", "yes", "expected"),
    [
        (True, False, False, False, TagConflict.STOP),
        (False, True, False, False, TagConflict.STOP),
        (False, False, True, True, TagConflict.AUTO),
        (False, False, False, True, TagConflict.STOP),
        (False, False, False, False, TagConflict.ASK),
    ],
)
def test_conflict_mode_uses_approved_precedence(
    dry_run: bool,
    self_contained: bool,
    auto: bool,
    yes: bool,
    expected: TagConflict,
) -> None:
    assert conflict_mode(
        dry_run=dry_run,
        build_self_contained=self_contained,
        bump_if_tagged=auto,
        yes=yes,
    ) is expected


@patch("release_tool.tag_guard.find_existing_tag", return_value=None)
def test_ensure_free_label_returns_label_when_tag_is_free(
    find_tag: Mock, tmp_path: Path
) -> None:
    catch_up = Mock()

    assert ensure_free_label(
        "1.2.3", tmp_path, TagConflict.ASK, catch_up, confirm_fn=Mock()
    ) == "1.2.3"

    find_tag.assert_called_once_with("1.2.3", tmp_path)
    catch_up.assert_not_called()


@patch("release_tool.tag_guard.find_existing_tag", return_value="locally")
def test_ensure_free_label_stops_without_prompt_in_stop_mode(
    find_tag: Mock, tmp_path: Path
) -> None:
    with pytest.raises(ReleaseCreateError, match="1.2.3.*already exists locally"):
        ensure_free_label("1.2.3", tmp_path, TagConflict.STOP, Mock(), confirm_fn=Mock())


@patch("release_tool.tag_guard.find_existing_tag", return_value="on origin")
def test_ensure_free_label_stops_when_user_declines_catch_up(
    find_tag: Mock, tmp_path: Path
) -> None:
    confirm = Mock(return_value=False)
    catch_up = Mock()

    with pytest.raises(ReleaseCreateError, match="1.2.3.*already exists on origin"):
        ensure_free_label("1.2.3", tmp_path, TagConflict.ASK, catch_up, confirm_fn=confirm)

    confirm.assert_called_once()
    catch_up.assert_not_called()


@patch("release_tool.tag_guard.find_existing_tag", side_effect=["locally", None])
def test_ensure_free_label_prompts_then_returns_caught_up_label(
    find_tag: Mock, tmp_path: Path
) -> None:
    confirm = Mock(return_value=True)
    catch_up = Mock(return_value="1.2.4")

    assert ensure_free_label(
        "1.2.3", tmp_path, TagConflict.ASK, catch_up, confirm_fn=confirm
    ) == "1.2.4"

    confirm.assert_called_once()
    catch_up.assert_called_once_with()
    assert find_tag.call_args_list == [call("1.2.3", tmp_path), call("1.2.4", tmp_path)]


@patch("release_tool.tag_guard.find_existing_tag", side_effect=["locally", "on origin", None])
def test_ensure_free_label_repeats_prompt_when_caught_up_label_is_taken(
    find_tag: Mock, tmp_path: Path
) -> None:
    confirm = Mock(side_effect=[True, True])
    catch_up = Mock(side_effect=["1.2.4", "1.2.5"])

    assert ensure_free_label(
        "1.2.3", tmp_path, TagConflict.ASK, catch_up, confirm_fn=confirm
    ) == "1.2.5"

    assert confirm.call_count == 2
    assert catch_up.call_count == 2
    assert find_tag.call_args_list == [
        call("1.2.3", tmp_path),
        call("1.2.4", tmp_path),
        call("1.2.5", tmp_path),
    ]


@patch("release_tool.tag_guard.find_existing_tag", side_effect=["locally", None])
def test_ensure_free_label_automatically_catches_up(
    find_tag: Mock, tmp_path: Path
) -> None:
    confirm = Mock()
    catch_up = Mock(return_value="1.2.4")

    assert ensure_free_label(
        "1.2.3", tmp_path, TagConflict.AUTO, catch_up, confirm_fn=confirm
    ) == "1.2.4"

    confirm.assert_not_called()
    catch_up.assert_called_once_with()


@patch("release_tool.tag_guard.find_existing_tag", return_value="locally")
def test_ensure_free_label_stops_when_catch_up_does_not_change_label(
    find_tag: Mock, tmp_path: Path
) -> None:
    with pytest.raises(ReleaseCreateError, match="did not change the shipping label"):
        ensure_free_label(
            "1.2.3", tmp_path, TagConflict.AUTO, Mock(return_value="1.2.3"), confirm_fn=Mock()
        )
