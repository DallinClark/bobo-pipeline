from __future__ import annotations

import ffmpeg  # type: ignore[import-untyped]
import logging
import os
import shutil
import subprocess

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self
    from pipe.struct.db import Shot


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FFMpegPreset:
    ext: str
    out_kwargs: dict[str, Any]

    def __hash__(self):
        return hash(frozenset(self.out_kwargs.items()))

class Playblaster(metaclass=ABCMeta):
    """Parent class for creating playblasters. Uses FFmpeg to encode videos"""

    _shot: Shot
    _in_context: bool

    FR = 24

    class PRESET(FFMpegPreset, Enum):
        EDIT_SQ = (
            "mov",
            {
                "vcodec": "dnxhd",
                "pix_fmt": "yuv422p",
                "vprofile": "dnxhr_sq",
                # this number comes from Avid's table in the DNxHD whitepaper
                "video_bitrate": "124M",
            },
        )
        EDIT_HQX = (
            "mov",
            {
                "vcodec": "dnxhd",
                "pix_fmt": "yuv422p10le",
                "vprofile": "dnxhr_hqx",
                "video_bitrate": "188M",
            },
        )
        WEB = (
            "mp4",
            {
                "vcodec": "libx264",
                "preset": "veryslow",
                "tune": "animation",
                "crf": 20,
            },
        )

    def __init__(self) -> None:
        pass

    @abstractmethod
    def _write_images(self, path: str) -> None:
        pass

    def __enter__(self) -> Self:
        self._in_context = True
        return self

    def __call__(self, shot: Shot, *args):
        self._shot = shot
        return self

    def __exit__(self, *args) -> None:
        self._in_context = False

    def _run_postprocess(self, video_path: Path) -> None:
        temp_output = video_path.with_suffix(".post.mp4")

        cmd = [
            "ffmpeg",
            "-y",  # overwrite without asking
            "-i", str(video_path),
            "-vf", "format=yuv420p",
            "-c:v", "dnxhr",
            "-profile:v", "dnxhr_hq",
            "-crf", "18",
            "-preset", "slow",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(temp_output)
        ]

        log.info(f"Running FFmpeg post-process: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        # Replace original with post-processed file
        video_path.unlink()
        temp_output.rename(video_path)
        
    def _do_playblast(
        self,
        out_paths: dict[PRESET, list[Path | str]] | None = None,
        tails: tuple[int, int] = (0, 0),
    ) -> None:
        if not self._in_context:
            raise RuntimeError("_do_playblast not called from within context self")

        if not out_paths:
            out_paths = {}

        tempdir = Path(os.getenv("TMPDIR", os.getenv("TEMP", "tmp"))).resolve()

        FILENAME = "bobo_pb_temp." + self._shot.code

        # remove any old playblasts
        for p in tempdir.glob(FILENAME + "*"):
            p.unlink()

        # do the playblast
        self._write_images(str(tempdir / FILENAME))

        # use ffmpeg to encode the video
        start_frame = int(self._shot.cut_in) - tails[0]
        images = ffmpeg.input(
            str(tempdir / FILENAME) + ".%04d.png",
            start_number=start_frame,
            r=self.FR,
            # precisely define input colorspace
            colorspace="bt709",
            color_trc="iec61966-2-1",
        ).filter("format", "yuv422p")
        for preset, paths in out_paths.items():
            try:
                out_filename = str(tempdir / FILENAME) + "." + preset.ext
                ffmpeg.output(
                    images,
                    out_filename,
                    **preset.out_kwargs,
                    timecode="00:00:{:02}:{:02}".format(
                        start_frame // self.FR,
                        start_frame % self.FR,
                    ),
                    r=self.FR,
            ).overwrite_output().run()
            except ffmpeg.Error as e:
                print("stdout:", e.stdout.decode())
                print("stderr:", e.stderr.decode()) 

            # copy video out of tempdir
            final_paths: list[Path] = []

            # copy video out of tempdir
            for path in (Path(str(p) + "." + preset.ext) for p in paths):
                if not path.parent.exists():
                    path.parent.mkdir(mode=0o770, parents=True)
                shutil.copyfile(out_filename, path)
                final_paths.append(path)  # <-- collect final output path

            #run postprocess so video works in vlc
            for final_path in final_paths:
                try:
                    self._run_postprocess(final_path)
                except Exception as e:
                    log.error(f"Post-process failed for {final_path}: {e}")

            


        # clean up if not in debug mode
        if not log.isEnabledFor(logging.DEBUG):
            for p in tempdir.glob(FILENAME + "*"):
                p.unlink()

        #

    @abstractmethod
    def playblast(self) -> None:
        """Function to be called by the user to trigger a playblast.
        This should call `_do_playblast` from within a `with self(...)`
        block.
        Looks something like:
            >>> def playblast(self) -> None:
            >>>     with self(shot):
            >>>         super()._do_playblast([filepath])
        """
        pass
