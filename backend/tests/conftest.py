import os
import tempfile

# Antes de importar la app: base de datos temporal
os.environ.setdefault("COMPELECTRIX_DATA", tempfile.mkdtemp())
