from types import SimpleNamespace

import pytest

from app.downloaders.youtube_subtitle import YouTubeSubtitleFetcher


class FakeTranscriptList:
    def __init__(self, transcript):
        self.transcript = transcript

    def __iter__(self):
        return iter([self.transcript])

    def find_manually_created_transcript(self, _langs):
        return self.transcript


def test_fetch_subtitles_supports_object_and_dict_snippets():
    transcript = SimpleNamespace(
        language_code="en",
        language="English",
        is_generated=False,
        fetch=lambda: [
            SimpleNamespace(text="first caption", start=1.2, duration=2.3),
            {"text": "second caption", "start": 4.0, "duration": 1.5},
        ],
    )
    fetcher = YouTubeSubtitleFetcher.__new__(YouTubeSubtitleFetcher)
    fetcher._api = SimpleNamespace(list=lambda _video_id: FakeTranscriptList(transcript))

    result = fetcher.fetch_subtitles("video-id")

    assert result is not None
    assert result.full_text == "first caption second caption"
    assert result.segments[0].text == "first caption"
    assert result.segments[0].start == pytest.approx(1.2)
    assert result.segments[0].end == pytest.approx(3.5)
    assert result.segments[1].text == "second caption"
    assert result.segments[1].start == pytest.approx(4.0)
    assert result.segments[1].end == pytest.approx(5.5)
