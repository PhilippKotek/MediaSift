# MediaSift icon source manifest

- `mediasift.svg` is the editable vector source for the application icon.
- `mediasift.png` is the 512 × 512 raster version used by the Qt window.
- `mediasift.ico` contains 16, 32, 48, 64, 128, and 256 pixel Windows icon sizes.

The artwork combines a photo thumbnail with a magnifier and plus mark to suggest finding and curating media. The SVG is rendered to PNG with Qt's `QSvgRenderer`; Pillow converts the PNG into the multi-size ICO.
