# Video Frame Extractor

한국어: [사용법](사용법.md)

A small, local desktop application for exporting the **first** and **last** frame of a video as lossless PNG files. It uses FFmpeg locally—your video is never uploaded anywhere.

## Features

- Extracts first and final video frames in original resolution
- Saves lossless PNG images with frame-number-aware filenames
- Shows a thumbnail, duration, resolution, FPS, and total frame count
- Supports drag and drop when `tkinterdnd2` is installed
- Handles common formats supported by FFmpeg, including MP4, MOV, MKV, AVI, WebM, M2TS, and more
- Offers manual color range and color-space overrides for videos with incomplete metadata

## Requirements

- Python 3.9 or later
- Tkinter (included with most Python installers)

## Install

```bash
git clone https://github.com/BONORA0413/frame_extractor.git
cd frame_extractor
python -m pip install -r requirements.txt
```

`imageio-ffmpeg` downloads or provides an FFmpeg executable automatically in the usual case. If FFmpeg cannot be found, install it separately and make it available on your system `PATH`.

On Ubuntu or other Debian-based Linux distributions, you may also need:

```bash
sudo apt install python3-tk
```

## Run

```bash
python frame_extractor.py
```

On Windows, use `py frame_extractor.py` if `python` is not available in your terminal.

1. Drop a video onto the highlighted area, or click it to choose a file.
2. Optionally choose a destination folder. By default, files are saved next to the source video.
3. Select **Extract Frames** to export both images.

For a 480-frame source named `video.mp4`, the exported files are named:

```text
video_first_frame1_of_480.png
video_last_frame480_of_480.png
```

## Color accuracy

Video pixels are commonly stored as YUV and need color-range and color-space metadata to convert accurately to RGB PNG. The app reads available FFmpeg metadata and defaults to Limited/BT.709 if metadata is missing. If the preview does not match the original video, use the on-screen **Color Range** and **Color Space** controls to select the appropriate values before extraction.

## Privacy

All analysis and image extraction happen on the local computer. This application does not upload or transmit video files.

## License

No license has been selected yet. Until a license is added, the repository content is subject to the default copyright protections of its author.

