# MediaSift icon source manifest

- `mediasift.svg` is the editable vector source for the application icon.
- `mediasift.png` is the 512 × 512 raster version used by the Qt window and bundled application.
- `mediasift.ico` contains 16, 32, 48, 64, 128, and 256 pixel Windows icon sizes.
- `render_icon.py` reproducibly renders all three raster assets from the SVG using Qt and Pillow: `python docs/assets/render_icon.py`.

The artwork uses a simple teal funnel on a dark navy rounded square, designed to remain clear at small Windows taskbar and Explorer sizes. The build runs the renderer before packaging.
