# Third-party software notices

MediaSift bundles third-party software in its Windows executable. Their
copyright and license terms remain with their respective authors. This file
identifies the principal bundled components and links to their full license
texts and attribution lists.

## PySide6, Shiboken6, and Qt

MediaSift uses the PySide6 Community Edition and Qt libraries, including Qt
Multimedia. The Community Edition is available under the GNU Lesser General
Public License version 3 (LGPLv3) and GNU General Public License version 3
(GPLv3), subject to each component's license and applicable conditions.
PySide6/Qt also incorporates separately licensed third-party code. See the
[Qt for Python license overview and third-party notices](https://doc.qt.io/qtforpython-6/licenses.html),
[Qt licensing information](https://doc.qt.io/qt-6/licensing.html), and
[Qt third-party code attribution list](https://doc.qt.io/qt-6/licenses-used-in-qt.html).

## FFmpeg

Qt Multimedia's Windows FFmpeg backend and FFmpeg libraries are included to
support video playback. Qt's supplied FFmpeg build is distributed under the
GNU Lesser General Public License version 2.1 or later and additional
permissive licenses, including BSD, ISC, MIT, and Mozilla Public License 2.0;
the precise attribution list is published in Qt's
[third-party code list](https://doc.qt.io/qt-6/licenses-used-in-qt.html).
FFmpeg licensing depends on build configuration. Qt documents its packaged
backend and deployment in the [Qt Multimedia documentation](https://doc.qt.io/qt-6/qtmultimedia-index.html).

## Pillow

MediaSift uses Pillow 12.3.0 for image decoding. Pillow is distributed under
the HPND License. See the [Pillow 12.3.0 license](https://github.com/python-pillow/Pillow/blob/12.3.0/LICENSE).

## PyInstaller

The Windows executable is assembled with PyInstaller 6.22.3. PyInstaller is
distributed under the GNU General Public License version 2 or later with a
special exception permitting distribution of executables that include
PyInstaller and its bootloader. See the
[PyInstaller license](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt).

## Source and replacement materials

MediaSift is distributed under the MIT License; see [LICENSE](LICENSE). Qt
and FFmpeg components are dynamically linked libraries in the executable
bundle. Users should consult the linked license terms for rights to modify or
replace those components and for any corresponding-source obligations. Qt's
official [LGPL compliance guidance](https://www.qt.io/licensing/open-source-lgpl-obligations)
describes the obligations that apply to LGPL Qt distributions. No patent
license for media codecs is granted by these notices; codec patent terms may
apply independently.
