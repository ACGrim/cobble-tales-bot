Montserrat-Black.ttf is used for the big word-by-word captions in every
Reddit-story video (see _render_caption_png in src/assemble_video.py).

Montserrat is released under the SIL Open Font License 1.1 (full text in
OFL.txt, next to it), which explicitly allows bundling and redistributing the
font with software like this and using it in commercial / monetized videos.
Source: https://github.com/JulietaUla/Montserrat

If this file is ever missing, captions fall back to DejaVu Sans Bold (which
the GitHub Actions workflow installs), so videos still build.
