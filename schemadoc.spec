# PyInstaller build recipe:  pyinstaller schemadoc.spec --noconfirm
# Produces dist/SchemaDocumenter(.exe), or dist/SchemaDocumenter.app on macOS.
import sys
from PyInstaller.utils.hooks import collect_submodules

hidden = (
    collect_submodules("sqlalchemy.dialects")
    + collect_submodules("psycopg")
    + collect_submodules("psycopg_binary")
    + ["sqlalchemy.sql.default_comparator", "pymysql", "pymssql", "pymssql._pymssql"]
)

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    hiddenimports=hidden,
    excludes=["pytest", "pypdf", "numpy", "PIL.ImageQt", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="SchemaDocumenter",
    console=False,          # windowed app; the CLI works when run from source
    upx=False,
    icon=None,
)

if sys.platform == "darwin":
    app = BUNDLE(exe, name="SchemaDocumenter.app", bundle_identifier="dev.schemadoc.app",
                 info_plist={"NSHighResolutionCapable": True})
