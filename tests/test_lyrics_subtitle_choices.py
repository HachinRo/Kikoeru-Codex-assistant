import sqlite3
import unittest

from load_script import load_script


kikoeru = load_script(
    "asmr_view_kikoeru_lyrics_test",
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "Web-UI/lib/asmr_view_kikoeru.py",
)


class LyricsSubtitleChoiceTests(unittest.TestCase):
    def test_lists_best_match_then_other_subtitles(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE files(id TEXT, name TEXT, parent_id TEXT, work_id TEXT, is_folder INTEGER, path TEXT)"
        )
        conn.executemany(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("audio", "02 scene.mp3", "disc", "RJ1", 0, "/RJ1/main/02 scene.mp3"),
                ("exact", "02 scene.vtt", "disc", "RJ1", 0, "/RJ1/main/02 scene.vtt"),
                ("nearby", "wrong-name.srt", "disc", "RJ1", 0, "/RJ1/main/wrong-name.srt"),
                ("elsewhere", "01 intro.lrc", "other", "RJ1", 0, "/RJ1/bonus/01 intro.lrc"),
                ("text", "notes.txt", "disc", "RJ1", 0, "/RJ1/main/notes.txt"),
            ],
        )

        choices = kikoeru.list_subtitles_for_audio(conn, "RJ1", "audio")

        self.assertEqual([item["hash"] for item in choices], ["exact", "nearby", "elsewhere"])
        self.assertEqual(choices[0]["title"], "main/02 scene.vtt")


if __name__ == "__main__":
    unittest.main()
