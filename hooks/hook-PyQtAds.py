"""PyInstaller hook for PyQtAds (Qt Advanced Docking System).

PyQtAds is a single .pyd extension module that internally defines the
``PyQtAds.ads`` submodule.  PyInstaller cannot automatically detect the
internal submodule, so we declare both as hidden imports.
"""

from PyInstaller.utils.hooks import collect_submodules

# PyQtAds is a single .pyd; its internal ``ads`` submodule is not a
# separate file on disk, so we must list it explicitly.
hiddenimports = [
    "PyQtAds",
    "PyQtAds.ads",
]